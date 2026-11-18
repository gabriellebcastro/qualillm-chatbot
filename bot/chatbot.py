"""Chatbot de negociação de dívidas.

Orquestra, a cada turno:
  1. recuperação de políticas relevantes (RAG);
  2. consultas à camada de dados (fonte de verdade) conforme o estado da conversa;
  3. seleção do prompt de sistema do ESTÁGIO atual (ver bot/prompts/);
  4. montagem do contexto (políticas + dados + histórico);
  5. chamada ao LLM (via ClienteLLM);
  6. atualização do estado da sessão e retorno da resposta.

A decisão de QUAIS dados consultar é feita aqui, no código, de forma
determinística — assim sabemos exatamente o que foi consultado em cada turno,
o que é essencial para a instrumentação e para a avaliação de fidelidade. O LLM
é responsável pela redação da resposta (linguagem natural + formatação), não
pelos números.

O prompt de sistema é escolhido por ESTÁGIO (bot/prompts/identificacao.md,
negociacao.md) em vez de um único prompt gigante com todos os passos. A
escolha de QUAL prompt usar (identificação ou negociação) é 100%
determinística, decidida ANTES de chamar a LLM (se o cliente já foi
identificado) — nunca depende de a LLM "lembrar" em que etapa está. Isso
também é uma barreira de dados, não só de instrução: antes da identificação,
a LLM sequer recebe dado de dívida no contexto, então não tem como inventar
valores mesmo que tente.

## A negociação é uma ESCADA de três etapas (ver dados/regras.py)

  0. 1ª oferta: à vista, 70% do desconto máximo.
  1. Se o cliente recusar: 2ª oferta, à vista, 100% do desconto máximo.
  2. Se recusar de novo (ou pedir parcelamento a qualquer momento, mesmo
     antes de recusar as ofertas à vista): parcelamento livre — o cliente
     escolhe o número de parcelas, sem desconto e com juros (fica sempre
     mais caro que qualquer oferta à vista).

QUAL condição está em jogo (`self.condicao_escolhida`) é sempre determinístico
— calculado aqui a partir do estágio (`self.estagio_oferta`) e de um número de
parcelas eventualmente mencionado pelo cliente (extraído por regex, uma
extração literal, não um julgamento de intenção). Já a decisão de que o
cliente RECUSOU a oferta atual (e por isso a escada deve avançar) é um
julgamento de intenção como outro qualquer — cabe à LLM, via saída
estruturada (`recusar_oferta`), pelo mesmo motivo de `confirmar_acordo` (ver
abaixo): "não gostei", "tá caro", "tem algo melhor?" têm formas infinitas, e
não são detectáveis com confiança por palavra-chave.

Para o bot conseguir revelar a PRÓXIMA oferta no MESMO turno em que reconhece
uma recusa — sem inventar números nem forçar uma rodada extra de conversa —
o contexto de cada turno inclui, além da condição atual, uma prévia da
próxima oferta (rotulada como uso interno, só a ser revelada em caso de
recusa). O código só PROMOVE essa prévia a condição atual DEPOIS da chamada,
quando `recusar_oferta` vem `true` — a mesma lógica de "code decide o estado,
LLM escreve o texto" usada para o registro do acordo.

Já a decisão de QUANDO o cliente genuinamente confirmou uma condição (e o
acordo deve ser registrado) ou de quando o atendimento deve encerrar NÃO é um
gatilho de palavra-chave sobre a mensagem crua — é a própria LLM, com o
contexto completo da conversa, quem julga a intenção. Essa decisão chega ao
código via SAÍDA ESTRUTURADA (JSON, com `response_format` da API), não um
marcador solto em texto livre: um achado real mostrou o modelo simplesmente
OMITIR um marcador de texto mesmo com instrução explícita no prompt — a
resposta afirmava "acordo registrado" mas o marcador não veio, e nada foi
registrado de fato. Pedir um campo JSON validado pela própria API é mais
confiável do que torcer para a LLM lembrar de uma convenção em prosa. A LLM
não decide OS DADOS do acordo (isso continua vindo do estado determinístico —
qual condição está em jogo agora), só OS SINAIS de intenção (confirmar_acordo,
recusar_oferta, encerrar_sessao).

Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import config
from dados import Acordo, CondicaoParcelamento, Divida, FonteDeDados, regras
from llm import ClienteLLM
from rag import RecuperadorRAG

DIR_PROMPTS = Path(__file__).resolve().parent / "prompts"

MSG_SESSAO_ENCERRADA = (
    "Este atendimento já foi encerrado. Para uma nova negociação, inicie uma nova sessão."
)
# Respostas fixas da guarda de identificação (passo 5.3 de `processar_turno`).
MSG_CPF_NAO_ENCONTRADO = (
    "Não encontrei um cadastro com o CPF informado. Pode conferir o número e me "
    "enviar novamente, por favor?"
)
MSG_PEDIR_CPF = (
    "Para apresentar os dados da dívida, preciso primeiro localizar o cadastro. "
    "Pode me informar o CPF, por favor?"
)

# Etapas da escada de ofertas à vista (0 e 1); 2 = parcelamento livre.
ETAPA_MAX_A_VISTA = 1


@dataclass
class ConsultaDados:
    """Uma consulta feita à fonte de verdade neste turno (dados brutos)."""
    operacao: str
    argumentos: dict
    resultado: object  # dict ou lista de dicts (serializável)


@dataclass
class ResultadoTurno:
    """Tudo o que aconteceu num turno — o que a instrumentação grava no log."""
    mensagem_usuario: str
    resposta_final: str
    trechos_rag: list[dict]
    consultas_dados: list[dict]
    prompt_completo: list[dict]
    resposta_bruta: object
    modelo: str
    provedor: str
    parametros: dict
    latencia_s: float
    estado: dict = field(default_factory=dict)
    # Nº de chamadas à API necessárias neste turno (ver RespostaLLM.tentativas).
    tentativas_llm: int = 1
    # Quanto histórico a chamada que gerou a resposta recebeu (None = tudo;
    # N = as N últimas mensagens) — ver RespostaLLM.historico_enviado.
    historico_enviado: int | None = None


class Chatbot:
    def __init__(
        self,
        fonte: FonteDeDados,
        recuperador: RecuperadorRAG,
        cliente_llm: ClienteLLM,
        temperatura: float | None = None,
        k_rag: int = 4,
        max_tokens: int = 512,
    ) -> None:
        """Monta o bot com suas dependências (dados, RAG, LLM) e carrega os
        dois prompts de sistema do disco."""
        self.fonte = fonte
        self.recuperador = recuperador
        self.llm = cliente_llm
        self.temperatura = temperatura
        self.k_rag = k_rag
        self.max_tokens = max_tokens
        self.prompt_identificacao = (DIR_PROMPTS / "identificacao.md").read_text(encoding="utf-8")
        self.prompt_negociacao = (DIR_PROMPTS / "negociacao.md").read_text(encoding="utf-8")
        self.reiniciar()

    def _selecionar_prompt(self) -> str:
        """Escolhe o prompt de sistema do estágio atual (identificação ou
        negociação) — 100% determinístico, decidido antes de chamar a LLM."""
        if self.cliente is None:
            return self.prompt_identificacao
        return self.prompt_negociacao

    # -- Estado da sessão ----------------------------------------------------
    def reiniciar(self) -> None:
        """Zera o estado da conversa (nova sessão, do zero)."""
        self.historico: list[dict] = []
        self.cliente = None
        self.dividas: list[Divida] = []
        self.divida_atual: Divida | None = None
        self.estagio_oferta: int = 0
        self.condicoes: list[CondicaoParcelamento] | None = None
        self.condicao_escolhida: CondicaoParcelamento | None = None
        # Data de vencimento pedida pelo cliente (mesma regra para à vista e
        # parcelado — ver dados/regras.py). None = usa a oferta padrão (D+1
        # útil); uma vez escolhida, persiste entre turnos e etapas da escada.
        self.data_vencimento_escolhida: date | None = None
        self.acordo: Acordo | None = None
        self.finalizada: bool = False
        # Última etapa à vista em jogo antes do parcelamento (0 se o cliente
        # pediu para parcelar logo na 1ª oferta, 1 depois das duas recusas).
        # É a oferta à vista que continua valendo se ele quiser voltar a ela.
        self.etapa_a_vista: int = 0
        # O cliente, já no parcelamento, voltou à oferta à vista: a condição
        # em jogo passa a ser a da `etapa_a_vista` (ver `_voltar_a_vista`).
        self.voltou_a_vista: bool = False
        # Prévia da próxima oferta, recalculada a cada turno (ver docstring
        # do módulo) — nunca persiste entre turnos por conta própria.
        self._proxima_oferta: CondicaoParcelamento | None = None
        self._proxima_oferta_hint: str | None = None
        # Data pedida nesta mensagem que caiu fora da janela permitida — só
        # um aviso transitório para o contexto deste turno, não persiste.
        self._data_invalida_pedida: date | None = None
        # Oferta à vista que continua valendo durante o parcelamento,
        # recalculada a cada turno (ver `_atualizar_dados`).
        self._oferta_a_vista: CondicaoParcelamento | None = None
        # O CPF desta mensagem foi consultado e não existe no cadastro — aviso
        # transitório para o contexto e para a guarda de `processar_turno`.
        self._cpf_nao_encontrado: bool = False

    # -- Turno ---------------------------------------------------------------
    def processar_turno(self, mensagem_usuario: str) -> ResultadoTurno:
        """Processa uma mensagem do cliente e devolve a resposta do bot.

        Ver o docstring do módulo para o passo a passo completo (RAG →
        consultas → prompt → LLM → registro/encerramento).
        """
        # 0. Sessão já encerrada: responde sem consultar RAG/dados/LLM.
        if self.finalizada:
            return ResultadoTurno(
                mensagem_usuario=mensagem_usuario,
                resposta_final=MSG_SESSAO_ENCERRADA,
                trechos_rag=[],
                consultas_dados=[],
                prompt_completo=[],
                resposta_bruta=None,
                modelo="sistema",
                provedor="sistema",
                parametros={},
                latencia_s=0.0,
                estado=self._estado_atual(),
            )

        # 1. RAG
        trechos = self.recuperador.recuperar(mensagem_usuario, k=self.k_rag)

        # 2. Consultas à fonte de verdade, conforme o estado
        consultas = self._atualizar_dados(mensagem_usuario)

        # 3. Prompt do estágio atual (já reflete o resultado de _atualizar_dados)
        prompt_sistema = self._selecionar_prompt()

        # 4. Montagem do contexto
        bloco_contexto = self._montar_contexto(trechos)
        mensagens = [
            *self.historico,
            {"role": "system", "content": bloco_contexto},
            {"role": "user", "content": mensagem_usuario},
        ]
        prompt_completo = [
            {"role": "system", "content": prompt_sistema},
            *mensagens,
        ]

        # 5. LLM — resposta em JSON estruturado (ver bot/prompts/), validado
        # pela própria API via response_format quando o provedor suportar.
        resposta = self.llm.gerar(
            sistema=prompt_sistema,
            mensagens=mensagens,
            temperatura=self.temperatura,
            max_tokens=self.max_tokens,
            formato_json=True,
        )
        (
            texto_final, confirmou_acordo, recusou_oferta, encerrou_sessao,
            data_ofertada,
        ) = _extrair_resposta_estruturada(resposta.texto)

        # 5.3 Guarda da identificação. Antes de o cliente ser localizado o
        # contexto não tem dado de dívida nenhum, então qualquer dado de dívida
        # na resposta é inventado. Achado da Fase 1 (persona_adversarial_001):
        # a consulta do CPF voltou vazia e o bot respondeu "Localizei o
        # cadastro", e no turno seguinte inventou credor, valores e atraso. A
        # instrução no prompt não basta como garantia; a resposta é trocada
        # por uma fixa, e a da LLM continua em `resposta_bruta` no log.
        if self.cliente is None and _apresenta_dados_de_divida(texto_final):
            texto_final = MSG_CPF_NAO_ENCONTRADO if self._cpf_nao_encontrado else MSG_PEDIR_CPF
            encerrou_sessao = False

        # 5.4 Volta à oferta à vista, já no parcelamento. Achado da Fase 1
        # (persona_insistente_001): a cliente recusou 24x, voltou ao à vista
        # e confirmou "o à vista de 1.798,50"; o estado tinha ficado no
        # parcelamento, e o acordo foi registrado em 24x. A LLM sinaliza a
        # volta (campo estruturado), o código troca a condição em jogo, e só
        # depois o passo 6 decide se registra — inclusive quando a volta e a
        # confirmação vêm na mesma resposta.
        if (
            _campo_booleano(resposta.texto, "voltar_a_vista")
            and self.acordo is None
            and self.estagio_oferta > ETAPA_MAX_A_VISTA
            and not self.voltou_a_vista
        ):
            self._voltar_a_vista(consultas)

        # 5.5 Data de vencimento que a LLM acabou de oferecer ao cliente.
        # Precisa vir da saída estruturada, e não só do regex sobre a
        # mensagem: o cliente pede a data em linguagem natural ("a mais
        # distante possível", "na sexta", "no último dia que der") e o regex
        # de DD/MM não pega nada disso. Achado real de teste: o bot disse
        # 28/08 ao cliente e o código registrou o acordo com 24/08, porque a
        # condição tinha ficado na data padrão. É a mesma classe de bug do
        # acordo registrado ≠ acordo descrito, e a mesma causa (intenção
        # capturada por palavra-chave em vez de vir do campo estruturado).
        #
        # Quem MANDA continua sendo o código: a data proposta só é aceita se
        # passar em `data_vencimento_valida` (dia útil, dentro da janela).
        # A LLM diz o que entendeu; a regra de negócio é validada aqui.
        if data_ofertada and self.acordo is None:
            pedida = _parse_data_estruturada(data_ofertada)
            if (
                pedida is not None
                and pedida != self.data_vencimento_escolhida
                and regras.data_vencimento_valida(config.data_referencia(), pedida)
            ):
                self.data_vencimento_escolhida = pedida
                self._recalcular_condicao_atual(consultas)

        # 6. Registro do acordo OU avanço da escada — nunca os dois no mesmo
        # turno. QUAL condição é registrada continua determinístico
        # (self.condicao_escolhida, já calculado em _atualizar_dados); a LLM
        # só sinaliza a intenção. Se recusou, a "próxima oferta" já estava no
        # contexto desta chamada (rotulada como uso interno) — promovê-la
        # aqui mantém a resposta que a LLM acabou de escrever consistente
        # com os dados que ela realmente tinha em mãos.
        if confirmou_acordo and self.condicao_escolhida is not None and self.acordo is None:
            acordo = self.fonte.registrar_acordo(
                self.divida_atual.id, self.condicao_escolhida.id
            )
            self.acordo = acordo
            consultas.append(
                ConsultaDados(
                    "registrar_acordo",
                    {"divida_id": self.divida_atual.id, "condicao_id": self.condicao_escolhida.id},
                    acordo.to_dict(),
                )
            )
        elif recusou_oferta and self.acordo is None and self.estagio_oferta <= ETAPA_MAX_A_VISTA:
            if self.estagio_oferta == ETAPA_MAX_A_VISTA:
                self.etapa_a_vista = ETAPA_MAX_A_VISTA
            self.estagio_oferta += 1
            if self._proxima_oferta is not None:
                self.condicoes = [self._proxima_oferta]
                self.condicao_escolhida = self._proxima_oferta
            else:
                # Virou etapa 2 (parcelamento) sem um nº de parcelas ainda
                # escolhido — nada a confirmar até o cliente informar quantas.
                self.condicoes = []
                self.condicao_escolhida = None

        # 7. Atualiza histórico (apenas user/assistant, só o texto da
        # resposta ao cliente — os campos de controle não fazem parte dela).
        #
        # Resposta em branco NÃO entra no histórico: mandar de volta uma
        # mensagem de assistant vazia é alimentar o modelo com uma conversa
        # degenerada. Num log real de sessão manual, 8 das 18 mensagens de
        # assistant enviadas à API tinham conteúdo vazio — lixo acumulado a
        # cada falha do provedor (ver ClienteDeepSeek.TENTATIVAS_RESPOSTA_VAZIA).
        # A mensagem do CLIENTE continua no histórico mesmo assim: ele de fato
        # a escreveu, e o modelo precisa dela para responder no turno seguinte.
        self.historico.append({"role": "user", "content": mensagem_usuario})
        if texto_final.strip():
            self.historico.append({"role": "assistant", "content": texto_final})

        # 8. Encerra a sessão: acordo acabou de ser registrado, o LLM
        # sinalizou o fim do atendimento (campo estruturado — cobre recusas e
        # despedidas em qualquer formulação), ou o cliente usou uma
        # palavra-chave explícita de encerramento (rede de segurança para o
        # caso de recusa, onde a decisão não pode ser tomada antes da
        # chamada; para o registro do acordo em si não há mais essa rede de
        # segurança por palavra-chave — ver docstring do módulo).
        if self.acordo is not None or encerrou_sessao or _detectar_encerramento(mensagem_usuario):
            self.finalizada = True

        return ResultadoTurno(
            mensagem_usuario=mensagem_usuario,
            resposta_final=texto_final,
            trechos_rag=[t.to_dict() for t in trechos],
            consultas_dados=[
                {"operacao": c.operacao, "argumentos": c.argumentos, "resultado": c.resultado}
                for c in consultas
            ],
            prompt_completo=prompt_completo,
            resposta_bruta=resposta.bruto,
            modelo=resposta.modelo,
            provedor=resposta.provedor,
            parametros=resposta.parametros,
            latencia_s=resposta.latencia_s,
            estado=self._estado_atual(),
            tentativas_llm=resposta.tentativas,
            historico_enviado=resposta.historico_enviado,
        )

    # -- Lógica de consulta de dados ----------------------------------------
    def _atualizar_dados(self, msg: str) -> list[ConsultaDados]:
        """Atualiza cliente/dívida/condição-atual a partir da mensagem e do
        estado atual, consultando a fonte de verdade conforme necessário.
        Devolve as consultas feitas neste turno (para o log)."""
        consultas: list[ConsultaDados] = []
        self._proxima_oferta = None
        self._proxima_oferta_hint = None
        self._data_invalida_pedida = None
        self._oferta_a_vista = None
        self._cpf_nao_encontrado = False

        # Identificação do cliente
        if self.cliente is None:
            ident = _extrair_identificador(msg)
            if ident:
                cli = self.fonte.consultar_cliente(ident)
                consultas.append(
                    ConsultaDados(
                        "consultar_cliente", {"identificador": ident},
                        cli.to_dict() if cli else None,
                    )
                )
                self._cpf_nao_encontrado = cli is None
                if cli:
                    self.cliente = cli
                    dividas = self.fonte.consultar_dividas(cli.id)
                    self.dividas = dividas
                    self.divida_atual = dividas[0] if dividas else None
                    consultas.append(
                        ConsultaDados(
                            "consultar_dividas", {"cliente_id": cli.id},
                            [d.to_dict() for d in dividas],
                        )
                    )

        if self.cliente is None or self.divida_atual is None or self.acordo is not None:
            return consultas

        divida_id = self.divida_atual.id
        hoje = config.data_referencia()

        # Pedido de uma data de vencimento diferente nesta mensagem — mesma
        # regra para à vista e parcelado (ver dados/regras.py). Extração
        # literal por regex, não julgamento de intenção. Se vier fora da
        # janela permitida, NÃO substitui a escolha válida anterior (ou o
        # padrão): fica só um aviso transitório para o contexto explicar ao
        # cliente, sem quebrar a condição que já estava confirmável.
        data_pedida = _extrair_data_pedida(msg, hoje.year)
        if data_pedida is not None:
            if regras.data_vencimento_valida(hoje, data_pedida):
                self.data_vencimento_escolhida = data_pedida
            else:
                self._data_invalida_pedida = data_pedida
        data_override = self.data_vencimento_escolhida

        # Pedido explícito de parcelamento (número de parcelas mencionado
        # nesta mensagem) tem prioridade máxima para decidir o MODO: o
        # cliente pode pedir parcelamento a qualquer momento, não só depois
        # de recusar as duas ofertas à vista. Extração literal por regex —
        # não é julgamento de intenção, é leitura de um número escrito.
        n_pedido = _extrair_num_parcelas(msg, aceitar_numero_solto=self._falando_de_parcelas())
        if n_pedido is not None:
            if self.estagio_oferta <= ETAPA_MAX_A_VISTA:
                self.etapa_a_vista = self.estagio_oferta
            self.estagio_oferta = 2
            self.voltou_a_vista = False

        if self.estagio_oferta == 2:
            # A oferta à vista continua valendo durante o parcelamento, e vai
            # ao contexto com os dados reais. Sem ela, quando o cliente queria
            # voltar ao à vista, o bot só tinha o histórico para se apoiar, e
            # na Fase 1 inventou valores (R$ 430,56 numa dívida cujas ofertas
            # eram R$ 349,83 e R$ 269,10).
            vista = self.fonte.consultar_condicoes(
                divida_id, estagio=self.etapa_a_vista, data_vencimento=data_override
            )
            consultas.append(
                ConsultaDados(
                    "consultar_condicoes",
                    {"divida_id": divida_id, "estagio": self.etapa_a_vista},
                    [c.to_dict() for c in vista],
                )
            )
            self._oferta_a_vista = vista[0] if vista else None
            if self.voltou_a_vista:
                self.condicoes = vista
                self.condicao_escolhida = self._oferta_a_vista
                return consultas
            # Já em modo parcelado: usa o N desta mensagem, ou o que já
            # estava escolhido (ex.: o cliente só mudou a data, sem repetir
            # o número de parcelas). Recalcula sempre — idempotente, barato,
            # garante que o contexto nunca fique com um valor desatualizado.
            n = n_pedido if n_pedido is not None else (
                self.condicao_escolhida.num_parcelas if self.condicao_escolhida else None
            )
            if n is None:
                self.condicoes = []
                self.condicao_escolhida = None
                return consultas
            conds = self.fonte.consultar_condicoes(
                divida_id, estagio=2, num_parcelas=n, data_vencimento=data_override
            )
            consultas.append(
                ConsultaDados(
                    "consultar_condicoes",
                    {"divida_id": divida_id, "estagio": 2, "num_parcelas": n},
                    [c.to_dict() for c in conds],
                )
            )
            self.condicoes = conds
            self.condicao_escolhida = conds[0] if conds else None
            return consultas

        # Etapa 0 ou 1 (escada à vista): mantém a oferta da etapa atual.
        conds = self.fonte.consultar_condicoes(
            divida_id, estagio=self.estagio_oferta, data_vencimento=data_override
        )
        consultas.append(
            ConsultaDados(
                "consultar_condicoes",
                {"divida_id": divida_id, "estagio": self.estagio_oferta},
                [c.to_dict() for c in conds],
            )
        )
        self.condicoes = conds
        self.condicao_escolhida = conds[0] if conds else None

        # Prévia da PRÓXIMA oferta — só é revelada pelo prompt se o cliente
        # recusar a atual NESTE MESMO turno (ver docstring do módulo).
        if self.estagio_oferta < ETAPA_MAX_A_VISTA:
            proximas = self.fonte.consultar_condicoes(
                divida_id, estagio=self.estagio_oferta + 1, data_vencimento=data_override
            )
            consultas.append(
                ConsultaDados(
                    "consultar_condicoes",
                    {"divida_id": divida_id, "estagio": self.estagio_oferta + 1},
                    [c.to_dict() for c in proximas],
                )
            )
            self._proxima_oferta = proximas[0] if proximas else None
        else:
            # A próxima etapa é o parcelamento livre — não há uma única
            # condição a pré-calcular (depende do N que o cliente ainda vai
            # escolher); só um resumo textual da regra.
            self._proxima_oferta_hint = _descrever_regra_parcelamento(
                self.divida_atual.valor_atualizado
            )

        return consultas

    def _falando_de_parcelas(self) -> bool:
        """True quando o assunto da conversa já é o número de parcelas.

        Só nesse caso um número solto ("muda pra 10") é lido como parcelas
        (ver `_extrair_num_parcelas`): já no parcelamento, ou quando a última
        resposta do bot perguntou em quantas vezes o cliente quer pagar.
        """
        if self.estagio_oferta > ETAPA_MAX_A_VISTA:
            return True
        ultima = next((m["content"] for m in reversed(self.historico)
                       if m["role"] == "assistant"), "")
        return bool(_RE_PERGUNTA_PARCELAS.search(ultima))

    def _recalcular_condicao_atual(self, consultas: list[ConsultaDados]) -> None:
        """Recalcula a condição em jogo com a data de vencimento escolhida.

        Chamado DEPOIS da resposta da LLM, quando ela sinaliza uma data que o
        código ainda não tinha registrado (ver passo 5.5 de `processar_turno`).
        Mantém o estado determinístico alinhado com o que o cliente acabou de
        ouvir, para o acordo não ser registrado com outra data.
        """
        if self.divida_atual is None:
            return
        divida_id = self.divida_atual.id
        estagio = self.etapa_a_vista if self.voltou_a_vista else self.estagio_oferta
        argumentos: dict = {"divida_id": divida_id, "estagio": estagio}

        if estagio > ETAPA_MAX_A_VISTA:
            n = self.condicao_escolhida.num_parcelas if self.condicao_escolhida else None
            if n is None:
                return
            argumentos["num_parcelas"] = n
            conds = self.fonte.consultar_condicoes(
                divida_id, estagio=2, num_parcelas=n,
                data_vencimento=self.data_vencimento_escolhida,
            )
        else:
            conds = self.fonte.consultar_condicoes(
                divida_id, estagio=estagio,
                data_vencimento=self.data_vencimento_escolhida,
            )

        consultas.append(
            ConsultaDados("consultar_condicoes", argumentos, [c.to_dict() for c in conds])
        )
        if conds:
            self.condicoes = conds
            self.condicao_escolhida = conds[0]

    def _voltar_a_vista(self, consultas: list[ConsultaDados]) -> None:
        """Troca a condição em jogo pela oferta à vista que continua valendo.

        Chamado DEPOIS da resposta da LLM, quando ela sinaliza que o cliente,
        já no parcelamento, quer voltar a pagar à vista (passo 5.4 de
        `processar_turno`). A oferta é consultada de novo, com a data já
        escolhida, para o acordo ser registrado com os dados que o cliente
        ouviu. O estágio continua 2: se o cliente voltar a pedir um número de
        parcelas, o parcelamento é retomado.
        """
        if self.divida_atual is None:
            return
        divida_id = self.divida_atual.id
        conds = self.fonte.consultar_condicoes(
            divida_id, estagio=self.etapa_a_vista,
            data_vencimento=self.data_vencimento_escolhida,
        )
        consultas.append(
            ConsultaDados(
                "consultar_condicoes",
                {"divida_id": divida_id, "estagio": self.etapa_a_vista},
                [c.to_dict() for c in conds],
            )
        )
        if conds:
            self.voltou_a_vista = True
            self.condicoes = conds
            self.condicao_escolhida = conds[0]

    # -- Montagem do contexto do prompt -------------------------------------
    def _montar_contexto(self, trechos) -> str:
        """Monta o bloco de contexto (políticas do RAG + dados da fonte de
        verdade disponíveis até agora) enviado como mensagem de sistema
        adicional em cada turno."""
        partes = ["POLÍTICAS RELEVANTES (recuperadas da base de conhecimento):"]
        for t in trechos:
            partes.append(f"- ({t.origem}) {t.texto}")

        # O aviso sobre os identificadores existe porque o modelo copiou o
        # formato deste bloco para a fala ao cliente: num teste de fumaça ele
        # respondeu "Localizei o cadastro de Henrique Dias (id CLI-008)". O
        # prompt não pedia o id em lugar nenhum — ele veio daqui, e faltava
        # dizer que esta parte é de consumo interno. O bloco já marca a oferta
        # seguinte como "[USO INTERNO]"; os identificadores não tinham marca.
        partes.append(
            "\nDADOS DA FONTE DE VERDADE (use EXATAMENTE estes valores; "
            "valores monetários estão em reais com ponto decimal e datas em "
            "formato ISO AAAA-MM-DD — formate-os conforme as regras do sistema).\n"
            "Os identificadores internos (id de cliente, de dívida, de condição "
            "e de acordo) servem só para você se orientar: NUNCA os repita ao "
            "cliente, nem como referência de protocolo:"
        )

        if self.cliente is None:
            partes.append("- Cliente ainda não identificado. Solicite apenas o CPF.")
            if self._cpf_nao_encontrado:
                partes.append(
                    "- O CPF informado nesta mensagem NÃO foi encontrado no cadastro. "
                    "Não diga que localizou o cadastro e não apresente nenhum dado de "
                    "dívida: diga que não encontrou cadastro com esse CPF e peça para "
                    "o cliente conferir o número."
                )
        else:
            partes.append(
                f"- Cliente: {self.cliente.nome} (id {self.cliente.id})"
            )
        if self.divida_atual is not None:
            d = self.divida_atual
            partes.append(
                f"- Dívida {d.id}: credor {d.credor}; valor_original {d.valor_original}; "
                f"valor_atualizado {d.valor_atualizado}; dias_atraso {d.dias_atraso}; "
                f"vencimento_original {d.data_vencimento_original}"
            )

        if self.acordo is None and self.condicao_escolhida is not None:
            partes.append(
                f"- Condição atual ofertada ({_rotulo_condicao(self.condicao_escolhida)}): "
                + _descrever_condicao(self.condicao_escolhida)
            )
        elif (
            self.acordo is None
            and self.divida_atual is not None
            and self.estagio_oferta > ETAPA_MAX_A_VISTA
            and self.condicao_escolhida is None
        ):
            partes.append(
                "- Nenhuma condição de parcelamento foi escolhida ainda. "
                + _descrever_regra_parcelamento(self.divida_atual.valor_atualizado)
                + " Pergunte ao cliente em quantas parcelas ele prefere pagar."
            )
        if (
            self.acordo is None
            and self._oferta_a_vista is not None
            and not self.voltou_a_vista
        ):
            partes.append(
                "- Oferta à vista que continua valendo, se o cliente quiser voltar a "
                "pagar à vista (já foi apresentada; use exatamente estes valores e "
                "marque \"voltar_a_vista\": true quando ele escolher voltar a ela): "
                + _descrever_condicao(self._oferta_a_vista)
            )

        if self.acordo is None and self.divida_atual is not None:
            hoje = config.data_referencia()
            data_min = regras.data_vencimento_padrao(hoje)
            # A LISTA das datas válidas, e não só os extremos: um intervalo
            # "de X até Y" contém o feriado do meio, e o bot o oferecia.
            validas = ", ".join(d.isoformat() for d in regras.datas_validas(hoje))
            partes.append(
                f"- Janela de datas de pagamento possível (à vista ou 1ª parcela): "
                f"SOMENTE estas datas: {validas}. Nenhuma outra é válida — sábado, "
                f"domingo e feriado nunca. Sem pedido do cliente, use {data_min.isoformat()}. "
                f"Ao apresentar as opções, cite as datas uma a uma, não como intervalo."
            )
            # O limite real vai em todo turno, e não só junto da prévia do
            # parcelamento. Achado da Fase 1 (persona_confuso_001,
            # persona_cooperativo_001): o cliente perguntava em quantas vezes
            # dava ainda na 1ª oferta, o contexto não tinha o limite, e o bot
            # respondia "até 24 parcelas" numa dívida que comportava 8.
            max_n = regras.max_parcelas_possivel(self.divida_atual.valor_atualizado)
            minimo = f"{regras.VALOR_MINIMO_PARCELA:.2f}".replace(".", ",")
            partes.append(
                f"- Limite de parcelas DESTA dívida: até {max_n} parcelas, com mínimo de "
                f"R$ {minimo} por parcela. Sempre que falar do parcelamento, informe "
                f"este limite (\"em até {max_n} parcelas\"), nunca outro número."
            )
            if self._data_invalida_pedida is not None:
                partes.append(
                    f"- O cliente pediu a data {self._data_invalida_pedida.isoformat()}, que "
                    f"NÃO é válida (fora da lista acima: fim de semana, feriado ou fora do "
                    f"prazo). Apresente as datas permitidas e peça uma delas — não aceite a "
                    f"data pedida."
                )

        if self._proxima_oferta is not None:
            partes.append(
                "\n[USO INTERNO — não revele isto ao cliente a menos que ele recuse "
                "CLARAMENTE a condição atual NESTA mensagem]"
            )
            partes.append(
                f"- Se o cliente recusar, a próxima oferta seria "
                f"({_rotulo_condicao(self._proxima_oferta)}): "
                + _descrever_condicao(self._proxima_oferta)
            )
        elif self._proxima_oferta_hint is not None:
            partes.append(
                "\n[USO INTERNO — não revele isto ao cliente a menos que ele recuse "
                "CLARAMENTE a condição atual NESTA mensagem]"
            )
            partes.append(f"- Se o cliente recusar, ofereça o parcelamento: {self._proxima_oferta_hint}")

        if self.acordo is not None:
            a = self.acordo
            partes.append(
                f"- Acordo REGISTRADO {a.id}: {a.num_parcelas} parcela(s); "
                f"valor_parcela {a.valor_parcela}; valor_ultima_parcela {a.valor_ultima_parcela}; "
                f"valor_total {a.valor_total}; primeiro_vencimento {a.data_primeiro_vencimento}; "
                f"registrado_em {a.data_registro}"
            )

        return "\n".join(partes)

    def _estado_atual(self) -> dict:
        """Snapshot do estado da sessão (usado no log e na UI de depuração)."""
        return {
            "cliente_id": self.cliente.id if self.cliente else None,
            "divida_id": self.divida_atual.id if self.divida_atual else None,
            "estagio_oferta": self.estagio_oferta,
            "data_vencimento_escolhida": (
                self.data_vencimento_escolhida.isoformat()
                if self.data_vencimento_escolhida else None
            ),
            "condicao_escolhida_id": (
                self.condicao_escolhida.id if self.condicao_escolhida else None
            ),
            "acordo_id": self.acordo.id if self.acordo else None,
            "voltou_a_vista": self.voltou_a_vista,
            "sessao_finalizada": self.finalizada,
        }


# -- Formatação de condições (uso interno, no bloco de contexto) -----------
def _rotulo_condicao(c: CondicaoParcelamento) -> str:
    """Rótulo curto do tipo de condição, para o cabeçalho do bloco de contexto."""
    return "à vista" if c.tipo == "vista" else f"parcelado em {c.num_parcelas}x"


def _descrever_condicao(c: CondicaoParcelamento) -> str:
    """Descreve os dados de uma condição no formato usado no contexto.

    O percentual de desconto/juros é omitido de propósito — o cliente não
    deve ver esse número, só os valores finais (parcela, total, vencimento);
    não incluir no contexto garante que o LLM não tenha como citá-lo (não
    depende apenas de instrução no prompt).
    """
    return (
        f"{c.num_parcelas} parcela(s); valor_parcela {c.valor_parcela}; "
        f"valor_ultima_parcela {c.valor_ultima_parcela}; "
        f"valor_total {c.valor_total_com_desconto}; "
        f"primeiro_vencimento {c.data_primeiro_vencimento}"
    )


def _descrever_regra_parcelamento(valor_atualizado: float) -> str:
    """Frase-resumo da regra de parcelamento livre, com o teto real (quando
    existe) calculado a partir do valor da dívida — ver
    dados.regras.max_parcelas_possivel."""
    max_n = regras.max_parcelas_possivel(valor_atualizado)
    limite = f"até {max_n} parcelas" if max_n is not None else "sem limite de parcelas"
    return (
        f"o cliente escolhe o número de parcelas que preferir ({limite}), "
        f"respeitando o mínimo de R$ 50,00 por parcela; o parcelamento não tem "
        f"desconto e tem juros, então fica mais caro que qualquer oferta à vista."
    )


# -- Heurísticas de parsing (determinísticas) -------------------------------
# Apenas CPF é aceito como identificador (o bot só pede o CPF ao cliente).
_RE_CPF = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")
# Menção explícita a uma quantidade de parcelas ("8x", "10 parcelas") — não
# inclui "à vista": a oferta à vista é a condição da etapa atual da escada,
# não uma opção com "1 parcela" que o cliente precise selecionar.
_RE_PARCELAS = re.compile(r"(\d+)\s*(?:x|vez|vezes|parcela|parcelas)", re.IGNORECASE)
# Número solto de parcelas, aceito só quando o assunto já é o parcelamento
# (ver `Chatbot._falando_de_parcelas`). Achado da Fase 1 (caso_ambiguidade_002,
# 5 de 5 execuções): "muda pra 10" não tinha "x" nem "vezes", a condição
# ficou em 6x, e o bot inventou os valores de 10x. Só vale a mensagem que é
# o número sozinho ou o número logo depois de "em", "pra", "para", "com" ou
# "ser" ("pode ser 12"), e nunca seguido de casa decimal, barra de data, "%"
# ou unidade de valor ou de tempo — "pago 50 reais", "dia 10" e "R$ 1.540"
# não são parcelas.
_RE_PARCELAS_SOLTO = re.compile(
    r"(?:^\s*|\b(?:em|pra|para|com|ser)\s+)(\d{1,2})(?![\d.,/%])"
    r"(?!\s*(?:reais|real|conto|contos|dias?|mes|mês|meses|por\s+m[eê]s|por\s+parcela|%))",
    re.IGNORECASE,
)
# A pergunta do bot que põe o número de parcelas em pauta.
_RE_PERGUNTA_PARCELAS = re.compile(r"quantas\s+(?:vezes|parcelas)", re.IGNORECASE)
# Data no formato DD/MM ou DD/MM/AAAA — o mesmo formato que o próprio bot é
# instruído a sempre usar, então é o formato mais provável de o cliente
# ecoar de volta ao pedir uma data diferente.
_RE_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
# Sinaliza que o cliente quer encerrar o atendimento sem fechar acordo (recusa
# negociar, cancela ou pede para parar). A sessão também deve encerrar aqui,
# não só quando um acordo é registrado. É só uma rede de segurança — o sinal
# principal é o campo "encerrar_sessao" da resposta estruturada da LLM —, por
# isso usa frases de intenção em 1ª pessoa, não verbos soltos: um teste real
# mostrou o cliente perguntando "não tem como desistir depois, né?" (dúvida
# sobre a irreversibilidade do acordo, não um pedido de encerramento) e o
# "desistir" solto encerrava a sessão errado, no meio de um fluxo de aceite.
_ENCERRAMENTOS = (
    "quero desistir", "vou desistir", "prefiro desistir", "desisto",
    "quero cancelar", "quero encerrar", "pode cancelar", "pode encerrar",
    "não quero negociar", "nao quero negociar", "não quero mais negociar",
    "nao quero mais negociar", "não tenho interesse", "nao tenho interesse",
    "sem interesse", "não, obrigado", "nao, obrigado", "não obrigado",
    "nao obrigado", "chega por hoje", "pare por aqui", "finalizar atendimento",
    "tchau", "até mais", "ate mais", "até logo", "ate logo",
)


def _extrair_identificador(msg: str) -> str | None:
    """Extrai um CPF da mensagem (com ou sem pontuação), se houver algum."""
    m = _RE_CPF.search(msg)
    return m.group(0) if m else None


def _extrair_num_parcelas(msg: str, aceitar_numero_solto: bool = False) -> int | None:
    """Se a mensagem mencionar mais de um número de parcelas (comparando ou
    mudando de ideia na mesma frase), usa a ÚLTIMA menção — reflete a
    preferência mais recente do cliente, não a primeira opção citada.

    A menção explícita ("10x", "10 vezes") vale sempre. O número solto ("muda
    pra 10") só vale com `aceitar_numero_solto`, quando o assunto já é o
    parcelamento (ver `_RE_PARCELAS_SOLTO`).
    """
    candidatos = [int(m.group(1)) for m in _RE_PARCELAS.finditer(msg)]
    if not candidatos and aceitar_numero_solto:
        candidatos = [int(m.group(1)) for m in _RE_PARCELAS_SOLTO.finditer(msg)
                      if int(m.group(1)) >= 1]
    return candidatos[-1] if candidatos else None


def _extrair_data_pedida(msg: str, ano_padrao: int) -> date | None:
    """Extrai uma data DD/MM ou DD/MM/AAAA mencionada na mensagem, se houver
    (última menção, mesmo critério de `_extrair_num_parcelas`).

    Sem ano explícito, assume o ano de referência do sistema. Uma data
    calendário inválida (ex.: "31/02") é ignorada (devolve None) — não é
    reportada como "fora da janela", porque sequer é uma data real.
    """
    candidatos = list(_RE_DATA.finditer(msg))
    if not candidatos:
        return None
    m = candidatos[-1]
    dia, mes = int(m.group(1)), int(m.group(2))
    ano = int(m.group(3)) if m.group(3) else ano_padrao
    if ano < 100:
        ano += 2000
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _contem_algum(msg: str, termos: tuple[str, ...]) -> bool:
    """Como palavra/frase inteira (\\b), não como substring solta — evita
    falso positivo tipo "sim" dentro de "assim" ou "desistir" dentro de uma
    pergunta sobre reversibilidade do acordo."""
    baixo = msg.lower()
    return any(re.search(rf"\b{re.escape(t)}\b", baixo) for t in termos)


# Sinais de que uma resposta apresenta dados de uma dívida: valor em reais,
# "localizei/encontrei" seguido de cadastro ou dívida, credor, atraso ou valor
# original/atualizado. Usado só antes da identificação (passo 5.3).
_RE_DADOS_DE_DIVIDA = re.compile(
    r"R\$\s?\d"
    r"|(?<!não )(?<!nao )\b(?:localizei|encontrei)\b[^.!?]*\b(?:cadastro|d[ií]vida)"
    r"|\bcredor\b|\bdias de atraso\b|\bvalor (?:original|atualizado)\b",
    re.IGNORECASE,
)


def _apresenta_dados_de_divida(texto: str) -> bool:
    """True se a resposta apresenta (ou diz ter localizado) dados de dívida."""
    return bool(_RE_DADOS_DE_DIVIDA.search(texto))


def _detectar_encerramento(msg: str) -> bool:
    """Rede de segurança: True se a mensagem do cliente contém uma frase
    inequívoca de recusa/encerramento (ver `_ENCERRAMENTOS`)."""
    return _contem_algum(msg, _ENCERRAMENTOS)


_RE_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _parse_data_estruturada(valor: object) -> date | None:
    """Interpreta a data do campo estruturado (AAAA-MM-DD ou DD/MM/AAAA).

    Devolve None em qualquer formato inesperado — quem chama trata isso como
    "a LLM não sinalizou data", nunca como erro fatal.
    """
    if not isinstance(valor, str) or not valor.strip():
        return None
    bruto = valor.strip()
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        pass
    m = _RE_DATA.fullmatch(bruto)
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    if not ano:
        return None
    try:
        return date(int(ano) + (2000 if len(ano) == 2 else 0), mes, dia)
    except ValueError:
        return None


def _campo_booleano(texto: str, campo: str) -> bool:
    """Lê um sinal booleano da saída estruturada; ausente ou mal formado é False.

    Mesma falha fechada de `_extrair_resposta_estruturada`: sem JSON válido e
    sem "resposta", nenhum sinal é assumido.
    """
    m = _RE_JSON.search(texto)
    if not m:
        return False
    try:
        dados = json.loads(m.group(0))
    except json.JSONDecodeError:
        return False
    if not isinstance(dados, dict) or not str(dados.get("resposta") or "").strip():
        return False
    return dados.get(campo) is True


def _extrair_resposta_estruturada(texto: str) -> tuple[str, bool, bool, bool, object]:
    """Extrai (resposta_ao_cliente, confirmar_acordo, recusar_oferta,
    encerrar_sessao, data_vencimento) do JSON estruturado que os prompts
    pedem (ver bot/prompts/).

    Falha "fechada": se o parsing falhar por qualquer motivo (a LLM não
    respeitou o formato mesmo com `formato_json=True`), o texto bruto vira a
    resposta mostrada ao cliente e nenhuma ação sensível é assumida (todos os
    campos de controle ficam False, sem data) — nunca registra um acordo,
    avança a escada, muda a data nem encerra a sessão por causa de uma
    resposta mal formada.
    """
    m = _RE_JSON.search(texto)
    if not m:
        return texto.strip(), False, False, False, None
    try:
        dados = json.loads(m.group(0))
    except json.JSONDecodeError:
        return texto.strip(), False, False, False, None

    resposta = dados.get("resposta")
    if not isinstance(resposta, str) or not resposta.strip():
        return texto.strip(), False, False, False, None

    return (
        resposta,
        bool(dados.get("confirmar_acordo", False)),
        bool(dados.get("recusar_oferta", False)),
        bool(dados.get("encerrar_sessao", False)),
        dados.get("data_vencimento"),
    )
