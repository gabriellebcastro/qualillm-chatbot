"""Camada de avaliação (prova de conceito): fidelidade + tom."""

from . import extratores, fidelidade, relatorio
from .tom import AvaliadorTom

__all__ = ["extratores", "fidelidade", "relatorio", "AvaliadorTom"]
