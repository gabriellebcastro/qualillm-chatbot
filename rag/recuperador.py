"""Recuperação por similaridade (RAG).

Dada uma consulta, calcula a similaridade por cosseno entre o embedding da
consulta e os embeddings dos fragmentos das políticas, e devolve os mais
relevantes. Como os embeddings são normalizados, cosseno = produto escalar.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import config
from .indexador import Fragmento, construir_indice, embedar_consulta


@dataclass(frozen=True)
class TrechoRecuperado:
    texto: str
    origem: str
    score: float

    def to_dict(self) -> dict:
        """Converte para dict simples (usado na instrumentação/log)."""
        return {"texto": self.texto, "origem": self.origem, "score": self.score}


class RecuperadorRAG:
    def __init__(self, modelo: str | None = None) -> None:
        """Prepara o recuperador; o índice só é construído no 1º `recuperar()`."""
        self.modelo = modelo or config.EMBEDDING_MODELO
        self._fragmentos: list[Fragmento] = []
        self._embeddings: np.ndarray | None = None

    def _garantir_indice(self) -> None:
        """Constrói o índice (fragmentos + embeddings) na primeira chamada."""
        if self._embeddings is None:
            self._fragmentos, self._embeddings = construir_indice(self.modelo)

    def recuperar(self, consulta: str, k: int = 4) -> list[TrechoRecuperado]:
        """Retorna os `k` fragmentos mais similares à consulta (cosseno)."""
        self._garantir_indice()
        assert self._embeddings is not None

        consulta_vec = embedar_consulta(consulta, self.modelo)
        scores = self._embeddings @ consulta_vec  # cosseno (vetores normalizados)
        indices = np.argsort(scores)[::-1][:k]

        return [
            TrechoRecuperado(
                texto=self._fragmentos[i].texto,
                origem=self._fragmentos[i].origem,
                score=float(scores[i]),
            )
            for i in indices
        ]
