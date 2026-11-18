"""Testes do avaliador de fidelidade (eval/fidelidade.py) com dados
sintéticos — sem API, sem depender do bot."""
from eval import fidelidade


def _turno(**over):
    """Monta um dict de turno sintético (formato do log), com defaults
    razoáveis sobrescritos pelos kwargs passados."""
    base = {"turno_id": 1, "resposta_final": "", "consultas_dados": []}
    base.update(over)
    return base


def test_pega_resposta_que_descreve_acordo_diferente_do_registrado():
    """Achado real (LLM real): o bot registrou um acordo à vista mas
    descreveu 12x, com valores de outra condição, na mesma resposta. Cada
    número citado existia na fonte de verdade (vinha de uma condição real
    diferente), então a checagem geral (valor_existe/parcelas_existe) não
    via problema — só uma checagem específica contra O QUE FOI REGISTRADO
    pega essa incoerência."""
    condicoes = [
        {"id": "C01", "num_parcelas": 1, "valor_parcela": 8310.72,
         "valor_ultima_parcela": 8310.72, "valor_total_com_desconto": 8310.72,
         "data_primeiro_vencimento": "2026-07-21"},
        {"id": "C12", "num_parcelas": 12, "valor_parcela": 865.70,
         "valor_ultima_parcela": 865.66, "valor_total_com_desconto": 10388.40,
         "data_primeiro_vencimento": "2026-08-15"},
    ]
    acordo = {
        "id": "ACO-001", "condicao_id": "C01", "num_parcelas": 1,
        "valor_parcela": 8310.72, "valor_ultima_parcela": 8310.72,
        "valor_total": 8310.72, "data_primeiro_vencimento": "2026-07-21",
    }
    turnos = [
        _turno(
            turno_id=1,
            resposta_final="Temos estas opções de parcelamento disponíveis.",
            consultas_dados=[
                {"operacao": "consultar_condicoes", "argumentos": {}, "resultado": condicoes}
            ],
        ),
        _turno(
            turno_id=2,
            resposta_final=(
                "Perfeito! Forma de pagamento: 12 parcelas de R$ 865,70 cada, "
                "valor total de R$ 10.388,40, primeiro vencimento em 15/08/2026."
            ),
            consultas_dados=[
                {"operacao": "registrar_acordo", "argumentos": {}, "resultado": acordo}
            ],
        ),
    ]

    resultados = {r.turno_id: r for r in fidelidade.avaliar_sessao(turnos)}

    assert not resultados[2].ok
    tipos_falha = {v.tipo for v in resultados[2].verificacoes if not v.passou}
    assert "valor_bate_com_acordo_registrado" in tipos_falha
    assert "parcelas_bate_com_acordo_registrado" in tipos_falha


def test_nao_reclama_quando_resposta_bate_com_acordo_registrado():
    """Caso "feliz": a resposta descreve exatamente o acordo registrado —
    nenhuma verificação deve falhar."""
    condicoes = [
        {"id": "C12", "num_parcelas": 12, "valor_parcela": 865.70,
         "valor_ultima_parcela": 865.66, "valor_total_com_desconto": 10388.40,
         "data_primeiro_vencimento": "2026-08-15"},
    ]
    acordo = {
        "id": "ACO-001", "condicao_id": "C12", "num_parcelas": 12,
        "valor_parcela": 865.70, "valor_ultima_parcela": 865.66,
        "valor_total": 10388.40, "data_primeiro_vencimento": "2026-08-15",
    }
    turnos = [
        _turno(
            turno_id=1,
            resposta_final="Temos estas opções de parcelamento disponíveis.",
            consultas_dados=[
                {"operacao": "consultar_condicoes", "argumentos": {}, "resultado": condicoes}
            ],
        ),
        _turno(
            turno_id=2,
            resposta_final=(
                "Perfeito! 12 parcelas de R$ 865,70 cada, total de R$ 10.388,40, "
                "primeiro vencimento em 15/08/2026."
            ),
            consultas_dados=[
                {"operacao": "registrar_acordo", "argumentos": {}, "resultado": acordo}
            ],
        ),
    ]

    resultados = {r.turno_id: r for r in fidelidade.avaliar_sessao(turnos)}

    assert resultados[2].ok


def _com_janela(datas: str, **over):
    """Turno cujo bloco de contexto declarou esta janela de pagamento."""
    contexto = f"- Janela de datas de pagamento possível: SOMENTE estas datas: {datas}. Nenhuma outra."
    return _turno(prompt_completo=[{"role": "system", "content": "regras"},
                                   {"role": "system", "content": contexto},
                                   {"role": "user", "content": "outra data?"}], **over)


def test_aceita_as_datas_da_janela_entregue_ao_bot():
    # Bateria de 26/10/2026: o cliente pede outra data e o bot lista a janela
    # que o código lhe entregou. As 62 acusações eram todas desta forma.
    turno = _com_janela(
        "2026-10-27, 2026-10-28, 2026-11-03",
        resposta_final="Posso agendar para 27/10/2026, 28/10/2026 ou 03/11/2026.",
    )
    (resultado,) = fidelidade.avaliar_sessao([turno])
    assert all(v.passou for v in resultado.verificacoes if v.tipo == "data_existe")


def test_data_fora_da_janela_continua_acusada():
    turno = _com_janela(
        "2026-10-27, 2026-10-28",
        resposta_final="Posso agendar para 02/11/2026.",   # feriado, fora da janela
    )
    (resultado,) = fidelidade.avaliar_sessao([turno])
    assert not resultado.ok


# --- I1: eco recusado do valor do cliente ------------------------------------
def _valores(resultado):
    return {v.encontrado: v.passou for v in resultado.verificacoes if v.tipo == "valor_existe"}


def test_eco_recusado_do_valor_do_cliente_nao_e_acusado():
    # Fase 2, persona_insistente_001 e1202 t6: as 5 falhas da Fase 2 eram assim.
    turno = _turno(
        mensagem_usuario="faz um esforço e chega pelo menos em R$ 1.500 que eu fecho hoje",
        resposta_final="Entendo, mas não consigo chegar em R$ 1.500,00. A condição é outra.",
    )
    (resultado,) = fidelidade.avaliar_sessao([turno])
    assert _valores(resultado) == {1500.0: True}


def test_valor_do_cliente_repetido_sem_recusa_continua_acusado():
    # Fase 1, persona_confuso_001 e785 t8: o bot adotou o "349" do cliente.
    turno = _turno(
        mensagem_usuario="mas voce nao tinha falado 349 antes?",
        resposta_final="O valor de R$ 349,00 era a oferta à vista.",
    )
    (resultado,) = fidelidade.avaliar_sessao([turno])
    assert _valores(resultado) == {349.0: False}


def test_valor_recusado_que_o_cliente_nao_pediu_continua_acusado():
    turno = _turno(
        mensagem_usuario="faz por 1.500?",
        resposta_final="Não consigo chegar em R$ 1.400,00.",
    )
    (resultado,) = fidelidade.avaliar_sessao([turno])
    assert _valores(resultado) == {1400.0: False}


def test_valor_oferecido_depois_de_uma_negacao_com_virgula_continua_acusado():
    # "não consigo, mas faço R$ X": o valor é oferecido, não recusado.
    turno = _turno(
        mensagem_usuario="faz por 1.600?",
        resposta_final="Não consigo, mas faço R$ 1.600,00 pra você.",
    )
    (resultado,) = fidelidade.avaliar_sessao([turno])
    assert _valores(resultado) == {1600.0: False}


def test_valor_pedido_em_turno_anterior_tambem_vale_como_eco():
    turnos = [
        _turno(turno_id=1, mensagem_usuario="consegue R$ 1.600?", resposta_final="Vou ver."),
        _turno(turno_id=2, mensagem_usuario="e aí?",
               resposta_final="Não consigo chegar a R$ 1.600,00."),
    ]
    resultados = {r.turno_id: r for r in fidelidade.avaliar_sessao(turnos)}
    assert _valores(resultados[2]) == {1600.0: True}
