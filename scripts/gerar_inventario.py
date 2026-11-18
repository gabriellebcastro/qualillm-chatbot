"""Gera tests/inventario_casos.json a partir dos arquivos de estímulo.

    python scripts/gerar_inventario.py

O inventário é o índice único de tudo que a bateria pode executar: cada `id`
corresponde ao `meta.origem_id` gravado no log, e é o que liga um resultado
ao caso planejado.

Ele é DERIVADO, nunca escrito à mão. Antes era mantido em paralelo aos
arquivos de estímulo, e os dois divergiram: metade das descrições no
inventário já não batia com a do arquivo de origem. Duplicar um dado que
pode divergir em silêncio é o problema; gerar resolve na raiz.

Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DIR_TESTES = RAIZ / "tests"
CAMINHO_INVENTARIO = DIR_TESTES / "inventario_casos.json"

# Onde procurar cada via, e de que tipo é cada estímulo encontrado ali.
FONTES = (
    ("reinjecao", "caso", DIR_TESTES / "casos", "*.json"),
    ("roteiro", "roteiro", DIR_TESTES / "roteiros", "*.json"),
    ("simulador", "persona", DIR_TESTES / "personas", "persona_*.json"),
)

# Campos copiados do estímulo para o inventário, quando presentes.
#
# `turnos_de_ataque` mora no arquivo do estímulo, ao lado das mensagens que
# ele indexa, e não aqui: um roteiro editado move as mensagens, e a marcação
# precisa estar onde quem edita a vê. Duplicá-la no inventário à mão seria o
# mesmo erro que levou este gerador a existir.
CAMPOS_OPCIONAIS = ("grupo_metamorfico", "turnos_de_ataque")


def _carregar(caminho: Path) -> list[dict]:
    """Lê um arquivo de estímulo — pode conter um objeto ou uma lista deles."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return dados if isinstance(dados, list) else [dados]


def coletar() -> list[dict]:
    """Varre os diretórios de estímulo e monta as entradas do inventário."""
    entradas: list[dict] = []
    for via, tipo, diretorio, padrao in FONTES:
        for arquivo in sorted(diretorio.glob(padrao)):
            relativo = arquivo.relative_to(RAIZ).as_posix()
            for estimulo in _carregar(arquivo):
                entrada = {
                    "id": estimulo["id"],
                    "via": via,
                    "tipo": tipo,
                    "descricao": estimulo.get("descricao", ""),
                    "categorias_alvo": estimulo.get("categorias_alvo", []),
                    "arquivo_origem": relativo,
                    "status": "implementado",
                }
                for campo in CAMPOS_OPCIONAIS:
                    if campo in estimulo:
                        entrada[campo] = estimulo[campo]
                entradas.append(entrada)
    return sorted(entradas, key=lambda e: e["id"])


def main() -> None:
    """Regera o inventário e imprime um resumo por via e por categoria."""
    estimulos = coletar()
    ids = [e["id"] for e in estimulos]
    duplicados = {i for i in ids if ids.count(i) > 1}
    if duplicados:
        raise SystemExit(f"ids duplicados entre arquivos de estímulo: {sorted(duplicados)}")

    inventario = {
        "_aviso": (
            "GERADO por scripts/gerar_inventario.py a partir dos arquivos de "
            "estimulo. Nao edite a mao: edite o arquivo de origem e rode o "
            "script de novo."
        ),
        "versao": "2.0",
        "atualizado_em": date.today().isoformat(),
        "descricao": (
            "Inventario de todos os estimulos executaveis pela bateria "
            "(docs/plano_de_testes.md). Cada 'id' corresponde ao "
            "'meta.origem_id' gravado no log, garantindo rastreabilidade de "
            "todo resultado ate o caso planejado."
        ),
        "estimulos": estimulos,
    }
    CAMINHO_INVENTARIO.write_text(
        json.dumps(inventario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    por_via: dict[str, int] = {}
    por_categoria: dict[str, int] = {}
    for e in estimulos:
        por_via[e["via"]] = por_via.get(e["via"], 0) + 1
        for c in e["categorias_alvo"]:
            por_categoria[c] = por_categoria.get(c, 0) + 1

    print(f"inventario gerado: {len(estimulos)} estimulos")
    print(f"  por via:       {dict(sorted(por_via.items()))}")
    print(f"  por categoria: {dict(sorted(por_categoria.items()))}")


if __name__ == "__main__":
    main()
