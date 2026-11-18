"""Recalcula o grau de certeza de relatórios já gravados, sem chamar juiz.

Existe porque o método do intervalo mudou (Wilson → Wilson modificado nas
bordas, Brown, Cai e DasGupta 2001, §4.1.1) depois de uma avaliação já ter
gravado relatórios. O intervalo depende só do valor, do n de estímulos e do
limiar, que estão no próprio relatório; refazer a avaliação inteira para
isso gastaria crédito à toa.

O status e o valor não mudam — a certeza nunca muda o status. A procedência
ganha `certeza_recalculada` com o método e o instante, para que o relatório
não esconda que esse campo foi refeito depois da coleta.

Uso:
    python scripts/recalcular_certeza.py                 # todos em logs/
    python scripts/recalcular_certeza.py logs/relatorio__seguranca__X.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from eval import relatorio  # noqa: E402

METODO = "wilson_modificado_95"


def _leitura(inferior: float, superior: float, limiar: float | None) -> str | None:
    # Mesma regra de `Secao.certeza`.
    if limiar is None:
        return None
    if inferior >= limiar:
        return "acima_do_limiar"
    if superior < limiar:
        return "abaixo_do_limiar"
    return "inconclusivo"


def recalcular(caminho: Path) -> int:
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    alteradas = 0
    for bloco in conteudo.get("categorias") or []:
        for m in bloco.get("metricas") or []:
            c = m.get("certeza")
            if not c or m.get("valor") is None or not c.get("n"):
                continue
            # Mesma regra de `Secao.certeza`: o menor entre observações e
            # estímulos (na equidade, os grupos).
            n = min(x for x in (m.get("n_estimulos"), m.get("n_amostras"), c["n"]) if x)
            inferior, superior = relatorio.intervalo_wilson_modificado(m["valor"], n)
            m["certeza"] = {
                "metodo": METODO,
                "n": n,
                "intervalo": [round(inferior, 4), round(superior, 4)],
                "leitura": _leitura(inferior, superior, m.get("limiar")),
            }
            alteradas += 1
    if alteradas:
        proc = conteudo.setdefault("procedencia", {})
        proc["certeza_recalculada"] = {
            "metodo": METODO,
            "em": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        }
        caminho.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return alteradas


def main(argv: list[str]) -> int:
    caminhos = [Path(a) for a in argv] or sorted(
        (RAIZ / "logs").glob("relatorio__*.json")
    )
    for caminho in caminhos:
        print(f"{caminho.name}: {recalcular(caminho)} métrica(s) recalculada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
