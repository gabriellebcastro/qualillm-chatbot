"""Nada sobrescreve nada: uma rodada nova soma-se à anterior.

A bateria nova é gravada nos mesmos arquivos da antiga (um por estímulo e
modelo). Estes testes garantem que ela acrescenta, com execuções de id novo,
e que a saída de terminal de cada rodada fica guardada.
"""
import json
import os
import time

from bot import ResultadoTurno
from instrumentacao.logger import Instrumentador


def _resultado(texto: str) -> ResultadoTurno:
    return ResultadoTurno(
        mensagem_usuario="oi", resposta_final=texto, trechos_rag=[],
        consultas_dados=[], prompt_completo=[], resposta_bruta=texto,
        modelo="m", provedor="p", parametros={}, latencia_s=0.0,
    )


def _linhas(caminho):
    return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_rodada_nova_acrescenta_sem_apagar_a_antiga(tmp_path):
    Instrumentador("bateria__x", 1, dir_logs=tmp_path).registrar(_resultado("antiga"))
    Instrumentador("bateria__x", 2, dir_logs=tmp_path).registrar(_resultado("nova"))
    linhas = _linhas(tmp_path / "bateria__x.jsonl")
    assert [l["resposta_final"] for l in linhas] == ["antiga", "nova"]


def test_execucao_nova_nunca_reusa_id_ja_gravado(tmp_path, monkeypatch):
    # Com "refazer tudo do zero" o contador volta a 1; o id precisa continuar
    # depois do maior já gravado, senão duas execuções se fundiriam.
    import config
    from scripts import rodar_bateria
    monkeypatch.setattr(config, "DIR_LOGS", tmp_path)
    for i in (1, 2, 3):
        Instrumentador("bateria__x", i, dir_logs=tmp_path).registrar(_resultado("antiga"))
    assert rodar_bateria.proximo_execucao_id("bateria__x", 1) == 4


def test_saida_de_terminal_da_rodada_anterior_fica_guardada(tmp_path, monkeypatch):
    from api import saidas
    monkeypatch.setattr(saidas, "DIR_SAIDAS", tmp_path / "saidas")
    caminho = tmp_path / ".bateria_saida.log"
    caminho.write_text("rodada 1", encoding="utf-8")
    primeira = saidas.guardar_anterior(caminho)
    caminho.write_text("rodada 2", encoding="utf-8")
    os.utime(caminho, (time.time(), os.path.getmtime(primeira)))  # mesmo instante
    segunda = saidas.guardar_anterior(caminho)
    assert primeira != segunda
    assert primeira.read_text(encoding="utf-8") == "rodada 1"
    assert segunda.read_text(encoding="utf-8") == "rodada 2"


def test_metadados_da_rodada_anterior_ficam_guardados(tmp_path, monkeypatch):
    from api import saidas
    monkeypatch.setattr(saidas, "DIR_SAIDAS", tmp_path / "saidas")
    caminho = tmp_path / ".bateria_rodada.json"
    saidas.gravar_rodada(caminho, {"comando": "a"})
    copia = saidas.guardar_anterior(caminho)
    saidas.gravar_rodada(caminho, {"comando": "b"})
    assert copia.suffix == ".json"
    assert json.loads(copia.read_text(encoding="utf-8"))["comando"] == "a"
    assert saidas.ler_rodada(caminho)["comando"] == "b"


def _isolar(modulo, tmp_path, monkeypatch):
    """Simula a API recém-reiniciada: nada em memória, só o disco."""
    monkeypatch.setattr(modulo, "CAMINHO_SAIDA", tmp_path / ".saida.log")
    monkeypatch.setattr(modulo, "CAMINHO_RODADA", tmp_path / ".rodada.json")
    monkeypatch.setattr(modulo, "_rodada", None)
    monkeypatch.setattr(modulo, "_processo", None)


def test_status_da_bateria_sobrevive_a_reinicio_da_api(tmp_path, monkeypatch):
    from api import bateria, saidas
    _isolar(bateria, tmp_path, monkeypatch)
    monkeypatch.setattr(bateria, "_episodios_concluidos", lambda desde=None: {"k1", "k2"})
    (tmp_path / ".saida.log").write_text("Episódios executados: 2\n", encoding="utf-8")
    saidas.gravar_rodada(tmp_path / ".rodada.json", {
        "iniciado_em": "2026-10-28T16:00:00+00:00", "parametros": {}, "comando": "x",
        "simulador": "s", "pid": 1, "interrompida": False,
        "plano_inicial": {"chaves": ["k1", "k2"], "episodios_restantes": 2,
                          "episodios_ja_feitos": 0, "recomecar": True},
    })
    s = bateria.status()
    assert s["houve_rodada"] and not s["rodando"]
    assert s["progresso"]["feitos"] == 2
    assert s["saida"] == ["Episódios executados: 2"]


def _episodio(caminho, execucao_id, rep, instante):
    """Um turno e o marcador de conclusão, como o runner grava."""
    meta = {"via": "roteiro", "origem_id": "x", "modelo_bot": "p:m", "repeticao": rep}
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps({"sessao_id": "bateria__x", "execucao_id": execucao_id, "turno_id": 1,
                            "timestamp": instante, "meta": meta}) + "\n")
        f.write(json.dumps({"tipo": "episodio_concluido", "sessao_id": "bateria__x",
                            "execucao_id": execucao_id, "timestamp": instante, "meta": meta}) + "\n")


def test_barra_de_refazer_do_zero_comeca_em_zero(tmp_path, monkeypatch):
    # Defeito de 28/10: a rodada nova repete as chaves da anterior, que já
    # estão nos logs, e a barra ficava em 100% a rodada inteira.
    import config
    from api import bateria, saidas
    _isolar(bateria, tmp_path, monkeypatch)
    monkeypatch.setattr(config, "DIR_LOGS", tmp_path)
    log = tmp_path / "bateria__x.jsonl"
    _episodio(log, 1, 1, "2026-10-27T01:00:00+00:00")
    _episodio(log, 2, 2, "2026-10-27T01:01:00+00:00")
    chaves = ["roteiro|x|p:m|rep1", "roteiro|x|p:m|rep2"]
    saidas.gravar_rodada(tmp_path / ".rodada.json", {
        "iniciado_em": "2026-10-28T16:00:00+00:00", "parametros": {}, "comando": "x",
        "pid": 1, "interrompida": False,
        "plano_inicial": {"chaves": chaves, "episodios_restantes": 2,
                          "episodios_ja_feitos": 0, "recomecar": True},
    })
    assert bateria.status()["progresso"]["feitos"] == 0
    _episodio(log, 3, 1, "2026-10-28T16:05:00+00:00")
    assert bateria.status()["progresso"]["feitos"] == 1


def test_rodada_sem_metadados_mostra_a_saida_gravada(tmp_path, monkeypatch):
    # Rodadas iniciadas antes de os metadados irem para disco.
    from api import avaliacao, bateria
    for modulo in (bateria, avaliacao):
        _isolar(modulo, tmp_path, monkeypatch)
        (tmp_path / ".saida.log").write_text("fim da rodada\n", encoding="utf-8")
        s = modulo.status()
        assert s["houve_rodada"] and s["sem_metadados"]
        assert s["saida"] == ["fim da rodada"]


def test_execucoes_de_rodadas_diferentes_no_mesmo_log_ficam_separadas():
    # A rodada nova acrescenta ao log do estímulo; a tela precisa mostrar as duas.
    from api.main import _rodadas_do_log
    turnos = [
        {"execucao_id": 1, "timestamp": "2026-10-27T00:51:00+00:00"},
        {"execucao_id": 2, "timestamp": "2026-10-27T00:52:00+00:00"},
        {"execucao_id": 3, "timestamp": "2026-10-28T16:24:00+00:00"},
        {"execucao_id": 4, "timestamp": "2026-10-28T16:25:00+00:00"},
    ]
    rodadas = _rodadas_do_log(turnos)
    assert [r["execucoes"] for r in rodadas] == [[1, 2], [3, 4]]


def test_saida_guardada_so_e_lida_pelo_nome_de_copia(tmp_path, monkeypatch):
    from api import saidas
    monkeypatch.setattr(saidas, "DIR_SAIDAS", tmp_path)
    (tmp_path / "bateria_saida__20261027T015300Z.log").write_text("ok\nResumo\n", encoding="utf-8")
    assert [i["arquivo"] for i in saidas.listar("bateria")] == ["bateria_saida__20261027T015300Z.log"]
    assert saidas.ler("bateria", "bateria_saida__20261027T015300Z.log") == ["ok", "Resumo"]
    assert saidas.ler("avaliacao", "bateria_saida__20261027T015300Z.log") is None
    assert saidas.ler("bateria", "../.env") is None
