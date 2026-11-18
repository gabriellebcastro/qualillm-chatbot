"""Retomada da bateria: episódio interrompido no meio não conta como feito."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from instrumentacao.logger import execucoes_concluidas  # noqa: E402
from rodar_bateria import episodios_concluidos  # noqa: E402


def _turno(execucao_id: int, turno_id: int, rep: int) -> dict:
    return {
        "sessao_id": "bateria__X", "execucao_id": execucao_id, "turno_id": turno_id,
        "mensagem_usuario": "oi", "resposta_final": "olá",
        "meta": {"via": "roteiro", "origem_id": "E1", "modelo_bot": "m", "repeticao": rep},
    }


def _gravar(caminho: Path, registros: list[dict]) -> None:
    caminho.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros),
        encoding="utf-8",
    )


def test_execucao_sem_marcador_nao_conta(tmp_path):
    arquivo = tmp_path / "bateria__X.jsonl"
    _gravar(arquivo, [
        _turno(0, 1, 1), _turno(0, 2, 1),
        {"tipo": "episodio_concluido", "execucao_id": 0},
        _turno(1, 1, 2),  # caiu depois do primeiro turno
    ])
    assert execucoes_concluidas(arquivo) == {0}
    assert episodios_concluidos(tmp_path) == {"roteiro|E1|m|rep1"}


def test_log_anterior_ao_marcador_segue_regra_antiga(tmp_path):
    arquivo = tmp_path / "bateria__X.jsonl"
    _gravar(arquivo, [_turno(0, 1, 1)])
    assert execucoes_concluidas(arquivo) is None
    assert episodios_concluidos(tmp_path) == {"roteiro|E1|m|rep1"}
