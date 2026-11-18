"""Interface agnóstica de LLM.

O bot (OpenAI) e o juiz (Anthropic) conversam com o modelo apenas através de
`ClienteLLM`. Trocar de modelo ou de provedor é escolher outro adaptador — o
resto do sistema não muda. Chamadas diretas às APIs oficiais, sem frameworks
de orquestração.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RespostaLLM:
    texto: str                     # texto final extraído da resposta
    modelo: str
    provedor: str
    parametros: dict = field(default_factory=dict)
    latencia_s: float = 0.0
    bruto: Any = None              # resposta bruta serializável (para o log)
    # Quantas chamadas à API foram necessárias para obter esta resposta.
    # Maior que 1 significa que o provedor devolveu conteúdo em branco e a
    # chamada foi repetida (ver ClienteOpenAI.TENTATIVAS_RESPOSTA_VAZIA).
    # Fica no log para que a taxa real de falha do provedor seja mensurável,
    # em vez de ficar escondida atrás do retry.
    tentativas: int = 1
    # Quanto do histórico da conversa a chamada que produziu esta resposta
    # recebeu: None = o histórico inteiro; um inteiro N = apenas as N últimas
    # mensagens (0 = nenhuma). Importa para a avaliação: uma resposta gerada
    # com contexto reduzido pode parecer fora de contexto, e o avaliador
    # precisa poder distinguir isso de uma falha do bot.
    historico_enviado: int | None = None

    @property
    def historico_reduzido(self) -> bool:
        """True se esta resposta saiu com menos que o histórico completo."""
        return self.historico_enviado is not None


class ClienteLLM(ABC):
    provedor: str
    modelo: str

    @abstractmethod
    def gerar(
        self,
        sistema: str,
        mensagens: list[dict],
        temperatura: float | None = None,
        max_tokens: int = 1024,
        formato_json: bool = False,
    ) -> RespostaLLM:
        """Gera uma resposta.

        `mensagens` é uma lista de {"role": "user"|"assistant", "content": str}.
        `temperatura=None` deixa o modelo usar o padrão dele (alguns modelos
        recentes não aceitam o parâmetro).
        `formato_json=True` pede ao provedor para VALIDAR que a resposta é um
        JSON sintaticamente válido (quando o provedor suportar o recurso
        nativamente) — usado para decisões que não podem depender de a LLM
        "lembrar" de incluir um marcador em texto livre (achado real: o
        modelo às vezes omite instruções soltas no meio da prosa).
        """
