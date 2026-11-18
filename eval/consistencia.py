"""Categoria 1 — Confiabilidade: taxa de consistência entre reexecuções.

Mede o não determinismo do sistema: a MESMA entrada, reexecutada N vezes
(`config.N_EXECUCOES_PADRAO`), produz a mesma resposta ao cliente?

Duas camadas, conforme o modelo do framework:

  1. DETERMINÍSTICA — compara entre execuções a TRAJETÓRIA DO ESTADO: o
     `estado` gravado em cada turno (estágio da oferta, condição escolhida,
     data, acordo, sessão finalizada). Divergência aqui não é questão de
     estilo: é o sistema decidindo coisas diferentes diante da mesma entrada.
     O texto fica de fora de propósito. Até 04/11/2026 esta camada comparava
     também os valores, datas e parcelas extraídos da resposta, por igualdade
     de conjuntos, e acusava paráfrase ("24 parcelas" × "24 vezes") e omissão
     (uma execução cita o limite de parcelas, outra não) como divergência:
     nas Fases 1 e 2 nenhum estímulo acusado por ela tinha contradição. Se o
     que o texto afirma está certo, quem responde é a fidelidade, turno a
     turno; se dois textos dizem a mesma coisa, é o juiz (camada 3).
     Limite conhecido: a data escolhida é relativa ao dia da execução, e
     repetições rodadas em dias diferentes divergem nela.
  3. JUIZ — para o texto livre, compara os pares de respostas e decide
     equivalência semântica (`prompt_juiz_equivalencia.md`).

Com N execuções são C(N,2) pares (N=5 → 10 pares). Comparar par a par é mais
rigoroso do que comparar todas com a primeira, e não privilegia nenhuma
execução como "referência".

DUAS TAXAS saem dos MESMOS julgamentos, e respondem a perguntas diferentes:

  TOTAL (`C_N`) — o estímulo conta só quando TODOS os seus pares são
  equivalentes. É a forma da taxa de concordância total de Atil2025, e a
  leitura próxima de quem usa o sistema: uma resposta contraditória entre
  cinco já é falha.

  POR PARES (`C̄_N`) — cada estímulo contribui com a proporção dos seus pares
  equivalentes, e a taxa é a média sobre os estímulos.

As duas existem porque a equivalência aqui é decidida por um juiz falível, e
não por igualdade exata como em Atil2025. Sob a regra tudo-ou-nada, um único
falso negativo zera o estímulo: com N=5 (dez pares) e 5% de erro por par,
cerca de 40% dos estímulos consistentes seriam zerados. A taxa por pares
degrada suavemente no mesmo cenário, deslocando o resultado em uma fração do
estímulo. A distância entre as duas localiza a instabilidade — próximas,
divergências dispersas; total baixa com média alta, concentração em poucos
estímulos.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from itertools import combinations

from . import extratores as ex
from .juiz import TETO_TOKENS_JUIZ, JuizLLM, falhou

NOME_PROMPT = "prompt_juiz_equivalencia.md"

# Teto único de todos os juízes (ver `juiz.TETO_TOKENS_JUIZ`). Histórico: era
# 400 e 1 par em 10 truncava, descartando o julgamento inteiro, inclusive o
# veredito já emitido. Subir o teto, e não encurtar a justificativa no prompt:
# mexer na instrução mudaria o que o juiz é perguntado, e o teto não muda nada
# do julgamento, só deixa a frase terminar.
MAX_TOKENS = TETO_TOKENS_JUIZ


@dataclass
class AssinaturaFactual:
    """Os fatos que uma resposta afirma, sem o texto em volta.

    Hoje só a equidade usa (`equidade.chave_oferta`, os valores e parcelas
    ofertados); a consistência compara a trajetória do estado.
    """
    valores: list[float]
    datas: list[str]
    parcelas: list[int]
    estado: dict

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)


@dataclass
class ParAvaliado:
    execucao_a: int
    execucao_b: int
    equivalente: bool | None
    justificativa: str

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return asdict(self)


@dataclass
class ResultadoConsistencia:
    origem_id: str
    n_execucoes: int
    assinaturas: dict           # execucao_id -> trajetória do estado (lista por turno)
    grupos_factuais: int        # nº de trajetórias distintas (1 = determinístico)
    consistente_deterministicamente: bool
    pares: list[ParAvaliado]
    falhas_juiz: int
    # Pares em que o juiz se ABSTEVE por falta de material (uma das respostas
    # vazia, truncada ou ilegível). Contado separado de `falhas_juiz` porque
    # as duas coisas pedem reações diferentes: falha é problema do avaliador,
    # abstenção é problema da instrumentação que produziu a evidência.
    abstencoes: int = 0

    @property
    def pares_esperados(self) -> int:
        """Comparações que as execuções permitem: C(N, 2)."""
        return self.n_execucoes * (self.n_execucoes - 1) // 2

    @property
    def pares_decididos(self) -> int:
        """Pares em que o juiz deu veredito (fora falhas e abstenções)."""
        return sum(1 for p in self.pares if p.equivalente is not None)

    @property
    def taxa_equivalencia(self) -> float | None:
        """Proporção de pares julgados equivalentes (ignora pares em que o
        juiz falhou ou se absteve).

        É a contribuição deste estímulo para a taxa POR PARES (`C̄_N`).

        Mínimo de pares (comentário #24 do orientador, 16/11/2026): o estímulo
        só contribui se o juiz decidiu MAIS DA METADE das comparações. Abaixo
        disso devolve None, e o estímulo sai do denominador e é contado à
        parte, para que poucos pares não decidam por ele.
        """
        validos = [p for p in self.pares if p.equivalente is not None]
        if not validos or 2 * len(validos) <= self.pares_esperados:
            return None
        return sum(1 for p in validos if p.equivalente) / len(validos)

    @property
    def consistente_totalmente(self) -> bool | None:
        """Este estímulo entra em `E_eq` da taxa TOTAL (`C_N`)?

        Exige as duas camadas: a trajetória do estado não pode ter divergido
        (camada 1) e nenhum par julgado pode ter saído não equivalente
        (camada 3).

        Pares em que o juiz FALHOU ou se absteve não contam como divergência:
        um juiz que não pôde ser consultado não transforma o estímulo em
        inconsistente, e a falha é contabilizada em `falhas_juiz`.

        Mínimo de pares (comentário #24 do orientador, 16/11/2026): para contar
        como CONSISTENTE, o juiz precisa ter decidido TODAS as comparações.
        Faltando alguma, devolve None e o estímulo sai do denominador, contado
        à parte. A divergência já observada (trajetória do estado ou par não
        equivalente) basta para reprovar, mesmo com pares faltando: o mínimo
        existe para que poucos pares não aprovem, e esconder uma falha vista
        puxaria a taxa para cima.
        """
        if not self.consistente_deterministicamente:
            return False
        validos = [p for p in self.pares if p.equivalente is not None]
        if any(not p.equivalente for p in validos):
            return False
        if not validos or len(validos) < self.pares_esperados:
            return None
        return True

    def to_dict(self) -> dict:
        """Converte para dict simples (serializável em JSON)."""
        return {
            "origem_id": self.origem_id,
            "n_execucoes": self.n_execucoes,
            "grupos_factuais": self.grupos_factuais,
            "consistente_deterministicamente": self.consistente_deterministicamente,
            "consistente_totalmente": self.consistente_totalmente,
            "taxa_equivalencia": self.taxa_equivalencia,
            "falhas_juiz": self.falhas_juiz,
            "assinaturas": self.assinaturas,
            "pares": [p.to_dict() for p in self.pares],
        }


def assinatura_factual(turnos: list[dict]) -> AssinaturaFactual:
    """Extrai os fatos afirmados no conjunto de turnos de UMA execução."""
    valores: list[float] = []
    datas: list[str] = []
    parcelas: list[int] = []
    estado: dict = {}
    for t in sorted(turnos, key=lambda x: x["turno_id"]):
        texto = t.get("resposta_final") or ""
        valores.extend(v for _, v in ex.extrair_valores(texto))
        datas.extend(d for _, d in ex.extrair_datas(texto))
        parcelas.extend(n for _, n in ex.extrair_parcelas(texto))
        estado = t.get("estado") or estado  # o do último turno
    return AssinaturaFactual(valores, datas, parcelas, estado)


def trajetoria_de_estado(turnos: list[dict]) -> list[dict]:
    """O `estado` de cada turno de UMA execução, em ordem: o que o sistema
    decidiu, sem o texto em volta."""
    return [t.get("estado") or {} for t in sorted(turnos, key=lambda x: x["turno_id"])]


def agrupar_execucoes(turnos: list[dict], apenas_estimulo: bool = True) -> dict[int, list[dict]]:
    """Agrupa os turnos por `execucao_id`.

    Com `apenas_estimulo`, considera só os turnos marcados como
    `meta.etapa == "estimulo"` pela bateria — os turnos de setup (via 1)
    preparam o estado e não são o que está sendo comparado. Logs sem essa
    marca (anteriores à bateria, ou roteiros inteiros) entram por completo.
    """
    grupos: dict[int, list[dict]] = {}
    for t in turnos:
        if apenas_estimulo and t.get("meta", {}).get("etapa") == "setup":
            continue
        grupos.setdefault(t.get("execucao_id", 0), []).append(t)
    return grupos


def avaliar(
    turnos: list[dict],
    origem_id: str = "",
    juiz: JuizLLM | None = None,
    usar_juiz: bool = True,
    coletor=None,
) -> ResultadoConsistencia:
    """Avalia a consistência entre as execuções presentes em `turnos`.

    `usar_juiz=False` roda só a camada determinística (sem custo de API),
    útil para inspecionar os logs antes de gastar chamadas.

    `coletor` (ver `eval/concordancia.Coletor`) recebe cada veredito de par
    junto do texto exato que o juiz leu, para a amostra da camada 4. A
    unidade aqui é o PAR, e é por isso que o conteúdo vai inteiro: quem
    rotular precisa ver as duas respostas, como o juiz viu.
    """
    grupos = agrupar_execucoes(turnos)
    origem_id = origem_id or _origem(turnos)

    trajetorias = {eid: trajetoria_de_estado(ts) for eid, ts in grupos.items()}
    grupos_factuais = len({
        json.dumps(t, ensure_ascii=False, sort_keys=True) for t in trajetorias.values()
    })

    pares: list[ParAvaliado] = []
    falhas = 0
    abstencoes = 0
    if usar_juiz and len(grupos) > 1:
        juiz = juiz or JuizLLM(NOME_PROMPT, max_tokens=MAX_TOKENS)
        for a, b in combinations(sorted(grupos), 2):
            conteudo = _montar_par(grupos[a], grupos[b])
            julgamento = juiz.julgar(conteudo)
            if falhou(julgamento):
                falhas += 1
                pares.append(ParAvaliado(a, b, None, julgamento["_erro"]))
                continue
            bruto = julgamento.get("equivalente")
            if bruto is None:
                # Abstenção: `bool(None)` daria False, isto é, contaria o par
                # como DIVERGENTE. Aqui não há camada 1 a que recorrer para
                # este par, então ele sai do denominador, como uma falha — mas
                # entra noutra conta, porque a causa é outra.
                abstencoes += 1
                pares.append(ParAvaliado(
                    a, b, None, str(julgamento.get("justificativa", ""))
                ))
                continue
            equivalente = bool(bruto)
            pares.append(
                ParAvaliado(
                    a, b, equivalente,
                    str(julgamento.get("justificativa", "")),
                )
            )
            if coletor is not None:
                coletor.adicionar(
                    "confiabilidade_equivalencia_par", equivalente,
                    item_julgado=conteudo,
                    sessao_id=origem_id, execucao_id=f"{a}x{b}",
                    justificativa=str(julgamento.get("justificativa", "")),
                )

    return ResultadoConsistencia(
        origem_id=origem_id,
        n_execucoes=len(grupos),
        assinaturas=trajetorias,
        grupos_factuais=grupos_factuais,
        consistente_deterministicamente=grupos_factuais <= 1,
        pares=pares,
        falhas_juiz=falhas,
        abstencoes=abstencoes,
    )


def _montar_par(turnos_a: list[dict], turnos_b: list[dict]) -> str:
    """Monta o conteúdo enviado ao juiz: a entrada e as duas respostas.

    A entrada são TODAS as mensagens do cliente, em ordem. Até 28/10/2026 ia
    só a primeira, e num estímulo de vários turnos o juiz comparava respostas
    a perguntas que não via. As mensagens são as mesmas nas duas execuções
    (reinjeção e roteiro repetem o mesmo texto), por isso vão uma vez só.
    """
    pergunta = "\n".join(
        (t.get("mensagem_usuario") or "").strip()
        for t in sorted(turnos_a, key=lambda x: x["turno_id"])
    ).strip()
    return (
        f"Mensagens do cliente, em ordem:\n{pergunta}\n\n"
        f"Resposta A:\n{_texto(turnos_a)}\n\n"
        f"Resposta B:\n{_texto(turnos_b)}"
    )


def _texto(turnos: list[dict]) -> str:
    """Concatena as respostas de uma execução, na ordem dos turnos."""
    return "\n".join(
        (t.get("resposta_final") or "").strip()
        for t in sorted(turnos, key=lambda x: x["turno_id"])
    ).strip()


def _origem(turnos: list[dict]) -> str:
    """Descobre o `origem_id` da bateria a partir do primeiro turno."""
    for t in turnos:
        origem = t.get("meta", {}).get("origem_id")
        if origem:
            return origem
    return turnos[0].get("sessao_id", "") if turnos else ""
