"""Inventário dos estímulos que a bateria pode executar.

Derivado AO VIVO dos arquivos em `tests/`, e não lido de
`tests/inventario_casos.json`. O arquivo é gerado por
`scripts/gerar_inventario.py` e pode estar velho — basta alguém acrescentar um
estímulo e esquecer de rodar o script. A tela mostraria um inventário que não
corresponde ao que a bateria de fato executaria, e esse é justamente o tipo de
divergência silenciosa que o próprio script foi criado para eliminar.

A varredura reaproveita `coletar()` daquele script em vez de reimplementar:
duplicar a regra de "onde mora cada via" traria de volta o mesmo problema, um
nível acima.
"""
from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from types import ModuleType

import config

# Campos que já vão no índice; não precisam ser repetidos dentro de `conteudo`.
_CAMPOS_DO_INDICE = {"id", "descricao", "categorias_alvo"}


def _carregar_gerador() -> ModuleType:
    """Importa scripts/gerar_inventario.py sem mexer no sys.path global.

    `scripts/` não é um pacote (não tem __init__.py), então o import normal não
    o alcança; carregar pelo caminho evita ter que transformá-lo em pacote só
    por causa da API.
    """
    caminho = config.RAIZ / "scripts" / "gerar_inventario.py"
    spec = importlib.util.spec_from_file_location("gerar_inventario", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@lru_cache(maxsize=1)
def _conteudo_por_id() -> dict[str, dict]:
    """Mapeia id do estímulo -> corpo específico do formato dele.

    O que vai em `conteudo` muda por via, e é justamente o que a tela precisa
    mostrar: a entrada fixa de um caso, a lista de mensagens de um roteiro, o
    perfil de uma persona.
    """
    mapa: dict[str, dict] = {}
    for diretorio, padrao in (
        (config.RAIZ / "tests" / "casos", "*.json"),
        (config.RAIZ / "tests" / "roteiros", "*.json"),
        (config.RAIZ / "tests" / "personas", "persona_*.json"),
    ):
        for arquivo in sorted(diretorio.glob(padrao)):
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            for estimulo in (dados if isinstance(dados, list) else [dados]):
                mapa[estimulo["id"]] = {
                    k: v for k, v in estimulo.items() if k not in _CAMPOS_DO_INDICE
                }
    return mapa


def repeticoes(estimulo_ou_corpo: dict, override: int | None = None) -> int:
    """Quantas vezes este estímulo roda, pela MESMA precedência do runner.

    `scripts/rodar_bateria.py` resolve assim:

        args.repeticoes or est.get("n_repeticoes") or config.N_EXECUCOES_PADRAO

    Replicar isso aqui não é preciosismo: hoje TODOS os estímulos trazem
    `n_repeticoes: null`, ou seja, todos caem no padrão. Um cálculo ingênuo
    (`.get(..., 1)`) daria 1 repetição por estímulo e mostraria uma estimativa
    de custo várias vezes menor que a real, bem na tela em que alguém decide
    gastar.
    """
    return (
        override
        or estimulo_ou_corpo.get("n_repeticoes")
        or config.N_EXECUCOES_PADRAO
    )


def catalogo() -> list[dict]:
    """Todos os estímulos, com índice e corpo, na ordem do inventário."""
    gerador = _carregar_gerador()
    conteudos = _conteudo_por_id()
    saida = []
    for entrada in gerador.coletar():
        corpo = conteudos.get(entrada["id"], {})
        saida.append({
            **entrada,
            # O valor declarado no arquivo (quase sempre null) e o efetivo,
            # já resolvido. A tela precisa do segundo; quem edita o estímulo
            # precisa enxergar o primeiro.
            "n_repeticoes_declarado": corpo.get("n_repeticoes"),
            "n_repeticoes": repeticoes(corpo),
            "conteudo": corpo,
        })
    return saida


def invalidar_cache() -> None:
    """Esquece o conteúdo lido, para reler os arquivos do disco."""
    _conteudo_por_id.cache_clear()


def episodios(
    estimulos: list[dict], n_modelos: int = 1, override: int | None = None
) -> int:
    """Quantos episódios uma rodada custaria: soma das repetições × modelos.

    É o número que precisa aparecer ANTES de alguém confirmar uma bateria —
    cada episódio é pelo menos uma chamada de API paga, e uma rodada completa
    leva dezenas de minutos. `override` corresponde ao `--repeticoes` da linha
    de comando, que vence o valor de cada estímulo.
    """
    total = sum(repeticoes(e, override) for e in estimulos)
    return total * max(1, n_modelos)
