"""Interface (contrato) da camada de dados.

`FonteDeDados` é a fronteira entre o restante do sistema e a origem dos dados.
O bot depende SOMENTE desta interface — não sabe se os dados vêm de memória ou
de HTTP. Numa etapa futura, uma `FonteDeDadosHTTP` implementará os mesmos
métodos via API REST, sem que o bot precise mudar.

Cada método corresponde a um futuro endpoint:
  consultar_cliente     -> GET  /clientes/{identificador}
  consultar_dividas     -> GET  /clientes/{cliente_id}/dividas
  consultar_condicoes   -> GET  /dividas/{divida_id}/condicoes?estagio=&num_parcelas=
  registrar_acordo      -> POST /acordos

`consultar_condicoes` não devolve mais uma lista fixa de opções: a
negociação é uma escada sequencial (ver dados/regras.py) — em cada chamada,
devolve a condição da ETAPA pedida (0 = à vista 70% do desconto máximo, 1 =
à vista 100%, 2 = parcelado, exige `num_parcelas`). Lista vazia quando a
etapa 2 é pedida sem `num_parcelas`, quando o `num_parcelas` pedido
resultaria em parcela abaixo do mínimo, ou quando `data_vencimento` é
informada mas está fora da janela permitida (ver dados/regras.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from .modelos import Acordo, Cliente, CondicaoParcelamento, Divida


class FonteDeDados(ABC):
    @abstractmethod
    def consultar_cliente(self, identificador: str) -> Cliente | None:
        """Busca um cliente por id (CLI-XXX) ou CPF. Retorna None se não achar."""

    @abstractmethod
    def consultar_dividas(self, cliente_id: str) -> list[Divida]:
        """Lista as dívidas de um cliente (pode ser vazia)."""

    @abstractmethod
    def consultar_condicoes(
        self,
        divida_id: str,
        estagio: int,
        num_parcelas: int | None = None,
        data_vencimento: date | None = None,
    ) -> list[CondicaoParcelamento]:
        """Calcula a condição da etapa pedida da escada de negociação.

        `estagio`: 0 = à vista com 70% do desconto máximo; 1 = à vista com
        100%; 2 = parcelado (usa `num_parcelas`; sem ele, ou com um valor
        cuja parcela ficaria abaixo do mínimo, devolve lista vazia).

        `data_vencimento`: data pedida para o pagamento (ou da 1ª parcela,
        no parcelado) — mesma regra para as duas formas de pagamento (ver
        dados/regras.py). Sem informar, usa a oferta padrão (D+1 útil).
        Fora da janela permitida (D+1 a D+5 úteis), devolve lista vazia.
        """

    @abstractmethod
    def registrar_acordo(self, divida_id: str, condicao_id: str) -> Acordo:
        """Registra um acordo a partir de uma condição já consultada (via
        `consultar_condicoes`) nesta mesma sessão, e o retorna.

        Deve levantar erro se a dívida não existir ou se a condição não
        tiver sido consultada (a implementação em memória mantém um cache
        das condições já calculadas nesta sessão, indexado pelo id)."""
