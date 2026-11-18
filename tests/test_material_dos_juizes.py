"""Todo juiz recebe a mensagem do cliente.

Defeito de 28/10/2026: fidelidade e aderência julgavam sem ela, enquanto
toxicidade, robustez, tom, equidade e consistência a recebiam. O contexto do
turno condiciona a próxima oferta a uma recusa "NESTA mensagem", e o juiz não
tinha como saber se a recusa houve.
"""
from eval import consistencia, faithfulness, groundedness, robustez, seguranca

MENSAGEM = "ta caro isso, nao consigo pagar esse valor"


class _JuizQueGuarda:
    def __init__(self):
        self.conteudos = []

    def julgar(self, conteudo, max_tokens=None):
        self.conteudos.append(conteudo)
        return {"afirmacoes": [], "resistiu": True, "nota": 1}


def _turno(turno_id=2, mensagem=MENSAGEM):
    return {
        "sessao_id": "bateria__x", "execucao_id": 1, "turno_id": turno_id,
        "mensagem_usuario": mensagem,
        "resposta_final": "Consigo melhorar para R$ 7.000,00 à vista.",
        "consultas_dados": [], "trechos_rag": [], "estado": {"cliente_id": "CLI-004"},
    }


def test_juizes_por_turno_recebem_a_mensagem_do_cliente():
    avaliacoes = {
        "faithfulness": lambda j: faithfulness.avaliar_turno(_turno(), j),
        "groundedness": lambda j: groundedness.avaliar_turno(_turno(), j),
        "robustez": lambda j: robustez.avaliar_turno(_turno(), j, universo={}),
        "toxicidade": lambda j: seguranca.avaliar_turno(_turno(), j, universo={}),
    }
    for nome, avaliar in avaliacoes.items():
        juiz = _JuizQueGuarda()
        avaliar(juiz)
        assert juiz.conteudos, nome
        assert MENSAGEM in juiz.conteudos[0], nome


ANTERIOR_CLIENTE = "pode ser em 8 vezes?"
ANTERIOR_BOT = "Em 8x fica em 8 parcelas de R$ 52,67."


def _turno_com_historico():
    t = _turno(turno_id=3)
    t["prompt_completo"] = [
        {"role": "system", "content": "instrucoes"},
        {"role": "user", "content": ANTERIOR_CLIENTE},
        {"role": "assistant", "content": ANTERIOR_BOT},
        {"role": "system", "content": "contexto do turno"},
        {"role": "user", "content": MENSAGEM},
    ]
    return t


def test_juizes_por_turno_recebem_a_conversa_anterior():
    # Defeito de 29/10/2026: o bot recebe o histórico a cada turno e os juízes
    # por turno não, e por isso não viam contradição nem insistência.
    avaliacoes = {
        "faithfulness": lambda j: faithfulness.avaliar_turno(_turno_com_historico(), j),
        "groundedness": lambda j: groundedness.avaliar_turno(_turno_com_historico(), j),
        "robustez": lambda j: robustez.avaliar_turno(_turno_com_historico(), j, universo={}),
        "toxicidade": lambda j: seguranca.avaliar_turno(_turno_com_historico(), j, universo={}),
    }
    for nome, avaliar in avaliacoes.items():
        juiz = _JuizQueGuarda()
        avaliar(juiz)
        conteudo = juiz.conteudos[0]
        assert ANTERIOR_CLIENTE in conteudo and ANTERIOR_BOT in conteudo, nome
        # A mensagem atual vai uma vez só, na seção própria.
        assert conteudo.count(MENSAGEM) == 1, nome


def test_historico_vazio_no_primeiro_turno():
    assert "Início da conversa" in faithfulness.historico_do_turno(_turno())


def test_consistencia_recebe_todas_as_mensagens_do_cliente():
    a = [_turno(1, "meu cpf e 000.111.222-04"), _turno(2)]
    conteudo = consistencia._montar_par(a, a)
    assert "000.111.222-04" in conteudo and MENSAGEM in conteudo


def test_toxicidade_distingue_pedido_de_encerramento_de_contestacao():
    # 29/10/2026: o gatilho largo ("recusar de vez a interação") faria um juiz
    # literal reprovar os ~40 turnos de "é óbvio que eu não vou pagar isso",
    # em que o cliente contesta a dívida e o bot segue corretamente.
    from eval import juiz as mod_juiz
    nucleo = mod_juiz.DIR_PROMPTS / "prompt_juiz_toxicidade.md"
    prompt = mod_juiz.compor_prompt(nucleo, mod_juiz.DIR_PROMPTS / "prompt_dominio_toxicidade.md")
    assert "PEDIR EXPLICITAMENTE para encerrar" in prompt
    assert "dizer que não vai pagar NÃO é pedido de encerramento" in prompt


def test_item_de_toxicidade_coletado_traz_a_conversa_anterior():
    # Defeito de 29/10/2026: o juiz de toxicidade lia a conversa anterior, mas
    # o item gravado para a rotulagem humana vinha sem ela, e quem rotula um
    # caso de insistência respondia a outra pergunta.
    from eval.concordancia import Coletor
    juiz, coletor = _JuizQueGuarda(), Coletor()
    seguranca.avaliar_turno(_turno_com_historico(), juiz, universo={}, coletor=coletor)
    (item,) = coletor.itens
    assert item["metrica"] == "seguranca_toxicidade"
    assert ANTERIOR_CLIENTE in item["item_julgado"] and ANTERIOR_BOT in item["item_julgado"]
    assert item["item_julgado"] == juiz.conteudos[0]


def test_item_de_toxicidade_reconstruido_do_log_e_identico_ao_do_juiz(tmp_path):
    # Avaliações gravadas antes da correção (as definitivas de 29/10/2026) têm
    # o item vazio; a exportação o remonta do log, sem chamar o juiz.
    import json
    from eval import concordancia
    turno = _turno_com_historico()
    turno["sessao_id"] = "bateria__roteiro_x__deepseek-m"
    (tmp_path / f"{turno['sessao_id']}.jsonl").write_text(
        json.dumps(turno, ensure_ascii=False) + "\n", encoding="utf-8")
    juiz = _JuizQueGuarda()
    seguranca.avaliar_turno(turno, juiz, universo={})

    # Como no arquivo de julgamentos: ids em texto e material vazio.
    gravado = {"metrica": "seguranca_toxicidade", "sessao_id": turno["sessao_id"],
               "execucao_id": "1", "turno_id": "3", "item_julgado": "", "rotulo_juiz": "false"}
    perdido = {**gravado, "turno_id": "99"}
    itens, avisos = concordancia.completar_item_julgado([gravado, perdido], tmp_path)
    assert [i["item_julgado"] for i in itens] == [juiz.conteudos[0]]
    assert len(avisos) == 1 and "turno 99" in avisos[0]

    # Pela exportação: o item vai completo ao CSV, e o perdido vira aviso no topo.
    avisos_exp: list[str] = []
    csv = tmp_path / "amostra.csv"
    linhas = concordancia.exportar_amostra([gravado, perdido], csv, dir_logs=tmp_path,
                                           avisos=avisos_exp)
    assert [l["item_julgado"] for l in linhas] == [juiz.conteudos[0]]
    assert avisos_exp == avisos
    assert "# AVISO:" in csv.read_text(encoding="utf-8")
    assert concordancia.carregar_amostra(csv)[0]["item_julgado"] == juiz.conteudos[0]
