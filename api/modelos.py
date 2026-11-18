"""Catálogo de modelos disponíveis para cada papel (bot, juiz, simulador).

A lista é pedida AO PROVEDOR sempre que possível, em vez de escrita à mão: um
catálogo estático envelhece em silêncio e passa a oferecer modelos que a conta
não tem mais, ou a esconder os que ela ganhou.

O endpoint de listagem também serve de **teste de chave grátis**. Ele não gera
token nenhum, e a resposta distingue três situações que a interface precisava
separar e não separava:

  - chave ausente          -> nem adianta tentar
  - chave presente e válida -> lista real do provedor
  - chave presente e INVÁLIDA -> o `tem_chave: true` de antes mentia, porque
    só verificava que a variável existia no .env

O catálogo estático continua existindo como reserva, para a tela não ficar
vazia quando o provedor não responde — mas nesse caso a origem vem marcada,
para ninguém confundir "o provedor confirmou" com "alguém digitou aqui".
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import config

# Reserva usada quando o provedor não responde. Não é a verdade — é o melhor
# palpite para a tela não ficar vazia, e vem sempre marcada como tal.
CATALOGO_RESERVA: dict[str, tuple[str, ...]] = {
    # Conferidas contra a listagem real do provedor em 20/10/2026. A reserva
    # anterior era de 28/08 e já escondia metade do catálogo Claude: faltavam
    # haiku-5-5, opus-5-5, sonnet-5-5 e fable-5-1, justamente os mais novos e,
    # no caso do haiku, o mais barato para o papel de juiz.
    "deepseek": ("deepseek-flash", "deepseek-v4-pro"),
    "anthropic": (
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-sonnet-5",
        "claude-haiku-5-5",
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    ),
    # Voltou em 25/10/2026, quando a conta ganhou chave e crédito: é o
    # provedor do segundo juiz. Reserva conferida contra a listagem real.
    "openai": (
        "gpt-6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4-mini",
        "gpt-4.1",
    ),
}

# Papel -> provedor configurado no .env. É o provedor que o seletor mostra
# primeiro; os outros continuam disponíveis.
def _papeis() -> dict[str, dict]:
    return {
        "bot": {"provedor": config.BOT_PROVEDOR, "modelo": config.BOT_MODELO},
        "juiz": {"provedor": config.JUIZ_PROVEDOR, "modelo": config.JUIZ_MODELO},
        "simulador": {"provedor": config.SIMULADOR_PROVEDOR, "modelo": config.SIMULADOR_MODELO},
    }


def _consultar(provedor: str) -> tuple[list[str] | None, str | None]:
    """Pede a lista ao provedor. Devolve (modelos, erro) — um dos dois é None."""
    chave = config.chave_do_provedor(provedor)
    if not chave:
        return None, "chave nao configurada no .env"

    if provedor == "anthropic":
        url = "https://api.anthropic.com/v1/models?limit=100"
        headers = {"x-api-key": chave, "anthropic-version": "2023-06-01"}
        # Ver config.ANTHROPIC_WORKSPACE_ID: chave identity-linked exige.
        if config.ANTHROPIC_WORKSPACE_ID:
            headers["anthropic-workspace-id"] = config.ANTHROPIC_WORKSPACE_ID
    elif provedor == "deepseek":
        url = config.DEEPSEEK_BASE_URL.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {chave}"}
    elif provedor == "openai":
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {chave}"}
    else:
        return None, f"provedor desconhecido: {provedor}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            dados = json.loads(r.read().decode("utf-8"))
        return sorted(m["id"] for m in dados.get("data", []) if m.get("id")), None
    except urllib.error.HTTPError as e:
        detalhe = "chave invalida ou sem permissao" if e.code in (401, 403) else f"HTTP {e.code}"
        return None, detalhe
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


# Consultar o provedor a cada carregamento de tela seria desperdício: a lista
# muda raramente e a chamada tem latência de rede.
_cache: dict[str, tuple[float, dict]] = {}
_VALIDADE_S = 600


def provedores(forcar: bool = False) -> dict[str, dict]:
    """Estado de cada provedor: chave, validade e modelos disponíveis."""
    agora = time.time()
    saida: dict[str, dict] = {}
    for provedor in CATALOGO_RESERVA:
        em_cache = _cache.get(provedor)
        if em_cache and not forcar and agora - em_cache[0] < _VALIDADE_S:
            saida[provedor] = em_cache[1]
            continue

        chave = bool(config.chave_do_provedor(provedor))
        modelos, erro = _consultar(provedor) if chave else (None, "chave nao configurada no .env")
        info = {
            "provedor": provedor,
            "chave_configurada": chave,
            # None = não deu para saber; True/False = o provedor respondeu.
            "chave_valida": None if not chave else (erro is None),
            "erro": erro,
            "origem": "provedor" if modelos else "catalogo_reserva",
            "modelos": modelos if modelos else list(CATALOGO_RESERVA[provedor]),
        }
        _cache[provedor] = (agora, info)
        saida[provedor] = info
    return saida


def catalogo(forcar: bool = False) -> dict:
    """Papéis configurados + provedores, como a interface consome."""
    return {"papeis": _papeis(), "provedores": provedores(forcar)}
