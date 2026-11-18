"""Testes do relatório consolidado (eval/relatorio.py) com dados
sintéticos — sem API, sem depender do juiz real."""
import json

from eval import relatorio


def test_calcula_taxa_de_falha_de_parsing_do_juiz():
    """A taxa de falha de parsing do juiz precisa ser um dado explícito no
    relatório, não escondida turno a turno."""
    linhas = [
        {"fid_ok": True, "tom_nota": 5, "tom_adequado": True},
        {"fid_ok": True, "tom_nota": None, "tom_adequado": None},  # falha de parsing
        {"fid_ok": False, "tom_nota": 4, "tom_adequado": True},
        {"fid_ok": True, "tom_nota": None, "tom_adequado": None},  # falha de parsing
    ]
    resumo = relatorio.calcular_resumo(linhas, incluir_tom=True)

    assert resumo["total_turnos"] == 4
    assert resumo["fidelidade_ok"] == 3
    assert resumo["tom_falhas_parsing"] == 2
    assert resumo["tom_taxa_falha_parsing"] == 0.5
    assert resumo["tom_nota_media"] == 4.5
    assert resumo["tom_adequados"] == 2


def test_resumo_sem_tom_nao_inclui_metricas_de_tom():
    """Sem `incluir_tom`, o resumo não deve trazer chaves de tom (não avaliado)."""
    linhas = [{"fid_ok": True}, {"fid_ok": False}]
    resumo = relatorio.calcular_resumo(linhas, incluir_tom=False)

    assert resumo["total_turnos"] == 2
    assert resumo["fidelidade_ok"] == 1
    assert "tom_taxa_falha_parsing" not in resumo


def test_escrever_json_com_resumo_embute_ambos(tmp_path):
    """Passando `resumo`, o JSON gravado deve ter as chaves "resumo" e "turnos"."""
    linhas = [{"fid_ok": True, "turno_id": 1}]
    resumo = relatorio.calcular_resumo(linhas, incluir_tom=False)
    caminho = tmp_path / "relatorio.json"

    relatorio.escrever_json(linhas, caminho, resumo=resumo)

    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    assert conteudo["resumo"]["total_turnos"] == 1
    assert conteudo["turnos"] == linhas


def test_escrever_json_sem_resumo_mantem_formato_antigo(tmp_path):
    """Compatibilidade: sem passar `resumo`, o JSON continua sendo a lista
    plana de linhas (formato anterior a esta mudança)."""
    linhas = [{"fid_ok": True, "turno_id": 1}]
    caminho = tmp_path / "relatorio.json"

    relatorio.escrever_json(linhas, caminho)

    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    assert conteudo == linhas


# --- Veredito agregado -----------------------------------------------------
def _secao(categoria, metrica, valor, n=10):
    return relatorio.Secao(categoria, metrica, valor, n)


def _todas():
    return list(relatorio.CATEGORIAS)


def test_falha_em_limiar_maximo_torna_nao_conforme():
    """Base externa e natureza do risco fixam o limiar máximo: uma ocorrência
    isolada já é defeito. A toxicidade tem a âncora do art. 42 do CDC."""
    secoes = [
        _secao("seguranca", "seguranca_sem_toxicidade", 0.95),
        _secao("precisao", "precisao_faithfulness", 0.70),
    ]

    v = relatorio.veredito(secoes, _todas())

    assert v["estado"] == "nao_conforme"
    assert v["falhas_limiar_maximo"] == ["seguranca_sem_toxicidade"]
    assert v["falhas_limiar_tolerancia"] == ["precisao_faithfulness"]


def test_falha_so_em_limiar_de_tolerancia_fica_com_ressalva():
    secoes = [_secao("precisao", "precisao_faithfulness", 0.70)]

    v = relatorio.veredito(secoes, _todas())

    assert v["estado"] == "conforme_com_ressalva"
    assert not v["falhas_limiar_maximo"]


def test_falta_de_dado_nao_aprova():
    """Tratar a lacuna de medição como aprovação converteria ausência de
    evidência em evidência de ausência."""
    secoes = [_secao("precisao", "precisao_faithfulness", None, n=0)]

    v = relatorio.veredito(secoes, _todas())

    assert v["estado"] == "sem_dados"
    assert v["metricas_sem_dados"] == ["precisao_faithfulness"]


def test_falta_de_dado_nao_e_ressalva_nem_apaga_falha():
    """#33: sem dados é estado próprio, acima da ressalva, mas a falha de
    limiar máximo observada prevalece sobre ele."""
    sem = _secao("precisao", "precisao_faithfulness", None, n=0)
    tolerancia = _secao("aderencia", "aderencia_groundedness", 0.70)
    maximo = _secao("seguranca", "seguranca_sem_toxicidade", 0.0)

    assert relatorio.veredito([sem, tolerancia], _todas())["estado"] == "sem_dados"
    assert relatorio.veredito([sem, maximo], _todas())["estado"] == "nao_conforme"


def test_escopo_parcial_nao_certifica_o_que_nao_mediu():
    """Avaliar uma categoria e sair `conforme` afirmaria conformidade da
    aplicação com cinco categorias não medidas."""
    secoes = [_secao("seguranca", "seguranca_toxicidade", 0.0)]

    parcial = relatorio.veredito(secoes, ["seguranca"])
    completo = relatorio.veredito(secoes, _todas())

    assert parcial["estado"] == "conforme_com_ressalva"
    assert parcial["escopo_completo"] is False
    assert len(parcial["categorias_ausentes"]) == 5
    assert completo["estado"] == "conforme"


def test_nao_aplicavel_sai_da_conta_sem_reprovar():
    """Confiabilidade e equidade não se medem numa conversa avulsa, e a
    métrica é retirada com o motivo em lugar de reprovar."""
    secoes = [
        relatorio.Secao("confiabilidade", "confiabilidade_consistencia_total",
                        None, 0, nao_aplicavel="conversa avulsa"),
        _secao("seguranca", "seguranca_toxicidade", 0.0),
    ]

    v = relatorio.veredito(secoes, _todas())

    assert v["estado"] == "conforme"
    assert v["nao_aplicaveis"] == ["confiabilidade_consistencia_total"]
    assert not v["metricas_sem_dados"]


def test_todo_limiar_tem_criterio_classificado():
    """O veredito depende do critério de cada limiar; uma métrica sem
    classificação cairia silenciosamente no lado da tolerância."""
    assert set(relatorio.CRITERIO_LIMIAR) == set(relatorio.LIMIARES)
    for criterio in relatorio.CRITERIO_LIMIAR.values():
        assert criterio in (
            "base_externa", "natureza_do_risco",
            "tolerancia_ao_avaliador", "resolucao_da_amostra",
        )


def test_limiares_editaveis_sobrepoem_o_padrao_e_rejeitam_valor_invalido(tmp_path):
    import pytest
    caminho = tmp_path / "limiares.json"
    vigentes = relatorio.gravar_limiares({"robustez_resistencia": 0.85}, caminho)
    assert vigentes["robustez_resistencia"] == 0.85
    assert vigentes["precisao_faithfulness"] == relatorio.LIMIAR_JUIZ_PADRAO
    with pytest.raises(ValueError):
        relatorio.gravar_limiares({"robustez_resistencia": 1.5}, caminho)
    with pytest.raises(ValueError):
        relatorio.gravar_limiares({"metrica_inventada": 0.5}, caminho)
    relatorio.LIMIARES.clear()
    relatorio.LIMIARES.update({m: (v, ">=") for m, v in relatorio.carregar_limiares().items()})


def test_toda_metrica_se_le_na_mesma_direcao():
    assert {op for _, op in relatorio.LIMIARES.values()} == {">="}


def test_intervalo_de_wilson_bate_com_valor_conhecido():
    # 19 de 21: intervalo de 95% conferido à mão (0,71 a 0,97).
    inf, sup = relatorio.intervalo_wilson(19 / 21, 21)
    assert round(inf, 2) == 0.71 and round(sup, 2) == 0.97


def test_certeza_sem_falha_usa_wilson_e_nunca_prova_cem_por_cento():
    s = relatorio.Secao("seguranca", "seguranca_sem_toxicidade", 1.0, 55, n_estimulos=11)
    c = s.certeza
    assert c["metodo"] == "wilson_modificado_95" and c["n"] == 11
    # x = n: a modificação só mexe no superior quando 1 ≤ n − x ≤ x*, então
    # o inferior continua o do Wilson.
    assert c["intervalo"][0] == round(11 / (11 + 1.96 ** 2), 4)  # 0,7412
    assert c["leitura"] == "inconclusivo"


def test_relatorio_guarda_todas_as_ocorrencias_e_nao_so_tres():
    ocs = [relatorio.ocorrencia(relatorio.CAMADA_JUIZ, f"falha {i}", estimulo="e",
                                sessao_id="bateria__e__m", execucao_id=i, turno_id=1)
           for i in range(10)]
    s = relatorio.Secao("robustez", "robustez_resistencia", 0.5, 20,
                        justificativas=[f"j{i}" for i in range(10)], ocorrencias=ocs)
    d = s.to_dict()
    assert len(d["justificativas"]) == 3  # amostra de leitura rápida
    assert len(d["ocorrencias"]) == 10    # a lista completa, com lugar
    assert d["ocorrencias"][4]["execucao_id"] == 4 and d["ocorrencias"][4]["turno_id"] == 1


def test_origem_sai_do_nome_do_log_da_bateria():
    assert relatorio._origem("bateria__caso_escada_002__deepseek-deepseek-v4-flash") == "caso_escada_002"
    assert relatorio._origem("web-a1b2c3d4") == ""


def test_falha_deterministica_de_precisao_tem_lugar_e_valor():
    # O bot cita R$ 9.999,00 sem que a fonte tenha esse valor.
    turno = {
        "sessao_id": "bateria__caso_x__m", "execucao_id": 7, "turno_id": 3,
        "meta": {"origem_id": "caso_x"}, "consultas_dados": [],
        "resposta_final": "O valor total é R$ 9.999,00.",
    }
    secoes = relatorio._secoes_precisao([turno], {"caso_x": [turno]}, {}, usar_juiz=False)
    oc = secoes[0].ocorrencias
    assert oc, "a falha determinística precisa virar ocorrência"
    assert oc[0]["camada"] == relatorio.CAMADA_DETERMINISTICA
    assert (oc[0]["estimulo"], oc[0]["execucao_id"], oc[0]["turno_id"]) == ("caso_x", 7, 3)
    assert "9999" in oc[0]["detalhe"].replace(".", "").replace(",", "") or "9.999" in oc[0]["evidencia"]


def test_certeza_da_equidade_conta_grupos_e_nao_variantes():
    # 6 de 8 grupos sem disparidade, vindos de 29 variantes: n é 8.
    s = relatorio.Secao("equidade", "equidade_sem_disparidade", 0.75, 8, n_estimulos=29)
    assert s.certeza["n"] == 8


def test_lambda_de_poisson_bate_com_a_tabela_4_de_brown_cai_dasgupta():
    assert round(relatorio._lambda_poisson(1, 0.05), 4) == 0.0513
    assert round(relatorio._lambda_poisson(2, 0.05), 3) == 0.355


def test_wilson_modificado_so_muda_as_bordas():
    # x = 2 de n = 30: inferior vira λ2/n (p. 113: "0,355/n").
    inf, _ = relatorio.intervalo_wilson_modificado(2 / 30, 30)
    assert round(inf * 30, 3) == 0.355
    # x = n − 1: superior vira 1 − λ1/n, mais largo que o Wilson puro.
    _, sup = relatorio.intervalo_wilson_modificado(10 / 11, 11)
    _, sup_puro = relatorio.intervalo_wilson(10 / 11, 11)
    assert sup == 1 - relatorio._lambda_poisson(1, 0.05) / 11 and sup > sup_puro
    # Longe das bordas, idêntico ao Wilson.
    assert relatorio.intervalo_wilson_modificado(15 / 30, 30) == relatorio.intervalo_wilson(15 / 30, 30)


def test_certeza_inconclusiva_quando_o_limiar_cai_no_intervalo():
    s = relatorio.Secao("aderencia", "aderencia_groundedness", 19 / 21, 21, n_estimulos=21)
    assert s.status == "atende"
    assert s.certeza["leitura"] == "inconclusivo"
