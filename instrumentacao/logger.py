"""Instrumentação: registro estruturado de cada turno da conversa.

Este é o requisito mais importante do MVP. Sem um log completo, a avaliação
(Seção 5) fica inviável, porque não dá para comparar o que o bot DISSE com o
que a fonte de verdade RETORNOU e com o contexto que foi RECUPERADO.

Cada turno vira uma linha JSON (formato JSONL) contendo tudo o que a avaliação
precisa. O campo `execucao_id` permite reexecutar a mesma entrada várias vezes,
registrando cada execução separadamente (para medir consistência).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import config
from bot import ResultadoTurno


class Instrumentador:
    def __init__(
        self,
        sessao_id: str,
        execucao_id: int = 0,
        dir_logs: Path | None = None,
    ) -> None:
        """Prepara o arquivo de log desta sessão (cria o diretório se preciso)."""
        self.sessao_id = sessao_id
        self.execucao_id = execucao_id
        self.dir_logs = dir_logs or config.DIR_LOGS
        self.dir_logs.mkdir(parents=True, exist_ok=True)
        self.caminho = self.dir_logs / f"{sessao_id}.jsonl"
        self._turno = 0

    def registrar(self, resultado: ResultadoTurno, meta_extra: dict | None = None) -> dict:
        """Grava um turno como uma linha JSON no arquivo da sessão e devolve
        o registro gravado (dict).

        `meta_extra` acrescenta campos DENTRO de `meta` (o schema do turno em
        si permanece inalterado). É por aí que a bateria injeta o contexto de
        rastreio — `via`, `origem_id`, `repeticao`, `modelo_bot`, `status` —
        sem poluir o `ResultadoTurno`, que é do domínio do bot, não do teste.
        Ver docs/plano_de_testes.md §4 e VIAS_DE_ESTIMULO.
        """
        self._turno += 1
        meta = {
            "provedor": resultado.provedor,
            "modelo": resultado.modelo,
            "parametros": resultado.parametros,
            "latencia_s": round(resultado.latencia_s, 4),
            # Quantas chamadas à API o turno custou. > 1 significa que o
            # provedor devolveu conteúdo em branco e a chamada foi repetida
            # (ver ClienteDeepSeek.TENTATIVAS_RESPOSTA_VAZIA). Fica no log
            # para que o retry não esconda a taxa real de falha do provedor —
            # ela é um dado do experimento, não um detalhe de implementação.
            "tentativas_llm": getattr(resultado, "tentativas_llm", 1),
            # Quanto histórico a chamada recebeu: None = tudo; N = as N
            # últimas mensagens (0 = nenhuma). Precisa aparecer no log porque
            # afeta a leitura da avaliação: com contexto reduzido o modelo
            # perde o fio do bate-papo — uma resposta fora de contexto aqui
            # tem causa conhecida.
            "historico_enviado": getattr(resultado, "historico_enviado", None),
            "historico_reduzido": getattr(resultado, "historico_enviado", None) is not None,
        }
        if meta_extra:
            meta.update(meta_extra)
        registro = {
            "sessao_id": self.sessao_id,
            "execucao_id": self.execucao_id,
            "turno_id": self._turno,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mensagem_usuario": resultado.mensagem_usuario,
            "trechos_rag": resultado.trechos_rag,
            "consultas_dados": resultado.consultas_dados,
            "prompt_completo": resultado.prompt_completo,
            "resposta_bruta": resultado.resposta_bruta,
            "resposta_final": resultado.resposta_final,
            "estado": resultado.estado,
            "meta": meta,
        }
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return registro

    def registrar_avaliacao_tom(self, julgamento: dict) -> dict:
        """Acrescenta o julgamento de tom da CONVERSA INTEIRA ao mesmo
        arquivo de log da sessão, como um registro à parte (sem `turno_id`,
        identificado por `"tipo": "avaliacao_tom_sessao"`) — assim ele
        aparece junto dos outros dados já visualizados, não num relatório
        separado.
        """
        registro = {
            "tipo": "avaliacao_tom_sessao",
            "sessao_id": self.sessao_id,
            "execucao_id": self.execucao_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tom_nota": julgamento.get("nota"),
            "tom_adequado": julgamento.get("adequado"),
            "tom_justificativa": julgamento.get("justificativa"),
            "meta": julgamento.get("_meta", {}),
        }
        with open(self.caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return registro


def execucoes_concluidas(caminho: Path) -> set[int] | None:
    """Ids de execução que o runner marcou como CONCLUÍDAS neste arquivo.

    O runner grava um registro `episodio_concluido` só depois de o episódio
    terminar inteiro. Sem esse marcador não há como distinguir uma conversa
    completa de uma interrompida no meio: antes, um único turno no log bastava
    para o episódio contar como feito, e uma queda no 2º de 5 turnos deixava a
    conversa truncada no acervo para sempre — a retomada a pulava.

    Devolve None quando o arquivo não tem marcador nenhum: é log anterior ao
    marcador, e quem consome deve tratá-lo como antes, em vez de descartá-lo
    inteiro.
    """
    concluidas: set[int] = set()
    viu_marcador = False
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            if registro.get("tipo") == "episodio_concluido":
                viu_marcador = True
                concluidas.add(registro.get("execucao_id"))
    return concluidas if viu_marcador else None


def carregar_turnos(caminho: Path) -> list[dict]:
    """Lê um arquivo JSONL de log e devolve só os registros de TURNO.

    Ignora outros tipos de registro que possam estar no mesmo arquivo (ex.:
    avaliação de tom da sessão, ver `carregar_avaliacoes_tom`) — protege
    quem consome isso (fidelidade, relatório da CLI) de registros sem
    `turno_id`.
    """
    registros: list[dict] = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                registro = json.loads(linha)
                if "turno_id" in registro:
                    registros.append(registro)
    return registros


def carregar_avaliacoes_tom(caminho: Path) -> dict[int, dict]:
    """Lê um arquivo JSONL de log e devolve as avaliações de tom por sessão
    já registradas (`Instrumentador.registrar_avaliacao_tom`), indexadas por
    `execucao_id` (a mais recente, se houver mais de uma para a mesma
    execução)."""
    avaliacoes: dict[int, dict] = {}
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                registro = json.loads(linha)
                if registro.get("tipo") == "avaliacao_tom_sessao":
                    avaliacoes[registro.get("execucao_id", 0)] = registro
    return avaliacoes


def extrair_tokens(resposta_bruta: object) -> tuple[int | None, int | None, int | None]:
    """Extrai (entrada, saida, total) do campo `usage` da resposta bruta da API.

    Suporta o formato OpenAI/DeepSeek (prompt/completion/total_tokens) e o da
    Anthropic (input/output_tokens).
    """
    if not isinstance(resposta_bruta, dict):
        return None, None, None
    u = resposta_bruta.get("usage") or {}
    entrada = u.get("prompt_tokens", u.get("input_tokens"))
    saida = u.get("completion_tokens", u.get("output_tokens"))
    total = u.get("total_tokens")
    if total is None and entrada is not None and saida is not None:
        total = entrada + saida
    return entrada, saida, total
