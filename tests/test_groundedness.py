"""Testes da camada 1 da aderência ao contexto (eval/groundedness.py) com
dados sintéticos — sem API, sem depender do juiz real.

A camada 3 (juiz) não é testada aqui de propósito: ela depende de chamada paga
e de um veredito não determinístico. O que se testa é a precondição, que é
justamente a parte decidível sem juiz.
"""
from eval import groundedness
from eval.juiz import parse_json


def _turno(turno_id: int, trechos: list[dict] | None) -> dict:
    return {"turno_id": turno_id, "sessao_id": "s", "trechos_rag": trechos,
            "resposta_final": "resposta qualquer"}


def test_cobertura_conta_turnos_com_e_sem_contexto():
    """A cobertura é (com contexto, total) — e o total inclui os sem contexto,
    que é o ponto: antes eles saíam da categoria sem deixar rastro."""
    turnos = [
        _turno(1, [{"texto": "politica", "origem": "a.md"}]),
        _turno(2, []),            # recuperou nada
        _turno(3, None),          # campo ausente no log
        _turno(4, [{"texto": "outra", "origem": "b.md"}]),
    ]

    com, total = groundedness.cobertura_de_contexto(turnos)

    assert (com, total) == (2, 4)


def test_cobertura_de_lista_vazia_nao_divide_por_zero():
    """Sem turnos, devolve (0, 0) — quem consome decide reportar `sem_dados`
    em vez de inventar uma taxa."""
    assert groundedness.cobertura_de_contexto([]) == (0, 0)


def test_turno_sem_contexto_sai_da_taxa_de_groundedness():
    """`avaliar_sessao` pula quem não recuperou contexto. Isso é intencional
    (não há contra o que medir), e é a razão de a cobertura existir: sem ela,
    o turno pulado desapareceria da categoria inteira."""
    turnos = [_turno(1, []), _turno(2, None)]

    assert groundedness.avaliar_sessao(turnos, juiz=object()) == []


class _JuizFalso:
    def __init__(self) -> None:
        self.conteudos: list[str] = []

    def julgar(self, conteudo: str) -> dict:
        self.conteudos.append(conteudo)
        return {"afirmacoes": []}


def test_juiz_recebe_o_contexto_do_turno_e_as_regras_fixas():
    # Sem isso o juiz acusava como inventadas regras que o bot tinha nas
    # instruções, como o piso de R$ 50,00 e a recusa de assunto fora da dívida
    # (avaliação do Haiku, 28/10/2026).
    turno = {**_turno(1, [{"texto": "politica", "origem": "a.md"}]), "prompt_completo": [
        {"role": "system", "content": "instrucoes inteiras"},
        {"role": "system", "content": "- politica\n- até 8 parcelas para esta dívida"},
    ]}
    juiz = _JuizFalso()
    groundedness.avaliar_turno(turno, juiz)
    conteudo = juiz.conteudos[0]
    assert "até 8 parcelas para esta dívida" in conteudo
    assert "R$ 50,00" in conteudo and "exclusivamente da dívida" in conteudo
    assert "instrucoes inteiras" not in conteudo


def test_log_sem_prompt_leva_so_os_trechos_e_as_regras():
    juiz = _JuizFalso()
    groundedness.avaliar_turno(_turno(1, [{"texto": "politica X", "origem": "a.md"}]), juiz)
    assert "politica X" in juiz.conteudos[0] and "24 parcelas" in juiz.conteudos[0]


def test_juiz_truncado_e_distinguido_de_juiz_sem_json():
    """A classe da falha separa "cortado no limite de tokens" de "respondeu
    prosa", porque as duas pedem correções diferentes — teto de tokens numa,
    prompt na outra."""
    truncado = parse_json('{"afirmacoes": [{"texto": "o desconto maximo')
    prosa = parse_json("nao consegui avaliar este turno")

    assert "truncado" in truncado["_erro_classe"]
    assert "truncado" not in prosa["_erro_classe"]
    # A amostra do texto original fica no `_erro`, para diagnosticar o caso.
    assert "afirmacoes" in truncado["_erro"]


def test_resposta_invalida_do_juiz_fica_inteira_no_erro():
    # O erro de sintaxe costuma estar no fim de uma resposta longa: cortar a
    # resposta apagava justamente o trecho que explica a falha.
    longa = '{"afirmacoes": [' + '{"texto": "x", "justificativa": "y"}, ' * 60 + '{"texto": "fim "aspas" sem escape"}]}'
    julgamento = parse_json(longa)
    assert "sintaticamente" in julgamento["_erro_classe"]
    assert longa in julgamento["_erro"]


def test_escape_invalido_do_juiz_e_reparado_e_o_veredito_lido():
    # Caso real (28/10/2026): "R\$" não existe em JSON e derrubava o objeto.
    resposta = '```json\n{"justificativa": "Oferta de R\\$ 9.100,00 coincide.", "resistiu": true}\n```'
    julgamento = parse_json(resposta)
    assert julgamento["resistiu"] is True
    assert julgamento["justificativa"] == "Oferta de R$ 9.100,00 coincide."
    assert julgamento["_json_reparado"] == 1


def test_reparo_preserva_escapes_validos():
    from eval.juiz import reparar_escapes
    texto, n = reparar_escapes(r'{"a": "linha\nnova \"aspas\" barra \\ e R\$"}')
    assert n == 1 and texto == r'{"a": "linha\nnova \"aspas\" barra \\ e R$"}'
