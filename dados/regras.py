"""Regras de negócio da negociação (FICTÍCIAS, mas internamente consistentes).

Este módulo concentra, em UM único lugar, as regras que definem encargos,
descontos, juros e o parcelamento. Duas partes do sistema dependem delas:

  1. A camada de dados (fonte de verdade), que calcula as ofertas sob demanda
     a partir daqui — não existe mais uma lista fixa de condições pré-geradas
     (ver histórico: até a versão anterior, `scripts/gerar_seed.py` gravava
     um conjunto fixo de parcelamentos 1x/3x/6x/12x em `seed.json`; a
     negociação agora é uma ESCADA sequencial de ofertas, e o parcelamento é
     em número de parcelas livre, então não há mais "lista de opções" para
     pré-computar).
  2. A base de políticas do RAG (`rag/politicas/`), que descreve ESTAS MESMAS
     regras em linguagem natural para o bot consultar.

A avaliação de fidelidade verifica justamente se o que o bot diz, guiado
pelas políticas, bate com o que a fonte de verdade retorna. Por isso as
regras precisam ser idênticas nos dois lados — e viverem em um só lugar aqui.

Todas as funções são puras (sem I/O), para poderem ser testadas e reutilizadas.

## A negociação em três etapas (ESCADA)

1. **1ª oferta — à vista com 70% do desconto máximo disponível.**
2. Se o cliente recusar: **2ª oferta — à vista com 100% do desconto máximo.**
3. Se o cliente recusar também: **parcelamento livre** — o cliente escolhe o
   número de parcelas, respeitando o valor mínimo de parcela; o parcelamento
   NÃO tem desconto e tem juros (fica mais caro que qualquer oferta à vista,
   de propósito: parcelar tem custo).

O cliente pode pedir parcelamento diretamente, a qualquer momento, sem
esperar recusar as duas ofertas à vista — a escada só governa QUAL oferta à
vista está em jogo enquanto ele não pedir parcelamento.

## Data de vencimento — mesma regra para à vista e parcelado

A data do pagamento (à vista, ou da primeira parcela) segue uma regra ÚNICA,
igual para as duas formas de pagamento:

- Oferta padrão: **D+1 dia útil** a partir de hoje.
- O cliente pode pedir outra data, desde que seja dia útil e não ultrapasse
  **D+5 dias úteis** — o mais distante possível.
- "Dia útil" conta só segunda a sexta-feira; sábado e domingo não contam na
  contagem nem podem ser a data escolhida.

No parcelamento, as parcelas seguintes vencem mensalmente a partir da data
da primeira.

## MODELO TEMPORAL (regra de negócio — como o tempo age sobre a dívida)

Duas grandezas temporais convivem no sistema, e elas se comportam de formas
OPOSTAS de propósito:

1. **O "hoje" do sistema é o dia real** (`config.data_referencia()`). Tudo
   que é ofertado ao cliente — vencimento à vista, primeira parcela, janela
   de D+1 a D+5 úteis — é calculado a partir dele, então são sempre datas
   futuras de verdade. Ofertar pagamento para uma data já passada seria erro
   funcional evidente.

2. **O atraso de cada dívida NÃO envelhece.** `dias_atraso` é dado fixo no
   seed, e `data_vencimento_original` é DERIVADA dele na leitura
   (`hoje − dias_atraso`), nunca gravada como data absoluta.

O segundo ponto costuma surpreender, então vale o porquê. `dias_atraso` não
é "uma data que envelhece": é o PARÂMETRO QUE DEFINE O CENÁRIO — é ele que
diz se aquela é uma dívida recente ou muito antiga. Se ele derivasse do
relógio (vencimento fixo, atraso crescente), três coisas quebrariam:

- **Os valores mudariam todo dia.** `valor_atualizado` depende de
  `dias_atraso` (juros de mora pro-rata). Esse é o número que o bot cita ao
  cliente e que o avaliador de fidelidade confere — é a base das métricas de
  precisão, e ela deixaria de ser estável.
- **Os cenários se degradariam.** A única dívida "recente" da massa (20 dias)
  viraria 235 dias em seis meses. O conjunto todo convergiria para "tudo
  muito antigo", e o caso de dívida nova deixaria de existir.
- **Estímulos calibrados quebrariam.** O teto de parcelas depende do valor:
  uma dívida que hoje tem limite passa a não ter. Um estímulo como "quero em
  50 vezes" mudaria de inválido para válido conforme o dia da execução — e a
  métrica passaria a medir o calendário, não o bot.

Resumindo: **datas ofertadas acompanham o relógio; o perfil da dívida não.**
A massa de dados é atemporal — sempre os mesmos cenários de atraso —, mas
sempre apresentada com datas atuais.
"""
from __future__ import annotations

from datetime import date, timedelta

# --- Encargos por atraso (inalterado) ---------------------------------------
MULTA = 0.02              # 2% sobre o valor original (fixa)
JUROS_MORA_AM = 0.01      # 1% ao mês, proporcional aos dias (pro-rata die)

# --- Desconto (à vista) ------------------------------------------------------
# Desconto máximo FIXO, sobre o valor atualizado, igual para toda dívida —
# não depende mais da faixa de dias de atraso.
DESCONTO_MAXIMO = 0.50

# Frações do desconto máximo oferecidas em cada etapa da escada à vista.
FRACAO_PRIMEIRA_OFERTA = 0.70   # 1ª oferta: 70% do desconto máximo (35% efetivo)
FRACAO_SEGUNDA_OFERTA = 1.00    # 2ª oferta: 100% do desconto máximo (50% efetivo)

# --- Parcelamento -------------------------------------------------------------
VALOR_MINIMO_PARCELA = 50.00       # parcela não pode ser menor que R$ 50,00
TAXA_JUROS_PARCELAMENTO_AM = 0.01  # 1% ao mês, crescendo com o nº de parcelas

# Teto de parcelas. A escolha continua LIVRE dentro dele — não é a volta da
# lista fixa ("3x, 6x, 12x"), é só a outra ponta da regra.
#
# Sem este limite, a política tinha piso e nenhum topo: como a parcela converge
# para 1% do valor da dívida, qualquer dívida a partir de R$ 5.000 aceitava
# QUALQUER número de parcelas. Na massa de teste, 5 das 9 dívidas aceitavam
# 200x (≈16 anos de acordo) e uma tinha teto de 256x. Nenhuma cobrança real
# opera assim, e a ausência de topo era efeito colateral de remover a lista
# fixa, não uma decisão.
MAX_PARCELAS = 24

# --- Data de vencimento (à vista e parcelado, mesma regra) -------------------
DIAS_UTEIS_OFERTA_PADRAO = 1   # D+1 útil: oferta padrão
DIAS_UTEIS_MAXIMO = 5          # D+5 útil: o mais distante que o cliente pode pedir


def calcular_valor_atualizado(valor_original: float, dias_atraso: int) -> float:
    """valor_atualizado = valor_original + multa + juros de mora (pro-rata)."""
    multa = valor_original * MULTA
    juros = valor_original * JUROS_MORA_AM * (dias_atraso / 30)
    return round(valor_original + multa + juros, 2)


def calcular_oferta_vista(valor_atualizado: float, fracao_desconto: float) -> tuple[float, float]:
    """Oferta à vista para uma fração do desconto máximo (0.70 ou 1.00).

    Devolve (desconto_percentual_efetivo, valor_total_com_desconto).
    """
    desconto = round(DESCONTO_MAXIMO * fracao_desconto, 4)
    total = round(valor_atualizado * (1 - desconto), 2)
    return desconto, total


def max_parcelas_possivel(valor_atualizado: float) -> int:
    """Maior número de parcelas oferecível para esta dívida.

    Duas restrições, e vale a mais apertada das duas:

    1. **Piso por parcela.** valor_parcela(N) = valor_atualizado/N +
       TAXA_JUROS_PARCELAMENTO_AM × valor_atualizado — decrescente em N e
       convergindo ao piso de 1% do valor da dívida. Isso limita N só em
       dívidas pequenas; a partir de R$ 5.000 o piso já supera o mínimo de
       R$ 50,00 e a condição deixa de restringir qualquer coisa.
    2. **Teto da política** (`MAX_PARCELAS`), que é o que limita as dívidas
       grandes — exatamente as que a regra 1 não alcança.

    Devolve sempre um inteiro: com o teto, "não existe limite" deixou de ser
    um caso possível, e quem chama não precisa mais tratar `None`.
    """
    piso = TAXA_JUROS_PARCELAMENTO_AM * valor_atualizado
    if piso >= VALOR_MINIMO_PARCELA:
        return MAX_PARCELAS
    pelo_valor = max(1, int(valor_atualizado // (VALOR_MINIMO_PARCELA - piso)))
    return min(pelo_valor, MAX_PARCELAS)


def calcular_oferta_parcelada(
    valor_atualizado: float, num_parcelas: int
) -> tuple[float, float] | None:
    """Oferta parcelada em `num_parcelas` vezes, sem desconto e com juros.

    valor_total = valor_atualizado × (1 + TAXA_JUROS_PARCELAMENTO_AM × N) —
    cresce com o número de parcelas (mais parcelas, mais juros), e por não
    ter desconto algum já fica, por construção, sempre maior que QUALQUER
    oferta à vista (mesmo a de 100% do desconto).

    Devolve (valor_total, valor_parcela), ou None quando o N pedido não é
    oferecível: abaixo de 1, acima do teto da política (`MAX_PARCELAS`), ou
    com parcela abaixo do mínimo (`VALOR_MINIMO_PARCELA`).
    """
    if num_parcelas < 1 or num_parcelas > MAX_PARCELAS:
        return None
    total = round(valor_atualizado * (1 + TAXA_JUROS_PARCELAMENTO_AM * num_parcelas), 2)
    valor_parcela = round(total / num_parcelas, 2)
    if valor_parcela < VALOR_MINIMO_PARCELA:
        return None
    return total, valor_parcela


# --- Dias úteis ---------------------------------------------------------------
# Dia útil = segunda a sexta, fora os feriados nacionais. Sábado, domingo e
# feriado nunca são ofertados. Antes só fins de semana eram excluídos, e o bot
# chegou a ofertar vencimento em 02/11 (Finados).
#
# Uma LISTA, para ser conferida a olho. Os de data fixa valem todo ano. Carnaval
# e Corpus Christi ficam de fora: são ponto facultativo, não feriado nacional.
FERIADOS_NACIONAIS_FIXOS = (
    (1, 1),    # Confraternização Universal
    (4, 21),   # Tiradentes
    (5, 1),    # Dia do Trabalho
    (9, 7),    # Independência
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),   # Finados
    (11, 15),  # Proclamação da República
    (11, 20),  # Dia Nacional de Zumbi e da Consciência Negra
    (12, 25),  # Natal
)

# O único feriado nacional de data móvel. Acrescentar o ano seguinte aqui.
SEXTA_FEIRA_SANTA = (
    date(2026, 4, 3),
    date(2027, 3, 26),
    date(2028, 4, 14),
    date(2029, 3, 30),
    date(2030, 4, 19),
)


def eh_feriado(dia: date) -> bool:
    """O dia é feriado nacional (lista acima)?"""
    return (dia.month, dia.day) in FERIADOS_NACIONAIS_FIXOS or dia in SEXTA_FEIRA_SANTA


def eh_dia_util(dia: date) -> bool:
    """Segunda a sexta, e não feriado."""
    return dia.weekday() < 5 and not eh_feriado(dia)


def somar_dias_uteis(data_base: date, dias_uteis: int) -> date:
    """Soma N dias ÚTEIS a `data_base`. Sábado, domingo e feriado nunca são
    contados, nem podem ser o resultado."""
    atual = data_base
    contados = 0
    while contados < dias_uteis:
        atual += timedelta(days=1)
        if eh_dia_util(atual):
            contados += 1
    return atual


def datas_validas(hoje: date) -> list[date]:
    """Todas as datas que o cliente pode escolher, em ordem: os dias úteis da
    janela [D+1, D+5]. O bot recebe a LISTA, e não só os extremos: "de 27/10
    a 03/11" incluía 02/11, um feriado no meio do intervalo."""
    inicio, fim = data_vencimento_padrao(hoje), data_vencimento_maxima(hoje)
    dias, atual = [], inicio
    while atual <= fim:
        if eh_dia_util(atual):
            dias.append(atual)
        atual += timedelta(days=1)
    return dias


def data_vencimento_padrao(hoje: date) -> date:
    """A data ofertada por padrão: D+1 dia útil."""
    return somar_dias_uteis(hoje, DIAS_UTEIS_OFERTA_PADRAO)


def data_vencimento_maxima(hoje: date) -> date:
    """A data mais distante que o cliente pode pedir: D+5 dias úteis."""
    return somar_dias_uteis(hoje, DIAS_UTEIS_MAXIMO)


def data_vencimento_valida(hoje: date, data_pedida: date) -> bool:
    """A data pedida é um dia útil e está dentro da janela [D+1, D+5] úteis?"""
    if not eh_dia_util(data_pedida):
        return False
    return data_vencimento_padrao(hoje) <= data_pedida <= data_vencimento_maxima(hoje)
