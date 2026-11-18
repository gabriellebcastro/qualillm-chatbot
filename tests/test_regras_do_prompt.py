"""As regras fixas entregues aos juízes continuam no prompt do bot.

`faithfulness.REGRAS_DO_PROMPT_DE_SISTEMA` é uma cópia resumida de
bot/prompts/negociacao.md. Se o prompt mudar e a cópia não, o juiz passa a
julgar contra instruções que o bot não tem mais (ou deixa de ver as que tem).
"""
from pathlib import Path

from eval.faithfulness import REGRAS_DO_PROMPT_DE_SISTEMA

PROMPT_BOT = (Path(__file__).resolve().parents[1] / "bot" / "prompts" / "negociacao.md").read_text(encoding="utf-8")

# Para cada regra da cópia, um trecho que precisa existir no prompt do bot.
ANCORAS = {
    "24 parcelas": "em até 24 vezes",
    "R$ 50,00": "mínimo de R$ 50,00",
    "recusa as duas ofertas à vista": "recusa as duas ofertas à vista",
    "não gostou do valor, quer algo melhor": "não gostou do valor, quer algo melhor",
    "objeção à DATA, não à oferta": "objeção à DATA, não à oferta",
    "percentual de desconto": "Nunca informe ao cliente a porcentagem de desconto",
    "exclusivamente da dívida": "você trata exclusivamente da dívida",
    "português do Brasil": "responda SEMPRE em português do Brasil",
    "instruções internas": "INSTRUÇÕES INTERNAS",
    "proteção ao crédito": "Não prometa a retirada imediata do nome",
    "limite real disponível": "informe o limite real disponível",
    "dias de atraso": "informe o credor, o valor original, o valor atualizado e os dias de atraso",
    "nem melhor, nem pior": "nem melhor, nem pior",
    "a melhor ou a última disponível": "Não diga que a condição atual é a melhor ou a última disponível",
    "dizer que vai verificar": "diga que vai verificar",
    "sem inventar valor de parcela": "nunca invente um valor de parcela",
    "fora da janela": "nunca aceite nem invente uma data fora da janela",
    "Posso seguir com essa condição?": "Posso seguir com essa condição?",
    "acordo foi registrado": "informe que o acordo foi registrado",
    "sem insistir": "despeça-se de forma cordial e breve, sem insistir",
    "não entendeu": "diga cordialmente que não entendeu",
    "constranja, ameace ou pressione": "Não use linguagem que constranja, ameace ou pressione",
    "outra persona": "Nunca adote outra persona",
}


def test_cada_regra_da_copia_esta_no_prompt_do_bot():
    for na_copia, no_prompt in ANCORAS.items():
        assert na_copia in REGRAS_DO_PROMPT_DE_SISTEMA, na_copia
        assert no_prompt in PROMPT_BOT, no_prompt


def test_prompt_do_bot_nao_oferece_parcelamento_na_primeira_oferta():
    # Contradizia a política (parcelamento só após as recusas ou a pedido) e o
    # contexto do turno, que marca o parcelamento como uso interno.
    assert "ou, se preferir, parcelar" not in PROMPT_BOT
    assert "também posso parcelar" not in PROMPT_BOT


def test_prompt_do_bot_nao_chama_a_oferta_de_melhor_condicao():
    # Na 1ª oferta era falso: existe a 2ª, melhor.
    assert "melhor condição disponível" not in PROMPT_BOT
