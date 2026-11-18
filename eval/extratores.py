"""Extração por regex de valores, datas e parcelas da resposta do bot.

Duas responsabilidades:

  1. EXTRAIR os valores/datas/parcelas que o bot citou, no formato correto, para
     comparar com a fonte de verdade (fidelidade de dados).
  2. DETECTAR violações de formato: qualquer valor ou data fora do padrão
     obrigatório (R$ X.XXX,XX / DD/MM/AAAA) ou número de parcelas por extenso.

Como o bot é instruído a seguir um padrão rígido de formatação, a extração por
regex é confiável — e desvios do padrão são, eles próprios, achados relevantes.
"""
from __future__ import annotations

import re

# --- Valores monetários ----------------------------------------------------
# Formato exigido: "R$ 1.234,56" (um espaço, milhar com ponto, 2 casas decimais).
_VALOR_ESTRITO = re.compile(r"R\$ \d{1,3}(?:\.\d{3})*,\d{2}")
# Qualquer menção a "R$" seguida de um número (para detectar formato errado).
# Não engole a pontuação final da frase (o ponto/vírgula após o número).
_VALOR_FROUXO = re.compile(r"R\$\s*\d[\d.]*(?:,\d+)?")

# --- Datas -----------------------------------------------------------------
_DATA_ESTRITA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
_DATA_FROUXA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_MESES = (
    "janeiro|fevereiro|março|marco|abril|maio|junho|julho|"
    "agosto|setembro|outubro|novembro|dezembro"
)
_DATA_EXTENSO = re.compile(rf"\b\d{{1,2}}\s+de\s+(?:{_MESES})\b", re.IGNORECASE)

# --- Parcelas --------------------------------------------------------------
_PARCELAS_X = re.compile(r"\b(\d+)\s*x\b", re.IGNORECASE)
_PARCELAS_PALAVRA = re.compile(r"\b(\d+)\s+parcelas?\b", re.IGNORECASE)
# Parcelamento anunciado com a última parcela à parte, para absorver os
# centavos do arredondamento. O bot usa esta construção de duas formas, e o
# mesmo texto significa coisas diferentes em cada uma:
#
#   "5 parcelas de R$ 1.166,67 e a última de R$ 1.166,65, totalizando
#    R$ 7.000,00"          -> 5 x 1.166,67 + 1.166,65 = 7.000,00  => SEIS
#   "3 parcelas de R$ 368,92 e a última de R$ 368,93, totalizando
#    R$ 1.106,77"          -> 2 x 368,92 + 368,93 = 1.106,77      => TRÊS
#
# Não há como decidir pela redação, e chutar N+1 gera falso positivo tanto
# quanto ler N. Quando o total é declarado, porém, a aritmética decide sem
# ambiguidade — é o que `_resolver_split` faz. Sem total declarado, o número
# citado é devolvido como está.
_PARCELAS_SPLIT = re.compile(
    r"(?P<n>\d+)\s*(?:x|parcelas?)"          # "6x" ou "5 parcelas"
    r"(?:\s*\((?P<sub>\d+)\s*parcelas?\))?"   # opcional: "(5 parcelas)"
    r"\s*(?:de\s*)?R\$\s*(?P<x>[\d.]+,\d{2})"
    r"[^;\n]{0,40}?e\s+a\s+[úu]ltima\s*(?:de\s*)?R\$\s*(?P<y>[\d.]+,\d{2})"
    r"(?:[^;\n]{0,40}?total(?:izando)?\s*(?:de\s*)?\s*R\$\s*(?P<t>[\d.]+,\d{2}))?",
    re.IGNORECASE,
)

_TOLERANCIA_CENTAVOS = 0.02
_NUM_EXTENSO = (
    "uma|um|duas|dois|três|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze"
)
_PARCELAS_EXTENSO = re.compile(
    rf"\b(?:{_NUM_EXTENSO})\s+(?:x|vez|vezes|parcela|parcelas)\b", re.IGNORECASE
)
_ARTIGO_INDEFINIDO = re.compile(r"uma?\s+parcela\b", re.IGNORECASE)
_COMPARATIVO_DEPOIS = re.compile(r"\s+(?:menor|maior|mais|menos)\b", re.IGNORECASE)

# --- Eco do valor do cliente -------------------------------------------------
# Negação até seis palavras antes do valor, sem pontuação entre elas.
_NEGACAO_ANTES = re.compile(r"\bn[ãa]o\s+(?:[^\s,.;:!?—–]+\s+){0,6}$", re.IGNORECASE)
_NUMERO_FROUXO = re.compile(
    r"(?<![\d.,/])(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?(?![\d/%]|[.,]\d)"
)


# ---------------------------------------------------------------------------
# Extração (formato correto)
# ---------------------------------------------------------------------------
def extrair_valores(texto: str) -> list[tuple[str, float]]:
    """(trecho, valor) para cada valor monetário BEM formatado."""
    return [(m.group(0), _parse_valor(m.group(0))) for m in _VALOR_ESTRITO.finditer(texto)]


def extrair_datas(texto: str) -> list[tuple[str, str]]:
    """(trecho, data_iso) para cada data no formato DD/MM/AAAA."""
    return [(m.group(0), _parse_data(m.group(0))) for m in _DATA_ESTRITA.finditer(texto)]


def extrair_parcelas(texto: str) -> list[tuple[str, int]]:
    """(trecho, numero) para cada nº de parcelas em algarismo.

    Parcelamentos anunciados com a última parcela à parte ("N parcelas de
    R$ X e a última de R$ Y") são resolvidos por `_resolver_split`, e os
    números soltos que vivem dentro dessa construção são descartados — assim
    o mesmo parcelamento não é contado duas vezes com dois números
    diferentes.
    """
    achados: list[tuple[str, int]] = []
    intervalos_consumidos: list[tuple[int, int]] = []

    for m in _PARCELAS_SPLIT.finditer(texto):
        total = _resolver_split(m)
        if total is not None:
            achados.append((m.group(0), total))
        intervalos_consumidos.append((m.start(), m.end()))

    for regex in (_PARCELAS_X, _PARCELAS_PALAVRA):
        for m in regex.finditer(texto):
            if any(inicio <= m.start() < fim for inicio, fim in intervalos_consumidos):
                continue
            achados.append((m.group(0), int(m.group(1))))
    return achados


def _resolver_split(m: "re.Match") -> int | None:
    """Quantas parcelas a construção "… e a última de …" realmente descreve.

    Com o total declarado, a aritmética decide: se N parcelas de X mais a
    última de Y fecham o total, são N+1; se (N-1) de X mais a última fecham,
    são N. Sem total declarado não há como decidir, e devolver o número
    citado é preferível a inventar um: um palpite errado acusaria o bot de
    ofertar um parcelamento que ele não ofertou.
    """
    n = int(m.group("n"))
    sub = m.group("sub")
    citado = int(sub) if sub else n

    bruto_t = m.group("t")
    if not bruto_t:
        return citado

    x, y, total = (_parse_valor(v) for v in (m.group("x"), m.group("y"), bruto_t))
    if abs(x * citado + y - total) <= _TOLERANCIA_CENTAVOS:
        return citado + 1
    if abs(x * (citado - 1) + y - total) <= _TOLERANCIA_CENTAVOS:
        return citado
    return citado


# ---------------------------------------------------------------------------
# Detecção de violações de formato
# ---------------------------------------------------------------------------
def violacoes_formato_valor(texto: str) -> list[str]:
    """Trechos que citam um valor monetário fora do padrão R$ X.XXX,XX."""
    estritos = {(m.start(), m.group(0)) for m in _VALOR_ESTRITO.finditer(texto)}
    estritos_por_inicio = {inicio: raw for inicio, raw in estritos}
    violacoes = []
    for m in _VALOR_FROUXO.finditer(texto):
        if estritos_por_inicio.get(m.start()) != m.group(0):
            violacoes.append(m.group(0))
    return violacoes


def violacoes_formato_data(texto: str) -> list[str]:
    """Trechos que citam uma data fora do padrão DD/MM/AAAA (ou por extenso)."""
    estritos_por_inicio = {m.start(): m.group(0) for m in _DATA_ESTRITA.finditer(texto)}
    violacoes = []
    for m in _DATA_FROUXA.finditer(texto):
        if estritos_por_inicio.get(m.start()) != m.group(0):
            violacoes.append(m.group(0))
    violacoes.extend(m.group(0) for m in _DATA_EXTENSO.finditer(texto))
    return violacoes


def violacoes_formato_parcelas(texto: str) -> list[str]:
    """Trechos que citam parcelas por extenso (ex.: "seis parcelas") em vez de algarismo.

    "Uma parcela menor" não é número de parcelas: é o artigo indefinido diante
    de uma comparação de valor (Fase 2, persona_insistente_001 e1202 t5, "se
    quiser uma parcela menor, é só me dizer em quantas vezes"). Fica de fora
    só o singular "uma/um parcela" seguido de comparativo; "seis parcelas" e
    "atraso de uma parcela" continuam acusados.
    """
    return [
        m.group(0) for m in _PARCELAS_EXTENSO.finditer(texto)
        if not (_ARTIGO_INDEFINIDO.fullmatch(m.group(0))
                and _COMPARATIVO_DEPOIS.match(texto, m.end()))
    ]


def valores_recusados(texto: str) -> set[float]:
    """Valores bem formatados que a resposta cita logo depois de uma negação.

    "não consigo chegar em R$ 1.500,00", "não consigo fazer uma parcela de
    até R$ 75,00": até seis palavras entre o "não" e o valor, sem pontuação
    no meio — em "não consigo, mas faço R$ X" o valor é oferecido, não
    recusado, e continua sendo conferido.
    """
    return {
        _parse_valor(m.group(0)) for m in _VALOR_ESTRITO.finditer(texto)
        if _NEGACAO_ANTES.search(texto, max(0, m.start() - 120), m.start())
    }


def valores_do_cliente(texto: str) -> set[float]:
    """Números que o cliente escreveu, no formato que for ("1.500", "R$
    1.798,50", "1500", "75"). Só servem para reconhecer o eco que o bot
    recusa, então a leitura é frouxa de propósito."""
    return {
        round(float(f"{m.group(1).replace('.', '')}.{m.group(2) or '0'}"), 2)
        for m in _NUMERO_FROUXO.finditer(texto)
    }


# ---------------------------------------------------------------------------
# Parsing auxiliar
# ---------------------------------------------------------------------------
def _parse_valor(raw: str) -> float:
    """Converte "R$ 1.234,56" (string) em 1234.56 (float)."""
    s = raw.replace("R$", "").strip().replace(".", "").replace(",", ".")
    return round(float(s), 2)


def _parse_data(raw: str) -> str:
    """Converte "DD/MM/AAAA" em "AAAA-MM-DD" (ISO), para comparar com a fonte."""
    dia, mes, ano = raw.split("/")
    return f"{ano}-{mes}-{dia}"
