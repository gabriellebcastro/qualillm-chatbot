"""Tom: DIMENSÃO DE APLICAÇÃO, não categoria do framework.

O framework propõe seis categorias de qualidade, derivadas da convergência
entre as normas e universais a sistemas que integram IA generativa. O tom não
é uma delas, e não deveria ser: o que conta como tom adequado depende do
propósito do sistema — num atendimento de cobrança a cordialidade tem peso
legal, num assistente de código a dimensão análoga seria concisão ou clareza.

Ele é, então, o exemplo da OUTRA classe de medida que o framework admite: a
dimensão específica da aplicação. Mesma operacionalização em camadas, mesmo
juiz, mesma validação humana — só a dimensão e a régua vêm do domínio. É a
resposta do framework a "meu sistema tem uma qualidade que as suas seis
categorias não cobrem", e é o que demonstra que o modelo de camadas não
depende do conjunto de categorias.

Consequência prática: o tom é reportado SEM entrar no veredito de
conformidade. Ele não está em `relatorio.LIMIARES`, e nenhuma categoria passa
a não atender por causa dele. O corte entre adequado e inadequado existe
(`LIMIAR_NOTA_TOM`) porque a tela precisa de um rótulo, e é declarado aqui em
lugar de ficar implícito no julgamento do modelo.


Um juiz LLM (o escolhido para a avaliação, de provedor distinto do bot) dá a
nota de tom da resposta num contexto de cobrança; o corte adequado/inadequado
é do código (`LIMIAR_NOTA_TOM`). O prompt de julgamento fica em arquivo
separado e versionável (prompt_juiz.md), para poder iterar sobre ele. A saída
é um JSON estruturado.

Duas granularidades:
  - `avaliar()`: por turno (uma chamada por mensagem+resposta) — usada pelo
    relatório da CLI (scripts/avaliar.py --tom), inalterada.
  - `avaliar_sessao()`: a conversa INTEIRA em uma única chamada — mais barato
    (1 chamada por sessão, não por turno) e mais parecido com QA de
    atendimento real (um analista lê a conversa toda, não frase por frase).
    Usada pelo botão "Avaliar tom" em pages/2_Sessao.py e pelos testes de
    consistência.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import config
from llm import ClienteLLM, criar_cliente

from .juiz import TETO_TOKENS_JUIZ, reparar_escapes

# Nota mínima, na escala 1 a 5, para o tom ser considerado adequado. Antes o
# ponto de corte vivia no prompt, como "tipicamente nota >= 4" — e o
# "tipicamente" deixava a decisão com o modelo, que podia devolver `adequado`
# em desacordo com a própria nota. Aqui o juiz dá a nota e o corte é do código,
# como em `seguranca.LIMIAR_NOTA_TOXICA`.
#
# 4 porque o prompt descreve 5 como tom exemplar e 3 como aceitável com
# ressalva: num contexto de cobrança, "aceitável com ressalva" não é adequado.
LIMIAR_NOTA_TOM = 4

CAMINHO_PROMPT_JUIZ = Path(__file__).resolve().parent / "prompt_juiz.md"
CAMINHO_PROMPT_JUIZ_SESSAO = Path(__file__).resolve().parent / "prompt_juiz_sessao.md"
_RE_JSON = re.compile(r"\{.*\}", re.DOTALL)


class AvaliadorTom:
    def __init__(
        self,
        cliente_llm: ClienteLLM | None = None,
        temperatura: float | None = None,
    ) -> None:
        """Monta o juiz (por padrão, o provedor/modelo configurados em config.py)."""
        self.llm = cliente_llm or criar_cliente(config.JUIZ_PROVEDOR, config.JUIZ_MODELO)
        self.temperatura = config.JUIZ_TEMPERATURA if temperatura is None else temperatura
        self.prompt_juiz = CAMINHO_PROMPT_JUIZ.read_text(encoding="utf-8")
        self.prompt_juiz_sessao = CAMINHO_PROMPT_JUIZ_SESSAO.read_text(encoding="utf-8")

    def avaliar(self, mensagem_usuario: str, resposta_bot: str) -> dict:
        """Pede ao juiz uma nota de tom para este par (mensagem, resposta) e
        devolve o julgamento (nota/adequado/justificativa) já com metadados."""
        conteudo = (
            f"Mensagem do cliente:\n{mensagem_usuario}\n\n"
            f"Resposta do bot:\n{resposta_bot}"
        )
        resposta = self.llm.gerar(
            sistema=self.prompt_juiz,
            mensagens=[{"role": "user", "content": conteudo}],
            temperatura=self.temperatura,
            max_tokens=TETO_TOKENS_JUIZ,
        )
        julgamento = _parse_json(resposta.texto)
        julgamento["adequado"] = _adequado(julgamento.get("nota"))
        julgamento["_meta"] = {
            "provedor": resposta.provedor,
            "modelo": resposta.modelo,
            "parametros": resposta.parametros,
            "latencia_s": round(resposta.latencia_s, 4),
        }
        return julgamento

    def avaliar_sessao(self, turnos: list[dict]) -> dict:
        """Pede ao juiz uma nota de tom para a CONVERSA INTEIRA (todos os
        turnos, em ordem), numa única chamada. Devolve o julgamento
        (nota/adequado/justificativa) já com metadados."""
        transcricao = "\n\n".join(
            f"Cliente: {t['mensagem_usuario']}\nAtendente: {t['resposta_final']}"
            for t in sorted(turnos, key=lambda t: t["turno_id"])
        )
        resposta = self.llm.gerar(
            sistema=self.prompt_juiz_sessao,
            mensagens=[{"role": "user", "content": transcricao}],
            temperatura=self.temperatura,
            max_tokens=TETO_TOKENS_JUIZ,
        )
        julgamento = _parse_json(resposta.texto)
        julgamento["adequado"] = _adequado(julgamento.get("nota"))
        julgamento["_meta"] = {
            "provedor": resposta.provedor,
            "modelo": resposta.modelo,
            "parametros": resposta.parametros,
            "latencia_s": round(resposta.latencia_s, 4),
        }
        return julgamento


def _adequado(nota: object) -> bool | None:
    """Deriva o veredito da nota. `None` quando não houve nota a interpretar.

    Deriva em lugar de ler o campo do juiz porque os dois podiam discordar:
    nada no prompt ligava `adequado` à `nota`, e o código lia os dois como se
    concordassem.
    """
    if not isinstance(nota, (int, float)) or isinstance(nota, bool):
        return None
    return nota >= LIMIAR_NOTA_TOM


def _parse_json(texto: str) -> dict:
    """Extrai o objeto JSON do texto do juiz, de forma tolerante."""
    m = _RE_JSON.search(texto)
    if not m:
        return {"nota": None, "adequado": None,
                "justificativa": "Não foi possível interpretar a resposta do juiz.",
                "_erro": texto}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        pass
    # Mesmo reparo dos outros juízes: "R\$" e afins (ver juiz.reparar_escapes).
    reparado, reparos = reparar_escapes(m.group(0))
    try:
        if reparos:
            return {**json.loads(reparado), "_json_reparado": reparos}
    except json.JSONDecodeError:
        pass
    return {"nota": None, "adequado": None,
            "justificativa": "JSON inválido na resposta do juiz.",
            "_erro": texto}
