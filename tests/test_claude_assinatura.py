"""Juiz pela assinatura (claude -p): comando montado e leitura da saída, sem
chamar o CLI de verdade."""
import json
import subprocess

import pytest

from instrumentacao.logger import extrair_tokens
from llm import claude_assinatura_client as mod


def _cliente(monkeypatch, saida: dict, codigo: int = 0):
    chamadas = []

    def falso_run(cmd, **kw):
        chamadas.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, codigo, stdout=json.dumps(saida), stderr="")

    monkeypatch.setattr(mod.subprocess, "run", falso_run)
    return mod.ClienteClaudeAssinatura("claude-haiku-5-5", executavel="claude"), chamadas


def test_monta_o_comando_isolado_e_le_a_resposta(monkeypatch):
    cliente, chamadas = _cliente(monkeypatch, {
        "is_error": False, "result": '{"resistiu": true}',
        "usage": {"input_tokens": 20, "cache_creation_input_tokens": 70,
                  "cache_read_input_tokens": 30, "output_tokens": 30},
    })
    r = cliente.gerar("PROMPT DO JUIZ", [{"role": "user", "content": "conteudo"}])

    cmd, kw = chamadas[0]
    # Sem ferramentas, sem as customizações do projeto, com o prompt do juiz.
    assert "--safe-mode" in cmd and cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "claude-haiku-5-5"
    prompt = cmd[cmd.index("--system-prompt-file") + 1]
    assert open(prompt, encoding="utf-8").read() == "PROMPT DO JUIZ"
    assert kw["input"] == "conteudo"
    assert r.texto == '{"resistiu": true}'
    assert extrair_tokens(r.bruto)[:2] == (120, 30)
    assert r.parametros["max_tokens"] is None   # o CLI não tem teto


def test_erro_do_cli_vira_excecao_com_a_mensagem(monkeypatch):
    # Sem login ou no limite da assinatura: o JuizLLM registra como falha.
    cliente, _ = _cliente(monkeypatch, {"is_error": True, "subtype": "error",
                                        "result": "limite de uso atingido"}, codigo=1)
    with pytest.raises(RuntimeError, match="limite de uso atingido"):
        cliente.gerar("p", [{"role": "user", "content": "c"}])


def test_provedor_registrado_sem_tocar_nos_outros(monkeypatch):
    from llm import criar_cliente
    monkeypatch.setattr(mod.shutil, "which", lambda _: "claude")
    assert criar_cliente("anthropic-assinatura", "claude-haiku-5-5").provedor == "anthropic-assinatura"
