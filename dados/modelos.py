"""Modelos de dados do sistema (todos os dados são FICTÍCIOS).

Dataclasses simples e serializáveis que representam as entidades manipuladas
pela camada de dados. Elas espelham o que uma futura API REST devolveria em
JSON — por isso todas expõem `to_dict()` / `from_dict()`.

Convenções:
  - Valores monetários: float com 2 casas decimais.
  - Datas: string no formato ISO "AAAA-MM-DD" (a formatação DD/MM/AAAA para
    exibição é responsabilidade da camada de apresentação/bot).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Cliente:
    id: str
    nome: str
    cpf: str            # fictício
    email: str          # fictício
    telefone: str       # fictício

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Cliente":
        """Reconstrói um Cliente a partir de um dict (ex.: linha do seed.json)."""
        return cls(**d)


@dataclass(frozen=True)
class Divida:
    id: str
    cliente_id: str
    credor: str
    valor_original: float
    valor_atualizado: float
    dias_atraso: int
    data_vencimento_original: str   # ISO AAAA-MM-DD
    status: str                     # ex.: "EM_ATRASO"

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Divida":
        """Reconstrói uma Divida a partir de um dict (ex.: linha do seed.json)."""
        return cls(**d)


@dataclass(frozen=True)
class CondicaoParcelamento:
    id: str
    divida_id: str
    tipo: str                       # "vista" (com desconto) | "parcelado" (com juros)
    num_parcelas: int
    valor_parcela: float
    valor_ultima_parcela: float     # ajuste de centavos na última parcela
    desconto_percentual: float      # 0.0 para "parcelado" (não tem desconto)
    valor_total_com_desconto: float  # valor total desta condição (nome mantido
                                      # por compatibilidade; no "parcelado" já
                                      # inclui os juros, não um desconto)
    data_primeiro_vencimento: str   # ISO AAAA-MM-DD

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CondicaoParcelamento":
        """Reconstrói uma CondicaoParcelamento a partir de um dict (ex.: linha do seed.json)."""
        return cls(**d)


@dataclass(frozen=True)
class Acordo:
    id: str
    divida_id: str
    condicao_id: str
    num_parcelas: int
    valor_parcela: float
    valor_ultima_parcela: float
    valor_total: float
    data_primeiro_vencimento: str   # ISO AAAA-MM-DD
    data_registro: str              # ISO AAAA-MM-DD
    status: str                     # ex.: "REGISTRADO"

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Acordo":
        """Reconstrói um Acordo a partir de um dict."""
        return cls(**d)
