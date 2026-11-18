"""Testes da extração de nº de parcelas.

Cobrem a construção "N parcelas de R$ X e a última de R$ Y", que descreve
N+1 parcelas. Ler o N como total gerava falso positivo na camada
determinística de fidelidade — o avaliador acusava o bot de citar um
parcelamento inexistente quando a resposta estava correta.
"""
from eval import extratores as ex


def test_split_em_que_o_total_indica_uma_parcela_a_mais():
    # 5 x 1.166,67 + 1.166,65 = 7.000,00 -> o parcelamento é de SEIS.
    texto = (
        "A condição em 6x é: 5 parcelas de R$ 1.166,67 e a última de "
        "R$ 1.166,65, totalizando R$ 7.000,00."
    )
    numeros = [n for _, n in ex.extrair_parcelas(texto)]
    assert 6 in numeros
    assert 5 not in numeros


def test_split_em_que_o_numero_citado_ja_e_o_total():
    # 2 x 368,92 + 368,93 = 1.106,77 -> o parcelamento é de TRÊS, não quatro.
    texto = (
        "- 3 parcelas de R$ 368,92 e a última de R$ 368,93, "
        "totalizando R$ 1.106,77, com primeiro vencimento em 15/08/2026."
    )
    numeros = [n for _, n in ex.extrair_parcelas(texto)]
    assert numeros == [3]


def test_split_com_subcontagem_entre_parenteses():
    # "6x ... (5 parcelas) e a última" -> o parcelamento é de SEIS.
    texto = (
        "- 6x de R$ 1.166,67 (5 parcelas) e a última de R$ 1.166,65, "
        "total de R$ 7.000,00, com vencimento em 15/08/2026"
    )
    numeros = [n for _, n in ex.extrair_parcelas(texto)]
    assert numeros == [6]


def test_split_sem_total_declarado_devolve_o_numero_citado():
    # Sem total não há como decidir; chutar acusaria o bot indevidamente.
    texto = "São 3 parcelas de R$ 130,04 e a última de R$ 130,05."
    assert [n for _, n in ex.extrair_parcelas(texto)] == [3]


def test_parcelamento_simples_continua_valendo():
    texto = "Você pode pagar em 12x de R$ 700,00, ou em 6 parcelas de R$ 1.166,67."
    numeros = sorted(n for _, n in ex.extrair_parcelas(texto))
    assert numeros == [6, 12]


def test_a_vista_nao_vira_parcelamento():
    texto = "O pagamento à vista é de R$ 5.600,00 com vencimento em 21/07/2026."
    assert ex.extrair_parcelas(texto) == []


# --- I5: "uma parcela menor" -------------------------------------------------
def test_uma_parcela_menor_nao_e_numero_por_extenso():
    # Fase 2, persona_insistente_001 e1202 t5.
    texto = "Se quiser uma parcela menor, é só me dizer em quantas vezes prefere."
    assert ex.violacoes_formato_parcelas(texto) == []


def test_numero_por_extenso_continua_acusado():
    texto = "Fica em seis parcelas, e o atraso é de uma parcela."
    assert ex.violacoes_formato_parcelas(texto) == ["seis parcelas", "uma parcela"]
