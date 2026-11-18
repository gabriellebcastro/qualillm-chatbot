"""Reexecuta a MESMA entrada várias vezes (para medir consistência).

    python scripts/reexecutar.py [n]

Cada execução é registrada separadamente (mesmo arquivo de log, campo
`execucao_id` distinto). Requer OPENAI_API_KEY. Dados FICTÍCIOS.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from bot import Chatbot  # noqa: E402
from dados import FonteDeDadosMemoria  # noqa: E402
from instrumentacao import Instrumentador  # noqa: E402
from llm import criar_cliente  # noqa: E402
from rag import RecuperadorRAG  # noqa: E402

# Roteiro fixo: fluxo completo de negociação com um cliente do seed.
ROTEIRO_PADRAO = [
    "Olá, quero negociar minha dívida.",
    "Meu CPF é 000.111.222-04.",
    "Quais são as opções de parcelamento?",
    "Quero pagar em 6x.",
    "Sim, pode confirmar.",
]


def main() -> None:
    """Roda ROTEIRO_PADRAO `n` vezes contra o bot real, uma sessão nova por
    execução, registrando tudo com o mesmo `sessao_id` (execucao_id distinto)."""
    n = int(sys.argv[1]) if len(sys.argv) > 1 else config.N_EXECUCOES_PADRAO
    sessao_id = "reexec"
    recuperador = RecuperadorRAG()  # índice reaproveitado entre execuções

    caminho = None
    for execucao in range(n):
        fonte = FonteDeDadosMemoria()  # fonte isolada por execução
        llm = criar_cliente(config.BOT_PROVEDOR, config.BOT_MODELO)
        bot = Chatbot(
            fonte, recuperador, llm,
            temperatura=config.BOT_TEMPERATURA,
            k_rag=config.RAG_K,
            max_tokens=config.BOT_MAX_TOKENS,
        )
        inst = Instrumentador(sessao_id, execucao_id=execucao)
        caminho = inst.caminho

        print(f"\n===== Execução {execucao} =====")
        for msg in ROTEIRO_PADRAO:
            resultado = bot.processar_turno(msg)
            inst.registrar(resultado)
            print(f"  U: {msg}")
            print(f"  B: {resultado.resposta_final[:120]}")
            if bot.finalizada:
                break

    print(f"\n{n} execução(ões) registrada(s) em: {caminho}")


if __name__ == "__main__":
    main()
