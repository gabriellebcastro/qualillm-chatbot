"""Camada de dados (fonte de verdade). Todos os dados são FICTÍCIOS."""

from .interface import FonteDeDados
from .memoria import FonteDeDadosMemoria
from .modelos import Acordo, Cliente, CondicaoParcelamento, Divida

__all__ = [
    "FonteDeDados",
    "FonteDeDadosMemoria",
    "Cliente",
    "Divida",
    "CondicaoParcelamento",
    "Acordo",
]
