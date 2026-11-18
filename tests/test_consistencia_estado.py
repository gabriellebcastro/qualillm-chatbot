"""Camada determinística da consistência: trajetória do estado (I4).

Sem API. Até 04/11/2026 a camada comparava os fatos extraídos do texto e
acusava paráfrase e omissão; agora compara o `estado` de cada turno.
"""
from eval import consistencia


def _execucao(eid: int, respostas: list[str], estados: list[dict]):
    return [
        {"sessao_id": "s", "execucao_id": eid, "turno_id": i + 1,
         "mensagem_usuario": "m", "resposta_final": r, "estado": e, "meta": {}}
        for i, (r, e) in enumerate(zip(respostas, estados))
    ]


ESTAGIO_1 = {"divida_id": "DIV-004", "estagio_oferta": 1, "condicao_escolhida_id": "DIV-004-V2"}
ESTAGIO_2 = {"divida_id": "DIV-004", "estagio_oferta": 2, "condicao_escolhida_id": None}


def test_parafrase_e_omissao_com_o_mesmo_estado_sao_consistentes():
    # Fase 2, caso_consistencia_001 (e816 × e819) e _006 (e842).
    turnos = (
        _execucao(1, ["Você pode parcelar em até 24 parcelas."], [ESTAGIO_1])
        + _execucao(2, ["Você pode parcelar em até 24 vezes."], [ESTAGIO_1])
        + _execucao(3, ["R$ 7.000,00 à vista, em 1 parcela."], [ESTAGIO_1])
    )
    r = consistencia.avaliar(turnos, origem_id="x", usar_juiz=False)
    assert r.consistente_deterministicamente
    assert r.grupos_factuais == 1


def test_mesmo_texto_com_estados_diferentes_e_inconsistente():
    # Fase 2, caso_consistencia_009 (e856 × e857, t3): recusa marcada numa
    # repetição e não na outra.
    texto = ["Não consigo um valor menor. Se preferir, posso parcelar."]
    turnos = _execucao(1, texto, [ESTAGIO_2]) + _execucao(2, texto, [ESTAGIO_1])
    r = consistencia.avaliar(turnos, origem_id="x", usar_juiz=False)
    assert not r.consistente_deterministicamente
    assert r.grupos_factuais == 2


def test_estado_igual_no_fim_mas_caminho_diferente_e_inconsistente():
    turnos = (
        _execucao(1, ["a", "b"], [ESTAGIO_1, ESTAGIO_2])
        + _execucao(2, ["a", "b"], [ESTAGIO_2, ESTAGIO_2])
    )
    r = consistencia.avaliar(turnos, origem_id="x", usar_juiz=False)
    assert not r.consistente_deterministicamente
