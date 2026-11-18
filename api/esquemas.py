"""Contratos de entrada e saída da API (Pydantic).

Os campos soltos (`dict`) são propositais onde o payload já tem uma forma
canônica definida em outro lugar do sistema — `estado` vem de
`Chatbot._estado_atual()`, `instrumentacao` vem do `ResultadoTurno`. Redeclarar
esses formatos aqui criaria uma segunda definição para manter em sincronia, e
é exatamente esse tipo de duplicação que faz a interface divergir do bot.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class NovaSessao(BaseModel):
    """Abre uma conversa. Sem provedor/modelo, usa o configurado no .env."""
    provedor: str | None = None
    modelo: str | None = None


class SessaoCriada(BaseModel):
    sessao_id: str
    provedor: str
    modelo: str
    arquivo_log: str
    estado: dict
    estagio_prompt: str


class Mensagem(BaseModel):
    texto: str = Field(min_length=1)


class Instrumentacao(BaseModel):
    """O que o turno custou e com que insumos ele foi montado."""
    prompt_completo: list[dict]
    consultas_dados: list[dict]
    trechos_rag: list[dict]
    latencia_s: float
    tentativas_llm: int
    historico_enviado: int | None


class TurnoResposta(BaseModel):
    turno_id: int
    resposta: str
    # True quando o provedor devolveu conteúdo em branco. O turno é gravado no
    # log assim mesmo: a taxa de falha do provedor é dado do experimento.
    resposta_vazia: bool
    aviso: str | None
    estado: dict
    estagio_prompt: str
    estagio_oferta_rotulo: str
    finalizada: bool
    instrumentacao: Instrumentacao


class ModeloDisponivel(BaseModel):
    provedor: str
    modelo: str
    papel: str
    tem_chave: bool


class ResumoSessao(BaseModel):
    """Uma linha da tela de histórico."""
    sessao_id: str
    turnos: int
    inicio: str | None
    fim: str | None
    provedor: str | None
    modelo: str | None
    acordo_fechado: bool
    turnos_vazios: int
    viva: bool
    # Preenchido só quando a listagem veio de uma busca: o trecho do turno que
    # casou, para a pessoa ver POR QUE a sessão apareceu no resultado.
    trecho: str | None = None


class PedidoAvaliacao(BaseModel):
    """`com_juiz=False` roda só as camadas determinísticas: grátis e na hora.

    `juiz_modelo` no formato "provedor:modelo"; vazio usa o do .env. Existe
    pelo mesmo motivo do campo homônimo em `PedidoAvaliacaoBateria`: o modelo
    que julga muda o resultado e o custo, então escolher qual é parte da
    medição, não configuração de ambiente.
    """
    com_juiz: bool = False
    execucao_id: int = 0
    juiz_modelo: str | None = None


class MetricaAvaliada(BaseModel):
    categoria: str
    metrica: str
    valor: float | None
    limiar: float | None
    operador: str | None
    status: str
    n_amostras: int
    falhas_juiz: int
    nao_aplicavel: str
    justificativas: list[str]
    # Todas as falhas, cada uma com onde ocorreu (ver `eval.relatorio.ocorrencia`).
    ocorrencias: list[dict] = []


class RespostaAvaliacao(BaseModel):
    usou_juiz: bool
    juiz: str | None
    n_turnos: int
    metricas: list[MetricaAvaliada]
    relatorios_gravados: list[str]


class PedidoBateria(BaseModel):
    """Filtros de uma rodada — os mesmos argumentos de rodar_bateria.py.

    Tudo opcional: sem nenhum filtro, roda o inventário inteiro contra os
    modelos de `config.MODELOS_BOT`.
    """
    via: str | None = None
    origem_id: str | None = None
    categoria: str | None = None
    modelo: str | None = None
    # Modelo que interpreta o CLIENTE na via 3 ("provedor:modelo"); vazio usa
    # o do .env. É o segundo papel de LLM da rodada, e o plano de testes
    # recomenda apontá-lo para outro provedor, para não medir o bot contra si
    # mesmo — escolha que precisava ser possível sem editar o .env.
    simulador_modelo: str | None = None
    repeticoes: int | None = None
    # Ignora o estado de retomada e refaz tudo. Custa a bateria inteira de
    # novo, então não é o padrão.
    recomecar: bool = False


class PedidoAvaliacaoBateria(BaseModel):
    """Uma rodada de avaliação sobre os logs já gravados.

    `categorias` vazio = todas. `juiz_modelo` no formato "provedor:modelo";
    vazio usa o configurado no .env.
    """
    categorias: list[str] = []
    com_juiz: bool = False
    juiz_modelo: str | None = None
    # --- Recorte dos LOGS a julgar. Eixo diferente de `categorias`, que
    # escolhe quais MÉTRICAS rodam sobre o que for selecionado aqui. ---
    modelo: str | None = None
    via: str | None = None
    origem_id: str | None = None
    desde: str | None = None


class ResumoRelatorio(BaseModel):
    """Uma linha da lista de relatórios.

    O histórico é preservado de propósito: duas execuções da mesma categoria
    podem dar números diferentes, porque o juiz não é determinístico, e isso
    É dado — não ruído a esconder mostrando só o mais recente.
    """
    nome: str
    categoria: str
    # Recorte medido. Vazio = bateria completa; senão, o id de uma conversa
    # manual (ex.: "web-a1b2c3d4-exec0").
    escopo: str
    momento: str
    gerado_em: str | None
    usou_juiz: bool
    juiz: str | None
    n_turnos: int | None
    n_arquivos_log: int
    # Contagem por status: {"atende": 2, "sem_dados": 1, ...}. Deixa a lista
    # legível sem abrir cada relatório.
    vereditos: dict[str, int]


class PedidoRotulo(BaseModel):
    """Um rótulo humano para um item da amostra do κ.

    `rotulo` é validado no servidor contra o vocabulário da métrica: um valor
    digitado errado viraria categoria nova no cálculo e baixaria a
    concordância por erro de digitação em vez de discordância real.
    """
    id: str
    rotulo: str
