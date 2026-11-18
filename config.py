"""Configuração central do MVP.

Lê variáveis de ambiente (arquivo .env) e expõe constantes usadas em todo o
sistema. Nada de segredos hardcoded — as chaves de API vêm do .env.

IMPORTANTE: todos os dados manipulados por este sistema são FICTÍCIOS.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

# Carrega o .env se python-dotenv estiver instalado (import opcional para que a
# camada de dados possa ser inspecionada sem dependências extras).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass


def _data(env_valor: str | None) -> date | None:
    """Converte "AAAA-MM-DD" (string do .env) em date; None se vazio."""
    if not env_valor:
        return None
    ano, mes, dia = (int(p) for p in env_valor.split("-"))
    return date(ano, mes, dia)


# ---------------------------------------------------------------------------
# Data de referência ("hoje" do sistema).
#
# Por padrão é o DIA REAL: as datas que o bot oferta ao cliente (vencimento à
# vista, primeira parcela) precisam ser datas de verdade — oferecer pagamento
# para uma data já passada é um erro funcional evidente para quem usa o
# sistema, e nada tem a ver com a qualidade da IA, já que essas datas são
# aritmética determinística no código.
#
# `DATA_REFERENCIA` no .env congela o "hoje" numa data fixa. Serve para
# reproduzir uma execução antiga exatamente como ela rodou. Fora disso, deixe
# vazio: com a data congelada, o sistema volta a ofertar datas passadas
# conforme o tempo real avança.
#
# O que NÃO muda com o tempo é o cenário de cada dívida — ver a seção "Modelo
# temporal" em dados/regras.py.
# ---------------------------------------------------------------------------
_DATA_REFERENCIA_FIXA: date | None = _data(os.getenv("DATA_REFERENCIA"))


def data_referencia() -> date:
    """O "hoje" do sistema: o dia real, ou a data congelada no .env.

    É função, e não constante de módulo, de propósito: a interface web pode
    ficar dias no ar sem reiniciar, e uma constante avaliada no import
    congelaria o "hoje" no dia em que o servidor subiu.
    """
    return _DATA_REFERENCIA_FIXA or date.today()

# ---------------------------------------------------------------------------
# LLM — bot e juiz. Modelos e provedores parametrizáveis: trocar de modelo ou
# de provedor (via os adaptadores em llm/) é só mudar o .env.
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
# Chaves "identity-linked" da Anthropic exigem dizer em qual workspace a
# chamada age: sem o header `anthropic-workspace-id` a API responde 400, mesmo
# com a chave correta. Chaves antigas não precisam — daí ser opcional.
ANTHROPIC_WORKSPACE_ID: str | None = os.getenv("ANTHROPIC_WORKSPACE_ID")
DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
# O DeepSeek é compatível com a API da OpenAI; só muda a URL base.
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Bot: provedor + modelo. Ex.: BOT_PROVEDOR=deepseek / BOT_MODELO=deepseek-chat.
# O padrão acompanha o que o trabalho de fato usa. Era openai/gpt-4o, e com a
# OpenAI fora da listagem da interface o padrão apontaria para um provedor que
# a tela não oferece.
BOT_PROVEDOR: str = os.getenv("BOT_PROVEDOR", "deepseek")
BOT_MODELO: str = os.getenv("BOT_MODELO", "deepseek-v4-flash")
BOT_TEMPERATURA: float = float(os.getenv("BOT_TEMPERATURA", "0.3"))
# Limite de tokens de SAÍDA por resposta (economiza tokens e reduz latência).
BOT_MAX_TOKENS: int = int(os.getenv("BOT_MAX_TOKENS", "512"))

# Juiz. Haiku 5.5 é o padrão; o outro juiz do estudo é o GPT-6 Luna. O par é a
# faixa mais baixa de cada fornecedor, ao mesmo preço por token (US$ 0,10 /
# 0,50 por milhão, conferido em 28/10/2026). Não é pareamento por capacidade: os
# índices públicos, medidos com raciocínio ligado, não os põem no mesmo
# patamar, e a equivalência na tarefa se mede pelo κ entre os dois. Até 28/10 o
# par era o GPT-5.6 Terra. O Haiku rejeita temperature (erro
# 400) — o adaptador (llm/anthropic_client.py) omite o parâmetro e desliga o
# raciocínio adaptativo; JUIZ_TEMPERATURA só tem efeito em modelos
# "clássicos" (ex.: claude-haiku-4-5).
JUIZ_PROVEDOR: str = os.getenv("JUIZ_PROVEDOR", "anthropic")
JUIZ_MODELO: str = os.getenv("JUIZ_MODELO", "claude-haiku-5-5")
JUIZ_TEMPERATURA: float = float(os.getenv("JUIZ_TEMPERATURA", "0"))
# Raciocínio do juiz. "desligado" é a configuração do estudo de caso (todas as
# avaliações das duas rodadas e o reteste). "padrao" liga o raciocínio no
# esforço padrão de cada fornecedor, o mesmo nos dois juízes (medium): no Haiku
# 5.5, thinking adaptativo; no GPT-6 Luna, reasoning_effort "medium". Existe
# para o experimento do comentário #39 do orientador (16/11/2026), que rejulga
# a amostra rotulada com o raciocínio ligado.
JUIZ_RACIOCINIO: str = os.getenv("JUIZ_RACIOCINIO", "desligado")

# Simulador de cliente (via 3): uma LLM interpreta o cliente para gerar
# conversas adaptativas. Por padrão usa o mesmo provedor/modelo do bot (funciona
# só com a chave do bot já configurada), e foi assim na bateria definitiva: no
# provedor do bot, nenhum juiz avalia conversas escritas pelo próprio modelo.
SIMULADOR_PROVEDOR: str = os.getenv("SIMULADOR_PROVEDOR", BOT_PROVEDOR)
SIMULADOR_MODELO: str = os.getenv("SIMULADOR_MODELO", BOT_MODELO)
SIMULADOR_TEMPERATURA: float = float(os.getenv("SIMULADOR_TEMPERATURA", "0.8"))
SIMULADOR_MAX_TOKENS: int = int(os.getenv("SIMULADOR_MAX_TOKENS", "200"))


def chave_do_provedor(provedor: str) -> str | None:
    """Retorna a chave de API configurada para um provedor."""
    return {
        "openai": OPENAI_API_KEY,
        "deepseek": DEEPSEEK_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
    }.get(provedor.lower())

# ---------------------------------------------------------------------------
# RAG — embeddings locais multilíngues (offline, sem chave de API).
# ---------------------------------------------------------------------------
EMBEDDING_MODELO: str = os.getenv(
    "EMBEDDING_MODELO", "paraphrase-multilingual-MiniLM-L12-v2"
)
# Nº de trechos de política recuperados por turno (afeta tokens de ENTRADA).
RAG_K: int = int(os.getenv("RAG_K", "4"))

# ---------------------------------------------------------------------------
# Testes de consistência — nº padrão de vezes que a MESMA entrada é executada
# (scripts/reexecutar.py e tests/test_consistencia.py usam este mesmo valor).
# ---------------------------------------------------------------------------
N_EXECUCOES_PADRAO: int = int(os.getenv("N_EXECUCOES_PADRAO", "5"))

# ---------------------------------------------------------------------------
# Bateria de testes (scripts/rodar_bateria.py) — ver docs/plano_de_testes.md.
# ---------------------------------------------------------------------------
# Modelos de bot avaliados na bateria (o bot é a VARIÁVEL do experimento).
# Formato: "provedor:modelo", separados por vírgula.
# Ex.: MODELOS_BOT=deepseek:deepseek-v4-flash,openai:gpt-4o
def _modelos_bot(env_valor: str | None) -> list[tuple[str, str]]:
    """Interpreta MODELOS_BOT ("provedor:modelo,provedor:modelo") como lista de
    pares. Sem a variável, usa o par BOT_PROVEDOR/BOT_MODELO já configurado."""
    if not env_valor:
        return [(BOT_PROVEDOR, BOT_MODELO)]
    pares = []
    for item in env_valor.split(","):
        item = item.strip()
        if not item:
            continue
        provedor, _, modelo = item.partition(":")
        pares.append((provedor.strip(), modelo.strip()))
    return pares


MODELOS_BOT: list[tuple[str, str]] = _modelos_bot(os.getenv("MODELOS_BOT"))

# Limite de segurança de turnos por episódio (vias 2 e 3): evita conversa
# infinita quando o fluxo não converge nem o simulador encerra.
MAX_TURNOS: int = int(os.getenv("MAX_TURNOS", "12"))

# Controle de ritmo: intervalo mínimo (segundos) entre chamadas ao mesmo
# provedor, para respeitar limites de RPM de free tiers.
INTERVALO_ENTRE_CHAMADAS_S: float = float(os.getenv("INTERVALO_ENTRE_CHAMADAS_S", "0"))

# A RETOMADA DA BATERIA NÃO TEM ARQUIVO DE ESTADO.
# Os episódios já concluídos são derivados dos próprios logs, por
# `episodios_concluidos()` em scripts/rodar_bateria.py. Havia um
# `logs/.bateria_estado.json` guardando essa lista em paralelo; ele divergiu
# em silêncio (declarava 4 episódios quando os logs registravam 160) e foi
# removido. Ver o docstring daquela função.

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
CAMINHO_SEED = RAIZ / "dados" / "seed.json"
DIR_LOGS = RAIZ / "logs"
# Conversas manuais (Chat manual e scripts/conversar.py) ficam numa pasta
# própria, e as avaliações delas numa subpasta. Em `logs/` fica só a
# automação: nenhuma leitura da bateria enxerga conversa de pessoa, e a
# Visão geral nunca mostra uma conversa avulsa como estado do sistema.
DIR_LOGS_MANUAIS = DIR_LOGS / "manuais"
DIR_RELATORIOS_MANUAIS = DIR_LOGS_MANUAIS / "relatorios"
