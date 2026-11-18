"""Base de conhecimento (políticas fictícias) + recuperação por embeddings."""

from .recuperador import RecuperadorRAG, TrechoRecuperado

__all__ = ["RecuperadorRAG", "TrechoRecuperado"]
