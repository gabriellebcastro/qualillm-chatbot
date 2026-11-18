"""Testes de cenário: o bot REAL conversa com uma LLM simulando o cliente
(simulador_cliente.py), seguindo os perfis de cenarios_conversacionais.py.

Toda a conversa é gerada por LLMs de verdade (bot e cliente simulado) — sem
nenhum duplo/mock no lugar da IA. Isso valida a qualidade das respostas do
bot em diálogos variados e mais elaborados, gerando logs reais (via
Instrumentador) da mesma forma que uma conversa de produção geraria. Chama a
API real (bot + simulador) várias vezes por cenário — marcado `integration`,
custa tokens.

    pytest -m integration -k cenario -v
"""
from __future__ import annotations

import pytest

import config
from bot import Chatbot
from cenarios_conversacionais import CENARIOS
from dados import FonteDeDadosMemoria
from eval import fidelidade
from instrumentacao import Instrumentador
from llm import criar_cliente
from rag import RecuperadorRAG
from simulador_cliente import SimuladorCliente

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not config.chave_do_provedor(config.BOT_PROVEDOR),
        reason=f"Chave de API do provedor do bot ('{config.BOT_PROVEDOR}') não configurada.",
    ),
    pytest.mark.skipif(
        not config.chave_do_provedor(config.SIMULADOR_PROVEDOR),
        reason=f"Chave de API do provedor do simulador ('{config.SIMULADOR_PROVEDOR}') não configurada.",
    ),
]


@pytest.mark.parametrize("cenario", CENARIOS, ids=lambda c: c.nome)
def test_cenario_conversacional(cenario, tmp_path):
    """Roda um cenário até o fim (acordo, recusa ou limite de turnos) e
    verifica o desfecho esperado e a fidelidade de todos os turnos."""
    fonte = FonteDeDadosMemoria()
    recuperador = RecuperadorRAG()
    llm_bot = criar_cliente(config.BOT_PROVEDOR, config.BOT_MODELO)
    bot = Chatbot(
        fonte, recuperador, llm_bot,
        temperatura=config.BOT_TEMPERATURA,
        k_rag=config.RAG_K,
        max_tokens=config.BOT_MAX_TOKENS,
    )
    simulador = SimuladorCliente(cenario.persona)
    inst = Instrumentador(f"teste-cenario-{cenario.nome}", dir_logs=tmp_path)

    fala_bot = None
    turnos = []
    for _ in range(cenario.max_turnos):
        fala_cliente = simulador.responder(fala_bot)
        resultado = bot.processar_turno(fala_cliente)
        turnos.append(inst.registrar(resultado))
        fala_bot = resultado.resposta_final
        if bot.finalizada:
            break
    else:
        pytest.fail(
            f"Cenário '{cenario.nome}' não encerrou em {cenario.max_turnos} turnos "
            f"(última fala do cliente: {fala_cliente!r})."
        )

    if cenario.resultado_esperado == "acordo":
        assert bot.acordo is not None, (
            f"Esperava acordo no cenário '{cenario.nome}', mas nenhum foi registrado."
        )
    else:
        assert bot.acordo is None, (
            f"Esperava recusa no cenário '{cenario.nome}', mas um acordo foi registrado."
        )

    if cenario.nome == "identifica_no_primeiro_turno":
        # O cliente deu o CPF já na 1ª mensagem — identificação e condições
        # devem estar disponíveis já no turno 1, não só num turno seguinte.
        operacoes_turno1 = {c["operacao"] for c in turnos[0]["consultas_dados"]}
        assert "consultar_cliente" in operacoes_turno1, (
            "Esperava identificação já no 1º turno (CPF veio na 1ª mensagem)."
        )
        assert "consultar_condicoes" in operacoes_turno1, (
            "Condições deveriam estar disponíveis já no turno da identificação."
        )

    resultados = fidelidade.avaliar_sessao(turnos)
    falhas = [r.to_dict() for r in resultados if not r.ok]
    assert not falhas, f"Fidelidade falhou no cenário '{cenario.nome}': {falhas}"
