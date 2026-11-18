"""Fragmentação da base de políticas (rag/indexador.py)."""
from rag.indexador import carregar_fragmentos, fragmentar_documento


def test_paragrafo_que_anuncia_lista_fica_com_a_lista(tmp_path):
    doc = tmp_path / "p.md"
    doc.write_text(
        "## Regra\n\nO cliente escolhe, respeitadas duas condições:\n\n"
        "- Máximo de 24 parcelas.\n- Mínimo de R$ 50,00.\n\nOutro parágrafo.\n",
        encoding="utf-8",
    )
    fragmentos = [f.texto for f in fragmentar_documento(doc)]
    assert len(fragmentos) == 2
    assert "duas condições:" in fragmentos[0] and "R$ 50,00" in fragmentos[0]


def test_base_real_nao_tem_fragmento_terminado_em_dois_pontos():
    # Caso real (28/10/2026): o trecho de parcelamento.md chegava ao bot
    # terminando em "respeitadas duas condições:", sem as condições.
    for f in carregar_fragmentos():
        assert not f.texto.rstrip().endswith(":"), f.origem
