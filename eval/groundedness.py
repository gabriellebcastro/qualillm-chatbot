"""Categoria 3 — Aderência ao contexto: groundedness sobre os trechos do RAG.

A referência aqui é o CONTEXTO RECUPERADO (as políticas em `trechos_rag`),
não os dados do cliente — essa é a distinção em relação a `faithfulness.py`,
que confere a resposta contra a fonte de verdade consultada. Um mesmo turno
pode ser fiel aos dados e, ainda assim, afirmar uma regra de negócio que
não estava no contexto recuperado; é esse caso que esta categoria pega.

Camada 1 (determinística) verifica só a PRECONDIÇÃO da medição: se o turno
recuperou algum contexto. Um turno sem contexto não pode ser aderente a
contexto, e isso se decide sem gastar chamada de API (`cobertura_de_contexto`).

**Esta é a categoria com a camada 1 mais estreita do framework, e isso é um
achado, não uma lacuna.** A tentativa óbvia — exigir que todo valor de
política citado na resposta apareça nos trechos recuperados — foi construída,
medida sobre os 511 turnos do acervo e DESCARTADA. Das 21 porcentagens
citadas, 4 não estavam no contexto recuperado, e 3 dessas 4 eram o bot citando
o número para RECUSÁ-LO:

    "não posso aplicar um desconto de 90%"      (recusando injeção, 2x)
    "sobre o desconto de 15% que você pediu,
     infelizmente não é possível"

Só o quarto caso era afirmação de regra de fato ("juros de 1% ao mês", com o
trecho dessa regra fora dos recuperados). Uma checagem literal reprovaria as
recusas, que são o melhor comportamento possível do bot — ficaria
ANTICORRELACIONADA com a qualidade que deveria medir. Distinguir afirmar de
citar-para-negar exige compreender o enunciado, e é por isso que a decisão é
do juiz: é o problema do oráculo nesta categoria, não uma camada 1 que falta
escrever.

Camada 3 (juiz, `prompt_juiz_groundedness.md`) classifica cada afirmação de
política como sustentada / não sustentada / fora de escopo.

Métrica: proporção de afirmações de política sustentadas pelo contexto.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .faithfulness import REGRAS_DO_PROMPT_DE_SISTEMA, contexto_do_turno, historico_do_turno
from .juiz import TETO_TOKENS_JUIZ, JuizLLM, falhou

NOME_PROMPT = "prompt_juiz_groundedness.md"

# Teto único de todos os juízes (ver `juiz.TETO_TOKENS_JUIZ`).
MAX_TOKENS = TETO_TOKENS_JUIZ

SUSTENTADA = "sustentada"
NAO_SUSTENTADA = "nao_sustentada"
FORA_DE_ESCOPO = "fora_de_escopo"

# Abstenção no nível do ITEM: a evidência não permite decidir esta afirmação
# (fonte vazia, truncada ou ilegível). Vale para falta de material, nunca para
# dúvida do juiz — se a incerteza dele tirasse itens da conta, os casos
# difíceis sairiam do denominador e a taxa passaria a ser medida só sobre os
# fáceis, inflando a qualidade. É o mesmo critério de `nao_verificavel`, que
# qualifica a AFIRMAÇÃO e não o estado do avaliador.
EVIDENCIA_INSUFICIENTE = "evidencia_insuficiente"


@dataclass
class AfirmacaoPolitica:
    texto: str
    classificacao: str
    justificativa: str

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)


@dataclass
class ResultadoGroundedness:
    turno_id: int
    afirmacoes: list[AfirmacaoPolitica]
    n_trechos: int
    erro: str | None
    # Onde o turno está (preenchido por `avaliar_sessao`), para o relatório
    # localizar cada afirmação não sustentada.
    sessao_id: str = ""
    execucao_id: object = ""

    @property
    def de_politica(self) -> int:
        """Afirmações que são de fato sobre regras/políticas."""
        return sum(
            1 for a in self.afirmacoes
            if a.classificacao not in (FORA_DE_ESCOPO, EVIDENCIA_INSUFICIENTE)
        )

    @property
    def sustentadas(self) -> int:
        """Quantas afirmações de política o contexto recuperado sustenta."""
        return sum(1 for a in self.afirmacoes if a.classificacao == SUSTENTADA)

    @property
    def nao_sustentadas(self) -> list[AfirmacaoPolitica]:
        """As regras afirmadas sem respaldo no contexto — o achado que interessa."""
        return [a for a in self.afirmacoes if a.classificacao == NAO_SUSTENTADA]

    @property
    def score(self) -> float | None:
        """Proporção de afirmações de política sustentadas pelo contexto."""
        return (self.sustentadas / self.de_politica) if self.de_politica else None

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return {
            "turno_id": self.turno_id,
            "n_trechos": self.n_trechos,
            "de_politica": self.de_politica,
            "sustentadas": self.sustentadas,
            "score": self.score,
            "erro": self.erro,
            "afirmacoes": [a.to_dict() for a in self.afirmacoes],
        }


def montar_contexto(turno: dict) -> str:
    """Serializa os trechos de política recuperados no turno."""
    trechos = turno.get("trechos_rag") or []
    if not trechos:
        return "(Nenhum trecho de política foi recuperado neste turno.)"
    return "\n".join(
        f"- [{t.get('origem')}] {t.get('texto')}" for t in trechos
    )


def montar_material(turno: dict) -> str:
    """O material de política que o bot tinha neste turno.

    Até 28/10/2026 ia ao juiz só a lista de trechos, sob o pressuposto de que
    ela era todo o material de política do bot. Não era: o bot recebe também
    o bloco de contexto do turno (com o limite de parcelas daquela dívida e a
    janela de datas) e as regras fixas das instruções. Das 122 afirmações
    acusadas na avaliação do Haiku de 28/10, cerca de 100 eram dessas fontes,
    e a métrica media a falta de material do juiz, não o bot. É o mesmo
    princípio de `faithfulness.montar_fonte`, sem as consultas de dados, que
    são da outra categoria.
    """
    contexto = contexto_do_turno(turno)
    partes = [
        "### Contexto entregue ao sistema neste turno (inclui os trechos recuperados)",
        contexto,
    ] if contexto else ["### Trechos de política recuperados", montar_contexto(turno)]
    partes += ["\n### Regras fixas das instruções do sistema", REGRAS_DO_PROMPT_DE_SISTEMA]
    return "\n".join(partes)


def cobertura_de_contexto(turnos: list[dict]) -> tuple[int, int]:
    """CAMADA 1: `(turnos com contexto recuperado, total de turnos)`.

    Precondição da categoria, verificável sem juiz: um turno que não recuperou
    trecho nenhum não tem contra o que ser aderente. Mede o RECUPERADOR, não o
    bot — e é por isso que vale como camada 1 isolada em vez de entrar na taxa
    de groundedness: uma falha aqui não é o modelo afirmando o que não devia,
    é o sistema respondendo sem base disponível.

    Existe também para tornar visível o que antes desaparecia: `avaliar_sessao`
    pula os turnos sem contexto, e sem esta contagem eles saíam da categoria
    sem deixar rastro — a taxa de groundedness seguia alta sobre os turnos que
    sobraram.
    """
    com = sum(1 for t in turnos if (t.get("trechos_rag") or []))
    return com, len(turnos)


def avaliar_turno(turno: dict, juiz: JuizLLM | None = None,
                  coletor=None) -> ResultadoGroundedness:
    """Avalia a aderência ao contexto de UM turno."""
    juiz = juiz or JuizLLM(NOME_PROMPT, max_tokens=MAX_TOKENS)
    # Mensagem do cliente e conversa anterior: mesmo motivo de
    # `faithfulness.avaliar_turno`.
    conteudo = (
        f"## CONVERSA ANTERIOR\n{historico_do_turno(turno)}\n\n"
        f"## MENSAGEM DO CLIENTE\n{turno.get('mensagem_usuario') or ''}\n\n"
        f"## MATERIAL DE POLÍTICA RECEBIDO\n{montar_material(turno)}\n\n"
        f"## RESPOSTA A VERIFICAR\n{turno.get('resposta_final') or ''}"
    )
    julgamento = juiz.julgar(conteudo)
    n_trechos = len(turno.get("trechos_rag") or [])
    if falhou(julgamento):
        return ResultadoGroundedness(turno["turno_id"], [], n_trechos, julgamento["_erro"])
    afirmacoes = _ler_afirmacoes(julgamento)
    if coletor is not None:
        for af in afirmacoes:
            coletor.adicionar(
                "aderencia_groundedness", af.classificacao,
                mensagem_usuario=turno.get("mensagem_usuario") or "",
                resposta_bot=turno.get("resposta_final") or "",
                item_julgado=f"AFIRMACAO: {af.texto}\n\n{conteudo}",
                sessao_id=turno.get("sessao_id", ""),
                execucao_id=turno.get("execucao_id", ""),
                turno_id=turno.get("turno_id", ""),
                justificativa=af.justificativa,
            )
    return ResultadoGroundedness(
        turno["turno_id"], afirmacoes, n_trechos, None
    )


def avaliar_sessao(
    turnos: list[dict],
    juiz: JuizLLM | None = None,
    apenas_com_contexto: bool = True,
    coletor=None,
) -> list[ResultadoGroundedness]:
    """Avalia os turnos de uma sessão.

    `apenas_com_contexto` pula turnos sem `trechos_rag`. Note que esses
    turnos não são "aprovados": simplesmente não há contexto contra o qual
    medir aderência, e o custo de perguntar ao juiz não se justifica.
    """
    juiz = juiz or JuizLLM(NOME_PROMPT, max_tokens=MAX_TOKENS)
    resultados: list[ResultadoGroundedness] = []
    for t in sorted(turnos, key=lambda x: x["turno_id"]):
        if apenas_com_contexto and not (t.get("trechos_rag") or []):
            continue
        r = avaliar_turno(t, juiz, coletor=coletor)
        r.sessao_id, r.execucao_id = t.get("sessao_id", ""), t.get("execucao_id", "")
        resultados.append(r)
    return resultados


def taxa_aderencia(resultados: list[ResultadoGroundedness]) -> float | None:
    """Métrica da categoria: proporção de afirmações de política sustentadas."""
    total = sum(r.de_politica for r in resultados)
    if not total:
        return None
    return sum(r.sustentadas for r in resultados) / total


def _ler_afirmacoes(julgamento: dict) -> list[AfirmacaoPolitica]:
    """Converte a lista devolvida pelo juiz, descartando itens malformados."""
    validas = {SUSTENTADA, NAO_SUSTENTADA, FORA_DE_ESCOPO, EVIDENCIA_INSUFICIENTE}
    afirmacoes: list[AfirmacaoPolitica] = []
    for item in julgamento.get("afirmacoes") or []:
        if not isinstance(item, dict):
            continue
        classificacao = str(item.get("classificacao", "")).strip().lower()
        if classificacao not in validas:
            continue
        afirmacoes.append(
            AfirmacaoPolitica(
                str(item.get("texto", "")),
                classificacao,
                str(item.get("justificativa", "")),
            )
        )
    return afirmacoes
