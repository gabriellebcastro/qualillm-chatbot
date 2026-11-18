"""Camada de LLM agnóstica de provedor.

Fábrica `criar_cliente(provedor, modelo)` — o único ponto que conhece os
provedores concretos. Bot e juiz recebem um `ClienteLLM` e não sabem qual API
está por trás.
"""
from __future__ import annotations

from .interface import ClienteLLM, RespostaLLM


def criar_cliente(provedor: str, modelo: str) -> ClienteLLM:
    """Instancia o adaptador do provedor pedido ("openai"/"deepseek"/"anthropic",
    ou "anthropic-assinatura" para testes pela assinatura do Claude).

    Levanta ValueError se o provedor não for reconhecido.
    """
    provedor = provedor.lower()
    if provedor == "openai":
        from .openai_client import ClienteOpenAI

        return ClienteOpenAI(modelo)
    if provedor == "deepseek":
        from .deepseek_client import ClienteDeepSeek

        return ClienteDeepSeek(modelo)
    if provedor == "anthropic":
        from .anthropic_client import ClienteAnthropic

        return ClienteAnthropic(modelo)
    if provedor == "anthropic-assinatura":
        # Terceira via, para testes: o Claude pelo login da assinatura no
        # Claude Code CLI, sem chave de API. Ver o docstring do adaptador.
        from .claude_assinatura_client import ClienteClaudeAssinatura

        return ClienteClaudeAssinatura(modelo)
    raise ValueError(f"Provedor de LLM desconhecido: {provedor}")


__all__ = ["ClienteLLM", "RespostaLLM", "criar_cliente"]
