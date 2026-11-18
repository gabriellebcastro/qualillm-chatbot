"""Planilha da avaliação: lê os relatórios gravados e não perde ocorrência."""

import json

import openpyxl

from eval import planilha, relatorio


def _gravar(tmp_path, instante="20261027T000000Z"):
    oc = relatorio.ocorrencia(
        relatorio.CAMADA_DETERMINISTICA, "valor_existe: 9999.0 não consta na fonte de verdade",
        estimulo="caso_x", sessao_id="bateria__caso_x__m", execucao_id=7, turno_id=3,
        evidencia="R$ 9.999,00",
    )
    s = relatorio.Secao("precisao", "precisao_deterministica", 0.5, 2,
                        n_estimulos=1, ocorrencias=[oc])
    proc = {"juiz": "openai:gpt-5.6-terra", "coletado_em": "2026-10-27T20:29:52+00:00",
            "veredito": {"estado": "nao_conforme"}, "uso_do_juiz": {"chamadas": 3}}
    relatorio.escrever_categorias_json(
        [s], tmp_path / f"relatorio__precisao__{instante}.json", proc)
    return instante


def test_planilha_tem_as_quatro_abas_e_cada_ocorrencia(tmp_path):
    instante = _gravar(tmp_path)
    caminho = planilha.gerar_planilha(tmp_path, instante)
    wb = openpyxl.load_workbook(caminho)
    assert wb.sheetnames == ["Resumo", "Métricas", "Ocorrências", "Procedência"]
    linhas = list(wb["Ocorrências"].iter_rows(min_row=2, values_only=True))
    assert len(linhas) == 1
    categoria, metrica, tipo, camada, estimulo, execucao, turno, *_ = linhas[0]
    assert (categoria, tipo, camada, estimulo, execucao, turno) == (
        "Precisão", "Falha do sistema", "Determinística", "caso_x", "7", 3)
    status = wb["Métricas"].cell(row=2, column=7).value
    assert status == "Não atende"
    resumo = {r[0]: r[1] for r in wb["Resumo"].iter_rows(min_row=2, values_only=True)}
    assert resumo["Veredito global"] == "Não conforme"
    assert resumo["Avaliação feita em"] == "27/10/2026 20:29 (UTC)"
