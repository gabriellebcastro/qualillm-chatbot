"""Testes de fumaça do servidor local (api/main.py).

Rodam num clone limpo: sem logs reais e sem chave de API. Toda rota lê de um
diretório temporário com a fixture de `tests/fixtures/api_fumaca/logs/`, que
reduz os arquivos reais (um log de bateria, um relatório, um arquivo de
julgamentos e uma amostra de κ) e troca o texto por um fictício, mantendo a
forma. Ficam fora as rotas que chamam modelo ou disparam processo (POST de
bateria, avaliação, sessões, conversa e tom) e os DELETE; o PUT de limiares
grava numa cópia temporária.
"""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
from api import avaliacao, bateria, main, saidas
from eval import relatorio

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "api_fumaca" / "logs"
BATERIA = "bateria__caso_injecao_001__deepseek-deepseek-v4-flash"
RELATORIO = "relatorio__seguranca__20261104T051306Z"
JULGAMENTOS = "julgamentos__geral__openai-gpt-6-luna__20261104T051306Z.jsonl"
AMOSTRA = "kappa__amostra__20261031T013350Z.csv"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    shutil.copytree(FIXTURE, logs)
    manuais = logs / "manuais"
    manuais.mkdir()
    monkeypatch.setattr(config, "DIR_LOGS", logs)
    monkeypatch.setattr(config, "DIR_LOGS_MANUAIS", manuais)
    monkeypatch.setattr(config, "DIR_RELATORIOS_MANUAIS", manuais / "relatorios")
    # Caminhos que os módulos fixam na importação, a partir do DIR_LOGS real.
    monkeypatch.setattr(saidas, "DIR_SAIDAS", logs / "saidas")
    for modulo in (bateria, avaliacao):
        monkeypatch.setattr(modulo, "CAMINHO_SAIDA", logs / modulo.CAMINHO_SAIDA.name)
        monkeypatch.setattr(modulo, "CAMINHO_RODADA", logs / modulo.CAMINHO_RODADA.name)
    # Limiares: cópia temporária do arquivo, e o dicionário em memória
    # restaurado no fim (o PUT o atualiza no lugar).
    limiares = tmp_path / "limiares.json"
    if relatorio.CAMINHO_LIMIARES.exists():
        shutil.copy(relatorio.CAMINHO_LIMIARES, limiares)
    monkeypatch.setattr(relatorio, "CAMINHO_LIMIARES", limiares)
    monkeypatch.setattr(relatorio, "LIMIARES", dict(relatorio.LIMIARES))
    return TestClient(main.app)


def _ok(resposta):
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_saude_responde_sem_chave(cliente):
    corpo = _ok(cliente.get("/api/saude"))
    for papel in ("bot", "juiz", "simulador"):
        assert {"provedor", "modelo", "tem_chave"} <= set(corpo[papel])


def test_visao_geral_conta_a_fixture(cliente):
    corpo = _ok(cliente.get("/api/visao-geral"))
    assert corpo["contadores"]["execucoes_bateria"] == 1
    assert corpo["contadores"]["relatorios"] == 1
    assert isinstance(corpo["categorias"], list) and corpo["categorias"]


def test_massa_e_estimulos(cliente):
    massa = _ok(cliente.get("/api/massa"))
    assert massa["arquivo"] == "dados/seed.json"
    estimulos = _ok(cliente.get("/api/estimulos"))
    assert estimulos["total"] == len(estimulos["estimulos"]) > 0
    assert any(e["id"] == "caso_injecao_001" for e in estimulos["estimulos"])


def test_prompts_lista_e_detalhe(cliente):
    lista = _ok(cliente.get("/api/prompts"))
    assert lista
    primeiro = lista[0]["id"]
    detalhe = _ok(cliente.get(f"/api/prompts/{primeiro}"))
    assert detalhe["id"] == primeiro


def test_relatorios_lista_e_detalhe(cliente):
    lista = _ok(cliente.get("/api/relatorios"))
    assert [r["nome"] for r in lista] == [RELATORIO]
    detalhe = _ok(cliente.get(f"/api/relatorios/{RELATORIO}"))
    assert detalhe["_categoria"] == "seguranca"
    assert detalhe["categorias"][0]["metricas"]


def test_execucoes(cliente):
    lista = _ok(cliente.get("/api/execucoes"))
    assert [e["nome"] for e in lista] == [BATERIA]


def test_kappa_amostras_itens_e_julgamentos(cliente):
    amostras = _ok(cliente.get("/api/kappa"))
    assert [a["nome"] for a in amostras] == [AMOSTRA]
    itens = _ok(cliente.get(f"/api/kappa/{AMOSTRA}"))
    assert itens["itens"] and all("rotulo_juiz" not in i for i in itens["itens"]), \
        "o veredito do juiz não chega à tela de rotulagem"
    pendentes = _ok(cliente.get(f"/api/kappa/{AMOSTRA}", params={"apenas_pendentes": True}))
    assert len(pendentes["itens"]) == 1
    julgamentos = _ok(cliente.get("/api/julgamentos"))
    assert [j["nome"] for j in julgamentos] == [JULGAMENTOS]


def test_comparacao_de_juizes(cliente):
    corpo = _ok(cliente.get("/api/comparacao-juizes", params={"a": JULGAMENTOS, "b": JULGAMENTOS}))
    assert corpo["metricas"]
    assert all(m["divergentes"] == 0 for m in corpo["metricas"])


def test_saidas_sem_rodada_anterior(cliente):
    for tipo in ("bateria", "avaliacao"):
        assert _ok(cliente.get(f"/api/saidas/{tipo}")) == {"saidas": []}


def test_limiares_leitura_e_gravacao_na_copia(cliente):
    corpo = _ok(cliente.get("/api/limiares"))
    assert corpo["limiar_juiz_padrao"] == 0.80
    assert {m["metrica"] for m in corpo["metricas"]} == set(relatorio.LIMIARES_PADRAO)
    novo = _ok(cliente.put("/api/limiares", json={"robustez_resistencia": 0.9}))
    valor = {m["metrica"]: m["valor"] for m in novo["metricas"]}["robustez_resistencia"]
    assert valor == 0.9
    assert cliente.put("/api/limiares", json={"inexistente": 0.5}).status_code == 400


def test_plano_da_bateria_nao_executa(cliente):
    corpo = _ok(cliente.post("/api/bateria/plano",
                             json={"origem_id": "caso_injecao_001", "repeticoes": 1}))
    assert isinstance(corpo, dict) and corpo


def test_plano_da_avaliacao_seleciona_a_fixture(cliente):
    corpo = _ok(cliente.post("/api/avaliacao/plano", json={"categorias": []}))
    assert corpo["arquivos"] == 1
    assert corpo["turnos"] > 0
