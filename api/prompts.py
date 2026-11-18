"""Catálogo dos prompts versionados do sistema.

É uma LISTA FECHADA, escrita à mão, e não uma varredura de diretório. Dois
motivos:

1. **Segurança.** O endpoint recebe um id vindo da URL. Com lista fechada, o
   id só pode resolver para um arquivo previsto aqui; não existe caminho que
   o cliente possa construir para ler outra coisa do disco.
2. **Sentido.** Uma varredura saberia o nome do arquivo e nada mais. O que a
   tela precisa mostrar é a que PAPEL cada prompt serve — qual estágio da
   conversa, qual categoria do framework ele julga —, e isso não está no
   nome do arquivo.

Nesta fase a tela é somente leitura: mostrar o conteúdo e de onde ele vem,
sem editor embutido.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import config


@dataclass(frozen=True)
class Prompt:
    id: str
    grupo: str          # bot | juiz | simulador
    titulo: str
    arquivo: str        # caminho relativo à raiz do projeto
    papel: str          # para que serve, em uma frase
    formato: str        # markdown | texto
    # Categoria do framework que este juiz mede. Vazio para bot e simulador.
    categoria: str = ""
    # Apêndice de domínio do juiz. O juiz recebe NÚCLEO + APÊNDICE, e a tela
    # mostra os dois e o texto composto, que é o que vai de fato ao modelo.
    dominio: str = ""
    # O que a categoria mede SEM prompt (camada determinística, por código).
    # Sem esta linha, a Biblioteca dava a entender que a categoria se
    # resumia ao juiz — a segurança parecia medir só toxicidade.
    sem_prompt: str = ""


CATALOGO: tuple[Prompt, ...] = (
    # --- Prompts do bot, um por estágio da conversa --------------------
    Prompt(
        id="bot-identificacao",
        grupo="bot",
        titulo="Identificação",
        arquivo="bot/prompts/identificacao.md",
        papel=(
            "Ativo enquanto o cliente ainda não foi identificado. A troca de "
            "estágio é decidida pelo código (Chatbot._selecionar_prompt), não "
            "pelo modelo."
        ),
        formato="markdown",
    ),
    Prompt(
        id="bot-negociacao",
        grupo="bot",
        titulo="Negociação",
        arquivo="bot/prompts/negociacao.md",
        papel=(
            "Ativo depois de identificar o cliente. Conduz a escada de oferta "
            "(1a à vista, 2a à vista, parcelamento) com os valores já "
            "calculados pelo código."
        ),
        formato="markdown",
    ),
    # --- Juízes: um por categoria avaliada -----------------------------
    Prompt(
        id="juiz-equivalencia",
        grupo="juiz",
        titulo="Equivalência",
        arquivo="eval/prompt_juiz_equivalencia.md",
        dominio="eval/prompt_dominio_equivalencia.md",
        papel="Decide se duas respostas à mesma entrada dizem a mesma coisa.",
        formato="markdown",
        categoria="confiabilidade",
        sem_prompt="Também por código, sem prompt: se as repetições afirmaram os mesmos valores, datas e parcelas.",
    ),
    Prompt(
        id="juiz-faithfulness",
        grupo="juiz",
        titulo="Faithfulness",
        arquivo="eval/prompt_juiz_faithfulness.md",
        dominio="eval/prompt_dominio_faithfulness.md",
        papel="Classifica cada afirmação da resposta como sustentada ou não pela fonte de verdade.",
        formato="markdown",
        categoria="precisao",
        sem_prompt="Também por código, sem prompt: se cada valor, data e número de parcelas bate com a fonte de verdade.",
    ),
    Prompt(
        id="juiz-groundedness",
        grupo="juiz",
        titulo="Groundedness",
        arquivo="eval/prompt_juiz_groundedness.md",
        dominio="eval/prompt_dominio_groundedness.md",
        papel="Verifica se as afirmações de política se apoiam no contexto recuperado pelo RAG.",
        formato="markdown",
        categoria="aderencia_contexto",
        sem_prompt="Também por código, sem prompt: se o bot recuperou alguma política antes de responder.",
    ),
    Prompt(
        id="juiz-toxicidade",
        grupo="juiz",
        titulo="Toxicidade",
        arquivo="eval/prompt_juiz_toxicidade.md",
        dominio="eval/prompt_dominio_toxicidade.md",
        papel="Mede a severidade do dano na fala do bot (ameaça, constrangimento, juízo moral, discriminação), numa escala de 1 a 5.",
        formato="markdown",
        categoria="seguranca",
        sem_prompt=(
            "A segurança também mede VAZAMENTO DE DADOS (CPF, dívida ou nome de "
            "outro cliente na resposta), conferido por código contra o cadastro, "
            "sem juiz e sem prompt."
        ),
    ),
    Prompt(
        id="juiz-equidade",
        grupo="juiz",
        titulo="Equidade",
        arquivo="eval/prompt_juiz_equidade.md",
        dominio="eval/prompt_dominio_equidade.md",
        papel="Compara duas conversas pareadas e aponta disparidade de tratamento.",
        formato="markdown",
        categoria="equidade",
        sem_prompt="Também por código, sem prompt: se as duas variantes receberam ofertas com valores diferentes.",
    ),
    Prompt(
        id="juiz-robustez",
        grupo="juiz",
        titulo="Robustez",
        arquivo="eval/prompt_juiz_robustez.md",
        dominio="eval/prompt_dominio_robustez.md",
        papel=(
            "Decide se o bot resistiu à tentativa de subversão — injeção direta "
            "ou INDIRETA (ordem plantada num dado consultado), autoridade falsa, "
            "saída de papel, vazamento das instruções. Recebe a mensagem, os "
            "dados consultados e a resposta."
        ),
        formato="markdown",
        categoria="robustez",
        sem_prompt=(
            "Também por código, sem prompt: trecho do prompt de sistema na "
            "resposta, acordo registrado fora das regras e formato quebrado "
            "(moeda, data, parcelas por extenso)."
        ),
    ),
    Prompt(
        id="juiz-tom-turno",
        grupo="juiz",
        titulo="Tom (por turno)",
        arquivo="eval/prompt_juiz.md",
        papel="Nota de cordialidade de uma resposta isolada. Medida auxiliar, fora das seis categorias.",
        formato="markdown",
    ),
    Prompt(
        id="juiz-tom-sessao",
        grupo="juiz",
        titulo="Tom (por sessão)",
        arquivo="eval/prompt_juiz_sessao.md",
        papel=(
            "Nota de cordialidade da conversa inteira, numa única chamada. É o "
            "formato que a literatura de LLM-as-a-judge recomenda para diálogo "
            "multi-turno: julgar turno isolado degrada o julgamento."
        ),
        formato="markdown",
    ),
    # --- Políticas que o bot consulta (RAG) ----------------------------
    # Não são prompts, mas orientam o bot tanto quanto eles: a cada turno os
    # trechos relevantes são recuperados e entram no contexto. O juiz de
    # groundedness confere o que o bot diz de política contra estes textos.
    Prompt(
        id="politica-descontos",
        grupo="politicas",
        titulo="Encargos e desconto",
        arquivo="rag/politicas/descontos.md",
        papel="Multa, juros de mora, teto de desconto e a escada das duas ofertas à vista.",
        formato="markdown",
    ),
    Prompt(
        id="politica-parcelamento",
        grupo="politicas",
        titulo="Parcelamento",
        arquivo="rag/politicas/parcelamento.md",
        papel="Quando o parcelamento entra, teto de 24 parcelas, parcela mínima e juros.",
        formato="markdown",
    ),
    Prompt(
        id="politica-procedimentos",
        grupo="politicas",
        titulo="Procedimentos de atendimento",
        arquivo="rag/politicas/procedimentos.md",
        papel="Fluxo, o que o atendente pode e não pode fazer, assunto, idioma, tom, não pagamento e contestação.",
        formato="markdown",
    ),
    # --- Simulador de cliente (via 3 da bateria) -----------------------
    Prompt(
        id="simulador",
        grupo="simulador",
        titulo="Simulador de cliente",
        arquivo="tests/personas/prompt_simulador.md",
        papel=(
            "Template preenchido com os campos de cada persona. É a LLM que "
            "faz o papel de cliente nas conversas LLM x LLM da bateria."
        ),
        formato="markdown",
    ),
)

_POR_ID = {p.id: p for p in CATALOGO}

TITULO_GRUPO = {
    "bot": "Prompts do bot",
    "juiz": "Prompts dos juízes",
    "politicas": "Políticas consultadas pelo bot (RAG)",
    "simulador": "Prompt do simulador de cliente",
}


def obter(prompt_id: str) -> Prompt | None:
    """Prompt do catálogo, ou None se o id não existe."""
    return _POR_ID.get(prompt_id)


def caminho(prompt: Prompt) -> Path:
    """Caminho absoluto do arquivo deste prompt."""
    return config.RAIZ / prompt.arquivo


def ler(prompt: Prompt) -> str:
    """Conteúdo do arquivo, como está versionado."""
    return caminho(prompt).read_text(encoding="utf-8")


def composto(prompt: Prompt) -> str | None:
    """Núcleo + apêndice de domínio, como o juiz recebe. None sem apêndice."""
    if not prompt.dominio:
        return None
    from eval.juiz import compor_prompt
    return compor_prompt(config.RAIZ / prompt.arquivo, config.RAIZ / prompt.dominio)
