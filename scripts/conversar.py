"""Conversa interativa com o chatbot (requer OPENAI_API_KEY).

    python scripts/conversar.py

Cada turno é registrado em logs/manuais/<sessao>.jsonl para posterior avaliação.
Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from bot import Chatbot  # noqa: E402
from dados import FonteDeDadosMemoria  # noqa: E402
from instrumentacao import Instrumentador  # noqa: E402
from llm import criar_cliente  # noqa: E402
from rag import RecuperadorRAG  # noqa: E402


def main() -> None:
    """Loop de conversa no terminal: lê mensagens do usuário, chama o bot,
    grava cada turno no log, até o usuário sair ou a sessão se encerrar."""
    sessao_id = f"conversa-{uuid.uuid4().hex[:8]}"
    fonte = FonteDeDadosMemoria()
    recuperador = RecuperadorRAG()
    llm = criar_cliente(config.BOT_PROVEDOR, config.BOT_MODELO)
    bot = Chatbot(
        fonte, recuperador, llm,
        temperatura=config.BOT_TEMPERATURA,
        k_rag=config.RAG_K,
        max_tokens=config.BOT_MAX_TOKENS,
    )
    inst = Instrumentador(sessao_id, dir_logs=config.DIR_LOGS_MANUAIS)

    print("=" * 70)
    print("Chatbot de negociação de dívidas — DADOS 100% FICTÍCIOS")
    print(f"Sessão: {sessao_id} | Bot: {config.BOT_PROVEDOR}/{config.BOT_MODELO}")
    print("Digite sua mensagem (ou 'sair' para encerrar).")
    print("Dica: identifique-se com um CPF do seed, ex.: 000.111.222-04")
    print("=" * 70)

    while True:
        try:
            msg = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        if msg.lower() in ("sair", "exit", "quit"):
            break
        resultado = bot.processar_turno(msg)
        inst.registrar(resultado)
        print(f"\nBot: {resultado.resposta_final}")
        if bot.finalizada:
            print("\n✅ Atendimento encerrado. A sessão foi finalizada automaticamente.")
            break

    print(f"\nLog da sessão salvo em: {inst.caminho}")


if __name__ == "__main__":
    main()
