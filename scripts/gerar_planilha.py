"""Gera a planilha Excel de avaliações já gravadas, sem chamar juiz.

Uso:
    python scripts/gerar_planilha.py                     # todas as avaliações em logs/
    python scripts/gerar_planilha.py 20261027T202952Z    # uma, pelo instante
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval import planilha  # noqa: E402

DIR_LOGS = RAIZ / "logs"


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    instantes = argv or sorted({
        p.stem.rsplit("__", 1)[-1] for p in DIR_LOGS.glob("relatorio__*.json")
        # Só as da bateria: o nome tem 3 partes (relatorio__categoria__instante).
        if len(p.stem.split("__")) == 3
    })
    for instante in instantes:
        print(planilha.gerar_planilha(DIR_LOGS, instante).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
