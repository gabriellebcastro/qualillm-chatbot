"""Testes do tratamento de resposta em branco do provedor.

O modo JSON do DeepSeek às vezes devolve conteúdo só com espaços — falha
conhecida e assumida na documentação oficial do provedor (ver
`ClienteDeepSeek.TENTATIVAS_RESPOSTA_VAZIA`). Estes testes cobrem as duas
defesas: repetir a chamada no adaptador, e não deixar a resposta em branco
poluir o histórico da conversa.

Sem API: o adaptador é exercitado com um duplo do SDK, e o bot com duplos das
suas dependências. Não é "teste falso da IA" — o que está sob teste aqui é o
código de resiliência em volta dela, cujo comportamento precisa ser
determinístico justamente porque a falha do provedor não é.
"""
from __future__ import annotations

import pytest

from bot import Chatbot
from llm.openai_client import ClienteOpenAI


# --- Duplos do SDK da OpenAI ------------------------------------------------
class _Mensagem:
    def __init__(self, content: str) -> None:
        self.content = content


class _Escolha:
    def __init__(self, content: str) -> None:
        self.message = _Mensagem(content)


class _Resposta:
    def __init__(self, content: str) -> None:
        self.choices = [_Escolha(content)]

    def model_dump(self) -> dict:
        return {"choices": [{"message": {"content": self.choices[0].message.content}}]}


class _CompletionsFalsa:
    """Devolve, em ordem, os conteúdos programados; conta as chamadas e
    guarda as mensagens recebidas em cada uma (para inspecionar o retry)."""

    def __init__(self, conteudos: list[str]) -> None:
        self._conteudos = list(conteudos)
        self.chamadas = 0
        self.mensagens_por_chamada: list[list[dict]] = []

    def create(self, **kwargs):
        self.chamadas += 1
        self.mensagens_por_chamada.append(list(kwargs.get("messages") or []))
        # Repete o último conteúdo se as tentativas passarem do programado.
        conteudo = self._conteudos[min(self.chamadas - 1, len(self._conteudos) - 1)]
        return _Resposta(conteudo)


class _ClienteFalso:
    def __init__(self, conteudos: list[str]) -> None:
        self.chat = type("_Chat", (), {"completions": _CompletionsFalsa(conteudos)})()


def _montar_cliente(
    conteudos: list[str], politica: tuple[int | None, ...] = (None,)
) -> ClienteOpenAI:
    """Cria um ClienteOpenAI com o SDK substituído por um duplo.

    `politica` é o HISTORICO_POR_TENTATIVA: quanto histórico mandar em cada
    tentativa (None = tudo, N = as N últimas mensagens).
    """
    cliente = ClienteOpenAI.__new__(ClienteOpenAI)  # sem __init__: não precisa de chave
    cliente.modelo = "modelo-de-teste"
    cliente.HISTORICO_POR_TENTATIVA = politica
    cliente._client = _ClienteFalso(conteudos)
    return cliente


# Conversa com histórico + bloco de contexto (system no meio) + pergunta
# atual — a mesma estrutura que o bot monta a cada turno.
_CONVERSA = [
    {"role": "user", "content": "oi"},
    {"role": "assistant", "content": "Olá! Qual seu CPF?"},
    {"role": "user", "content": "000.111.222-04"},
    {"role": "assistant", "content": "Encontrei sua dívida..."},
    {"role": "system", "content": "DADOS DA FONTE DE VERDADE: ..."},
    {"role": "user", "content": "não consigo pagar nesse dia"},
]


# --- Retry no adaptador -----------------------------------------------------
def test_repete_a_chamada_quando_a_resposta_vem_em_branco():
    """Duas respostas em branco seguidas de uma válida: deve repetir e
    entregar a válida, registrando quantas tentativas foram gastas."""
    cliente = _montar_cliente(["   ", "  ", '{"resposta": "ok"}'], politica=(None, 2, 0))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.texto == '{"resposta": "ok"}'
    assert resposta.tentativas == 3
    assert cliente._client.chat.completions.chamadas == 3


def test_nao_repete_quando_a_primeira_resposta_ja_e_valida():
    """O retry não pode custar chamadas extras no caminho feliz."""
    cliente = _montar_cliente(['{"resposta": "ok"}'], politica=(None, 2, 0))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.tentativas == 1
    assert cliente._client.chat.completions.chamadas == 1


def test_falha_fechada_quando_todas_as_tentativas_vem_em_branco():
    """Esgotadas as tentativas, devolve o branco mesmo — sem exceção
    surpresa. Quem chama é que decide o que fazer (o bot não registra acordo,
    a interface avisa o usuário)."""
    cliente = _montar_cliente(["   "], politica=(None, 2, 0))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert not resposta.texto.strip()
    assert resposta.tentativas == 3
    assert cliente._client.chat.completions.chamadas == 3


def test_sem_retry_configurado_chama_uma_unica_vez():
    """O padrão do adaptador OpenAI puro é não repetir (a falha é conhecida
    do DeepSeek, não de todo provedor compatível)."""
    cliente = _montar_cliente(["   "], politica=(None,))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.tentativas == 1
    assert cliente._client.chat.completions.chamadas == 1


# --- Degradação gradual do contexto -----------------------------------------
def test_segunda_tentativa_preserva_o_ultimo_par_da_conversa():
    """Repetir idêntico resgata pouco (5 de 126 falhas numa bateria real);
    reduzir o histórico resgata muito mais. Por isso a 2ª tentativa já corta
    o histórico, mas mantém o último par — 5 de 6 resgates nos testes, SEM
    perder a continuidade do diálogo."""
    cliente = _montar_cliente(["  ", '{"resposta": "ok"}'], politica=(None, 2, 0))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.texto == '{"resposta": "ok"}'
    assert resposta.historico_enviado == 2
    assert resposta.historico_reduzido is True

    chamadas = cliente._client.chat.completions.mensagens_por_chamada
    # 1ª: conversa inteira (prompt de sistema + 6 mensagens).
    assert len(chamadas[0]) == len(_CONVERSA) + 1
    # 2ª: sistema + as 2 últimas do histórico + bloco de contexto + pergunta.
    assert [m["role"] for m in chamadas[1]] == [
        "system", "user", "assistant", "system", "user",
    ]
    assert chamadas[1][1]["content"] == "000.111.222-04"
    assert chamadas[1][-1]["content"] == "não consigo pagar nesse dia"


def test_ultima_tentativa_descarta_o_historico_inteiro():
    """Último recurso, quando nem o histórico reduzido resolve: manda só o
    enquadramento do turno. Perde o fio da conversa, mas os dados sobrevivem
    porque o bloco de contexto é reinjetado pelo código a cada turno."""
    cliente = _montar_cliente(["  ", "  ", '{"resposta": "ok"}'], politica=(None, 2, 0))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.historico_enviado == 0
    chamadas = cliente._client.chat.completions.mensagens_por_chamada
    assert [m["role"] for m in chamadas[2]] == ["system", "system", "user"]
    assert chamadas[2][-1]["content"] == "não consigo pagar nesse dia"


def test_caminho_feliz_nunca_perde_contexto():
    """Acertando de primeira, o histórico vai inteiro e nada é marcado."""
    cliente = _montar_cliente(['{"resposta": "ok"}'], politica=(None, 2, 0))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.historico_enviado is None
    assert resposta.historico_reduzido is False
    assert cliente._client.chat.completions.chamadas == 1


def test_adaptador_sem_politica_de_retry_preserva_o_contexto():
    """A redução é específica do provedor com a falha conhecida; o adaptador
    OpenAI puro nunca mexe no contexto."""
    cliente = _montar_cliente(["  "], politica=(None,))

    resposta = cliente.gerar(sistema="s", mensagens=_CONVERSA)

    assert resposta.historico_reduzido is False
    for msgs in cliente._client.chat.completions.mensagens_por_chamada:
        assert len(msgs) == len(_CONVERSA) + 1


def test_limitar_historico_preserva_sempre_o_enquadramento_do_turno():
    """A cauda (bloco de contexto + pergunta atual) nunca é cortada: ela é o
    enquadramento do turno, não bate-papo."""
    for limite in (0, 1, 2, 4):
        reduzido = ClienteOpenAI._limitar_historico(_CONVERSA, limite)
        assert reduzido[-1] is _CONVERSA[-1], "pergunta atual foi perdida"
        assert reduzido[-2] is _CONVERSA[-2], "bloco de contexto foi perdido"
        assert len(reduzido) == min(limite, 4) + 2


# --- Histórico do bot -------------------------------------------------------
class _LLMFalsa:
    """ClienteLLM mínimo que devolve sempre o mesmo texto."""

    provedor = "falso"
    modelo = "falso"

    def __init__(self, texto: str) -> None:
        self._texto = texto

    def gerar(self, **_kwargs):
        from llm.interface import RespostaLLM

        return RespostaLLM(
            texto=self._texto, modelo=self.modelo, provedor=self.provedor,
            parametros={}, latencia_s=0.0, bruto={}, tentativas=3,
        )


class _RecuperadorFalso:
    def recuperar(self, _consulta: str, k: int = 4):
        return []


class _FonteFalsa:
    def consultar_cliente(self, _identificador):
        return None

    def consultar_dividas(self, _cliente_id):
        return []

    def consultar_condicoes(self, _divida_id, estagio, num_parcelas=None,
                            data_vencimento=None):
        return []

    def registrar_acordo(self, _divida_id, _condicao_id):
        raise AssertionError("não deveria registrar acordo neste teste")


@pytest.fixture
def bot_com_resposta(monkeypatch):
    """Fábrica de Chatbot com LLM de resposta controlada."""

    def _criar(texto_resposta: str) -> Chatbot:
        return Chatbot(_FonteFalsa(), _RecuperadorFalso(), _LLMFalsa(texto_resposta))

    return _criar


def test_resposta_em_branco_nao_entra_no_historico(bot_com_resposta):
    """Achado real: mensagens de assistant VAZIAS eram devolvidas ao modelo a
    cada turno seguinte (8 de 18, num log de sessão manual), alimentando-o com
    uma conversa degenerada. A fala do CLIENTE continua no histórico."""
    bot = bot_com_resposta("     ")

    bot.processar_turno("oi, tudo bem?")

    papeis = [m["role"] for m in bot.historico]
    assert papeis == ["user"], f"histórico deveria ter só a fala do cliente: {bot.historico}"
    assert all(m["content"].strip() for m in bot.historico)


def test_resposta_valida_entra_no_historico(bot_com_resposta):
    """O caminho normal não pode ter sido afetado pela correção acima."""
    bot = bot_com_resposta('{"resposta": "Olá! Qual é o seu CPF?"}')

    bot.processar_turno("oi")

    papeis = [m["role"] for m in bot.historico]
    assert papeis == ["user", "assistant"]
    assert bot.historico[1]["content"] == "Olá! Qual é o seu CPF?"


def test_tentativas_chegam_ao_resultado_do_turno(bot_com_resposta):
    """O nº de tentativas precisa chegar ao log: é ele que torna a taxa real
    de falha do provedor mensurável, em vez de escondida pelo retry."""
    bot = bot_com_resposta('{"resposta": "ok"}')

    resultado = bot.processar_turno("oi")

    assert resultado.tentativas_llm == 3
