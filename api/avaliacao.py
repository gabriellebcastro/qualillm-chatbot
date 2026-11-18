"""Disparo e acompanhamento da avaliação (scripts/avaliar_bateria.py).

Mesmo padrão de `api/bateria.py`: roda o script existente como subprocesso, em
vez de reimplementar a avaliação na API. Duas diferenças importantes.

**Não há estado de retomada.** A avaliação não é retomável como a bateria: ela
lê os logs e escreve relatórios novos do zero. Então o progresso aqui é a
saída do próprio script, não uma contagem — e é honesto dizer isso na tela em
vez de inventar uma barra que não mede nada.

**O modelo do juiz é escolhido por variável de ambiente**, e não por argumento
novo no script. `config.py` foi desenhado para que trocar de provedor ou de
modelo seja só mudar o ambiente ("trocar de modelo é só mudar o .env"), e usar
essa mesma porta mantém a interface e a linha de comando com um único
mecanismo. Acrescentar `--juiz` criaria um segundo caminho para a mesma
decisão.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone

import config
from api import saidas

CAMINHO_SAIDA = config.DIR_LOGS / ".avaliacao_saida.log"
# Metadados da última rodada. Em memória eles sumiam a cada reinício da API.
CAMINHO_RODADA = config.DIR_LOGS / ".avaliacao_rodada.json"

_lock = threading.Lock()
_rodada: dict | None = None
_processo: subprocess.Popen | None = None


def rodando() -> bool:
    """Há uma avaliação em andamento agora?"""
    return _processo is not None and _processo.poll() is None


# Os dois eixos de escolha desta tela, que sao facilmente confundidos:
#   RECORTE  -> quais logs vao ser julgados (modelo, via, estimulo, data)
#   CATEGORIA -> quais metricas rodam sobre o que foi selecionado
_RECORTE = ("modelo", "via", "origem_id", "desde")


def recorte(params: dict) -> dict:
    """Só os filtros de log preenchidos."""
    return {k: params.get(k) for k in _RECORTE if params.get(k)}


def _comando(params: dict) -> list[str]:
    cmd = [sys.executable, str(config.RAIZ / "scripts" / "avaliar_bateria.py")]
    for categoria in params.get("categorias") or []:
        cmd += ["--categoria", categoria]
    if not params.get("com_juiz"):
        cmd.append("--sem-juiz")
    for chave, valor in recorte(params).items():
        cmd += [f"--{chave.replace('_', '-')}", str(valor)]
    return cmd


def _carregar_bateria():
    """Importa `carregar_bateria` do script, para a prévia usar a MESMA
    selecao que a execucao vai usar — duas implementacoes divergiriam, e a
    previa existe justamente para dizer o que vai acontecer."""
    import importlib.util
    caminho = config.RAIZ / "scripts" / "avaliar_bateria.py"
    spec = importlib.util.spec_from_file_location("avaliar_bateria", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.carregar_bateria


def plano(params: dict) -> dict:
    """O que este recorte selecionaria, sem julgar nada.

    Precisa aparecer antes da confirmacao pelo mesmo motivo da bateria: com o
    juiz, o custo cresce com o numero de turnos.
    """
    turnos, arquivos = _carregar_bateria()(config.DIR_LOGS, **recorte(params))
    modelos: dict[str, int] = {}
    vias: dict[str, int] = {}
    for t in turnos:
        meta = t.get("meta", {})
        m = meta.get("modelo_bot") or f"{meta.get('provedor')}:{meta.get('modelo')}"
        modelos[m] = modelos.get(m, 0) + 1
        vias[meta.get("via") or "?"] = vias.get(meta.get("via") or "?", 0) + 1
    return {
        "turnos": len(turnos),
        "arquivos": len(arquivos),
        "modelos": modelos,
        "vias": vias,
        "recorte": recorte(params),
        # Misturar modelos num relatorio so junta dois sistemas diferentes
        # num numero unico. A tela avisa; nao bloqueia, porque pode ser
        # intencional (ex.: medir "o sistema" independentemente do modelo).
        "mistura_modelos": len(modelos) > 1,
    }


def _ambiente(params: dict) -> dict:
    """Ambiente do subprocesso, com o juiz escolhido na interface."""
    env = os.environ.copy()
    # Sem isto o Python grava a saída em blocos de kilobytes quando ela vai
    # para arquivo, e a tela ficava minutos sem nenhuma linha, parecendo travada.
    env["PYTHONUNBUFFERED"] = "1"
    juiz = params.get("juiz_modelo")
    if juiz and ":" in juiz:
        provedor, _, modelo = juiz.partition(":")
        env["JUIZ_PROVEDOR"] = provedor
        env["JUIZ_MODELO"] = modelo
    return env


def iniciar(params: dict) -> dict:
    """Dispara a avaliação em segundo plano."""
    global _rodada, _processo
    with _lock:
        if rodando():
            raise RuntimeError("Ja existe uma avaliacao em andamento.")

        cmd = _comando(params)
        CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
        saidas.guardar_anterior(CAMINHO_SAIDA)
        saida = open(CAMINHO_SAIDA, "w", encoding="utf-8", errors="replace")
        _processo = subprocess.Popen(
            cmd, cwd=str(config.RAIZ), env=_ambiente(params),
            stdout=saida, stderr=subprocess.STDOUT,
        )
        juiz = params.get("juiz_modelo") or f"{config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}"
        _rodada = {
            "iniciado_em": datetime.now(timezone.utc).isoformat(),
            "parametros": params,
            "comando": " ".join(cmd[1:]),
            "juiz": juiz if params.get("com_juiz") else None,
            "pid": _processo.pid,
            "interrompida": False,
        }
        saidas.guardar_anterior(CAMINHO_RODADA)
        saidas.gravar_rodada(CAMINHO_RODADA, _rodada)
        return status()


def parar() -> bool:
    """Interrompe a avaliação em andamento.

    Diferente da bateria, aqui interromper pode deixar o trabalho pela metade:
    relatórios das categorias já concluídas ficam gravados, o resto não sai.
    """
    global _rodada
    with _lock:
        if not rodando():
            return False
        _processo.terminate()
        if _rodada:
            _rodada["interrompida"] = True
            saidas.gravar_rodada(CAMINHO_RODADA, _rodada)
        return True


def _linhas() -> list[str]:
    return saidas.ler_linhas(CAMINHO_SAIDA)


def _ultimas_linhas(n: int = 60) -> list[str]:
    """Fim da saída, sem as linhas de progresso (que viram a barra)."""
    uteis = [l for l in _linhas() if l.strip() and not l.startswith("PROGRESSO_")]
    return uteis[-n:]


def _progresso(terminou: bool) -> dict | None:
    """Andamento lido das linhas PROGRESSO_* que o script emite.

    O total de chamadas ao juiz é ESTIMADO antes de rodar (ver
    `relatorio.estimar_chamadas_juiz`), então a porcentagem é aproximada e
    fica em no máximo 99% até o processo terminar.
    """
    estimado = feitas = 0
    categoria = None
    for l in _linhas():
        partes = l.split()
        if not partes:
            continue
        if partes[0] == "PROGRESSO_ESTIMADO" and len(partes) > 1:
            estimado = int(partes[1])
        elif partes[0] == "PROGRESSO_JUIZ" and len(partes) > 1:
            feitas = int(partes[1])
        elif partes[0] == "PROGRESSO_CATEGORIA" and len(partes) > 2:
            i, n = partes[1].split("/")
            categoria = {"atual": partes[2], "indice": int(i), "total": int(n)}
    if not estimado and not categoria:
        return None
    if terminou:
        percentual = 100.0
    elif estimado:
        percentual = min(99.0, round(100 * feitas / estimado, 1))
    else:
        percentual = None
    return {
        "chamadas_feitas": feitas,
        "chamadas_estimadas": estimado,
        "percentual": percentual,
        "categoria": categoria,
        "aproximado": True,
    }


def status() -> dict:
    """Situação da avaliação atual ou da última."""
    # Depois de um reinício da API, a última rodada vem do disco; o processo
    # dela não é mais filho deste servidor, então não há código de saída.
    rodada = _rodada or saidas.ler_rodada(CAMINHO_RODADA)
    if rodada is None:
        # Rodada iniciada antes de os metadados irem para disco: mostra-se a
        # saída, que é o que existe.
        if not _linhas():
            return {"rodando": False, "houve_rodada": False, "saida": []}
        fim = datetime.fromtimestamp(CAMINHO_SAIDA.stat().st_mtime, timezone.utc)
        return {
            "rodando": False, "houve_rodada": True, "sem_metadados": True,
            "terminado_em": fim.isoformat(), "interrompida": False,
            "progresso": None, "saida": _ultimas_linhas(),
        }
    # Sem o processo (reinício), não há código de saída: conta como terminada
    # a rodada que não foi interrompida pela tela.
    terminou = (_processo.poll() == 0) if _processo else not rodada["interrompida"]
    return {
        "rodando": rodando(),
        "houve_rodada": True,
        "iniciado_em": rodada["iniciado_em"],
        "parametros": rodada["parametros"],
        "comando": rodada["comando"],
        "juiz": rodada["juiz"],
        "pid": rodada["pid"],
        "interrompida": rodada["interrompida"],
        "codigo_saida": _processo.poll() if _processo else None,
        "progresso": _progresso(terminou=terminou),
        "saida": _ultimas_linhas(),
    }
