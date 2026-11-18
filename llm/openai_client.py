"""Adaptador da API da OpenAI.

Serve ao juiz GPT-6 Luna (até 28/10/2026, ao GPT-5.6 Terra) e, por herança
(`ClienteDeepSeek`), ao bot e ao simulador, que usam a API compatível do
DeepSeek.
"""
from __future__ import annotations

import time

import config
from .interface import ClienteLLM, RespostaLLM


class ClienteOpenAI(ClienteLLM):
    provedor = "openai"

    # Política de retry para resposta em branco: quanto do histórico da
    # conversa enviar em CADA tentativa. `None` = histórico inteiro; um
    # inteiro N = apenas as N últimas mensagens do histórico (0 = nenhuma).
    # O tamanho da tupla é o número máximo de tentativas.
    #
    # Um único item significa "sem retry", o comportamento correto para um
    # provedor sem falha conhecida desse tipo. Subclasses sobrescrevem quando
    # o provedor documenta a falha — ver ClienteDeepSeek.
    HISTORICO_POR_TENTATIVA: tuple[int | None, ...] = (None,)

    def __init__(
        self,
        modelo: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Cria o cliente OpenAI (ou compatível, se `base_url` for informado)."""
        from openai import OpenAI  # import tardio: só exige o SDK se for usado

        self.modelo = modelo
        kwargs: dict = {"api_key": api_key or config.OPENAI_API_KEY}
        if base_url:
            kwargs["base_url"] = base_url  # permite APIs compatíveis (ex.: DeepSeek)
        else:
            # Mesmo motivo do adaptador da Anthropic: numa avaliação de
            # milhares de chamadas, as 2 repetições padrão do SDK não cobrem
            # um pico de 429/5xx mais longo.
            kwargs["max_retries"] = 6
        self._client = OpenAI(**kwargs)

    def _parametros_extra(self) -> dict:
        """Parâmetros extras específicos de um provedor OpenAI-compatível.

        Sobrescrito por subclasses (ex.: ClienteDeepSeek) para injetar
        opções que só fazem sentido para aquele provedor, sem afetar o
        adaptador OpenAI puro.
        """
        return {}

    def _familia_raciocinio(self) -> bool:
        """Modelo da OpenAI com raciocínio embutido (GPT-5, GPT-6, o3, o4)?

        Só vale para a OpenAI de fato: o DeepSeek herda deste adaptador e tem
        as próprias regras. O GPT-6 entrou em 28/10/2026: sem ele, o
        gpt-6-luna raciocinaria no esforço padrão (medium) e o juiz deixaria
        de rodar nas mesmas condições do Haiku, que roda sem raciocínio.
        """
        return self.provedor == "openai" and self.modelo.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))

    @staticmethod
    def _limitar_historico(mensagens: list[dict], limite: int | None) -> list[dict]:
        """Mantém apenas as `limite` últimas mensagens do histórico.

        O "histórico" é tudo o que vem ANTES da última mensagem de `system`
        — no bot, essa última `system` é o bloco de contexto do turno (dados
        da fonte de verdade), seguido da pergunta atual do cliente. Essa
        cauda é sempre preservada: é o enquadramento do turno, não bate-papo.

        Reduzir o histórico é seguro NESTA arquitetura porque o estado da
        conversa vive no código, não na memória do modelo: o bloco de
        contexto reinjeta a cada turno o cliente, a dívida, a condição em
        jogo e o acordo. A resposta perde o fio do bate-papo, não os dados.

        `limite=None` devolve tudo, sem cópia desnecessária.
        """
        if limite is None or not mensagens:
            return mensagens
        indices_system = [i for i, m in enumerate(mensagens) if m.get("role") == "system"]
        corte = indices_system[-1] if indices_system else len(mensagens) - 1
        historico, cauda = mensagens[:corte], mensagens[corte:]
        if limite <= 0:
            return cauda
        return historico[len(historico) - limite:] + cauda

    def gerar(
        self,
        sistema: str,
        mensagens: list[dict],
        temperatura: float | None = None,
        max_tokens: int = 1024,
        formato_json: bool = False,
    ) -> RespostaLLM:
        """Chama `chat.completions.create` e devolve uma RespostaLLM padronizada.

        Repete a chamada se a resposta vier em branco, até
        `TENTATIVAS_RESPOSTA_VAZIA` vezes (ver a constante). A latência
        reportada é a soma de todas as tentativas — é o tempo que o usuário
        de fato esperou —, e `tentativas` registra quantas foram necessárias.
        Esgotadas as tentativas, devolve a última resposta em branco mesmo:
        quem chama decide o que fazer, sem exceção surpresa.
        """
        msgs = [{"role": "system", "content": sistema}, *mensagens]
        params: dict = {
            "model": self.modelo,
            "messages": msgs,
            "max_tokens": max_tokens,
        }
        if temperatura is not None:
            params["temperature"] = temperatura
        if formato_json:
            # A API valida que a resposta é um JSON sintaticamente válido —
            # mais confiável do que pedir, só via texto, que a LLM inclua um
            # marcador solto no meio da prosa (ela pode simplesmente esquecer).
            params["response_format"] = {"type": "json_object"}
        params.update(self._parametros_extra())
        if self._familia_raciocinio():
            # GPT-5, GPT-6 e série o: `max_tokens` e temperatura diferente de 1 voltam
            # 400, e o raciocínio consome o mesmo teto de tokens antes da
            # resposta — no juiz, o JSON sairia cortado ou vazio. Medido no
            # gpt-5.6-terra em 25/10/2026: com o raciocínio desligado a resposta
            # vem direta, sem tokens de raciocínio.
            params["max_completion_tokens"] = params.pop("max_tokens")
            params.pop("temperature", None)
            # Experimento #39: esforço padrão declarado (medium).
            params["reasoning_effort"] = ("medium" if getattr(self, "raciocinio_padrao", False)
                                          else "none")

        # Retry com DEGRADAÇÃO GRADUAL do contexto, invisível para quem chama.
        # Cada tentativa manda menos histórico que a anterior (ver
        # HISTORICO_POR_TENTATIVA). O desenho vem de medição, não de palpite:
        #
        #   repetir a requisição idêntica  ->  resgatou 5 de 126 falhas (4%)
        #   manter só as 2 últimas msgs    ->  resgatou 5 de 6 (83%)
        #   descartar o histórico inteiro  ->  resgatou 6 de 6 (100%)
        #
        # Repetir idêntico é quase inútil porque a falha raramente é
        # intermitente: em geral é o próprio histórico que envenena o
        # contexto, e a mesma requisição reproduz o mesmo resultado
        # degenerado. Por isso a 2ª tentativa já reduz o histórico — resgata
        # muito mais E preserva o último par da conversa, em vez de jogar
        # todo o contexto fora de uma vez.
        #
        # A temperatura NÃO varia entre tentativas: foi testado e não ajuda
        # (8/8 falhas tanto a 0.3 quanto a 0.9), e mudar em silêncio um
        # parâmetro de amostragem corromperia a medição de consistência entre
        # reexecuções, que é uma das métricas do projeto.
        politica = self.HISTORICO_POR_TENTATIVA or (None,)
        limite_aplicado: int | None = None

        t0 = time.perf_counter()
        for tentativa, limite in enumerate(politica, start=1):
            if tentativa > 1:
                params["messages"] = [
                    {"role": "system", "content": sistema},
                    *self._limitar_historico(mensagens, limite),
                ]
            try:
                resp = self._client.chat.completions.create(**params)
            except Exception as erro:  # noqa: BLE001
                # Nem todo modelo da família aceita "none" (o gpt-5 original só
                # vai até "minimal"). A recusa da API decide, uma vez, e a
                # chamada repete com o menor esforço que todos aceitam.
                if not (params.get("reasoning_effort") == "none"
                        and "reasoning_effort" in str(erro)):
                    raise
                params["reasoning_effort"] = "low"
                resp = self._client.chat.completions.create(**params)
            texto = resp.choices[0].message.content or ""
            if texto.strip():
                limite_aplicado = limite
                break
            limite_aplicado = limite
        latencia = time.perf_counter() - t0

        return RespostaLLM(
            texto=texto,
            modelo=self.modelo,
            provedor=self.provedor,
            # O que foi REALMENTE enviado: na família de raciocínio a
            # temperatura pedida não sai, e o registro não pode fingir que saiu.
            parametros={
                "temperatura": params.get("temperature"),
                "max_tokens": max_tokens,
                "raciocinio": params.get("reasoning_effort"),
            },
            latencia_s=latencia,
            bruto=resp.model_dump(),
            tentativas=tentativa,
            # Quanto histórico a chamada que produziu ESTA resposta recebeu
            # (None = tudo). Fica no log porque muda a leitura da avaliação:
            # uma resposta gerada com contexto reduzido pode parecer fora de
            # contexto, e isso tem causa conhecida.
            historico_enviado=limite_aplicado,
        )
