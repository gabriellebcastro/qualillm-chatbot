"""Simulador de cliente (via 3): uma LLM interpretando um cliente real, para
gerar conversas adaptativas — cada fala do "cliente" depende da resposta
anterior do bot.

Não é ferramenta de terceiros: é o mesmo padrão de adaptador (`ClienteLLM`)
já usado pelo bot e pelo juiz, só que instruído a interpretar o CLIENTE.

Duas formas de construir:

- `SimuladorCliente(persona_texto)` — persona em texto livre. Usado pelos
  cenários de `tests/cenarios_conversacionais.py`.
- `SimuladorCliente.de_persona(persona_dict)` — persona estruturada, carregada
  de `tests/personas/*.json`, formatada no template versionável
  `tests/personas/prompt_simulador.md`. É a forma usada pela bateria
  (`scripts/rodar_bateria.py`), conforme VIAS_DE_ESTIMULO.

Em ambas, o simulador sinaliza o fim do episódio emitindo o token `[FIM]` ao
final da fala (removido antes de a mensagem chegar ao bot; ver `encerrou`).
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from llm import criar_cliente

DIR_PERSONAS = Path(__file__).resolve().parent / "personas"
CAMINHO_TEMPLATE = DIR_PERSONAS / "prompt_simulador.md"

# Token que o simulador emite quando a condição de encerramento da persona é
# atingida. É sinal interno do teste — nunca chega ao bot.
TOKEN_FIM = "[FIM]"

_SISTEMA_SIMULADOR = """\
Você está simulando um CLIENTE de verdade num CHAT DE TEXTO (um chatbot web, \
não é uma ligação telefônica) com o atendente virtual de uma empresa de \
negociação de dívidas. Nunca revele que isso é uma simulação nem mencione \
que você é uma IA. Fale em português do Brasil, como uma pessoa real \
escreveria num chat, em 1 a 3 frases por vez.

Perfil do cliente que você deve interpretar:
{persona}

Regras:
- Fale APENAS como o cliente, nunca como o atendente.
- Você inicia a conversa (o atendente ainda não disse nada na primeira fala).
- É um chat de texto: não use expressões de ligação telefônica (nunca abra \
com "Alô", nunca diga que "ligou" para a empresa — diga que está \
conversando/entrando em contato pelo chat).
- Leve a conversa adiante de forma coerente com o perfil acima, mas de \
forma natural — não repita frases prontas, reaja ao que o atendente disser.
"""

_ABERTURA = {"role": "user", "content": "(Inicie a conversa como o cliente.)"}


def carregar_persona(caminho: Path) -> dict:
    """Lê um arquivo de persona (tests/personas/*.json)."""
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def listar_personas(dir_personas: Path = DIR_PERSONAS) -> list[dict]:
    """Carrega todas as personas do diretório, em ordem de id."""
    personas = [
        carregar_persona(p)
        for p in sorted(dir_personas.glob("persona_*.json"))
    ]
    return sorted(personas, key=lambda p: p["id"])


class SimuladorCliente:
    def __init__(
        self,
        persona: str,
        provedor: str | None = None,
        modelo: str | None = None,
        sistema: str | None = None,
    ) -> None:
        """Monta o simulador com uma persona (texto livre) e o provedor/
        modelo que vai interpretá-la (por padrão, os de `config.SIMULADOR_*`).

        `sistema` permite injetar um prompt já pronto — é por onde
        `de_persona()` passa o template preenchido.
        """
        self.provedor = provedor or config.SIMULADOR_PROVEDOR
        self.modelo = modelo or config.SIMULADOR_MODELO
        self.llm = criar_cliente(self.provedor, self.modelo)
        self.sistema = sistema or _SISTEMA_SIMULADOR.format(persona=persona)
        self.historico: list[dict] = []
        # Vira True quando o simulador emite TOKEN_FIM (condição de
        # encerramento da persona atingida).
        self.encerrou: bool = False

    @classmethod
    def de_persona(
        cls,
        persona: dict,
        provedor: str | None = None,
        modelo: str | None = None,
        caminho_template: Path = CAMINHO_TEMPLATE,
    ) -> "SimuladorCliente":
        """Constrói a partir de uma persona estruturada (tests/personas/*.json),
        preenchendo o template versionável do simulador com os campos dela."""
        perfil = persona.get("perfil", {})
        sistema = Path(caminho_template).read_text(encoding="utf-8").format(
            cpf=perfil.get("cpf", ""),
            situacao=perfil.get("situacao", ""),
            limite_parcelas_aceitavel=perfil.get("limite_parcelas_aceitavel", ""),
            comportamento=persona.get("comportamento", ""),
            objetivo=persona.get("objetivo", ""),
            encerramento=persona.get("encerramento", ""),
        )
        return cls(persona="", provedor=provedor, modelo=modelo, sistema=sistema)

    def responder(self, fala_atendente: str | None) -> str:
        """Gera a próxima fala do cliente simulado.

        `fala_atendente=None` na abertura (o cliente fala primeiro); nas
        chamadas seguintes, é a última resposta do bot de verdade — do
        ponto de vista do simulador, o que o bot disse é "user" (é a ele
        que o simulador está reagindo), e as falas do próprio simulador
        entram como "assistant" no seu próprio histórico.

        Se a fala trouxer o token `[FIM]`, ele é removido do texto devolvido
        e `self.encerrou` passa a True — o token é sinal para o runner, não
        conteúdo para o bot.
        """
        if fala_atendente is not None:
            self.historico.append({"role": "user", "content": fala_atendente})

        resposta = self.llm.gerar(
            sistema=self.sistema,
            mensagens=self.historico or [_ABERTURA],
            temperatura=config.SIMULADOR_TEMPERATURA,
            max_tokens=config.SIMULADOR_MAX_TOKENS,
        )
        texto = resposta.texto
        if TOKEN_FIM in texto:
            self.encerrou = True
            texto = texto.replace(TOKEN_FIM, "").rstrip()

        self.historico.append({"role": "assistant", "content": texto})
        return texto
