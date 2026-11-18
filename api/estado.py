"""Estado vivo da API: conversas em andamento e o índice do RAG.

Duas coisas precisam sobreviver entre requisições HTTP e por isso moram aqui:

1. **O `Chatbot` de cada sessão.** Ele é uma máquina de estados — guarda o
   estágio da oferta, a data escolhida, o histórico da conversa. Recriá-lo a
   cada requisição zeraria a negociação a cada mensagem.
2. **O `Instrumentador` de cada sessão.** Ele numera os turnos (`_turno`)
   incrementalmente. Recriá-lo faria a numeração recomeçar do 1 e gravar
   turnos duplicados no mesmo arquivo.

O store é um dicionário em memória, sem persistência: é uma ferramenta local
de usuária única. A consequência aceita: reiniciar o servidor perde as
conversas EM ANDAMENTO (o frontend começa uma nova). Nada se perde do que já
foi medido — os turnos já gravados estão no JSONL, que é a fonte de verdade
da avaliação.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

import config
from bot import Chatbot, ResultadoTurno
from dados import FonteDeDadosMemoria
from instrumentacao import Instrumentador
from llm import criar_cliente
from rag import RecuperadorRAG

# --- Índice do RAG (caro de construir, compartilhado por todas as sessões) --
_recuperador: RecuperadorRAG | None = None
_lock_rag = threading.Lock()


def obter_recuperador() -> RecuperadorRAG:
    """Constrói o índice de embeddings uma vez e reaproveita.

    Equivale ao `@st.cache_resource` do protótipo. A carga é preguiçosa de
    propósito: o servidor sobe na hora e só paga o custo do modelo de
    embeddings quando a primeira conversa começar.
    """
    global _recuperador
    with _lock_rag:
        if _recuperador is None:
            rec = RecuperadorRAG()
            rec.recuperar("aquecimento do indice", k=1)  # força a carga agora
            _recuperador = rec
        return _recuperador


# --- Conversas vivas -------------------------------------------------------
@dataclass
class SessaoViva:
    """Uma conversa em andamento, do ponto de vista do servidor."""
    sessao_id: str
    bot: Chatbot
    instrumentador: Instrumentador
    provedor: str
    modelo: str
    mensagens: list[dict] = field(default_factory=list)
    ultimo: ResultadoTurno | None = None
    # Aviso de turno sem resposta do provedor. Não entra em `mensagens`: é um
    # recado da interface sobre uma falha técnica, não uma fala do bot.
    aviso: str | None = None


_sessoes: dict[str, SessaoViva] = {}
_lock_sessoes = threading.Lock()


def criar_sessao(provedor: str | None = None, modelo: str | None = None) -> SessaoViva:
    """Abre uma conversa nova, com seu próprio bot, fonte de dados e log."""
    provedor = provedor or config.BOT_PROVEDOR
    modelo = modelo or config.BOT_MODELO
    sessao_id = f"web-{uuid.uuid4().hex[:8]}"
    bot = Chatbot(
        FonteDeDadosMemoria(),
        obter_recuperador(),
        criar_cliente(provedor, modelo),
        temperatura=config.BOT_TEMPERATURA,
        k_rag=config.RAG_K,
        max_tokens=config.BOT_MAX_TOKENS,
    )
    sessao = SessaoViva(
        sessao_id=sessao_id,
        bot=bot,
        instrumentador=Instrumentador(sessao_id, dir_logs=config.DIR_LOGS_MANUAIS),
        provedor=provedor,
        modelo=modelo,
    )
    with _lock_sessoes:
        _sessoes[sessao_id] = sessao
    return sessao


def obter_sessao(sessao_id: str) -> SessaoViva | None:
    """Devolve a conversa viva, ou None se ela não existe mais em memória."""
    with _lock_sessoes:
        return _sessoes.get(sessao_id)


def encerrar_sessao(sessao_id: str) -> bool:
    """Descarta a conversa da memória. O log em disco permanece intacto."""
    with _lock_sessoes:
        return _sessoes.pop(sessao_id, None) is not None


def sessoes_vivas() -> list[str]:
    """Ids das conversas ainda em memória (as que aceitam nova mensagem)."""
    with _lock_sessoes:
        return list(_sessoes)
