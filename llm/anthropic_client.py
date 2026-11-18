"""Adaptador da API da Anthropic (usado pelo juiz Claude Haiku 5.5).

Observação sobre determinismo: modelos de "adaptive thinking" (Claude Sonnet 5,
Haiku 5.5, Opus 4.7+) REJEITAM (erro 400) qualquer valor de
`temperature`/`top_p`/`top_k` diferente do padrão — a amostragem é controlada
internamente pelo próprio modelo, e a orientação oficial da Anthropic é remover
o parâmetro e usar instruções no prompt para guiar o comportamento. O Haiku 4.5
(modelo "clássico", sem adaptive thinking) ainda aceita `temperature`
normalmente. Por isso este adaptador só envia `temperature` para modelos que a
suportam — ver `_aceita_temperatura()`.

Essa decisão é tomada DUAS vezes, por uma razão medida na prática: a lista de
prefixos é uma aposta sobre nomes de modelo, e modelos novos aparecem sem
avisar. Quando a aposta erra, o erro não aparece como erro — a avaliação
devolve `falhas_juiz` em todos os pares e a métrica sai `sem_dados`, que é
fácil confundir com "a bateria daquela categoria não rodou". Foi o que
aconteceu ao apontar o juiz para `claude-haiku-5-5`: dez pares, dez falhas,
nenhuma mensagem. Por isso a recusa da própria API também conta, em
`_erro_de_temperatura()`: ela é a fonte de verdade, a lista é só o atalho que
evita gastar uma chamada para descobrir o óbvio.
"""
from __future__ import annotations

import time

import config
from .interface import ClienteLLM, RespostaLLM

# Prefixos de modelo que REJEITAM temperature/top_p/top_k (adaptive thinking
# sempre ligado). Fora dessa lista, assume-se que o modelo aceita o parâmetro
# normalmente (ex.: Haiku 4.5, Sonnet 4.5 e anteriores).
_SEM_TEMPERATURA = (
    "claude-sonnet-5", "claude-haiku-5", "claude-opus-5",
    "claude-opus-4-8", "claude-opus-4-7", "claude-fable", "claude-mythos",
)

# Modelos que a API recusou em tempo de execução, descobertos pelo erro 400.
# Alimentado por `gerar()` para que a chamada seguinte ao mesmo modelo já saia
# sem o parâmetro, em vez de gastar uma ida à API para errar de novo.
_RECUSARAM_TEMPERATURA: set[str] = set()

# Como desligar o raciocínio adaptativo, por modelo. No juiz o raciocínio custa
# tokens de saída e, pior, consome o teto de `max_tokens` antes do JSON, que
# sai truncado. Cada modelo aceita uma forma: o Haiku 5.5 aceita "disabled";
# o Sonnet 5.5 recusa "disabled" (400) e desliga com "between_tools", conferido
# com chamada real em 25/10/2026.
_DESLIGAR_RACIOCINIO: dict[str, dict] = {
    "claude-haiku-5": {"type": "disabled"},
    "claude-sonnet-5-5": {"type": "between_tools"},
}


def _aceita_temperatura(modelo: str) -> bool:
    return (
        not modelo.startswith(_SEM_TEMPERATURA)
        and modelo not in _RECUSARAM_TEMPERATURA
    )


def _erro_de_temperatura(erro: Exception) -> bool:
    """O erro é a API recusando `temperature` para este modelo?

    Checa o status 400 junto com a menção ao parâmetro: um 401 ou um 429 que
    por acaso citasse a palavra não deve ser tratado como incompatibilidade de
    parâmetro — isso esconderia uma chave inválida atrás de um retry.
    """
    if getattr(erro, "status_code", None) != 400:
        return False
    return "temperature" in str(erro).lower()


class ClienteAnthropic(ClienteLLM):
    provedor = "anthropic"

    def __init__(self, modelo: str, api_key: str | None = None) -> None:
        """Cria o cliente da Anthropic (usado pelos juízes)."""
        import anthropic  # import tardio: só exige o SDK se for usado

        self.modelo = modelo
        # Chave identity-linked precisa declarar o workspace em toda chamada;
        # sem o header a API recusa com 400. Só é enviado quando configurado,
        # porque chaves antigas rejeitam o header desconhecido.
        cabecalhos = (
            {"anthropic-workspace-id": config.ANTHROPIC_WORKSPACE_ID}
            if config.ANTHROPIC_WORKSPACE_ID else None
        )
        self._client = anthropic.Anthropic(
            api_key=api_key or config.ANTHROPIC_API_KEY,
            default_headers=cabecalhos,
            # O padrão do SDK são 2 repetições. Numa avaliação de milhares de
            # chamadas, um pico de sobrecarga (429/529) mais longo que isso
            # virava falha de juiz no meio da medição.
            max_retries=6,
        )

    def gerar(
        self,
        sistema: str,
        mensagens: list[dict],
        temperatura: float | None = None,
        max_tokens: int = 1024,
        formato_json: bool = False,
    ) -> RespostaLLM:
        """Chama `messages.create` e devolve uma RespostaLLM padronizada."""
        # A API de Messages da Anthropic não tem um modo JSON nativo como a da
        # OpenAI; `formato_json` fica só na assinatura, por conformidade com a
        # interface — o pedido de formato precisa vir do próprio prompt.
        del formato_json
        params: dict = {
            "model": self.modelo,
            "max_tokens": max_tokens,
            "system": sistema,
            "messages": mensagens,
        }
        if getattr(self, "raciocinio_padrao", False):
            # Experimento #39: raciocínio adaptativo no esforço padrão do
            # modelo (medium no Haiku 5.5), declarado em vez de omitido.
            params["thinking"] = {"type": "adaptive"}
            params["output_config"] = {"effort": "medium"}
        else:
            for prefixo, thinking in _DESLIGAR_RACIOCINIO.items():
                if self.modelo.startswith(prefixo):
                    params["thinking"] = thinking
                    break
        temperatura_aplicada = temperatura is not None and _aceita_temperatura(self.modelo)
        if temperatura_aplicada:
            params["temperature"] = temperatura

        t0 = time.perf_counter()
        try:
            resp = self._client.messages.create(**params)
        except Exception as erro:  # noqa: BLE001
            if not (temperatura_aplicada and _erro_de_temperatura(erro)):
                raise
            # Modelo novo, fora da lista de prefixos: remove o parâmetro e
            # repete uma vez. Melhor uma chamada extra do que uma categoria
            # inteira medida como `sem_dados` (ver o docstring do módulo).
            _RECUSARAM_TEMPERATURA.add(self.modelo)
            params.pop("temperature")
            temperatura_aplicada = False
            resp = self._client.messages.create(**params)
        latencia = time.perf_counter() - t0

        texto = "".join(b.text for b in resp.content if b.type == "text")
        return RespostaLLM(
            texto=texto,
            modelo=self.modelo,
            provedor=self.provedor,
            # Registra o que foi REALMENTE enviado à API, não o que foi
            # pedido — para modelos que rejeitam temperature, fica None aqui
            # mesmo que `temperatura` tenha sido passado para `gerar()`.
            parametros={
                "temperatura": temperatura if temperatura_aplicada else None,
                "max_tokens": max_tokens,
                "raciocinio": (params.get("thinking", {}).get("type")
                               + (f"/{params['output_config']['effort']}"
                                  if "output_config" in params else "")
                               if params.get("thinking") else None),
            },
            latencia_s=latencia,
            bruto=resp.model_dump(),
        )
