"""Base comum aos juízes LLM da camada de avaliação (camada 3 do modelo).

`tom.py` veio antes e traz sua própria cópia deste padrão; ele funciona e é
coberto por teste, então não foi reescrito. Os avaliadores novos
(consistência, faithfulness, groundedness, segurança, equidade, robustez)
compartilham esta base para não repetir seis vezes o mesmo carregamento de
prompt, a mesma chamada e o mesmo parsing tolerante de JSON.

Convenções preservadas de `tom.py`:
  - prompt do juiz em arquivo versionável (`eval/prompt_juiz_<x>.md`);
  - cliente obtido por `criar_cliente(config.JUIZ_PROVEDOR, config.JUIZ_MODELO)`,
    nunca acoplado a um provedor concreto;
  - saída JSON estrita, com parsing tolerante que NUNCA levanta exceção;
  - `_meta` anexado ao julgamento (provedor, modelo, parâmetros, latência).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import config
from instrumentacao.logger import extrair_tokens
from llm import ClienteLLM, criar_cliente

DIR_PROMPTS = Path(__file__).resolve().parent
_RE_JSON = re.compile(r"\{.*\}", re.DOTALL)


# --- Motivos das falhas de juiz --------------------------------------------
# `falhas_juiz` por métrica diz QUANTOS julgamentos se perderam; não dizia por
# quê. O motivo nascia aqui, ia para o campo `_erro` do julgamento e morria
# ali, porque o relatório conta as falhas e descarta a mensagem. Isso custou
# uma rodada inteira: com o juiz apontado para um modelo que recusava
# `temperature`, dez pares deram dez falhas e as duas métricas de consistência
# saíram `sem_dados` — indistinguível de "a bateria daquela categoria não
# rodou". A causa só apareceu chamando o juiz à mão.
#
# O registro vive no processo, e isso é deliberado: uma avaliação é uma
# invocação de script (ou um subprocesso, quando vem da API), então o escopo
# do processo é exatamente o escopo da medição. `JuizLLM.julgar` é o único
# lugar onde falha de juiz nasce, então registrar aqui cobre as seis
# categorias de uma vez, em vez de repetir o mesmo campo em seis avaliadores.
_falhas: Counter = Counter()

# Partes que mudam a cada chamada e não dizem nada sobre a causa.
_RE_VOLATIL = re.compile(r"req_[A-Za-z0-9]+|'request_id':\s*'[^']*'")


def _resumir(motivo: str) -> str:
    """Normaliza a mensagem para que falhas de mesma causa se agrupem.

    Sem isto o agrupamento não serviria para nada: o erro da API carrega um
    `request_id` distinto em cada chamada, então dez ocorrências da MESMA
    causa apareceriam como dez motivos diferentes.
    """
    return _RE_VOLATIL.sub("<req>", motivo or "").strip()[:300]


def registrar_falha(motivo: str) -> None:
    """Contabiliza um motivo de falha de juiz nesta medição."""
    _falhas[_resumir(motivo)] += 1


def falhas_registradas() -> list[dict]:
    """Motivos distintos de falha, do mais frequente ao menos frequente.

    Vai para a procedência do relatório: é característica da MEDIÇÃO, não de
    uma métrica — a mesma causa (chave expirada, parâmetro recusado, modelo
    sobrecarregado) derruba todas as categorias da rodada ao mesmo tempo.
    """
    return [{"motivo": m, "ocorrencias": n} for m, n in _falhas.most_common()]


def limpar_falhas() -> None:
    """Zera o registro, para que uma medição não herde a anterior."""
    _falhas.clear()
    _sequencia_api[0] = 0
    _uso.clear()
    _raciocinio.clear()


# --- Uso e custo -------------------------------------------------------------
# Mesmo escopo do registro de falhas: o processo é a medição. Somado em
# `julgar`, que é por onde passa toda chamada ao juiz, inclusive as duas ordens
# da equidade. É o insumo da comparação de custo-benefício entre juízes.
_uso: Counter = Counter()

# Raciocínio EFETIVO de cada chamada que respondeu, como o cliente o enviou.
# Na OpenAI o pedido é `reasoning_effort` "none", com recuo para "low" se a API
# recusar; sem este registro, a recusa não deixaria rastro e não daria para
# dizer em que condição o juiz rodou. Na Anthropic é o tipo de `thinking`.
_raciocinio: Counter = Counter()

# Qual parâmetro da API o valor acima representa, por provedor.
PARAMETRO_DE_RACIOCINIO = {"openai": "reasoning_effort", "anthropic": "thinking.type"}

# Preço em US$ por milhão de tokens (entrada, saída). Só entra o que foi
# conferido em fonte oficial; modelo fora da tabela sai com tokens e sem custo,
# em vez de um custo inventado. Para acrescentar: a página de preços do
# provedor, e a data em que foi conferida.
PRECOS_POR_MILHAO: dict[str, tuple[float, float]] = {
    # Anthropic, referência da API conferida em 10/2026. Haiku: prompts de até
    # 100 mil tokens.
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    # OpenAI, página do modelo em developers.openai.com, conferida em 25/10/2026.
    "gpt-5.6-terra": (2.00, 12.00),
    # OpenAI, página de preços em developers.openai.com, conferida em 28/10/2026.
    "gpt-6-luna": (0.10, 0.50),
}


def uso_registrado() -> dict:
    """Chamadas, tokens, tempo e custo estimado do juiz nesta medição."""
    uso = {
        "chamadas": _uso["chamadas"],
        "tokens_entrada": _uso["tokens_entrada"],
        "tokens_saida": _uso["tokens_saida"],
        "latencia_total_s": round(_uso["latencia_ms"] / 1000, 1),
        # Respostas lidas só depois de reparar escape inválido (ver
        # `reparar_escapes`). Sem o reparo, cada uma seria falha do juiz.
        "respostas_json_reparadas": _uso["respostas_json_reparadas"],
        # Chamadas por valor efetivo de raciocínio, ex.: {"none": 1470, "low": 2}.
        # "nao_enviado" é a chamada que saiu sem o parâmetro.
        "raciocinio_efetivo": dict(sorted(_raciocinio.items())),
        "raciocinio_parametro": PARAMETRO_DE_RACIOCINIO.get(config.JUIZ_PROVEDOR),
    }
    modelo = config.JUIZ_MODELO
    # Pela assinatura (`anthropic-assinatura`) não há cobrança por token: o
    # preço da API aplicado aqui inventaria um custo que ninguém pagou.
    preco = (None if config.JUIZ_PROVEDOR == "anthropic-assinatura"
             else PRECOS_POR_MILHAO.get(modelo))
    uso["custo_estimado_usd"] = (
        None if preco is None else round(
            (uso["tokens_entrada"] * preco[0] + uso["tokens_saida"] * preco[1]) / 1e6, 4
        )
    )
    uso["preco_conhecido"] = preco is not None
    return uso


# Falhas de CHAMADA seguidas, sem nenhum sucesso no meio, a partir das quais a
# avaliação para. Instabilidade passageira já é absorvida pelo SDK, que repete
# com espera crescente; o que sobra depois disso, repetido dez vezes em
# sequência, é causa persistente — crédito esgotado, chave revogada, modelo
# retirado. Continuar produziria um relatório inteiro de `falhas_juiz`, com
# cara de medição e nenhum julgamento dentro.
MAX_FALHAS_API_SEGUIDAS = 10

# Teto de tokens de SAÍDA, o mesmo para todo juiz (categorias e tom).
#
# O teto não participa do julgamento: enquanto não corta, é irrelevante;
# quando corta, o JSON sai truncado, o julgamento falha e o item sai do
# denominador. Os tetos por categoria (500 a 2000) tinham sido fixados por
# estimativa e subidos a cada truncamento, sem critério que distinguisse uma
# categoria da outra — e na avaliação de 27/10/2026 o de equidade (600)
# cortou 61 respostas do Haiku, que escreve mais que o Terra, de modo que a
# comparação entre juízes passava a medir quem cabe no limite. Um valor só,
# folgado, tira o teto da medição. Não encarece: cobra-se o que o modelo
# escreve, não o limite. Fica registrado na procedência de cada relatório.
TETO_TOKENS_JUIZ = 2000
# Com o raciocínio ligado (experimento #39), o raciocínio gasta o mesmo teto de
# saída antes do JSON. O teto sobe para que ele não corte o julgamento.
TETO_TOKENS_JUIZ_RACIOCINIO = 16000
_sequencia_api = [0]


class JuizIndisponivel(RuntimeError):
    """O provedor do juiz parou de responder de forma persistente."""


class JuizLLM:
    def __init__(
        self,
        nome_prompt: str,
        cliente_llm: ClienteLLM | None = None,
        temperatura: float | None = None,
        max_tokens: int = TETO_TOKENS_JUIZ,
    ) -> None:
        """Monta um juiz a partir do nome do arquivo de prompt (ex.:
        "prompt_juiz_toxicidade.md"), usando por padrão o provedor/modelo
        de juiz configurados.

        O prompt enviado é a COMPOSIÇÃO de duas partes, e a separação é a
        distinção entre framework e instanciação levada ao instrumento:

          `prompt_juiz_<x>.md`     — o NÚCLEO, genérico. A pergunta, o
                                      vocabulário de classificação, as regras
                                      de decisão e o contrato de saída. Vale
                                      para qualquer sistema que integre IA
                                      generativa, e é o que o framework
                                      publica.
          `prompt_dominio_<x>.md`  — o APÊNDICE desta aplicação. O que conta
                                      como fato, como regra ou como dano NESTE
                                      domínio, com o vocabulário do negócio e
                                      a âncora legal quando houver.

        Os dois estavam num arquivo só, e o resultado era um instrumento que
        ninguém reusa sem reescrever: todo prompt declarava "chatbot de
        negociação de dívidas" na segunda linha. Tirar o domínio para
        generalizar pioraria a medição — é ele que faz o juiz reconhecer o
        dano específico da cobrança. Separar preserva a precisão aqui e torna
        o núcleo publicável sem edição.

        O apêndice é OPCIONAL: sem ele, o juiz roda só com o núcleo, que é o
        caminho de quem pega o framework para outro sistema.
        """
        self.llm = cliente_llm or criar_cliente(config.JUIZ_PROVEDOR, config.JUIZ_MODELO)
        self.temperatura = config.JUIZ_TEMPERATURA if temperatura is None else temperatura
        self.max_tokens = max_tokens
        self.raciocinio = config.JUIZ_RACIOCINIO == "padrao"
        if self.raciocinio:
            self.llm.raciocinio_padrao = True
        self.caminho_prompt = DIR_PROMPTS / nome_prompt
        self.caminho_dominio = DIR_PROMPTS / nome_prompt.replace(
            "prompt_juiz_", "prompt_dominio_", 1
        )
        self.prompt = compor_prompt(self.caminho_prompt, self.caminho_dominio)

    def julgar(self, conteudo: str, max_tokens: int | None = None) -> dict:
        """Envia o conteúdo ao juiz e devolve o julgamento já parseado, com
        `_meta`. Falhas de chamada ou de parsing viram um julgamento com
        `_erro` — a avaliação de um turno nunca derruba a bateria inteira.
        """
        # Progresso conta TENTATIVAS, com ou sem sucesso: se contasse só as
        # bem-sucedidas, a barra pararia justamente quando o juiz está falhando.
        _uso["tentativas"] += 1
        print(f"PROGRESSO_JUIZ {_uso['tentativas']}", flush=True)
        try:
            resposta = self.llm.gerar(
                sistema=self.prompt,
                mensagens=[{"role": "user", "content": conteudo}],
                temperatura=self.temperatura,
                max_tokens=(max(max_tokens or self.max_tokens, TETO_TOKENS_JUIZ_RACIOCINIO)
                            if self.raciocinio else (max_tokens or self.max_tokens)),
            )
        except Exception as erro:  # noqa: BLE001
            motivo = f"{type(erro).__name__}: {erro}"
            registrar_falha(motivo)
            _sequencia_api[0] += 1
            if _sequencia_api[0] >= MAX_FALHAS_API_SEGUIDAS:
                raise JuizIndisponivel(
                    f"{_sequencia_api[0]} falhas seguidas do juiz; a última: {motivo}. "
                    "Avaliação interrompida em vez de gerar relatório sem julgamentos. "
                    "Confira crédito e chave do provedor e rode de novo."
                ) from erro
            return {"_erro": motivo, "_meta": {}}
        _sequencia_api[0] = 0
        entrada, saida, _ = extrair_tokens(resposta.bruto)
        _uso["chamadas"] += 1
        _uso["tokens_entrada"] += entrada or 0
        _uso["tokens_saida"] += saida or 0
        _uso["latencia_ms"] += int(resposta.latencia_s * 1000)
        _raciocinio[(resposta.parametros or {}).get("raciocinio") or "nao_enviado"] += 1

        julgamento = parse_json(resposta.texto)
        if julgamento.get("_json_reparado"):
            _uso["respostas_json_reparadas"] += 1
        if falhou(julgamento):
            # A classe, quando existe, é o que agrupa; a mensagem crua só
            # agruparia falhas de API, que não carregam texto do juiz.
            registrar_falha(julgamento.get("_erro_classe") or julgamento["_erro"])
        julgamento["_meta"] = {
            "provedor": resposta.provedor,
            "modelo": resposta.modelo,
            "parametros": resposta.parametros,
            "latencia_s": round(resposta.latencia_s, 4),
        }
        return julgamento


def compor_prompt(caminho_nucleo: Path, caminho_dominio: Path) -> str:
    """Junta o núcleo genérico ao apêndice de domínio, nessa ordem.

    O núcleo vem primeiro porque é ele que define a tarefa e o formato da
    resposta; o apêndice especializa o que já foi definido. Invertido, o
    modelo leria exemplos de um domínio antes de saber o que está decidindo.

    Sem arquivo de domínio, devolve o núcleo intacto — é o caso de quem
    aplica o framework a outro sistema, e precisa funcionar sem edição.
    """
    nucleo = caminho_nucleo.read_text(encoding="utf-8").rstrip()
    if not caminho_dominio.exists():
        return nucleo + "\n"
    dominio = caminho_dominio.read_text(encoding="utf-8").strip()
    if not dominio:
        return nucleo + "\n"
    return f"{nucleo}\n\n{dominio}\n"


def versoes_das_instrucoes() -> dict[str, str]:
    """Impressão digital de cada instrução de avaliador, por nome.

    O hash cobre o prompt COMPOSTO — núcleo mais apêndice de domínio —, que é
    o texto que o modelo de fato recebe. Vai para a procedência do relatório
    porque a aferição do avaliador vale para o instrumento com que foi feita:
    sem isso, um κ medido antes de uma mudança de instrução seria
    indistinguível de um medido depois, e os dois não são comparáveis.
    Registrar o hash, e não um número de versão, evita que o relatório declare
    uma versão que o arquivo já não tem.
    """
    import hashlib
    versoes: dict[str, str] = {}
    for nucleo in sorted(DIR_PROMPTS.glob("prompt_juiz_*.md")):
        dominio = DIR_PROMPTS / nucleo.name.replace("prompt_juiz_", "prompt_dominio_", 1)
        composto = compor_prompt(nucleo, dominio).encode("utf-8")
        versoes[nucleo.stem] = hashlib.sha256(composto).hexdigest()[:12]
    # As regras fixas vão no conteúdo de fidelidade, aderência e robustez, não
    # no prompt, e mudaram em 28 e 29/10/2026 sem deixar rastro no relatório.
    # Import tardio: faithfulness importa este módulo.
    from .faithfulness import REGRAS_DO_PROMPT_DE_SISTEMA
    versoes["regras_fixas_dos_juizes"] = hashlib.sha256(
        REGRAS_DO_PROMPT_DE_SISTEMA.encode("utf-8")).hexdigest()[:12]
    return versoes


# Barra seguida de qualquer caractere, consumida em PAR: assim "\\" (barra
# escapada) passa inteira e não é confundida com o início de outra sequência.
_RE_ESCAPE = re.compile(r"\\(.)", re.DOTALL)
_ESCAPES_JSON = set(r'"\/bfnrtu')


def reparar_escapes(texto: str) -> tuple[str, int]:
    r"""Tira a barra das sequências que o JSON não reconhece; devolve o texto e
    quantas foram reparadas.

    O caso que motivou: o juiz escreve "R\$ 9.100,00", e `\$` não existe em
    JSON — o objeto inteiro deixa de ser lido, com o veredito dentro. Visto na
    resposta inteira de um teste de 28/10/2026. Nas 11 falhas de JSON da
    avaliação do Haiku do mesmo dia não dá para confirmar a causa: a resposta
    foi gravada só até o caractere 500, e o padrão não aparece nesse trecho.
    Só a barra sai: o caractere fica, e nada do conteúdo muda.
    """
    reparos = 0

    def trocar(m: re.Match) -> str:
        nonlocal reparos
        if m.group(1) in _ESCAPES_JSON:
            return m.group(0)
        reparos += 1
        return m.group(1)

    return _RE_ESCAPE.sub(trocar, texto), reparos


def parse_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta do juiz, de forma tolerante.

    Devolve `{"_erro": ...}` em vez de levantar: um juiz que quebrou o formato
    é um dado a medir (ver `tom_taxa_falha_parsing` em relatorio.py), não uma
    exceção que interrompe a avaliação.

    Acompanha `_erro_classe`: a CAUSA, sem o texto do julgamento. A separação
    existe porque as duas servem a coisas diferentes — `_erro` guarda a
    resposta bruta INTEIRA, que vira a evidência da ocorrência e é o único
    registro do que o juiz devolveu (cortá-la apagava justamente o trecho com
    o erro de sintaxe); `_erro_classe` é o que agrupa as falhas da rodada.
    Registrar a mensagem completa não agruparia nada: o texto do juiz muda a
    cada julgamento, então dez truncamentos pela MESMA causa apareceriam como
    dez motivos distintos.

    Um JSON que só falha por escape inválido é reparado (`reparar_escapes`) e
    lido; o julgamento leva `_json_reparado` com o número de reparos, e a
    rodada conta quantos foram (`uso_registrado`).
    """
    bruto = texto or ""
    m = _RE_JSON.search(bruto)
    if not m:
        # Começou a emitir o objeto e não o fechou: a resposta foi cortada no
        # limite de tokens. Diferente de "o juiz respondeu prosa", e a
        # distinção decide a correção — teto de tokens, não prompt.
        truncado = "{" in bruto
        return {
            "_erro": f"sem JSON na resposta do juiz: {bruto}",
            "_erro_classe": (
                "JSON truncado: a resposta do juiz foi cortada antes de fechar "
                "o objeto (limite de max_tokens)" if truncado
                else "resposta do juiz sem nenhum JSON"
            ),
        }
    reparos = 0
    try:
        dados = json.loads(m.group(0))
    except json.JSONDecodeError:
        reparado, reparos = reparar_escapes(m.group(0))
        try:
            dados = json.loads(reparado) if reparos else None
        except json.JSONDecodeError:
            dados = None
        if dados is None:
            return {
                "_erro": f"JSON inválido na resposta do juiz: {bruto}",
                "_erro_classe": "JSON sintaticamente inválido na resposta do juiz",
            }
    if not isinstance(dados, dict):
        return {
            "_erro": "JSON não é um objeto",
            "_erro_classe": "JSON do juiz não é um objeto",
        }
    if reparos:
        dados["_json_reparado"] = reparos
    return dados


def falhou(julgamento: dict) -> bool:
    """True se este julgamento não pôde ser obtido/interpretado."""
    return "_erro" in julgamento
