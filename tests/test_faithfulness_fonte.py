"""Fonte do juiz de faithfulness: o que o bot tinha à mão no turno."""
from eval import faithfulness


def test_fonte_traz_o_contexto_do_turno_e_as_regras_fixas():
    turno = {
        "turno_id": 2,
        "trechos_rag": [{"origem": "x.md", "texto": "trecho"}],
        "prompt_completo": [
            {"role": "system", "content": "prompt de sistema inteiro"},
            {"role": "system", "content": "DADOS DA FONTE DE VERDADE\n- SOMENTE estas datas: 2026-10-27"},
            {"role": "user", "content": "oi"},
        ],
    }
    fonte = faithfulness.montar_fonte(turno)
    assert "SOMENTE estas datas: 2026-10-27" in fonte   # a data que o juiz não via
    assert "24 parcelas" in fonte and "R$ 50,00" in fonte
    assert "prompt de sistema inteiro" not in fonte      # o prompt não vai inteiro


def test_log_sem_prompt_cai_na_forma_antiga():
    turno = {"turno_id": 1, "trechos_rag": [{"origem": "x.md", "texto": "trecho"}]}
    fonte = faithfulness.montar_fonte(turno)
    assert "Trechos de política recuperados" in fonte and "trecho" in fonte
