"""Guarda a saída de terminal de cada rodada antes de a seguinte começar.

A bateria e a avaliação escrevem a saída do processo num arquivo fixo
(`logs/.bateria_saida.log`, `logs/.avaliacao_saida.log`), que as telas leem
para mostrar o acompanhamento. Aberto em modo de escrita a cada rodada, ele
apagava a saída da rodada anterior. Os dados não se perdiam (conversas e
relatórios têm arquivos próprios), mas a saída é parte do histórico de cada
rodada, e a regra do projeto é que nada sobrescreva nada.

Os metadados da rodada (comando, parâmetros, plano) também vão para disco.
Ficavam só na memória do servidor, e um reinício da API fazia a tela dizer
que nunca houve rodada, com a saída inteira gravada ao lado.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import config

DIR_SAIDAS = config.DIR_LOGS / "saidas"

# Nome das cópias: `<tipo>_saida__AAAAMMDDTHHMMSSZ[_n].log`. A rota que lê
# uma cópia só aceita nomes neste formato, o que barra caminho com "..".
_NOME_COPIA = re.compile(r"^(bateria|avaliacao)_saida__(\d{8}T\d{6}Z)(?:_\d+)?\.log$")


def guardar_anterior(caminho: Path) -> Path | None:
    """Copia `caminho` para `logs/saidas/`, com o instante da última escrita
    no nome, e devolve a cópia. Não faz nada se o arquivo não existir ou
    estiver vazio. Nunca sobrescreve uma cópia já guardada."""
    if not caminho.exists() or caminho.stat().st_size == 0:
        return None
    instante = datetime.fromtimestamp(caminho.stat().st_mtime, timezone.utc)
    nome = caminho.name.lstrip(".")
    sufixo = Path(nome).suffix
    nome = nome.removesuffix(sufixo)
    DIR_SAIDAS.mkdir(parents=True, exist_ok=True)
    destino = DIR_SAIDAS / f"{nome}__{instante:%Y%m%dT%H%M%SZ}{sufixo}"
    n = 1
    while destino.exists():
        n += 1
        destino = DIR_SAIDAS / f"{nome}__{instante:%Y%m%dT%H%M%SZ}_{n}{sufixo}"
    shutil.copy2(caminho, destino)
    return destino


def gravar_rodada(caminho: Path, rodada: dict) -> None:
    """Grava os metadados da rodada. Na primeira escrita de uma rodada nova,
    quem chama guarda antes os da anterior (`guardar_anterior`)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(rodada, ensure_ascii=False, indent=2), encoding="utf-8")


def ler_rodada(caminho: Path) -> dict | None:
    """Metadados da última rodada, ou None se não houver ou estiverem ilegíveis."""
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ler_linhas(caminho: Path) -> list[str]:
    try:
        return caminho.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def listar(tipo: str) -> list[dict]:
    """Saídas guardadas de rodadas anteriores, da mais recente para a mais antiga."""
    itens = []
    for p in DIR_SAIDAS.glob(f"{tipo}_saida__*.log"):
        m = _NOME_COPIA.match(p.name)
        if not m:
            continue
        instante = datetime.strptime(m.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        # Fim da saída: o resumo que o script imprime ao terminar.
        fim = [l for l in ler_linhas(p)[-8:] if l.strip()]
        itens.append({
            "arquivo": p.name,
            "terminado_em": instante.isoformat(),
            "tamanho": p.stat().st_size,
            "fim": fim,
        })
    return sorted(itens, key=lambda i: i["arquivo"], reverse=True)


def ler(tipo: str, arquivo: str) -> list[str] | None:
    """Conteúdo de uma saída guardada; None se o nome não for de uma cópia."""
    m = _NOME_COPIA.match(arquivo)
    if not m or m.group(1) != tipo:
        return None
    caminho = DIR_SAIDAS / arquivo
    return ler_linhas(caminho) if caminho.exists() else None
