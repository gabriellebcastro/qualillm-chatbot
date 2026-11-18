"""Implementação em memória da camada de dados (FICTÍCIA).

Lê o seed.json (gerado por scripts/gerar_seed.py) e serve os dados através da
interface `FonteDeDados`. Os acordos registrados ficam em memória, no próprio
objeto — a instrumentação (Seção 4) é quem persiste o histórico de cada turno.

Como o restante do sistema só conhece `FonteDeDados`, trocar esta classe por
uma `FonteDeDadosHTTP` no futuro não exige mudar o bot.

Diferente da versão anterior, as condições de parcelamento NÃO vêm mais
pré-calculadas do seed: `consultar_condicoes` as CALCULA na hora, a partir de
`dados/regras.py`, conforme a etapa da negociação (a escada de ofertas). Cada
condição calculada é guardada num cache interno (`_condicoes_geradas`),
indexado pelo id — é o que permite `registrar_acordo` continuar recebendo só
o `condicao_id`, sem mudar essa parte do contrato.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import config
from . import regras
from .interface import FonteDeDados
from .modelos import Acordo, Cliente, CondicaoParcelamento, Divida


class FonteDeDadosMemoria(FonteDeDados):
    def __init__(self, caminho_seed: Path | None = None) -> None:
        """Carrega o seed.json e monta os índices em memória (clientes e
        dívidas) usados pelas consultas abaixo."""
        caminho = caminho_seed or config.CAMINHO_SEED
        with open(caminho, encoding="utf-8") as f:
            seed = json.load(f)

        # Índices por id (e por CPF, para busca de cliente).
        self._clientes: dict[str, Cliente] = {}
        self._cliente_por_cpf: dict[str, str] = {}
        for d in seed["clientes"]:
            cli = Cliente.from_dict(d)
            self._clientes[cli.id] = cli
            self._cliente_por_cpf[_so_digitos(cli.cpf)] = cli.id

        # `data_vencimento_original` é DERIVADA de `dias_atraso` — o seed não
        # guarda data absoluta. Ver "Modelo temporal" em dados/regras.py: o
        # atraso é o parâmetro do cenário e não envelhece; a data de
        # vencimento é que acompanha o "hoje" para permanecer coerente com
        # ele. Gravá-la no seed faria as duas divergirem com o tempo.
        hoje = config.data_referencia()
        self._dividas: dict[str, Divida] = {}
        for d in seed["dividas"]:
            registro = dict(d)
            registro["data_vencimento_original"] = (
                hoje - timedelta(days=registro["dias_atraso"])
            ).isoformat()
            divida = Divida.from_dict(registro)
            self._dividas[divida.id] = divida

        # Cache das condições já calculadas nesta sessão (ver docstring do
        # módulo) — populado por `consultar_condicoes`, lido por
        # `registrar_acordo`.
        self._condicoes_geradas: dict[str, CondicaoParcelamento] = {}

        # Acordos registrados nesta sessão (em memória).
        self._acordos: list[Acordo] = []
        self._contador_acordos = 0

    # --- Consultas (endpoints GET) -----------------------------------------
    def consultar_cliente(self, identificador: str) -> Cliente | None:
        """Busca por id (CLI-XXX) ou CPF (com ou sem pontuação)."""
        if identificador in self._clientes:
            return self._clientes[identificador]
        cliente_id = self._cliente_por_cpf.get(_so_digitos(identificador))
        return self._clientes.get(cliente_id) if cliente_id else None

    def consultar_dividas(self, cliente_id: str) -> list[Divida]:
        """Lista as dívidas de um cliente (vazia se não houver nenhuma)."""
        return [d for d in self._dividas.values() if d.cliente_id == cliente_id]

    def consultar_condicoes(
        self,
        divida_id: str,
        estagio: int,
        num_parcelas: int | None = None,
        data_vencimento: date | None = None,
    ) -> list[CondicaoParcelamento]:
        """Calcula a condição da etapa pedida (ver docstring da interface).

        Levanta ValueError se a dívida não existir ou `estagio` for inválido.
        """
        divida = self._dividas.get(divida_id)
        if divida is None:
            raise ValueError(f"Dívida inexistente: {divida_id}")

        hoje = config.data_referencia()
        # Mesma regra de data para as duas formas de pagamento (ver
        # dados/regras.py): sem pedido explícito, D+1 útil; com pedido, só
        # aceita se estiver dentro da janela D+1..D+5 útil.
        if data_vencimento is None:
            venc = regras.data_vencimento_padrao(hoje)
        elif regras.data_vencimento_valida(hoje, data_vencimento):
            venc = data_vencimento
        else:
            return []

        if estagio in (0, 1):
            fracao = (
                regras.FRACAO_PRIMEIRA_OFERTA if estagio == 0
                else regras.FRACAO_SEGUNDA_OFERTA
            )
            desconto, total = regras.calcular_oferta_vista(divida.valor_atualizado, fracao)
            condicao = CondicaoParcelamento(
                id=f"{divida_id}-V{estagio + 1}",
                divida_id=divida_id,
                tipo="vista",
                num_parcelas=1,
                valor_parcela=total,
                valor_ultima_parcela=total,
                desconto_percentual=desconto,
                valor_total_com_desconto=total,
                data_primeiro_vencimento=venc.isoformat(),
            )
        elif estagio == 2:
            if not num_parcelas:
                return []
            resultado = regras.calcular_oferta_parcelada(divida.valor_atualizado, num_parcelas)
            if resultado is None:
                return []
            total, valor_parcela = resultado
            valor_ultima = round(total - valor_parcela * (num_parcelas - 1), 2)
            condicao = CondicaoParcelamento(
                id=f"{divida_id}-P{num_parcelas:03d}",
                divida_id=divida_id,
                tipo="parcelado",
                num_parcelas=num_parcelas,
                valor_parcela=valor_parcela,
                valor_ultima_parcela=valor_ultima,
                desconto_percentual=0.0,
                valor_total_com_desconto=total,
                data_primeiro_vencimento=venc.isoformat(),
            )
        else:
            raise ValueError(f"Etapa de negociação inválida: {estagio!r}")

        self._condicoes_geradas[condicao.id] = condicao
        return [condicao]

    # --- Comando (endpoint POST) -------------------------------------------
    def registrar_acordo(self, divida_id: str, condicao_id: str) -> Acordo:
        """Registra um acordo a partir de uma condição já consultada nesta
        sessão (via `consultar_condicoes`).

        Levanta ValueError se a dívida não existir, ou se a condição não
        tiver sido consultada antes (não existe no cache) ou não pertencer
        à dívida informada.
        """
        if divida_id not in self._dividas:
            raise ValueError(f"Dívida inexistente: {divida_id}")
        condicao = self._condicoes_geradas.get(condicao_id)
        if condicao is None:
            raise ValueError(
                f"Condição {condicao_id} não foi consultada nesta sessão"
            )
        if condicao.divida_id != divida_id:
            raise ValueError(
                f"Condição {condicao_id} não pertence à dívida {divida_id}"
            )

        self._contador_acordos += 1
        acordo = Acordo(
            id=f"ACO-{self._contador_acordos:03d}",
            divida_id=divida_id,
            condicao_id=condicao_id,
            num_parcelas=condicao.num_parcelas,
            valor_parcela=condicao.valor_parcela,
            valor_ultima_parcela=condicao.valor_ultima_parcela,
            valor_total=condicao.valor_total_com_desconto,
            data_primeiro_vencimento=condicao.data_primeiro_vencimento,
            data_registro=config.data_referencia().isoformat(),
            status="REGISTRADO",
        )
        self._acordos.append(acordo)
        return acordo

    # --- Auxiliares ---------------------------------------------------------
    @property
    def acordos(self) -> list[Acordo]:
        """Todos os acordos registrados nesta instância (cópia da lista)."""
        return list(self._acordos)


def _so_digitos(texto: str) -> str:
    """Remove tudo que não for dígito (usado para comparar CPFs com/sem pontuação)."""
    return "".join(c for c in texto if c.isdigit())
