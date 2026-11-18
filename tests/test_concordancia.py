"""Testes da camada 4 — concordância humano × juiz (eval/concordancia.py).

Sem API: o coletor é alimentado à mão e o κ é aritmética sobre os rótulos.
"""
from eval import concordancia


def _item(metrica, rotulo, **extra):
    base = {"metrica": metrica, "rotulo_juiz": rotulo}
    base.update(extra)
    return base


def test_coletor_descarta_julgamento_sem_veredito():
    """Um julgamento que falhou não é veredito com que alguém possa
    concordar; incluí-lo inflaria o n do κ com linhas não rotuláveis."""
    c = concordancia.Coletor()
    c.adicionar("seguranca_toxicidade", True)
    c.adicionar("seguranca_toxicidade", None)   # juiz falhou
    c.adicionar("seguranca_toxicidade", False)

    assert c.por_metrica() == {"seguranca_toxicidade": 2}


def test_coletor_normaliza_e_numera():
    c = concordancia.Coletor()
    c.adicionar("robustez_resistencia", True, turno_id=3)
    c.adicionar("robustez_resistencia", "Sim", turno_id=4)

    assert [i["rotulo_juiz"] for i in c.itens] == ["true", "true"]
    assert [i["id"] for i in c.itens] == [1, 2]


def test_amostra_estratificada_garante_minimo_por_metrica():
    """O κ é por métrica, então sortear do bolo todo daria n grande numa
    métrica e n=2 em outra. Estratificar garante o mínimo onde há pouco."""
    itens = (
        [_item("a", "true") for _ in range(100)]
        + [_item("b", "false") for _ in range(3)]
    )

    amostra = concordancia.amostrar_por_metrica(itens, por_metrica=5)

    contagem = {}
    for i in amostra:
        contagem[i["metrica"]] = contagem.get(i["metrica"], 0) + 1
    assert contagem == {"a": 5, "b": 3}   # 'b' entra inteira: tinha menos que 5


def test_amostra_e_reproduzivel_com_a_mesma_semente():
    itens = [_item("a", "true", id=i) for i in range(50)]

    um = concordancia.amostrar_por_metrica(itens, 10, semente=42)
    dois = concordancia.amostrar_por_metrica(itens, 10, semente=42)
    outra = concordancia.amostrar_por_metrica(itens, 10, semente=7)

    assert [i["id"] for i in um] == [i["id"] for i in dois]
    assert [i["id"] for i in um] != [i["id"] for i in outra]


def test_kappa_de_acordo_perfeito_com_duas_categorias():
    linhas = (
        [{"metrica": "m", "rotulo_humano": "true", "rotulo_juiz": "true"}] * 6
        + [{"metrica": "m", "rotulo_humano": "false", "rotulo_juiz": "false"}] * 4
    )

    (r,) = concordancia.calcular_kappa(linhas)

    assert r.n == 10
    assert r.concordancia_observada == 1.0
    assert r.kappa == 1.0
    assert r.interpretacao == "quase perfeita"


def test_kappa_indefinido_quando_so_existe_uma_categoria():
    """Amostra degenerada: os dois rotuladores usaram um único rótulo. Não há
    acordo a medir além do acaso, e a fórmula dividiria por zero."""
    linhas = [{"metrica": "m", "rotulo_humano": "true", "rotulo_juiz": "true"}] * 8

    (r,) = concordancia.calcular_kappa(linhas)

    assert r.kappa is None
    assert r.interpretacao == "indefinido"


def test_escala_de_landis_e_koch_tem_seis_faixas():
    # Landis e Koch (1977, p. 165): "pobre" é só abaixo de zero; de 0,00 a
    # 0,20 é "leve". A versão anterior chamava 0,00–0,20 de "pobre".
    casos = {
        -0.05: "pobre", 0.0: "leve", 0.20: "leve", 0.21: "razoável",
        0.40: "razoável", 0.41: "moderada", 0.60: "moderada",
        0.61: "substancial", 0.80: "substancial", 0.81: "quase perfeita",
        1.0: "quase perfeita",
    }
    for kappa, faixa in casos.items():
        assert concordancia.interpretar(kappa) == faixa, kappa


def test_fronteira_da_escala_usa_o_valor_arredondado():
    # A escala tem duas casas: 0,2005 é 0,20 (leve), e não cai no vão entre
    # 0,20 e 0,21.
    assert concordancia.interpretar(0.2005) == "leve"
    assert concordancia.interpretar(0.2051) == "razoável"
    assert concordancia.interpretar(0.8049) == "substancial"
    assert concordancia.interpretar(-0.004) == "leve"   # arredonda para 0,00
    assert concordancia.interpretar(None) == "indefinido"


def test_linhas_sem_rotulo_humano_ficam_fora():
    """Rotulagem parcial é o caso comum: o que não foi rotulado não entra."""
    linhas = [
        {"metrica": "m", "rotulo_humano": "true", "rotulo_juiz": "true"},
        {"metrica": "m", "rotulo_humano": "", "rotulo_juiz": "false"},
        {"metrica": "m", "rotulo_humano": "false", "rotulo_juiz": "false"},
    ]

    (r,) = concordancia.calcular_kappa(linhas)

    assert r.n == 2


def test_cerquilha_dentro_do_item_julgado_sobrevive_ao_round_trip(tmp_path):
    """Achado real: o filtro de comentário apagava linhas de DENTRO dos
    campos. O `item_julgado` de precisão e aderência traz o texto que o juiz
    leu, e esse texto tem `## FONTE` e `## TRECHOS RECUPERADOS` — quem fosse
    rotular veria a evidência sem o cabeçalho que separa fonte de resposta."""
    conteudo = (
        "AFIRMACAO: o desconto maximo e 50%\n\n"
        "## TRECHOS RECUPERADOS\n- politica X\n\n"
        "## RESPOSTA A VERIFICAR\nOla!"
    )
    caminho = tmp_path / "amostra.csv"
    concordancia.exportar_amostra(
        [_item("aderencia_groundedness", "sustentada", item_julgado=conteudo)],
        caminho,
    )

    (lido,) = concordancia.carregar_amostra(caminho)

    assert lido["item_julgado"] == conteudo
    assert lido["rotulo_juiz"] == "sustentada"
    assert lido["rotulo_humano"] == ""


def test_amostra_enriquecida_garante_os_casos_que_decidem():
    """Nas métricas de alvo zero os positivos são raríssimos, e um sorteio
    aleatório traz zero deles: os dois rotuladores respondem a mesma coisa em
    tudo, não há acordo a medir além do acaso e o κ degenera. Medido num teste
    de fumaça: Po 0,80 com κ 0,0000."""
    itens = (
        [_item("seguranca_toxicidade", "false") for _ in range(100)]
        + [_item("seguranca_toxicidade", "true") for _ in range(3)]
    )

    sem = concordancia.amostrar_por_metrica(itens, 10, enriquecer=False)
    com = concordancia.amostrar_por_metrica(itens, 10, enriquecer=True)

    assert sum(1 for i in sem if i["rotulo_juiz"] == "true") == 0
    assert sum(1 for i in com if i["rotulo_juiz"] == "true") == 3
    assert len(com) == 10, "a cota continua sendo teto"


def test_o_rotulo_de_interesse_nao_e_sempre_true():
    """Na robustez e na consistência o achado é o `false` (não resistiu,
    divergiu); na toxicidade e na equidade é o `true`. Enriquecer com o rótulo
    errado traria justamente os casos sem informação."""
    assert concordancia.ROTULO_DE_INTERESSE["robustez_resistencia"] == "false"
    assert concordancia.ROTULO_DE_INTERESSE["confiabilidade_equivalencia_par"] == "false"
    assert concordancia.ROTULO_DE_INTERESSE["seguranca_toxicidade"] == "true"
    assert set(concordancia.ROTULO_DE_INTERESSE) == set(concordancia.ROTULOS_POSSIVEIS)


def test_csv_enriquecido_avisa_no_proprio_arquivo(tmp_path):
    """Quem ler o κ meses depois precisa saber que a amostra não é estimativa
    populacional, e o aviso não pode viver só na tela de quem exportou."""
    caminho = tmp_path / "amostra.csv"
    # Com `item_julgado`: sem ele e sem log, o item de toxicidade sairia da
    # amostra (ver `completar_item_julgado`), e não é isso que se testa aqui.
    concordancia.exportar_amostra(
        [_item("seguranca_toxicidade", "true", item_julgado="conversa")],
        caminho, por_metrica=5,
    )

    texto = caminho.read_text(encoding="utf-8")
    assert "AMOSTRA ENRIQUECIDA" in texto
    # E as duas linhas de comentário não atrapalham a leitura.
    assert len(concordancia.carregar_amostra(caminho)) == 1


def test_abstencao_humana_fica_fora_do_kappa_e_e_contada():
    from eval.concordancia import calcular_kappa
    linhas = (
        [{"metrica": "m", "rotulo_humano": "true", "rotulo_juiz": "true"}] * 3
        + [{"metrica": "m", "rotulo_humano": "false", "rotulo_juiz": "false"}] * 3
        + [{"metrica": "m", "rotulo_humano": "evidencia_insuficiente", "rotulo_juiz": "true"}] * 2
    )
    (r,) = calcular_kappa(linhas)
    assert r.n == 6 and r.kappa == 1.0 and r.abstencoes_humanas == 2


def _julgado(metrica, rotulo, turno=1, execucao=0):
    from eval.concordancia import chave_item
    return {"metrica": metrica, "rotulo_juiz": rotulo, "sessao_id": "s",
            "execucao_id": execucao, "turno_id": turno,
            "chave": chave_item(metrica, "s", execucao, turno)}


def test_comparar_juizes_casa_itens_e_conta_os_de_um_juiz_so():
    from eval.concordancia import comparar_juizes
    a = [_julgado("robustez_resistencia", "true", t) for t in (1, 2, 3)] + [_julgado("robustez_resistencia", "false", 4)]
    b = [_julgado("robustez_resistencia", "true", t) for t in (1, 2)] + [_julgado("robustez_resistencia", "false", 3)]
    (m,) = comparar_juizes(a, b)["metricas"]
    assert m["n"] == 3 and m["divergentes"] == 1 and m["so_um_juiz"] == 1


def test_afirmacoes_sobem_para_o_turno_na_comparacao():
    from eval.concordancia import comparar_juizes
    # O juiz A decompôs em duas afirmações, o B em uma, com textos diferentes.
    a = [_julgado("precisao_faithfulness", "sustentada"), _julgado("precisao_faithfulness", "nao_sustentada")]
    b = [_julgado("precisao_faithfulness", "nao_sustentada")]
    (m,) = comparar_juizes(a, b)["metricas"]
    assert m["metrica"] == "precisao_faithfulness_turno"
    assert m["n"] == 1 and m["divergentes"] == 0


def test_rotulo_humano_vale_contra_o_segundo_juiz_pela_chave():
    from eval.concordancia import kappa_humano_contra
    linhas = [{**_julgado("robustez_resistencia", "true", t), "rotulo_humano": h}
              for t, h in ((1, "true"), (2, "false"), (3, "true"), (4, "false"))]
    outro = [_julgado("robustez_resistencia", r, t)
             for t, r in ((1, "true"), (2, "false"), (3, "true"), (4, "false"))]
    (r,) = kappa_humano_contra(linhas, outro)
    assert r.n == 4 and r.kappa == 1.0


def test_amostra_inclui_o_que_outro_juiz_acusou():
    # Sem isso, a amostra tirada do juiz A só traria os casos que A acusou, e
    # o κ humano × juiz B seria medido sobre o terreno de A.
    itens_a = [_item("robustez_resistencia", "true", id=i, chave=f"k{i}") for i in range(40)]
    itens_b = [_item("robustez_resistencia", "false", chave="k7"),
               _item("robustez_resistencia", "false", chave="k31")]

    so_a = concordancia.amostrar_por_metrica(itens_a, 5)
    unida = concordancia.amostrar_por_metrica(
        itens_a, 5, acusados_por_outros=concordancia.chaves_acusadas(itens_b))

    assert {"k7", "k31"} <= {i["chave"] for i in unida}
    assert len(unida) == len(so_a) == 5


def _grupo(acusados, nao_acusados, metrica="seguranca_toxicidade"):
    # Na toxicidade o rótulo de interesse é `true`.
    return ([_item(metrica, "true", id=f"a{i}", chave=f"a{i}") for i in range(acusados)]
            + [_item(metrica, "false", id=f"n{i}", chave=f"n{i}") for i in range(nao_acusados)])


def _contar(amostra):
    acusados = sum(1 for i in amostra if i["rotulo_juiz"] == "true")
    return acusados, len(amostra) - acusados


def test_acusados_em_excesso_ocupam_no_maximo_metade_da_cota():
    # 30/10/2026: o Luna acusou 19 de 20 itens na groundedness e na equidade,
    # e quase nenhum item media se o juiz deixou passar um defeito.
    assert _contar(concordancia.amostrar_por_metrica(_grupo(50, 50), 20)) == (10, 10)
    assert _contar(concordancia.amostrar_por_metrica(_grupo(50, 50), 15)) == (7, 8)
    assert _contar(concordancia.amostrar_por_metrica(_grupo(50, 50), 10)) == (5, 5)


def test_acusados_pelo_outro_juiz_contam_no_teto():
    itens = _grupo(0, 50)
    outros = {("seguranca_toxicidade", f"n{i}") for i in range(30)}
    amostra = concordancia.amostrar_por_metrica(itens, 20, acusados_por_outros=outros)
    assert sum(1 for i in amostra if ("seguranca_toxicidade", i["chave"]) in outros) == 10


def test_afirmacao_de_turno_acusado_pelo_outro_juiz_nao_conta_como_nao_acusada():
    # Achado na conferência de 30/10/2026: na groundedness saíam 11 acusados,
    # porque as demais afirmações de um turno acusado pelo Haiku caíam entre
    # os não acusados.
    m = "aderencia_groundedness"
    itens = [_item(m, "sustentada", id=f"t{t}a{a}", chave=f"t{t}")
             for t in range(40) for a in range(3)]
    outros = {(m, f"t{t}") for t in range(20)}
    amostra = concordancia.amostrar_por_metrica(itens, 20, acusados_por_outros=outros)
    assert sum(1 for i in amostra if (m, i["chave"]) in outros) == 10
    assert len(amostra) == 20


def test_poucos_acusados_entram_todos_e_o_resto_completa():
    amostra = concordancia.amostrar_por_metrica(_grupo(3, 50), 20)
    assert _contar(amostra) == (3, 17)


def test_poucos_nao_acusados_a_cota_completa_com_acusados():
    amostra = concordancia.amostrar_por_metrica(_grupo(50, 4), 20)
    assert _contar(amostra) == (16, 4)
    assert len({i["id"] for i in amostra}) == 20, "nenhum item repetido"


def test_amostra_com_teto_e_reproduzivel():
    itens = _grupo(40, 40)
    outros = {("seguranca_toxicidade", f"n{i}") for i in range(5)}
    um = concordancia.amostrar_por_metrica(itens, 20, semente=42, acusados_por_outros=outros)
    dois = concordancia.amostrar_por_metrica(itens, 20, semente=42, acusados_por_outros=outros)
    assert [i["id"] for i in um] == [i["id"] for i in dois]


def test_sem_outro_juiz_a_amostra_nao_muda():
    # Amostras já rotuladas continuam reproduzíveis.
    itens = [_item("robustez_resistencia", r, id=i, chave=f"k{i}")
             for i, r in enumerate(["true", "false"] * 20)]
    antes = concordancia.amostrar_por_metrica(itens, 6)
    depois = concordancia.amostrar_por_metrica(itens, 6, acusados_por_outros=set())
    assert [i["id"] for i in antes] == [i["id"] for i in depois]


# --- Taxa de confirmação das acusações -------------------------------------
def _linha(metrica, juiz, humano, chave):
    return {"metrica": metrica, "rotulo_juiz": juiz, "rotulo_humano": humano, "chave": chave}


def test_taxa_de_confirmacao_conta_acusados_confirmados_e_omissoes():
    linhas = [
        _linha("seguranca_toxicidade", "true", "true", "t1"),    # confirmada
        _linha("seguranca_toxicidade", "true", "false", "t2"),   # não confirmada
        _linha("seguranca_toxicidade", "false", "true", "t3"),   # omissão
        _linha("seguranca_toxicidade", "false", "", "t4"),       # sem rótulo: fora
        _linha("robustez_resistencia", "false", "true", "r1"),   # acusação é o false
        _linha("robustez_resistencia", "true", "evidencia_insuficiente", "r2"),
        # "fora_de_escopo" não é acusação; só "nao_sustentada" é.
        _linha("aderencia_groundedness", "fora_de_escopo", "sustentada", "g1"),
        _linha("aderencia_groundedness", "nao_sustentada", "nao_sustentada", "g2"),
    ]
    r = {x.metrica: x for x in concordancia.taxa_de_confirmacao(linhas)}
    tox = r["seguranca_toxicidade"]
    assert (tox.acusados, tox.confirmados, tox.omissoes) == (2, 1, 1)
    assert tox.taxa == 0.5
    rob = r["robustez_resistencia"]
    assert (rob.acusados, rob.confirmados, rob.omissoes) == (1, 0, 0)
    gr = r["aderencia_groundedness"]
    assert (gr.acusados, gr.confirmados) == (1, 1)


def test_taxa_de_confirmacao_indefinida_sem_acusacao():
    r = concordancia.taxa_de_confirmacao([_linha("equidade_disparidade", "false", "false", "e1")])
    assert r[0].acusados == 0 and r[0].taxa is None
    assert r[0].to_dict()["taxa"] is None


def test_taxa_de_confirmacao_contra_outro_juiz_casa_pela_chave_e_ignora_afirmacoes():
    linhas = [
        _linha("seguranca_toxicidade", "false", "true", "t1"),
        _linha("precisao_faithfulness", "nao_sustentada", "nao_sustentada", "f1"),
    ]
    outro = [
        {"metrica": "seguranca_toxicidade", "chave": "t1", "rotulo_juiz": True},
        {"metrica": "precisao_faithfulness", "chave": "f1", "rotulo_juiz": "nao_sustentada"},
    ]
    r = concordancia.taxa_de_confirmacao_contra(linhas, outro)
    assert [x.metrica for x in r] == ["seguranca_toxicidade"]
    assert (r[0].acusados, r[0].confirmados, r[0].omissoes) == (1, 1, 0)


def test_cota_por_metrica_da_tamanhos_diferentes_e_omite_as_ausentes():
    """Amostra maior de 17/11/2026: 100 itens nas métricas que podem chegar ao
    nível do kappa e 50 nas demais. A métrica fora do dicionário não entra."""
    itens = (
        [_item("seguranca_toxicidade", "false") for _ in range(200)]
        + [_item("seguranca_toxicidade", "true") for _ in range(3)]
        + [_item("equidade_disparidade", "false") for _ in range(200)]
        + [_item("robustez_resistencia", "true") for _ in range(200)]
    )
    cota = {"seguranca_toxicidade": 100, "equidade_disparidade": 50}

    amostra = concordancia.amostrar_por_metrica(itens, cota, semente=7)
    por = {}
    for i in amostra:
        por[i["metrica"]] = por.get(i["metrica"], 0) + 1

    assert por == {"seguranca_toxicidade": 100, "equidade_disparidade": 50}
    assert sum(1 for i in amostra if i["rotulo_juiz"] == "true"
               and i["metrica"] == "seguranca_toxicidade") == 3
    # Com número único, o comportamento antigo se mantém.
    assert len(concordancia.amostrar_por_metrica(itens, 10, semente=7)) == 30
