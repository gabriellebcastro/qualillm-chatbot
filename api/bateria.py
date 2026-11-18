"""Disparo e acompanhamento da bateria de testes.

Esta é a única parte da API que causa efeito caro e irreversível: cada
episódio é ao menos uma chamada de API paga, e uma rodada completa leva
dezenas de minutos. Três decisões saem daí.

**Roda o script, não reimplementa.** `scripts/rodar_bateria.py` é invocado
como subprocesso, com os mesmos argumentos da linha de comando. Reescrever a
lógica aqui criaria um segundo caminho de execução que poderia divergir do
que foi usado nas medições anteriores — e comparabilidade entre rodadas é o
que sustenta o experimento.

**O progresso vem dos próprios logs**, derivado pelo mesmo código que a
execução usa, e não de um canal paralelo. Um contador próprio poderia discordar do arquivo que
manda de verdade na retomada.

**Fechar a aba não interrompe nada.** O processo é filho do servidor, não da
requisição. Isso é intencional: uma rodada de 40 minutos não pode depender de
a janela ficar aberta.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import config
from api import estimulos, saidas

CAMINHO_SAIDA = config.DIR_LOGS / ".bateria_saida.log"
# Metadados da última rodada. Em memória eles sumiam a cada reinício da API.
CAMINHO_RODADA = config.DIR_LOGS / ".bateria_rodada.json"

_lock = threading.Lock()
_rodada: dict | None = None   # metadados da rodada atual/última
_processo: subprocess.Popen | None = None


# --- Estado de retomada gravado pelo runner --------------------------------
def _runner():
    """Importa `scripts/rodar_bateria.py` por caminho.

    A retomada é DERIVADA dos logs, e a derivação precisa ser a MESMA que a
    execução usa — duas implementações divergiriam, que é exatamente o
    problema que o arquivo de estado criou antes de ser removido.
    """
    import importlib.util
    caminho = config.RAIZ / "scripts" / "rodar_bateria.py"
    spec = importlib.util.spec_from_file_location("rodar_bateria", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _episodios_concluidos(desde: str | None = None) -> set[str]:
    """Chaves dos episódios já feitos, no formato `via|origem|modelo|repN`.

    Reconstruídas dos logs pelo próprio runner. Não há arquivo de estado: ele
    existia, divergiu em silêncio (declarava 4 episódios quando os logs tinham
    160) e foi substituído por derivação. Com `desde`, só os concluídos a
    partir desse instante.
    """
    try:
        return _runner().episodios_concluidos(desde=desde)
    except Exception:  # noqa: BLE001
        # Sem a derivação, tratar como "nada concluído" é o lado seguro: a
        # tela mostra MAIS episódios a rodar do que o real, em vez de menos.
        return set()


def _modelos(modelo: str | None) -> list[str]:
    """Modelos de bot desta rodada, como "provedor:modelo"."""
    if modelo:
        return [modelo]
    return [f"{p}:{m}" for p, m in config.MODELOS_BOT]


def plano(
    via: str | None = None,
    origem_id: str | None = None,
    categoria: str | None = None,
    modelo: str | None = None,
    repeticoes: int | None = None,
    recomecar: bool = False,
    # Aceito e ignorado: trocar o modelo do simulador muda o conteúdo das
    # conversas, não quantas acontecem, então não entra na estimativa de
    # custo. Está na assinatura porque `iniciar` repassa os parâmetros
    # inteiros, e um campo novo no esquema quebraria a chamada aqui.
    simulador_modelo: str | None = None,
) -> dict:
    """O que uma rodada com estes filtros faria — SEM executar nada.

    Distingue planejado de restante porque a bateria é retomável: sem
    `--recomecar`, os episódios já concluídos são pulados. Mostrar só o
    total planejado faria alguém confirmar uma rodada de 160 episódios que
    na prática não faria nenhum.
    """
    selecionados = [
        e for e in estimulos.catalogo()
        if (not via or e["via"] == via)
        and (not origem_id or e["id"] == origem_id)
        and (not categoria or categoria in e["categorias_alvo"])
    ]
    modelos = _modelos(modelo)
    concluidos = set() if recomecar else _episodios_concluidos()

    esperados: list[str] = []
    for e in selecionados:
        n = estimulos.repeticoes(e["conteudo"], repeticoes)
        for m in modelos:
            for rep in range(1, n + 1):
                esperados.append(f"{e['via']}|{e['id']}|{m}|rep{rep}")

    restantes = [k for k in esperados if k not in concluidos]
    return {
        "estimulos": len(selecionados),
        "modelos": modelos,
        "episodios_planejados": len(esperados),
        "episodios_ja_feitos": len(esperados) - len(restantes),
        "episodios_restantes": len(restantes),
        "recomecar": recomecar,
        "ids": [e["id"] for e in selecionados],
        # Guardadas para o acompanhamento: o progresso é a interseção destas
        # com o estado em disco, e não um replanejamento (ver `status`).
        "chaves": esperados,
    }


# --- Execução --------------------------------------------------------------
def _comando(params: dict) -> list[str]:
    """Monta a linha de comando equivalente à que se digitaria no terminal."""
    cmd = [sys.executable, str(config.RAIZ / "scripts" / "rodar_bateria.py")]
    for chave, flag in (
        ("via", "--via"), ("origem_id", "--origem-id"),
        ("categoria", "--categoria"), ("modelo", "--modelo"),
    ):
        if params.get(chave):
            cmd += [flag, str(params[chave])]
    if params.get("repeticoes"):
        cmd += ["--repeticoes", str(params["repeticoes"])]
    if params.get("recomecar"):
        cmd.append("--recomecar")
    return cmd


def _ambiente(params: dict) -> dict:
    """Ambiente do subprocesso, com o simulador escolhido na interface.

    O runner lê `config.SIMULADOR_PROVEDOR/MODELO`, e `config` resolve as
    variáveis no import — que no subprocesso acontece depois deste ponto.
    Por isso a escolha viaja por ambiente, e não por flag: é o mesmo caminho
    que `api/avaliacao.py` usa para o juiz, e não exige argumento novo no
    script, que continua sendo o mesmo comando que se digitaria no terminal.
    """
    env = os.environ.copy()
    # Sem isto o Python grava a saída em blocos de kilobytes quando ela vai
    # para arquivo, e a tela ficava minutos sem nenhuma linha, parecendo travada.
    env["PYTHONUNBUFFERED"] = "1"
    sim = params.get("simulador_modelo")
    if sim and ":" in sim:
        provedor, _, modelo = sim.partition(":")
        env["SIMULADOR_PROVEDOR"] = provedor
        env["SIMULADOR_MODELO"] = modelo
    return env


def rodando() -> bool:
    """Há uma rodada em andamento agora?"""
    return _processo is not None and _processo.poll() is None


def iniciar(params: dict) -> dict:
    """Dispara a bateria em segundo plano. Erro se já houver uma rodando."""
    global _rodada, _processo
    with _lock:
        if rodando():
            raise RuntimeError("Ja existe uma bateria em andamento.")

        p = plano(**params)
        cmd = _comando(params)
        CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
        saidas.guardar_anterior(CAMINHO_SAIDA)
        saida = open(CAMINHO_SAIDA, "w", encoding="utf-8", errors="replace")
        _processo = subprocess.Popen(
            cmd, cwd=str(config.RAIZ), env=_ambiente(params),
            stdout=saida, stderr=subprocess.STDOUT,
        )
        _rodada = {
            "iniciado_em": datetime.now(timezone.utc).isoformat(),
            "parametros": params,
            "comando": " ".join(cmd[1:]),  # sem o caminho do interpretador
            # Registrado porque não aparece no comando: viaja por ambiente, e
            # sem isto a rodada não diria quem interpretou o cliente.
            "simulador": params.get("simulador_modelo")
                         or f"{config.SIMULADOR_PROVEDOR}:{config.SIMULADOR_MODELO}",
            "plano_inicial": p,
            "pid": _processo.pid,
            "interrompida": False,
        }
        saidas.guardar_anterior(CAMINHO_RODADA)
        saidas.gravar_rodada(CAMINHO_RODADA, _rodada)
        return status()


def parar() -> bool:
    """Interrompe a rodada. O progresso já feito permanece: o runner grava
    incrementalmente e retoma de onde parou na próxima vez."""
    global _rodada
    with _lock:
        if not rodando():
            return False
        _processo.terminate()
        if _rodada:
            _rodada["interrompida"] = True
            saidas.gravar_rodada(CAMINHO_RODADA, _rodada)
        return True


def _ultimas_linhas(n: int = 40) -> list[str]:
    """Fim da saída do runner, para acompanhar o que ele está fazendo."""
    return [l for l in saidas.ler_linhas(CAMINHO_SAIDA)[-n:] if l.strip()]


def _sem_metadados() -> dict:
    """Rodada com saída em disco mas sem metadados: iniciada antes de eles
    irem para disco. Mostra-se a saída, que é o que existe."""
    if not CAMINHO_SAIDA.exists() or CAMINHO_SAIDA.stat().st_size == 0:
        return {"rodando": False, "houve_rodada": False, "saida": []}
    fim = datetime.fromtimestamp(CAMINHO_SAIDA.stat().st_mtime, timezone.utc)
    return {
        "rodando": False, "houve_rodada": True, "sem_metadados": True,
        "terminado_em": fim.isoformat(), "interrompida": False,
        "saida": _ultimas_linhas(),
    }


def status() -> dict:
    """Situação da rodada atual ou da última, com progresso medido no disco."""
    ativo = rodando()
    # Depois de um reinício da API, a última rodada vem do disco; o processo
    # dela não é mais filho deste servidor, então não há código de saída.
    rodada = _rodada or saidas.ler_rodada(CAMINHO_RODADA)
    if rodada is None:
        return _sem_metadados()

    inicial = rodada["plano_inicial"]
    # Progresso = quantas das chaves planejadas foram concluídas DESDE o
    # início desta rodada.
    #
    # Antes a interseção era com tudo o que havia nos logs, e o comentário
    # supunha que `--recomecar` zerava um arquivo de estado que já não existe.
    # Os logs só acumulam: a rodada nova repete as chaves (via, estímulo,
    # modelo, rep 1..N) da anterior, a interseção nascia cheia e a barra
    # ficava em 100% a rodada inteira. O corte por instante vale para os dois
    # modos: sem `--recomecar`, as chaves já feitas nem rodam de novo.
    esperadas = set(inicial.get("chaves") or [])
    agora = _episodios_concluidos(desde=rodada["iniciado_em"])
    alvo = inicial["episodios_restantes"]
    feitos = max(0, min(len(esperadas & agora), alvo))
    restantes = alvo - feitos

    codigo = _processo.poll() if _processo else None

    # Episódio em curso: a última linha "  [via] estimulo · modelo · rep k/n"
    # que o runner imprimiu. A barra só anda quando um episódio TERMINA, e um
    # roteiro de seis turnos leva dezenas de segundos — sem isto a tela parece
    # parada no meio dele.
    atual = next(
        (l.strip() for l in reversed(_ultimas_linhas(80)) if l.lstrip().startswith("[")),
        None,
    )
    # Tempo restante pela média dos episódios desta rodada.
    decorrido = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(rodada["iniciado_em"])).total_seconds()
    restante_s = round(decorrido / feitos * restantes) if feitos and ativo else None
    return {
        "rodando": ativo,
        "houve_rodada": True,
        "iniciado_em": rodada["iniciado_em"],
        "parametros": rodada["parametros"],
        "comando": rodada["comando"],
        "simulador": rodada.get("simulador"),
        "pid": rodada["pid"],
        "interrompida": rodada["interrompida"],
        "codigo_saida": codigo,
        "progresso": {
            "alvo": alvo,
            "feitos": feitos,
            "restantes": restantes,
            "percentual": round(100 * feitos / alvo, 1) if alvo else 100.0,
            "episodio_atual": atual if ativo else None,
            "decorrido_s": round(decorrido),
            "restante_estimado_s": restante_s,
        },
        "plano_inicial": inicial,
        "saida": _ultimas_linhas(),
    }
