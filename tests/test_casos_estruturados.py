"""Casos de teste estruturados: {mensagem, identificador_cliente} fixos,
carregados de tests/casos_teste.json.

Diferente de tests/cenarios_conversacionais.py (personas em linguagem
natural, conversa dinâmica gerada por uma LLM simulando o cliente) e de
scripts/reexecutar.py (roteiro fixo de N turnos, embutido no script, focado
em medir consistência) — este arquivo é a terceira via: casos determinísticos
de turno único, com identificador do cliente explícito, em um arquivo de
dados separado do código. Chama a API real do bot — marcado `integration`.

    pytest -m integration -k caso_estruturado -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import config
from bot import Chatbot
from dados import FonteDeDadosMemoria
from llm import criar_cliente
from rag import RecuperadorRAG

CAMINHO_CASOS = Path(__file__).resolve().parent / "casos_teste.json"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not config.chave_do_provedor(config.BOT_PROVEDOR),
        reason=f"Chave de API do provedor do bot ('{config.BOT_PROVEDOR}') não configurada.",
    ),
]


def _carregar_casos() -> list[dict]:
    """Lê os casos de teste estruturados de tests/casos_teste.json."""
    return json.loads(CAMINHO_CASOS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", _carregar_casos(), ids=lambda c: c["nome"])
def test_caso_estruturado(caso):
    """Envia a mensagem do caso ao bot real e verifica se o cliente certo
    (ou nenhum, quando esperado) foi identificado."""
    fonte = FonteDeDadosMemoria()
    recuperador = RecuperadorRAG()
    llm = criar_cliente(config.BOT_PROVEDOR, config.BOT_MODELO)
    bot = Chatbot(
        fonte, recuperador, llm,
        temperatura=config.BOT_TEMPERATURA,
        k_rag=config.RAG_K,
        max_tokens=config.BOT_MAX_TOKENS,
    )

    bot.processar_turno(caso["mensagem"])

    if caso["cliente_deve_ser_encontrado"]:
        assert bot.cliente is not None, (
            f"Caso '{caso['nome']}': esperava identificar o CPF "
            f"{caso['identificador_cliente']!r}, mas não identificou."
        )
        encontrado = bot.cliente.cpf.replace(".", "").replace("-", "")
        esperado = caso["identificador_cliente"].replace(".", "").replace("-", "")
        assert encontrado == esperado, (
            f"Caso '{caso['nome']}': identificou o CPF errado."
        )
    else:
        assert bot.cliente is None, (
            f"Caso '{caso['nome']}': não deveria ter identificado nenhum cliente."
        )
