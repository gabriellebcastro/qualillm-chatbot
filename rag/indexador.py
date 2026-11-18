"""Fragmentação e indexação da base de políticas para o RAG.

Os documentos .md de rag/politicas/ são quebrados em fragmentos, cada um
associado à seção (título) de onde veio, e transformados em embeddings por um
modelo multilíngue local (sentence-transformers). Os embeddings são
normalizados, de modo que a similaridade por cosseno vira um simples produto
escalar (ver recuperador.py).

Os embeddings são cacheados em disco (indexados por um hash dos documentos +
nome do modelo), para não recalcular a cada execução.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DIR_POLITICAS = Path(__file__).resolve().parent / "politicas"
CAMINHO_CACHE = Path(__file__).resolve().parent / ".cache_indice.npz"


@dataclass(frozen=True)
class Fragmento:
    texto: str      # conteúdo do fragmento (com o título da seção como contexto)
    origem: str     # ex.: "parcelamento.md#Cálculo das parcelas"


def fragmentar_documento(caminho: Path) -> list[Fragmento]:
    """Quebra um .md em fragmentos, um por parágrafo, com o título da seção."""
    fragmentos: list[Fragmento] = []
    titulo_atual = ""
    bloco: list[str] = []

    def descarregar() -> None:
        texto = " ".join(l.strip() for l in bloco).strip()
        bloco.clear()
        if not texto:
            return
        prefixo = f"[{titulo_atual}] " if titulo_atual else ""
        fragmentos.append(
            Fragmento(texto=prefixo + texto, origem=f"{caminho.name}#{titulo_atual}")
        )

    for linha in caminho.read_text(encoding="utf-8").splitlines():
        stripped = linha.strip()
        if stripped.startswith("#"):
            descarregar()
            titulo_atual = stripped.lstrip("#").strip()
        elif stripped.startswith(">"):
            continue  # ignora blocos de aviso/citação
        elif not stripped:
            # Parágrafo que termina em ":" anuncia a lista seguinte ("respeitadas
            # duas condições:"); separado dela, o fragmento chegava ao modelo sem
            # as condições que anunciava.
            if bloco and bloco[-1].rstrip().endswith(":"):
                continue
            descarregar()
        else:
            bloco.append(linha)
    descarregar()
    return fragmentos


def carregar_fragmentos(dir_politicas: Path = DIR_POLITICAS) -> list[Fragmento]:
    """Fragmenta todos os .md de um diretório de políticas, em ordem alfabética."""
    fragmentos: list[Fragmento] = []
    for caminho in sorted(dir_politicas.glob("*.md")):
        fragmentos.extend(fragmentar_documento(caminho))
    return fragmentos


def _hash(fragmentos: list[Fragmento], modelo: str) -> str:
    """Hash do conteúdo dos fragmentos + nome do modelo (chave do cache)."""
    h = hashlib.sha256(modelo.encode("utf-8"))
    for f in fragmentos:
        h.update(f.texto.encode("utf-8"))
    return h.hexdigest()


def construir_indice(modelo: str) -> tuple[list[Fragmento], np.ndarray]:
    """Retorna (fragmentos, matriz de embeddings normalizados) usando cache."""
    fragmentos = carregar_fragmentos()
    chave = _hash(fragmentos, modelo)

    if CAMINHO_CACHE.exists():
        cache = np.load(CAMINHO_CACHE, allow_pickle=True)
        if str(cache["chave"]) == chave:
            return fragmentos, cache["embeddings"]

    embeddings = _embedar([f.texto for f in fragmentos], modelo)
    np.savez(CAMINHO_CACHE, chave=chave, embeddings=embeddings)
    return fragmentos, embeddings


# Cache do modelo carregado: evita recarregar o SentenceTransformer do disco a
# cada chamada (isso era o principal gargalo de latência por turno).
_modelos: dict[str, object] = {}


def _obter_modelo(modelo: str):
    """Carrega o SentenceTransformer uma vez e reaproveita nas chamadas seguintes."""
    if modelo not in _modelos:
        from sentence_transformers import SentenceTransformer

        _modelos[modelo] = SentenceTransformer(modelo)
    return _modelos[modelo]


def _embedar(textos: list[str], modelo: str) -> np.ndarray:
    """Gera embeddings normalizados reusando o modelo em memória."""
    vetores = _obter_modelo(modelo).encode(
        textos, normalize_embeddings=True, convert_to_numpy=True
    )
    return vetores.astype(np.float32)


def embedar_consulta(texto: str, modelo: str) -> np.ndarray:
    """Embedding normalizado de uma consulta (mesma normalização do índice)."""
    return _embedar([texto], modelo)[0]
