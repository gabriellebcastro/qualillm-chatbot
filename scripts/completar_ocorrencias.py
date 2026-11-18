"""Completa, sem chamar juiz, as ocorrências de relatórios gravados antes delas.

Relatórios anteriores a 27/10/2026 diziam que a métrica falhou e mostravam
três amostras sem lugar. Este script reconstrói a lista completa de falhas,
cada uma com estímulo, execução e turno, a partir do que já está em disco:

  - camada DETERMINÍSTICA: refeita sobre os mesmos logs. É código, então dá o
    mesmo resultado da avaliação original, com o detalhe completo (esperado,
    encontrado, trecho).
  - camada do JUIZ: lida do arquivo de julgamentos da mesma avaliação
    (`julgamentos__*__<instante>.jsonl`), que guarda cada veredito com o lugar.
    A justificativa do juiz não era gravada nessas avaliações; a ocorrência diz
    isso, em vez de inventar uma. As falhas do juiz (JSON cortado etc.) também
    não tinham lugar gravado e ficam só na contagem do relatório.

Valores, status e veredito não mudam. A procedência registra que as
ocorrências foram completadas depois da coleta.

Uso:
    python scripts/completar_ocorrencias.py              # todos os relatórios sem ocorrências
    python scripts/completar_ocorrencias.py 20261027T202952Z
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from avaliar_bateria import carregar_bateria  # noqa: E402
from eval import relatorio  # noqa: E402
from eval.relatorio import ABSTENCAO, CAMADA_DETERMINISTICA, CAMADA_JUIZ, ocorrencia  # noqa: E402

DIR_LOGS = RAIZ / "logs"
SEM_JUSTIFICATIVA = "(justificativa do juiz não gravada nesta avaliação)"

# Métrica do arquivo de julgamentos -> métricas do relatório que ela alimenta,
# o rótulo que é falha e o detalhe da ocorrência.
DO_JUIZ = {
    "precisao_faithfulness": (["precisao_faithfulness"], "nao_sustentada", "afirmação não sustentada"),
    "aderencia_groundedness": (["aderencia_groundedness"], "nao_sustentada", "afirmação não sustentada"),
    "robustez_resistencia": (["robustez_resistencia"], "false", "subversão apontada pelo juiz"),
    "seguranca_toxicidade": (["seguranca_sem_toxicidade", "seguranca_sem_toxicidade_turnos"], "true", "toxicidade apontada pelo juiz"),
    "confiabilidade_equivalencia_par": (["confiabilidade_consistencia_pares", "confiabilidade_consistencia_total"], "false", "par de reexecuções julgado não equivalente"),
    # Veredito BRUTO de uma comparação: o grupo só reprova se a disparidade
    # persistir, superar o piso interno e favorecer sempre o mesmo lado.
    "equidade_disparidade": (["equidade_sem_disparidade"], "true", "comparação julgada com disparidade (veredito bruto; o grupo só reprova com as três condições)"),
}


def _sessoes_por_estimulo(turnos: list[dict]) -> dict[str, str]:
    return {t.get("meta", {}).get("origem_id", ""): t.get("sessao_id", "") for t in turnos}


def _ocorrencias_do_juiz(caminho: Path, sessoes: dict[str, str]) -> dict[str, list[dict]]:
    """Ocorrências por métrica do relatório, a partir dos julgamentos."""
    saida: dict[str, list[dict]] = {}
    linhas = caminho.read_text(encoding="utf-8").splitlines()[1:]  # 1ª = cabeçalho
    for linha in linhas:
        item = json.loads(linha)
        regra = DO_JUIZ.get(item["metrica"])
        if not regra:
            continue
        metricas, rotulo_falha, detalhe = regra
        rotulo = item.get("rotulo_juiz")
        abstencao = rotulo == "evidencia_insuficiente"
        if rotulo != rotulo_falha and not abstencao:
            continue
        sessao = str(item.get("sessao_id", ""))
        if sessao.startswith("bateria__"):
            estimulo = relatorio._origem(sessao)
        elif " x " in sessao:  # equidade: "variante_a x variante_b"
            estimulo = sessao.split(" x ")[0]
            detalhe = f"{detalhe}: {sessao}"
            sessao = sessoes.get(estimulo, "")
        else:  # consistência: o id do estímulo
            estimulo, sessao = sessao, sessoes.get(sessao, "")
        evidencia = item.get("item_julgado") or item.get("resposta_bot") or ""
        if evidencia.startswith("AFIRMACAO: "):
            evidencia = evidencia.split("\n", 1)[0][len("AFIRMACAO: "):]
        oc = ocorrencia(
            CAMADA_JUIZ,
            "juiz se absteve (evidência insuficiente)" if abstencao else detalhe,
            estimulo=estimulo, sessao_id=sessao,
            execucao_id=str(item.get("execucao_id", "")).replace("x", "×"),
            turno_id=item.get("turno_id", ""),
            justificativa=item.get("justificativa") or SEM_JUSTIFICATIVA,
            evidencia=evidencia,
            tipo=ABSTENCAO if abstencao else relatorio.FALHA,
        )
        for m in metricas:
            saida.setdefault(m, []).append(oc)
    return saida


def completar(instante: str) -> None:
    relatorios = sorted(DIR_LOGS.glob(f"relatorio__*__{instante}.json"))
    if not relatorios:
        print(f"{instante}: nenhum relatório")
        return
    turnos, _ = carregar_bateria(DIR_LOGS)
    sessoes = _sessoes_por_estimulo(turnos)
    julgamentos = sorted(DIR_LOGS.glob(f"julgamentos__*__{instante}.jsonl"))
    do_juiz = _ocorrencias_do_juiz(julgamentos[0], sessoes) if julgamentos else {}

    for caminho in relatorios:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        categorias = [b["categoria"] for b in conteudo.get("categorias") or []]
        # Só a camada determinística: sem juiz, nenhuma chamada paga.
        secoes = relatorio.avaliar_categorias(turnos, usar_juiz=False, categorias=categorias)
        deterministicas = {
            s.metrica: [o for o in (s.ocorrencias or []) if o["camada"] == CAMADA_DETERMINISTICA]
            for s in secoes
        }
        total = 0
        for bloco in conteudo.get("categorias") or []:
            for m in bloco.get("metricas") or []:
                m["ocorrencias"] = deterministicas.get(m["metrica"], []) + do_juiz.get(m["metrica"], [])
                total += len(m["ocorrencias"])
        conteudo.setdefault("procedencia", {})["ocorrencias_completadas"] = {
            "em": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "deterministicas": "refeitas sobre os mesmos logs",
            "juiz": julgamentos[0].name if julgamentos else None,
            "justificativa_do_juiz": "não gravada nesta avaliação",
        }
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{caminho.name}: {total} ocorrência(s)")


def main(argv: list[str]) -> int:
    instantes = argv or sorted({
        p.stem.rsplit("__", 1)[-1] for p in DIR_LOGS.glob("relatorio__*.json")
    })
    for instante in instantes:
        completar(instante)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
