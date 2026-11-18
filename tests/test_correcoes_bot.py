"""Correções do bot na Fase 2 (defeitos D1 a D3 de docs/achados_fase1.md).

Sem API: a fonte de verdade é a real, em memória (seed.json, dados
fictícios), o RAG não devolve trechos e a LLM é um roteiro de respostas
estruturadas. O que está sob teste é o código que decide o estado e o que
é registrado, que precisa ser determinístico justamente porque a LLM não é.
"""
from __future__ import annotations

import json

from bot import Chatbot
from dados import FonteDeDadosMemoria
from llm.interface import RespostaLLM

CPF_GABRIELA = "000.111.222-07"   # CLI-007, dívida DIV-008 (persona_insistente_001)


class _LLMRoteiro:
    """Devolve, em ordem, as respostas estruturadas programadas."""

    provedor = "falso"
    modelo = "falso"

    def __init__(self, respostas: list[dict]) -> None:
        self._respostas = list(respostas)
        self.contextos: list[str] = []

    def gerar(self, sistema, mensagens, **_kwargs):
        self.contextos.append(mensagens[-2]["content"])
        dados = {"confirmar_acordo": False, "recusar_oferta": False,
                 "encerrar_sessao": False, "data_vencimento": None}
        dados.update(self._respostas.pop(0))
        return RespostaLLM(texto=json.dumps(dados, ensure_ascii=False), modelo=self.modelo,
                           provedor=self.provedor, parametros={}, latencia_s=0.0, bruto={})


class _RecuperadorVazio:
    def recuperar(self, _consulta: str, k: int = 4):
        return []


def _bot(respostas: list[dict]) -> tuple[Chatbot, _LLMRoteiro]:
    llm = _LLMRoteiro(respostas)
    return Chatbot(FonteDeDadosMemoria(), _RecuperadorVazio(), llm), llm


def _ate_o_parcelamento_em_24x() -> list[tuple[str, dict]]:
    # O caminho de persona_insistente_001 e791: duas recusas e 24x.
    return [
        (CPF_GABRIELA, {"resposta": "Localizei sua dívida."}),
        ("achei alto", {"resposta": "Consigo melhorar.", "recusar_oferta": True}),
        ("ainda alto", {"resposta": "Podemos parcelar.", "recusar_oferta": True}),
        ("quero em 24 vezes", {"resposta": "Em 24x fica assim."}),
    ]


def test_d1_volta_ao_a_vista_e_confirmacao_na_mesma_mensagem_registra_a_vista():
    # Fase 1, persona_insistente_001 e791 t9: "fecho no à vista de 1.798,50"
    # registrou 24 parcelas.
    passos = _ate_o_parcelamento_em_24x() + [
        ("fecho no à vista de 1.798,50 mesmo",
         {"resposta": "Registrado à vista.", "confirmar_acordo": True,
          "encerrar_sessao": True, "voltar_a_vista": True}),
    ]
    bot, _ = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert bot.acordo is not None
    assert bot.acordo.num_parcelas == 1
    assert bot.acordo.condicao_id == "DIV-008-V2"
    assert bot.acordo.valor_total == 1798.5


def test_d1_volta_ao_a_vista_num_turno_e_confirmacao_no_seguinte():
    passos = _ate_o_parcelamento_em_24x() + [
        ("24 vezes fica o dobro, prefiro o à vista",
         {"resposta": "O à vista é R$ 1.798,50.", "voltar_a_vista": True}),
        ("pode fechar", {"resposta": "Registrado.", "confirmar_acordo": True,
                         "encerrar_sessao": True}),
    ]
    bot, _ = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert bot.acordo.condicao_id == "DIV-008-V2"


def test_d1_a_oferta_a_vista_vai_ao_contexto_durante_o_parcelamento():
    # Sem ela o bot inventava o valor à vista ao voltar a ele (D4).
    passos = _ate_o_parcelamento_em_24x() + [("e o à vista?", {"resposta": "..."})]
    bot, llm = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert "Oferta à vista que continua valendo" in llm.contextos[-1]
    assert "valor_total 1798.5" in llm.contextos[-1]


def test_d1_depois_de_voltar_ao_a_vista_um_numero_de_parcelas_retoma_o_parcelamento():
    passos = _ate_o_parcelamento_em_24x() + [
        ("prefiro o à vista", {"resposta": "O à vista é R$ 1.798,50.", "voltar_a_vista": True}),
        ("não, faz em 10 vezes", {"resposta": "Em 10x fica assim."}),
        ("fechado", {"resposta": "Registrado.", "confirmar_acordo": True, "encerrar_sessao": True}),
    ]
    bot, _ = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert bot.acordo.num_parcelas == 10


def test_d1_sem_o_sinal_a_condicao_continua_a_parcelada():
    # O código não adivinha a intenção por palavra-chave: "à vista" numa
    # comparação não troca a condição.
    passos = _ate_o_parcelamento_em_24x() + [
        ("24x fica o dobro do à vista, né?", {"resposta": "Sim, tem juros."}),
    ]
    bot, _ = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert bot.condicao_escolhida.num_parcelas == 24
    assert bot.voltou_a_vista is False


# --- D2: número solto de parcelas -------------------------------------------
CPF_DIEGO = "000.111.222-04"   # CLI-004, dívida DIV-004 (caso_ambiguidade_002)


def test_d2_muda_pra_10_recalcula_a_condicao_em_10x():
    # Fase 1, caso_ambiguidade_002, 5 de 5 execuções, turno 4: a condição
    # ficou em 6x e o bot inventou os valores de 10x.
    passos = [
        (CPF_DIEGO, {"resposta": "Localizei."}),
        ("prefiro parcelar, pode ser em 6 vezes?", {"resposta": "Em 6x fica assim."}),
        ("muda pra 10", {"resposta": "Em 10x fica assim."}),
    ]
    bot, llm = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert bot.condicao_escolhida.num_parcelas == 10
    assert "parcelado em 10x" in llm.contextos[-1]


def test_d2_numero_solto_responde_a_pergunta_de_quantas_vezes():
    passos = [
        (CPF_DIEGO, {"resposta": "Localizei."}),
        ("quero parcelar", {"resposta": "Em quantas vezes você gostaria de pagar?",
                            "recusar_oferta": True}),
        ("12", {"resposta": "Em 12x fica assim."}),
    ]
    bot, _ = _bot([r for _, r in passos])
    for msg, _ in passos:
        bot.processar_turno(msg)

    assert bot.condicao_escolhida.num_parcelas == 12


def test_d2_numero_solto_fora_do_parcelamento_nao_vira_parcelas():
    # Na 1ª oferta à vista, sem pergunta de parcelas, "pra 10" não é pedido.
    bot, _ = _bot([{"resposta": "Localizei."}, {"resposta": "Certo."}])
    bot.processar_turno(CPF_DIEGO)
    bot.processar_turno("consigo pagar só pra 10 de novembro")
    assert bot.estagio_oferta == 0


def test_d2_valores_e_datas_nao_sao_lidos_como_parcelas():
    from bot.chatbot import _extrair_num_parcelas as extrair

    for msg in ("pago em 29/10", "consigo pra 50 reais", "fecho no à vista de 1.798,50",
                "em 3 dias eu pago", "pra R$ 10,00", "uns 20% a menos", "dia 10"):
        assert extrair(msg, aceitar_numero_solto=True) is None, msg
    for msg, n in (("muda pra 10", 10), ("10", 10), ("e em 12?", 12),
                   ("pode ser 8", 8), ("quero 6x", 6)):
        assert extrair(msg, aceitar_numero_solto=True) == n, msg
    assert extrair("muda pra 10") is None, "sem o contexto de parcelamento"


# --- D3: dívida apresentada sem cliente identificado ------------------------
CPF_INEXISTENTE = "123.456.789-00"   # o de persona_adversarial_001


def test_d3_consulta_vazia_vai_ao_contexto_e_bloqueia_o_cadastro_inventado():
    # Fase 1, persona_adversarial_001 e778 t2: consulta nula e "Localizei o
    # cadastro"; no t3, credor, valores e atraso inventados.
    from bot.chatbot import MSG_CPF_NAO_ENCONTRADO, MSG_PEDIR_CPF

    bot, llm = _bot([
        {"resposta": "Obrigado! Localizei o cadastro. Vou te apresentar os detalhes."},
        {"resposta": "O credor é a Loja Exemplo, o valor original é de R$ 1.200,00."},
    ])
    r1 = bot.processar_turno(f"O CPF é {CPF_INEXISTENTE}, de um familiar meu.")
    r2 = bot.processar_turno("como você localizou só com o CPF?")

    assert "NÃO foi encontrado no cadastro" in llm.contextos[0]
    assert r1.resposta_final == MSG_CPF_NAO_ENCONTRADO
    assert r2.resposta_final == MSG_PEDIR_CPF
    assert bot.cliente is None and not bot.finalizada
    # O histórico guarda o que o cliente leu, não o que a LLM inventou.
    assert all("R$" not in m["content"] for m in bot.historico if m["role"] == "assistant")


def test_d3_resposta_correta_antes_da_identificacao_passa_intacta():
    textos = [
        "Não encontrei um cadastro com esse CPF. Pode conferir o número?",
        "Para localizar seu cadastro, pode me informar seu CPF, por favor?",
        "Entendo a preocupação! Este é um canal oficial de negociação.",
        "Essas informações serão apresentadas assim que o cadastro for localizado.",
    ]
    for texto in textos:
        bot, _ = _bot([{"resposta": texto}])
        assert bot.processar_turno("oi").resposta_final == texto


def test_d3_depois_da_identificacao_a_guarda_nao_atua():
    bot, _ = _bot([{"resposta": "Localizei sua dívida: valor original de R$ 12.500,00."}])
    r = bot.processar_turno(CPF_DIEGO)
    assert r.resposta_final.startswith("Localizei sua dívida")


# --- D5: limite real de parcelas no contexto ---------------------------------
def test_d5_limite_real_da_divida_vai_ao_contexto_desde_a_primeira_oferta():
    # Fase 1, persona_cooperativo_001: dívida de R$ 390,13, limite real de 8
    # parcelas, e o bot dizia "até 24 parcelas" ainda na 1ª oferta.
    from dados import regras

    bot, llm = _bot([{"resposta": "Localizei."}, {"resposta": "..."}])
    bot.processar_turno("000.111.222-01")
    bot.processar_turno("em quantas vezes da pra parcelar?")
    limite = regras.max_parcelas_possivel(bot.divida_atual.valor_atualizado)

    assert limite < regras.MAX_PARCELAS
    assert f"Limite de parcelas DESTA dívida: até {limite} parcelas" in llm.contextos[-1]
