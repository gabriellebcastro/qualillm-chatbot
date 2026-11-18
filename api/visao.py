"""Visão geral: o resumo que responde "como está o sistema agora?".

Compõe o que as outras telas já expõem. Duas decisões de leitura importam mais
que o código:

**O veredito de uma categoria é o PIOR dos vereditos das suas métricas.**
Precisão tem duas métricas; se uma atende e a outra não, a categoria não
atende. Mostrar "atende" porque a maioria passou esconderia exatamente o que
precisa ser visto. A ordem é: não atende > sem dados > não se aplica > atende.

**O estado de cada categoria vem do relatório de BATERIA mais recente**, não do
relatório mais recente de qualquer origem. Uma avaliação de conversa avulsa
mede nove turnos de um diálogo; a bateria mede centenas, sobre o inventário
inteiro. Deixar a primeira sobrescrever a segunda no painel principal daria a
impressão de que o sistema regrediu quando só mudou o tamanho da amostra.
Quando não existe relatório de bateria, o de conversa aparece marcado como tal.
"""
from __future__ import annotations

import json

import config
from api import estimulos, prompts
from instrumentacao import carregar_avaliacoes_tom, carregar_turnos

CATEGORIAS = (
    "confiabilidade", "precisao", "aderencia_contexto",
    "seguranca", "equidade", "robustez",
)

# Do pior para o melhor. É esta ordem que decide o veredito da categoria.
_GRAVIDADE = ("nao_atende", "sem_dados", "sem_limiar", "nao_aplicavel", "atende")


def _pior(status: list[str]) -> str:
    """O veredito que representa o conjunto: o pior que aparecer."""
    for s in _GRAVIDADE:
        if s in status:
            return s
    return "sem_dados"


def _relatorios_por_categoria() -> dict[str, dict]:
    """Último relatório de cada categoria, preferindo os de bateria."""
    melhores: dict[str, dict] = {}
    for caminho in config.DIR_LOGS.glob("relatorio__*.json"):
        partes = caminho.stem.split("__")
        if len(partes) >= 4:
            escopo, categoria, momento = partes[1], partes[2], partes[3]
        elif len(partes) == 3:
            escopo, categoria, momento = "", partes[1], partes[2]
        else:
            continue
        if categoria not in CATEGORIAS:
            continue

        atual = melhores.get(categoria)
        de_bateria = escopo == ""
        # Bateria vence conversa avulsa; entre iguais, o mais recente vence.
        if atual is None or (de_bateria, momento) > (atual["_de_bateria"], atual["momento"]):
            melhores[categoria] = {
                "nome": caminho.stem, "momento": momento, "escopo": escopo,
                "_de_bateria": de_bateria, "_caminho": caminho,
            }
    return melhores


def _estado_das_categorias() -> list[dict]:
    """Uma linha por categoria, com o veredito consolidado."""
    relatorios = _relatorios_por_categoria()
    saida = []
    for categoria in CATEGORIAS:
        info = relatorios.get(categoria)
        if info is None:
            saida.append({
                "categoria": categoria, "status": "nunca_avaliada",
                "metricas": [], "relatorio": None, "momento": None,
                "escopo": None, "de_bateria": None, "usou_juiz": None,
                "n_turnos": None,
            })
            continue
        try:
            conteudo = json.loads(info["_caminho"].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        metricas = [m for b in conteudo.get("categorias", []) for m in b.get("metricas", [])]
        proc = conteudo.get("procedencia") or {}
        saida.append({
            "categoria": categoria,
            "status": _pior([m.get("status", "sem_dados") for m in metricas]),
            "metricas": metricas,
            "relatorio": info["nome"],
            "momento": info["momento"],
            "escopo": info["escopo"],
            "de_bateria": info["_de_bateria"],
            "usou_juiz": proc.get("usou_juiz"),
            "n_turnos": proc.get("n_turnos"),
        })
    return saida


def resumo() -> dict:
    """Contadores, estado das categorias e as últimas conversas."""
    manuais = sorted(config.DIR_LOGS_MANUAIS.glob("web-*.jsonl"))
    execucoes = sorted(config.DIR_LOGS.glob("bateria__*.jsonl"))

    turnos_bateria = 0
    episodios = 0
    for caminho in execucoes:
        turnos = carregar_turnos(caminho)
        turnos_bateria += len(turnos)
        episodios += len({t.get("execucao_id", 0) for t in turnos})

    ultimas = []
    notas_tom = []
    for caminho in manuais:
        turnos = carregar_turnos(caminho)
        if not turnos:
            continue
        for aval in carregar_avaliacoes_tom(caminho).values():
            if isinstance(aval.get("tom_nota"), (int, float)):
                notas_tom.append(aval["tom_nota"])
        ultimas.append({
            "sessao_id": caminho.stem,
            "turnos": len(turnos),
            "inicio": turnos[0].get("timestamp"),
            "acordo_fechado": bool(turnos[-1].get("estado", {}).get("acordo_id")),
        })
    ultimas.sort(key=lambda s: s["inicio"] or "", reverse=True)

    return {
        "contadores": {
            "sessoes_manuais": len(ultimas),
            "execucoes_bateria": len(execucoes),
            "episodios_bateria": episodios,
            "turnos_bateria": turnos_bateria,
            "estimulos": len(estimulos.catalogo()),
            "prompts": len(prompts.CATALOGO),
            "relatorios": len(list(config.DIR_LOGS.glob("relatorio__*.json"))),
        },
        "categorias": _estado_das_categorias(),
        "ultimas_sessoes": ultimas[:5],
        "tom": {
            "media": round(sum(notas_tom) / len(notas_tom), 2) if notas_tom else None,
            "n_sessoes": len(notas_tom),
        },
    }
