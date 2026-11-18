"""Avaliador determinístico: fidelidade de dados (Seção 5.1).

Lê os logs de uma sessão e, por comparação exata (sem LLM, sem julgamento),
verifica se os dados que o bot APRESENTOU correspondem ao que a fonte de verdade
RETORNOU. Verifica também o cumprimento do padrão de formatação e a consistência
do acordo registrado com a condição ofertada.

Como o bot segue o padrão de formatação, a extração é feita por regex sobre a
resposta (ver extratores.py).

## O que conta como "fonte de verdade" aqui

Não é só o que veio das consultas. Números da POLÍTICA também são legítimos, e
tratá-los como inventados é falso positivo:

  - o valor mínimo de parcela (R$ 50,00), que o bot informa ao explicar o
    parcelamento livre;
  - o teto de parcelas de cada dívida, que não vem de consulta nenhuma — é
    derivado do valor pela regra (`regras.max_parcelas_possivel`).

Os dois passaram a aparecer nas respostas quando a negociação virou uma escada
com parcelamento livre: antes o bot listava condições prontas e nunca precisava
citar limite nem mínimo. Numa bateria real, isso sozinho derrubou a precisão
medida de ~98% para 88,4% — 56 das 55 falhas eram esses dois números (40 do
mínimo, 16 de tetos), com o bot se comportando corretamente.

  - as datas da JANELA DE PAGAMENTO do turno (D+1 a D+5 dias úteis, sem
    feriado), que o código calcula e entrega ao bot no bloco de contexto. Ao
    cliente que pede outra data, o bot lista essa janela. Sem ela, a bateria
    de 26/10/2026 acusou 62 datas, todas certas — a janela entregue era
    exatamente 27, 28, 29, 30/10 e 03/11, pulando o feriado de 02/11.

A permissividade para aqui: continuam sendo acusados quaisquer outros valores,
datas ou números de parcelas que não venham das consultas ou do bloco de
contexto do turno.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from dados import regras

from . import extratores as ex

# Campos da fonte de verdade que carregam cada tipo de dado.
_CAMPOS_VALOR = frozenset(
    {
        "valor_original", "valor_atualizado", "valor_parcela",
        "valor_ultima_parcela", "valor_total_com_desconto", "valor_total",
    }
)
_CAMPOS_DATA = frozenset(
    {"data_vencimento_original", "data_primeiro_vencimento", "data_registro"}
)
_CAMPO_PARCELAS = "num_parcelas"

_TOLERANCIA = 0.005  # centavos

# A linha do bloco de contexto com a janela de datas (ver
# `Chatbot._montar_contexto`). É o que o CÓDIGO entregou ao bot naquele turno,
# então é fonte de verdade como uma consulta.
_RE_JANELA = re.compile(r"SOMENTE estas datas: ([0-9, -]+)")
_RE_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def datas_da_janela(turno: dict) -> set[str]:
    """Datas de pagamento que o bloco de contexto do turno declarou válidas.

    Lidas do `prompt_completo` gravado no log, e não recalculadas: o "hoje"
    do bot é o dia em que a conversa rodou, e recalcular com o dia da
    avaliação daria outra janela. Log sem prompt devolve conjunto vazio, e a
    checagem volta a aceitar só as datas das consultas.
    """
    mensagens = turno.get("prompt_completo") or []
    contexto = next((m.get("content") or "" for m in reversed(mensagens)
                     if isinstance(m, dict) and m.get("role") == "system"), "")
    achado = _RE_JANELA.search(contexto)
    return set(_RE_DATA_ISO.findall(achado.group(1))) if achado else set()


@dataclass
class Verificacao:
    tipo: str
    passou: bool
    esperado: object      # valor da fonte de verdade (ou padrão esperado)
    encontrado: object    # o que foi encontrado na resposta do bot
    trecho: str           # trecho onde foi encontrado

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)


@dataclass
class ResultadoTurnoFidelidade:
    turno_id: int
    verificacoes: list[Verificacao]
    # Onde o turno está: sem isso o relatório diz "turno 4 falhou" sem dizer
    # de qual conversa nem de qual execução, e a falha não se localiza.
    sessao_id: str = ""
    execucao_id: object = ""

    @property
    def total(self) -> int:
        """Número total de verificações feitas neste turno."""
        return len(self.verificacoes)

    @property
    def falhas(self) -> int:
        """Quantas verificações não passaram."""
        return sum(1 for v in self.verificacoes if not v.passou)

    @property
    def ok(self) -> bool:
        """True se todas as verificações passaram (zero falhas)."""
        return self.falhas == 0

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return {
            "turno_id": self.turno_id,
            "total": self.total,
            "falhas": self.falhas,
            "ok": self.ok,
            "verificacoes": [v.to_dict() for v in self.verificacoes],
        }


def avaliar_sessao(turnos: list[dict]) -> list[ResultadoTurnoFidelidade]:
    """Avalia todos os turnos de uma sessão (na ordem)."""
    # O mínimo de parcela é constante da política, citável em qualquer turno
    # (ver docstring do módulo) — entra já no conjunto inicial.
    valores_verdadeiros: set[float] = {round(regras.VALOR_MINIMO_PARCELA, 2)}
    datas_verdadeiras: set[str] = set()
    parcelas_verdadeiras: set[int] = set()
    condicoes_por_id: dict[str, dict] = {}
    # `valor_atualizado` das dívidas vistas — base para decidir se um número
    # de parcelas citado é viável (ver `_verificar_resposta`).
    valores_divida: set[float] = set()
    # Números escritos pelo cliente até aqui, para reconhecer o eco recusado
    # (ver `_verificar_resposta`).
    valores_cliente: set[float] = set()

    resultados: list[ResultadoTurnoFidelidade] = []
    for turno in sorted(turnos, key=lambda t: t["turno_id"]):
        acordo_registrado = None
        valores_cliente |= ex.valores_do_cliente(turno.get("mensagem_usuario") or "")
        # Acumula os dados da fonte de verdade retornados NESTE turno antes de
        # checar a resposta (o bot pode citar dados consultados agora).
        for consulta in turno.get("consultas_dados", []):
            _coletar(consulta["resultado"], valores_verdadeiros,
                     datas_verdadeiras, parcelas_verdadeiras)
            if consulta["operacao"] == "consultar_dividas":
                # O teto de parcelas não vem de consulta: é derivado do valor
                # da dívida pela regra de negócio. O bot o informa quando o
                # cliente pede um número de parcelas inviável.
                parcelas_verdadeiras.update(
                    _tetos_de_parcelas(consulta["resultado"])
                )
                valores_divida.update(_valores_atualizados(consulta["resultado"]))
            elif consulta["operacao"] == "consultar_condicoes":
                for cond in consulta["resultado"]:
                    condicoes_por_id[cond["id"]] = cond
            elif consulta["operacao"] == "registrar_acordo":
                acordo_registrado = consulta["resultado"]
        datas_verdadeiras.update(datas_da_janela(turno))

        verificacoes = _verificar_resposta(
            turno["resposta_final"], valores_verdadeiros,
            datas_verdadeiras, parcelas_verdadeiras, valores_divida,
            valores_cliente,
        )
        if acordo_registrado is not None:
            verificacoes.extend(_verificar_acordo(acordo_registrado, condicoes_por_id))
            verificacoes.extend(
                _verificar_resposta_bate_com_acordo(turno["resposta_final"], acordo_registrado)
            )

        resultados.append(ResultadoTurnoFidelidade(
            turno["turno_id"], verificacoes,
            turno.get("sessao_id", ""), turno.get("execucao_id", ""),
        ))
    return resultados


# ---------------------------------------------------------------------------
def _verificar_resposta(texto, valores, datas, parcelas, valores_divida=(),
                        valores_cliente=()) -> list[Verificacao]:
    """Verifica se os valores/datas/parcelas citados no texto existem na
    fonte de verdade acumulada até este turno, e se o formato está correto.

    `valores_divida` são os `valor_atualizado` das dívidas vistas na sessão,
    usados para decidir se um número de parcelas citado é VIÁVEL — ver a
    checagem de parcelas abaixo.

    `valores_cliente` são os números que o cliente escreveu na sessão até
    este turno. Um valor fora da fonte passa quando é ECO RECUSADO: o cliente
    o pediu e a resposta o cita logo depois de uma negação ("não consigo
    chegar em R$ 1.500,00"). Até 04/11/2026 esse eco era acusado como valor
    inventado — 9 ocorrências na Fase 1 e todas as 5 da Fase 2, com o bot
    correto. As duas condições são exigidas juntas: o valor do cliente
    repetido sem recusa ("a opção à vista de R$ 349,00", arredondando o que o
    cliente disse) e o valor recusado que o cliente nunca pediu continuam
    acusados.
    """
    verificacoes: list[Verificacao] = []

    # Valores citados existem na fonte de verdade?
    recusados = ex.valores_recusados(texto)
    for trecho, valor in ex.extrair_valores(texto):
        correspondente = _mais_proximo(valor, valores)
        if (correspondente is None and valor in recusados
                and _mais_proximo(valor, valores_cliente) is not None):
            correspondente = "eco recusado do valor do cliente"
        verificacoes.append(
            Verificacao("valor_existe", correspondente is not None,
                        correspondente, valor, trecho)
        )

    # Datas citadas correspondem às da fonte?
    for trecho, data_iso in ex.extrair_datas(texto):
        passou = data_iso in datas
        verificacoes.append(
            Verificacao("data_existe", passou, data_iso if passou else None,
                        data_iso, trecho)
        )

    # Nº de parcelas citado é legítimo?
    #
    # No fluxo antigo havia uma lista fechada de parcelamentos, e bastava
    # conferir se o número citado estava nela. Hoje o cliente ESCOLHE
    # livremente quantas parcelas quer, respeitando só o mínimo por parcela —
    # então citar "6x" ao sugerir uma simulação é comportamento correto, e
    # não invenção, mesmo que 6 nunca tenha sido consultado.
    #
    # O que a regra de negócio de fato proíbe é citar um número INVIÁVEL (que
    # deixaria a parcela abaixo do mínimo). É isso que se verifica agora: o
    # número passa se veio da fonte OU se é viável para alguma dívida da
    # sessão. Manter a checagem antiga acusava o bot em 10 de 24 casos numa
    # bateria real, todos com o bot correto.
    for trecho, n in ex.extrair_parcelas(texto):
        veio_da_fonte = n in parcelas
        viavel = any(
            regras.calcular_oferta_parcelada(v, n) is not None for v in valores_divida
        )
        passou = veio_da_fonte or viavel
        verificacoes.append(
            Verificacao("parcelas_existe", passou, n if passou else None, n, trecho)
        )

    # Formato (padrão obrigatório R$ X.XXX,XX / DD/MM/AAAA / algarismos).
    viol_valor = ex.violacoes_formato_valor(texto)
    verificacoes.append(
        Verificacao("formato_valor", not viol_valor, "R$ X.XXX,XX", viol_valor,
                    "; ".join(viol_valor))
    )
    viol_data = ex.violacoes_formato_data(texto)
    verificacoes.append(
        Verificacao("formato_data", not viol_data, "DD/MM/AAAA", viol_data,
                    "; ".join(viol_data))
    )
    viol_parc = ex.violacoes_formato_parcelas(texto)
    verificacoes.append(
        Verificacao("formato_parcelas", not viol_parc, "algarismo (ex.: 6x)",
                    viol_parc, "; ".join(viol_parc))
    )
    return verificacoes


def _verificar_acordo(acordo: dict, condicoes_por_id: dict) -> list[Verificacao]:
    """O acordo registrado bate com a condição que foi ofertada?"""
    cond = condicoes_por_id.get(acordo.get("condicao_id"))
    if cond is None:
        return [
            Verificacao("acordo_consistente", False,
                        "condição ofertada correspondente", "condição não ofertada",
                        acordo.get("condicao_id", ""))
        ]
    checagens = [
        ("num_parcelas", acordo["num_parcelas"], cond["num_parcelas"]),
        ("valor_total", acordo["valor_total"], cond["valor_total_com_desconto"]),
        ("data_primeiro_vencimento", acordo["data_primeiro_vencimento"],
         cond["data_primeiro_vencimento"]),
    ]
    verificacoes = []
    for campo, registrado, ofertado in checagens:
        if isinstance(registrado, (int, float)):
            passou = abs(registrado - ofertado) <= _TOLERANCIA
        else:
            passou = registrado == ofertado
        verificacoes.append(
            Verificacao(f"acordo_{campo}", passou, ofertado, registrado, acordo["id"])
        )
    return verificacoes


def _verificar_resposta_bate_com_acordo(texto: str, acordo: dict) -> list[Verificacao]:
    """Quando um acordo é registrado neste turno, os valores/parcelas citados
    na resposta devem bater com ESTE acordo especificamente.

    `_verificar_resposta` só confere se um valor citado existe EM ALGUM LUGAR
    do histórico (qualquer condição já vista) — não é suficiente aqui: achado
    real mostrou o bot registrar um acordo (à vista) e descrever outro, bem
    diferente (12x), no mesmo turno — cada número citado "existia" na fonte
    de verdade (vinha de uma condição real), então a checagem geral não via
    problema, mas o acordo que o cliente ACHA que tem não é o que foi
    registrado.
    """
    valores_acordo = {round(acordo["valor_parcela"], 2), round(acordo["valor_total"], 2)}
    if acordo.get("valor_ultima_parcela") is not None:
        valores_acordo.add(round(acordo["valor_ultima_parcela"], 2))

    verificacoes = []
    for trecho, valor in ex.extrair_valores(texto):
        passou = any(abs(valor - v) <= _TOLERANCIA for v in valores_acordo)
        verificacoes.append(
            Verificacao("valor_bate_com_acordo_registrado", passou,
                        sorted(valores_acordo), valor, trecho)
        )
    for trecho, n in ex.extrair_parcelas(texto):
        passou = n == acordo["num_parcelas"]
        verificacoes.append(
            Verificacao("parcelas_bate_com_acordo_registrado", passou,
                        acordo["num_parcelas"], n, trecho)
        )
    return verificacoes


# ---------------------------------------------------------------------------
def _valores_atualizados(dividas: object) -> set[float]:
    """Os `valor_atualizado` das dívidas retornadas por `consultar_dividas`."""
    if not isinstance(dividas, list):
        return set()
    return {
        float(d["valor_atualizado"])
        for d in dividas
        if isinstance(d, dict) and isinstance(d.get("valor_atualizado"), (int, float))
    }


def _tetos_de_parcelas(dividas: object) -> set[int]:
    """Teto de parcelas de cada dívida retornada, pela regra de negócio.

    `max_parcelas_possivel` devolve None quando não existe teto prático (o
    piso de juros já supera o mínimo por parcela) — nesse caso não há número
    a citar, e nada é acrescentado.
    """
    if not isinstance(dividas, list):
        return set()
    tetos = set()
    for divida in dividas:
        if not isinstance(divida, dict):
            continue
        valor = divida.get("valor_atualizado")
        if isinstance(valor, (int, float)):
            teto = regras.max_parcelas_possivel(float(valor))
            if teto is not None:
                tetos.add(teto)
    return tetos


def _coletar(obj, valores: set, datas: set, parcelas: set) -> None:
    """Percorre o resultado (dict/lista) coletando os valores da fonte."""
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            if chave in _CAMPOS_VALOR and isinstance(valor, (int, float)):
                valores.add(round(float(valor), 2))
            elif chave in _CAMPOS_DATA and isinstance(valor, str):
                datas.add(valor)
            elif chave == _CAMPO_PARCELAS and isinstance(valor, int):
                parcelas.add(valor)
            else:
                _coletar(valor, valores, datas, parcelas)
    elif isinstance(obj, list):
        for item in obj:
            _coletar(item, valores, datas, parcelas)


def _mais_proximo(valor: float, verdadeiros: set[float]) -> float | None:
    """Devolve o valor verdadeiro mais próximo de `valor` (dentro da
    tolerância de centavos), ou None se nenhum bater."""
    for v in verdadeiros:
        if abs(v - valor) <= _TOLERANCIA:
            return v
    return None
