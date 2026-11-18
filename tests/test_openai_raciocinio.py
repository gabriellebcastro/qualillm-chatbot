"""O juiz da OpenAI roda sem raciocínio, como o Haiku.

Defeito de 28/10/2026: o gpt-6-luna não entrava na família de raciocínio e
sairia com o esforço padrão (medium), `max_tokens` e temperatura.
"""
from types import SimpleNamespace

import pytest

from llm.openai_client import ClienteOpenAI


class _Completions:
    def __init__(self):
        self.params = None

    def create(self, **params):
        self.params = params
        msg = SimpleNamespace(content='{"ok": true}')
        uso = SimpleNamespace(prompt_tokens=1, completion_tokens=1)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=uso,
                               model_dump=lambda: {})


@pytest.mark.parametrize("modelo", ["gpt-5.6-terra", "gpt-6-luna"])
def test_juiz_openai_vai_sem_raciocinio(modelo):
    cliente = ClienteOpenAI.__new__(ClienteOpenAI)
    cliente.modelo = modelo
    completions = _Completions()
    cliente._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    cliente.gerar("sistema", [{"role": "user", "content": "oi"}],
                  temperatura=0, max_tokens=100, formato_json=True)
    p = completions.params
    assert p["reasoning_effort"] == "none"
    assert p["max_completion_tokens"] == 100
    assert "max_tokens" not in p and "temperature" not in p
    assert p["response_format"] == {"type": "json_object"}


# --- Registro do raciocínio efetivo na procedência ---------------------------
class _CompletionsRecusaNone:
    """Recusa "none" na primeira chamada, como um modelo que só vai até "low"."""

    def __init__(self):
        self.recusou = False

    def create(self, **params):
        if params.get("reasoning_effort") == "none" and not self.recusou:
            self.recusou = True
            raise ValueError("Unsupported value: 'reasoning_effort' does not support 'none'")
        msg = SimpleNamespace(content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               model_dump=lambda: {"usage": {}})


class _MessagesAnthropic:
    def __init__(self):
        self.params = None

    def create(self, **params):
        self.params = params
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"ok": true}')],
                               model_dump=lambda: {"usage": {}})


def _juiz_com(cliente, monkeypatch, provedor):
    from eval import juiz
    import config
    monkeypatch.setattr(config, "JUIZ_PROVEDOR", provedor)
    juiz.limpar_falhas()
    return juiz, juiz.JuizLLM("prompt_juiz_toxicidade.md", cliente_llm=cliente, temperatura=0)


def test_uso_do_juiz_conta_chamadas_por_raciocinio_efetivo_na_openai(monkeypatch):
    """A recusa de "none" cai para "low" sem rastro no que é enviado; o
    registro é o que diz em que condição o juiz de fato rodou."""
    cliente = ClienteOpenAI.__new__(ClienteOpenAI)
    cliente.modelo = "gpt-6-luna"
    completions = _CompletionsRecusaNone()
    cliente._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    juiz, j = _juiz_com(cliente, monkeypatch, "openai")
    for _ in range(3):
        j.julgar("conteudo")
    uso = juiz.uso_registrado()
    assert uso["raciocinio_efetivo"] == {"low": 1, "none": 2}
    assert uso["raciocinio_parametro"] == "reasoning_effort"
    juiz.limpar_falhas()
    assert juiz.uso_registrado()["raciocinio_efetivo"] == {}


def test_uso_do_juiz_registra_o_thinking_enviado_na_anthropic(monkeypatch):
    from llm.anthropic_client import ClienteAnthropic
    cliente = ClienteAnthropic.__new__(ClienteAnthropic)
    cliente.modelo = "claude-haiku-5-5"
    mensagens = _MessagesAnthropic()
    cliente._client = SimpleNamespace(messages=mensagens)
    juiz, j = _juiz_com(cliente, monkeypatch, "anthropic")
    j.julgar("conteudo")
    j.julgar("conteudo")
    uso = juiz.uso_registrado()
    assert mensagens.params["thinking"] == {"type": "disabled"}, "o envio não muda"
    assert uso["raciocinio_efetivo"] == {"disabled": 2}
    assert uso["raciocinio_parametro"] == "thinking.type"


# --- Experimento #39: raciocínio ligado no esforço padrão ---------------------
def test_openai_com_raciocinio_padrao_pede_medium():
    cliente = ClienteOpenAI.__new__(ClienteOpenAI)
    cliente.modelo = "gpt-6-luna"
    cliente.raciocinio_padrao = True
    completions = _Completions()
    cliente._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    r = cliente.gerar("s", [{"role": "user", "content": "oi"}], max_tokens=100, formato_json=True)
    assert completions.params["reasoning_effort"] == "medium"
    assert r.parametros["raciocinio"] == "medium"


def test_anthropic_com_raciocinio_padrao_pede_adaptativo():
    from llm.anthropic_client import ClienteAnthropic
    cliente = ClienteAnthropic.__new__(ClienteAnthropic)
    cliente.modelo = "claude-haiku-5-5"
    cliente.raciocinio_padrao = True
    mensagens = _MessagesAnthropic()
    cliente._client = SimpleNamespace(messages=mensagens)
    r = cliente.gerar("s", [{"role": "user", "content": "oi"}], max_tokens=100)
    assert mensagens.params["thinking"] == {"type": "adaptive"}
    assert mensagens.params["output_config"] == {"effort": "medium"}
    assert r.parametros["raciocinio"] == "adaptive/medium"


def test_anthropic_sem_a_opcao_continua_desligado():
    from llm.anthropic_client import ClienteAnthropic
    cliente = ClienteAnthropic.__new__(ClienteAnthropic)
    cliente.modelo = "claude-haiku-5-5"
    mensagens = _MessagesAnthropic()
    cliente._client = SimpleNamespace(messages=mensagens)
    r = cliente.gerar("s", [{"role": "user", "content": "oi"}], max_tokens=100)
    assert mensagens.params["thinking"] == {"type": "disabled"}
    assert "output_config" not in mensagens.params
    assert r.parametros["raciocinio"] == "disabled"
