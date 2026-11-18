"""Roda os avaliadores sobre os logs e gera o relatório consolidado.

    python scripts/avaliar.py [--tom] [--log <arquivo.jsonl>] [--saida <prefixo>]

Sem --log, avalia todas as conversas manuais de logs/manuais/ (nunca os
logs da bateria, que ficam em logs/). A fidelidade
(determinística) roda sempre; --tom adiciona o juiz de tom (requer
ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from eval import AvaliadorTom, relatorio  # noqa: E402
from instrumentacao import carregar_turnos  # noqa: E402


def _arg(nome: str, padrao: str | None = None) -> str | None:
    """Lê o valor de um argumento de linha de comando tipo `--nome valor`."""
    if nome in sys.argv:
        i = sys.argv.index(nome)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return padrao


def main() -> None:
    """Carrega os logs, roda os avaliadores e grava o relatório (CSV+JSON)."""
    incluir_tom = "--tom" in sys.argv
    log = _arg("--log")
    prefixo = _arg("--saida", str(config.DIR_RELATORIOS_MANUAIS / "relatorio"))

    if log:
        arquivos = [Path(log)]
    else:
        arquivos = [
            p for p in sorted(config.DIR_LOGS_MANUAIS.glob("*.jsonl"))
        ]
    if not arquivos:
        print("Nenhuma conversa em logs/manuais/. Rode uma conversa primeiro.")
        return

    turnos: list[dict] = []
    for arquivo in arquivos:
        turnos.extend(carregar_turnos(arquivo))
    print(f"Avaliando {len(turnos)} turno(s) de {len(arquivos)} arquivo(s).")

    avaliador_tom = AvaliadorTom() if incluir_tom else None
    if incluir_tom:
        print(f"Juiz de tom: {config.JUIZ_MODELO} (temperatura {config.JUIZ_TEMPERATURA})")

    linhas = relatorio.gerar_relatorio(turnos, incluir_tom, avaliador_tom)
    resumo = relatorio.calcular_resumo(linhas, incluir_tom)

    csv_path = Path(f"{prefixo}.csv")
    json_path = Path(f"{prefixo}.json")
    relatorio.escrever_csv(linhas, csv_path)
    relatorio.escrever_json(linhas, json_path, resumo=resumo)

    # Resumo no terminal (os mesmos números gravados em resumo, no JSON)
    print("\n--- Resumo ---")
    print(f"Turnos avaliados: {resumo['total_turnos']}")
    print(f"Fidelidade OK: {resumo['fidelidade_ok']}/{resumo['total_turnos']}")
    if incluir_tom:
        print(
            f"Juiz — taxa de falha de parsing: {resumo['tom_falhas_parsing']}/"
            f"{resumo['total_turnos']} ({resumo['tom_taxa_falha_parsing']:.1%})"
        )
        if resumo["tom_nota_media"] is not None:
            print(
                f"Tom — nota média: {resumo['tom_nota_media']:.2f} "
                f"(adequados: {resumo['tom_adequados']}/{resumo['total_turnos']})"
            )
    print(f"\nRelatório: {csv_path}  e  {json_path}")


if __name__ == "__main__":
    main()
