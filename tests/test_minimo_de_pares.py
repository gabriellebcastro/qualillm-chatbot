"""Mínimo de pares na consistência (comentário #24 do orientador).

Taxa total: só conta como consistente com TODOS os pares decididos; a
divergência observada reprova mesmo com pares faltando. Taxa por pares: o
estímulo só contribui com mais da metade dos pares decididos. Sem API.
"""
from eval.consistencia import ParAvaliado, ResultadoConsistencia


def _resultado(vereditos, n=5, deterministico=True):
    from itertools import combinations
    pares = [ParAvaliado(a, b, v, "") for (a, b), v in zip(combinations(range(n), 2), vereditos)]
    return ResultadoConsistencia(
        origem_id="x", n_execucoes=n, assinaturas={}, grupos_factuais=1 if deterministico else 2,
        consistente_deterministicamente=deterministico, pares=pares,
        falhas_juiz=sum(v is None for v in vereditos),
    )


def test_todos_os_pares_decididos_e_equivalentes_conta_como_consistente():
    r = _resultado([True] * 10)
    assert r.consistente_totalmente is True
    assert r.taxa_equivalencia == 1.0


def test_par_faltando_tira_o_estimulo_da_taxa_total():
    r = _resultado([True] * 9 + [None])
    assert r.consistente_totalmente is None
    assert r.taxa_equivalencia == 1.0  # 9 de 10 decididos: mais da metade


def test_divergencia_observada_reprova_mesmo_com_pares_faltando():
    assert _resultado([False] + [None] * 9).consistente_totalmente is False
    assert _resultado([None] * 10, deterministico=False).consistente_totalmente is False


def test_metade_ou_menos_dos_pares_tira_o_estimulo_da_taxa_por_pares():
    assert _resultado([True] * 5 + [None] * 5).taxa_equivalencia is None
    assert _resultado([True] * 6 + [None] * 4).taxa_equivalencia == 1.0
