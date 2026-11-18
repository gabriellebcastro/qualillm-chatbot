"""Teste de consistência (Seção do TCC sobre reexecução).

Roda a MESMA interação `config.N_EXECUCOES_PADRAO` vezes contra o provedor
de LLM configurado de verdade e verifica, em cada execução, que a
fidelidade de dados se mantém (Seção 5.1) e — se o juiz estiver configurado
(ANTHROPIC_API_KEY) — que o tom da conversa inteira continua adequado
(Seção 5.2, `AvaliadorTom.avaliar_sessao`, 1 chamada por execução). Chama a
API real do bot — custa tokens — por isso é marcado `integration` e fica de
fora do `pytest` comum (pytest.ini já registra `addopts = -m "not integration"`).

    pytest -m integration -v
"""
from __future__ import annotations

import pytest

import config
from bot import Chatbot
from dados import FonteDeDadosMemoria
from eval import fidelidade
from eval.tom import AvaliadorTom
from instrumentacao import Instrumentador
from llm import criar_cliente
from rag import RecuperadorRAG

pytestmark = pytest.mark.integration

ROTEIRO_PADRAO = [
    "Olá, quero negociar minha dívida.",
    "Meu CPF é 000.111.222-04.",
    "Quais são as opções de parcelamento?",
    "Quero pagar em 6x.",
    "Sim, pode confirmar.",
]


@pytest.mark.skipif(
    not config.chave_do_provedor(config.BOT_PROVEDOR),
    reason=f"Chave de API do provedor '{config.BOT_PROVEDOR}' não configurada em .env.",
)
@pytest.mark.repeat(config.N_EXECUCOES_PADRAO)
def test_fidelidade_se_mantem_em_execucoes_repetidas(tmp_path):
    """Roda ROTEIRO_PADRAO uma vez (repetido N vezes pelo `pytest.mark.repeat`)
    e verifica que a sessão encerra com fidelidade OK em todos os turnos."""
    fonte = FonteDeDadosMemoria()
    recuperador = RecuperadorRAG()
    llm = criar_cliente(config.BOT_PROVEDOR, config.BOT_MODELO)
    bot = Chatbot(
        fonte, recuperador, llm,
        temperatura=config.BOT_TEMPERATURA,
        k_rag=config.RAG_K,
        max_tokens=config.BOT_MAX_TOKENS,
    )
    # Log da execução vai para um diretório temporário (não polui logs/).
    inst = Instrumentador("teste-consistencia", dir_logs=tmp_path)

    turnos = []
    for msg in ROTEIRO_PADRAO:
        resultado = bot.processar_turno(msg)
        turnos.append(inst.registrar(resultado))
        if bot.finalizada:
            break

    assert bot.finalizada, "O roteiro padrão não encerrou a sessão."

    resultados = fidelidade.avaliar_sessao(turnos)
    falhas = [r.to_dict() for r in resultados if not r.ok]
    assert not falhas, f"Fidelidade falhou em {len(falhas)} turno(s): {falhas}"

    # Tom: melhor esforço — só roda se o juiz estiver configurado, pra não
    # exigir ANTHROPIC_API_KEY de quem só quer testar a consistência do bot.
    if config.chave_do_provedor(config.JUIZ_PROVEDOR):
        julgamento = AvaliadorTom().avaliar_sessao(turnos)
        inst.registrar_avaliacao_tom(julgamento)
        assert julgamento.get("adequado") is True, (
            f"Tom considerado inadequado nesta execução: {julgamento.get('justificativa')}"
        )
