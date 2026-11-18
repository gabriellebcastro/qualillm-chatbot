"""Adaptador do Claude pela ASSINATURA, via Claude Code CLI (`claude -p`).

Terceira via, ao lado da API da Anthropic e da OpenAI, e não substituta delas:
serve para TESTES sem gastar crédito de API — conferir o encanamento, repetir
uma avaliação depois de corrigir um defeito. O uso sai dos limites do plano
Claude de quem está logado no CLI.

Não é o mesmo instrumento da API, e por isso grava num lugar separado (ver
`scripts/avaliar_bateria.py`) e se identifica na procedência:

  - o raciocínio fica no padrão do CLI, e não desligado como na API;
  - não há teto de tokens de saída controlável (`max_tokens` é ignorado);
  - o custo que o CLI informa é estimativa, não cobrança.

Cada julgamento é um processo `claude -p`, com o prompt do juiz no lugar do
prompt do Claude Code (`--system-prompt-file`), sem nenhuma ferramenta
(`--tools ""`) e em `--safe-mode`, que não carrega CLAUDE.md, memória, skills,
plugins, hooks nem MCP — sem isso, as memórias do projeto entrariam no
contexto do juiz. O `--bare`, que seria o modo indicado para scripts, não
serve aqui: ele não usa o login da assinatura, só chave de API.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .interface import ClienteLLM, RespostaLLM

# Um julgamento longo leva segundos; o processo inteiro, com a subida do CLI,
# raramente passa de um minuto. Acima disto é travamento, e vira falha do juiz.
TEMPO_LIMITE_S = 300


class ClienteClaudeAssinatura(ClienteLLM):
    provedor = "anthropic-assinatura"

    def __init__(self, modelo: str, executavel: str | None = None) -> None:
        """`executavel` sobrepõe o `claude` do PATH (ou a variável CLAUDE_CLI)."""
        self.modelo = modelo
        self.executavel = executavel or os.getenv("CLAUDE_CLI") or shutil.which("claude")
        if not self.executavel:
            raise RuntimeError(
                "Claude Code CLI não encontrado. Instale-o e faça login com a "
                "assinatura (comando `claude`), ou aponte CLAUDE_CLI para o executável."
            )
        # Pasta vazia, fora do projeto: é o diretório de trabalho do processo,
        # para que nada do repositório seja descoberto, e onde fica o prompt.
        self._pasta = Path(tempfile.mkdtemp(prefix="juiz_assinatura_"))

    def _comando(self, caminho_prompt: Path) -> list[str]:
        return [
            self.executavel, "-p",
            "--safe-mode",
            "--tools", "",
            "--system-prompt-file", str(caminho_prompt),
            "--model", self.modelo,
            "--output-format", "json",
            "--no-session-persistence",
            "--max-turns", "1",
        ]

    def gerar(
        self,
        sistema: str,
        mensagens: list[dict],
        temperatura: float | None = None,
        max_tokens: int = 1024,
        formato_json: bool = False,
    ) -> RespostaLLM:
        """Uma chamada `claude -p`; devolve uma RespostaLLM padronizada.

        `temperatura` e `max_tokens` não têm equivalente no CLI e são
        ignorados — o registro diz isso, em vez de fingir que foram enviados.
        Falha do CLI (sem login, limite da assinatura) levanta exceção, que o
        `JuizLLM` registra como falha do juiz com a mensagem inteira.
        """
        del temperatura, formato_json
        caminho_prompt = self._pasta / "prompt_juiz.md"
        caminho_prompt.write_text(sistema, encoding="utf-8")
        # O juiz manda uma mensagem só; mais de uma vira transcrição simples.
        if len(mensagens) == 1:
            entrada = mensagens[0]["content"]
        else:
            entrada = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in mensagens)

        t0 = time.perf_counter()
        proc = subprocess.run(
            self._comando(caminho_prompt), input=entrada, cwd=str(self._pasta),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TEMPO_LIMITE_S,
        )
        latencia = time.perf_counter() - t0
        try:
            saida = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"claude -p saiu com código {proc.returncode} sem JSON: "
                f"{(proc.stdout or proc.stderr).strip()}"
            ) from None
        if saida.get("is_error") or proc.returncode != 0:
            raise RuntimeError(f"claude -p falhou ({saida.get('subtype')}): {saida.get('result')}")
        # O CLI divide a entrada em três campos — normal, gravada em cache e
        # lida do cache —, e numa chamada real quase tudo vem nos dois últimos
        # (2 + 2.556 + 649 tokens no teste de 28/10/2026). `extrair_tokens` lê
        # só `input_tokens`, então a entrada é somada aqui; o detalhe fica em
        # `usage_cli`.
        uso = saida.get("usage") or {}
        saida["usage_cli"] = uso
        saida["usage"] = {
            "input_tokens": sum(uso.get(c) or 0 for c in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            "output_tokens": uso.get("output_tokens") or 0,
        }

        return RespostaLLM(
            texto=saida.get("result") or "",
            modelo=self.modelo,
            provedor=self.provedor,
            parametros={
                "temperatura": None,
                "max_tokens": None,
                "raciocinio": "padrao_do_cli",
                "via": "assinatura (claude -p)",
            },
            latencia_s=latencia,
            # `usage` no mesmo formato da API (input/output_tokens), que é o
            # que `extrair_tokens` lê para somar o uso da avaliação.
            bruto=saida,
        )
