"""Adaptador da API do DeepSeek.

O DeepSeek expõe uma API compatível com a da OpenAI, então reaproveitamos o
mesmo cliente, apenas apontando para a URL base do DeepSeek e usando a chave
DEEPSEEK_API_KEY. Modelo típico: "deepseek-v4-flash" ("deepseek-chat" foi
descontinuado em 2026-07-24).
"""
from __future__ import annotations

import config
from .openai_client import ClienteOpenAI


class ClienteDeepSeek(ClienteOpenAI):
    provedor = "deepseek"

    # O modo JSON do DeepSeek às vezes devolve conteúdo em branco. É falha
    # conhecida e assumida pelo próprio provedor, na documentação oficial do
    # recurso: "When using the JSON Output feature, the API may occasionally
    # return empty content. We are actively working on optimizing this issue.
    # You can try modifying the prompt to mitigate such problems."
    # (https://api-docs.deepseek.com/guides/json_mode)
    #
    # As mitigações oficiais por prompt JÁ estão todas aplicadas aqui —
    # response_format json_object, a palavra "json" no prompt, exemplos do
    # formato alvo, max_tokens folgado e thinking desligado — e ainda assim a
    # falha ocorreu em 42% dos turnos de uma sessão manual real. O sintoma
    # observado é uma variante do que a doc descreve: em vez de fluxo infinito
    # de espaços até estourar o limite, o modelo emite um punhado de tokens de
    # espaço (35 a 89) e para sozinho, com finish_reason "stop".
    #
    # Como a falha é estocástica (a MESMA mensagem falhou e, repetida,
    # funcionou) e barata, repetir a chamada é a mitigação eficaz. 3 tentativas
    # levam a chance de falha de ~42% para ~7%, mantendo o custo baixo: só
    # repete quando falha, e a resposta em branco gasta poucos tokens.
    # A falha raramente é intermitente: em geral é o próprio histórico que
    # envenena o contexto, e repetir a requisição idêntica reproduz o mesmo
    # resultado degenerado. Numa bateria de 423 turnos, o retry idêntico
    # resgatou 5 das 126 falhas (4%); reduzir o histórico resgatou o resto.
    # Por isso a escada reduz o contexto em degraus, em vez de repetir:
    #   1ª tentativa: histórico inteiro;
    #   2ª: só o último par da conversa (resgatou 5 de 6 nos testes, e
    #       preserva a continuidade do diálogo);
    #   3ª: sem histórico nenhum (resgatou 6 de 6, mas perde o fio da
    #       conversa — por isso é o último recurso, não o primeiro).
    HISTORICO_POR_TENTATIVA = (None, 2, 0)

    def __init__(
        self,
        modelo: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Cria o cliente reaproveitando o SDK da OpenAI, apontado para o
        endpoint do DeepSeek."""
        super().__init__(
            modelo,
            api_key=api_key or config.DEEPSEEK_API_KEY,
            base_url=base_url or config.DEEPSEEK_BASE_URL,
        )

    def _parametros_extra(self) -> dict:
        """Desliga o "thinking mode" do DeepSeek.

        deepseek-v4-flash/v4-pro vêm com esse modo LIGADO por padrão. O bot
        precisa do comportamento do antigo modo non-thinking (mais rápido e
        mais barato, sem overhead de raciocínio) — desliga explicitamente via
        extra_body (parâmetro específico do DeepSeek, não faz parte do
        schema padrão da API OpenAI-compatível).
        """
        return {"extra_body": {"thinking": {"type": "disabled"}}}
