"""Endpoints HTTP da interface web.

    uvicorn api.main:app --reload --port 8000

Todos os dados manipulados são FICTÍCIOS.

Organização das rotas:
  /api/saude                        estado do servidor e da configuração
  /api/modelos                      catálogo de provedores (bot, juiz, simulador)
  /api/sessoes                      POST abre conversa · GET lista o histórico
  /api/sessoes/{id}                 detalhe (turnos gravados + avaliações)
  /api/sessoes/{id}/mensagens       envia uma mensagem e recebe o turno
  /api/sessoes/{id}/tom             avaliação de tom da conversa (juiz)
  /api/sessoes/{id}/avaliacao       avaliação por categoria (com ou sem juiz)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from api import avaliacao, bateria, esquemas, estado, estimulos, kappa, massa, modelos, prompts, saidas, visao
from bot.chatbot import ETAPA_MAX_A_VISTA
from dados.regras import (
    DESCONTO_MAXIMO,
    FRACAO_PRIMEIRA_OFERTA,
    FRACAO_SEGUNDA_OFERTA,
)
from eval import relatorio
from eval.tom import AvaliadorTom
from llm import criar_cliente
from instrumentacao import Instrumentador, carregar_avaliacoes_tom, carregar_turnos

app = FastAPI(
    title="QualiLLM — API do MVP de negociação de dívidas",
    description="Camada de transporte da interface web. Dados 100% fictícios.",
    version="0.1.0",
)

# O frontend roda no dev server do Vite, em outra porta. Liberado só para
# localhost: é uma ferramenta local de usuária única, não um serviço exposto.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Rótulos derivados das regras de negócio -------------------------------
def _rotulo_estagio_oferta(estagio: int) -> str:
    """Descreve em que degrau da escada a negociação está.

    Derivado das constantes de `dados/regras.py` em vez de escrito à mão: se
    a fração de desconto mudar lá, o rótulo acompanha sozinho.
    """
    if estagio > ETAPA_MAX_A_VISTA:
        return "parcelamento livre (sem desconto, com juros)"
    fracao = FRACAO_PRIMEIRA_OFERTA if estagio == 0 else FRACAO_SEGUNDA_OFERTA
    ordinal = "1a" if estagio == 0 else "2a"
    return f"{ordinal} oferta a vista — {DESCONTO_MAXIMO * fracao:.0%} de desconto"


def _estagio_prompt(sessao: estado.SessaoViva) -> str:
    """Qual prompt de sistema está ativo agora (decisão determinística do bot,
    tomada por `Chatbot._selecionar_prompt`: depende de já ter cliente)."""
    return "identificacao" if sessao.bot.cliente is None else "negociacao"


# --- Saúde e configuração --------------------------------------------------
@app.get("/api/saude")
def saude() -> dict:
    """Diz se dá para conversar (chave do bot) e o que está configurado."""
    return {
        "ok": True,
        "data_referencia": config.data_referencia().isoformat(),
        "bot": {
            "provedor": config.BOT_PROVEDOR,
            "modelo": config.BOT_MODELO,
            "tem_chave": bool(config.chave_do_provedor(config.BOT_PROVEDOR)),
        },
        "juiz": {
            "provedor": config.JUIZ_PROVEDOR,
            "modelo": config.JUIZ_MODELO,
            "tem_chave": bool(config.chave_do_provedor(config.JUIZ_PROVEDOR)),
        },
        "simulador": {
            "provedor": config.SIMULADOR_PROVEDOR,
            "modelo": config.SIMULADOR_MODELO,
            "tem_chave": bool(config.chave_do_provedor(config.SIMULADOR_PROVEDOR)),
        },
        "sessoes_vivas": len(estado.sessoes_vivas()),
    }


@app.get("/api/modelos")
def catalogo_modelos(forcar: bool = False) -> dict:
    """Modelos disponíveis por provedor, perguntados ao próprio provedor.

    Um provedor sem chave (ou com chave inválida) aparece na lista com o
    motivo, em vez de sumir: some da interface esconde a razão de a opção não
    funcionar. `forcar=true` ignora o cache de 10 minutos.
    """
    return modelos.catalogo(forcar)


# --- Conversa manual -------------------------------------------------------
@app.post("/api/sessoes", response_model=esquemas.SessaoCriada, status_code=201)
def abrir_sessao(pedido: esquemas.NovaSessao) -> esquemas.SessaoCriada:
    """Abre uma conversa nova. A primeira chamada paga a carga do índice RAG."""
    provedor = pedido.provedor or config.BOT_PROVEDOR
    if not config.chave_do_provedor(provedor):
        raise HTTPException(
            status_code=503,
            detail=f"Chave de API do provedor '{provedor}' nao configurada no .env.",
        )
    sessao = estado.criar_sessao(pedido.provedor, pedido.modelo)
    return esquemas.SessaoCriada(
        sessao_id=sessao.sessao_id,
        provedor=sessao.provedor,
        modelo=sessao.modelo,
        arquivo_log=sessao.instrumentador.caminho.name,
        estado=sessao.bot._estado_atual(),
        estagio_prompt=_estagio_prompt(sessao),
    )


@app.post(
    "/api/sessoes/{sessao_id}/mensagens",
    response_model=esquemas.TurnoResposta,
)
def enviar_mensagem(sessao_id: str, mensagem: esquemas.Mensagem) -> esquemas.TurnoResposta:
    """Processa um turno e grava no log.

    O turno é registrado em QUALQUER caso — inclusive quando o provedor
    devolve resposta em branco. Essa taxa de falha é dado do experimento, não
    algo a esconder da avaliação.
    """
    sessao = estado.obter_sessao(sessao_id)
    if sessao is None:
        raise HTTPException(
            status_code=404,
            detail="Conversa nao esta mais em memoria. Comece uma nova sessao.",
        )
    if sessao.bot.finalizada:
        raise HTTPException(
            status_code=409, detail="Esta conversa ja foi encerrada."
        )

    try:
        resultado = sessao.bot.processar_turno(mensagem.texto)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Erro ao chamar o modelo: {e}")

    registro = sessao.instrumentador.registrar(resultado)
    sessao.ultimo = resultado
    sessao.mensagens.append({"papel": "user", "texto": mensagem.texto})

    vazia = not resultado.resposta_final.strip()
    if vazia:
        sessao.aviso = (
            "O modelo nao retornou resposta neste turno (falha conhecida do "
            f"provedor, apos {resultado.tentativas_llm} tentativa(s)). Sua "
            "mensagem foi registrada — envie novamente ou reformule."
        )
    else:
        sessao.aviso = None
        sessao.mensagens.append({"papel": "assistant", "texto": resultado.resposta_final})

    estado_atual = sessao.bot._estado_atual()
    return esquemas.TurnoResposta(
        turno_id=registro["turno_id"],
        resposta=resultado.resposta_final,
        resposta_vazia=vazia,
        aviso=sessao.aviso,
        estado=estado_atual,
        estagio_prompt=_estagio_prompt(sessao),
        estagio_oferta_rotulo=_rotulo_estagio_oferta(estado_atual["estagio_oferta"]),
        finalizada=sessao.bot.finalizada,
        instrumentacao=esquemas.Instrumentacao(
            prompt_completo=resultado.prompt_completo,
            consultas_dados=resultado.consultas_dados,
            trechos_rag=resultado.trechos_rag,
            latencia_s=round(resultado.latencia_s, 4),
            tentativas_llm=resultado.tentativas_llm,
            historico_enviado=resultado.historico_enviado,
        ),
    )


@app.delete("/api/sessoes/{sessao_id}", status_code=204)
def fechar_sessao(sessao_id: str) -> None:
    """Descarta a conversa da memória. O log gravado permanece intacto."""
    estado.encerrar_sessao(sessao_id)


# --- Histórico (lido dos logs, não da memória) -----------------------------
def _caminho_log(sessao_id: str) -> Path:
    caminho = config.DIR_LOGS_MANUAIS / f"{sessao_id}.jsonl"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail=f"Log nao encontrado: {caminho.name}")
    return caminho


def _trecho_que_casa(turnos: list[dict], termo: str, contexto: int = 60) -> str | None:
    """Primeiro pedaço de conversa que contém `termo`, com alguma vizinhança.

    Devolver só "casou" obrigaria a abrir a sessão para descobrir por quê; o
    trecho responde isso na própria lista de resultados.
    """
    alvo = termo.lower()
    for t in turnos:
        for campo in ("mensagem_usuario", "resposta_final"):
            texto = str(t.get(campo) or "")
            pos = texto.lower().find(alvo)
            if pos < 0:
                continue
            ini = max(0, pos - contexto)
            fim = min(len(texto), pos + len(termo) + contexto)
            return ("…" if ini else "") + texto[ini:fim].strip() + ("…" if fim < len(texto) else "")
    return None


@app.get("/api/sessoes", response_model=list[esquemas.ResumoSessao])
def listar_sessoes(busca: str | None = None) -> list[esquemas.ResumoSessao]:
    """Conversas manuais já gravadas, da mais recente para a mais antiga.

    Só lista os logs `web-*.jsonl` de `logs/manuais/`. Os da bateria
    (`logs/bateria__*.jsonl`) são outra coisa — testes automatizados, não
    conversa de uma pessoa — e ficam em outra pasta e em tela própria, para
    que as duas fontes não se misturem.

    Com `busca`, filtra pelas sessões cujo texto (mensagem da pessoa ou
    resposta do bot) contém o termo, e devolve o trecho que casou.
    """
    vivas = set(estado.sessoes_vivas())
    termo = (busca or "").strip()
    resumos: list[esquemas.ResumoSessao] = []
    for caminho in config.DIR_LOGS_MANUAIS.glob("web-*.jsonl"):
        turnos = carregar_turnos(caminho)
        if not turnos:
            continue
        trecho = None
        if termo:
            trecho = _trecho_que_casa(turnos, termo)
            if trecho is None:
                continue
        ultimo = turnos[-1]
        meta = turnos[0].get("meta", {})
        resumos.append(
            esquemas.ResumoSessao(
                sessao_id=caminho.stem,
                turnos=len(turnos),
                inicio=turnos[0].get("timestamp"),
                fim=ultimo.get("timestamp"),
                provedor=meta.get("provedor"),
                modelo=meta.get("modelo"),
                acordo_fechado=bool(ultimo.get("estado", {}).get("acordo_id")),
                turnos_vazios=sum(
                    1 for t in turnos if not str(t.get("resposta_final", "")).strip()
                ),
                viva=caminho.stem in vivas,
                trecho=trecho,
            )
        )
    return sorted(resumos, key=lambda r: r.inicio or "", reverse=True)


@app.get("/api/sessoes/{sessao_id}")
def detalhar_sessao(sessao_id: str) -> dict:
    """Turnos gravados de uma conversa, com as avaliações de tom já feitas."""
    caminho = _caminho_log(sessao_id)
    turnos = carregar_turnos(caminho)
    avaliacoes = carregar_avaliacoes_tom(caminho)
    return {
        "sessao_id": sessao_id,
        "arquivo_log": caminho.name,
        "viva": sessao_id in estado.sessoes_vivas(),
        "execucoes": sorted({t.get("execucao_id", 0) for t in turnos}),
        "turnos": turnos,
        "avaliacoes_tom": {str(k): v for k, v in avaliacoes.items()},
    }


@app.get("/api/visao-geral")
def visao_geral() -> dict:
    """Resumo do sistema: contadores, estado das 6 categorias e últimas conversas.

    O veredito de cada categoria é o PIOR dos vereditos das suas métricas, e o
    estado vem do relatório de bateria mais recente — ver api/visao.py.
    """
    return visao.resumo()


@app.get("/api/massa")
def catalogo_massa() -> dict:
    """Massa de dados fictícia, com as ofertas que cada dívida geraria hoje.

    Responde a "com que CPF eu testo?" e serve de oráculo: as condições saem
    de `dados/regras.py`, o mesmo código que o bot usa.
    """
    return massa.catalogo()


# --- Inventário de estímulos -----------------------------------------------
@app.get("/api/estimulos")
def listar_estimulos(via: str | None = None, categoria: str | None = None) -> dict:
    """Tudo o que a bateria pode executar, com o corpo específico de cada via.

    Devolve também as contagens do conjunto INTEIRO (não do filtrado), porque
    a tela precisa mostrar quantos existem por via e por categoria para que os
    filtros façam sentido.
    """
    todos = estimulos.catalogo()

    por_via: dict[str, int] = {}
    por_categoria: dict[str, int] = {}
    for e in todos:
        por_via[e["via"]] = por_via.get(e["via"], 0) + 1
        for c in e["categorias_alvo"]:
            por_categoria[c] = por_categoria.get(c, 0) + 1

    filtrados = [
        e for e in todos
        if (not via or e["via"] == via)
        and (not categoria or categoria in e["categorias_alvo"])
    ]
    return {
        "total": len(todos),
        "por_via": por_via,
        "por_categoria": por_categoria,
        "episodios_do_filtro": estimulos.episodios(filtrados),
        "estimulos": filtrados,
    }


# --- Biblioteca de prompts (somente leitura) -------------------------------
@app.get("/api/prompts")
def listar_prompts() -> list[dict]:
    """Os prompts versionados, agrupados por papel.

    `existe` e `bytes` vêm do disco: um prompt catalogado cujo arquivo sumiu
    precisa aparecer como problema na tela, não desaparecer silenciosamente.
    """
    saida = []
    for p in prompts.CATALOGO:
        arq = prompts.caminho(p)
        existe = arq.is_file()
        saida.append({
            "id": p.id,
            "grupo": p.grupo,
            "grupo_titulo": prompts.TITULO_GRUPO.get(p.grupo, p.grupo),
            "titulo": p.titulo,
            "arquivo": p.arquivo,
            "papel": p.papel,
            "formato": p.formato,
            "categoria": p.categoria,
            "dominio": p.dominio,
            "existe": existe,
            "bytes": arq.stat().st_size if existe else 0,
        })
    return saida


@app.get("/api/prompts/{prompt_id}")
def detalhar_prompt(prompt_id: str) -> dict:
    """Conteúdo de um prompt. Só ids do catálogo resolvem para um arquivo."""
    p = prompts.obter(prompt_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Prompt desconhecido: {prompt_id}")
    arq = prompts.caminho(p)
    if not arq.is_file():
        raise HTTPException(
            status_code=410,
            detail=f"Prompt catalogado mas ausente do disco: {p.arquivo}",
        )
    return {
        "id": p.id,
        "grupo": p.grupo,
        "titulo": p.titulo,
        "arquivo": p.arquivo,
        "papel": p.papel,
        "formato": p.formato,
        "categoria": p.categoria,
        "sem_prompt": p.sem_prompt,
        "conteudo": prompts.ler(p),
        # Juízes: o apêndice de domínio e o texto composto que vai ao modelo.
        "dominio": p.dominio,
        "conteudo_dominio": (
            (config.RAIZ / p.dominio).read_text(encoding="utf-8")
            if p.dominio and (config.RAIZ / p.dominio).is_file() else None
        ),
        "conteudo_composto": prompts.composto(p),
    }


# --- Relatórios já gravados ------------------------------------------------
def _partes_do_nome(nome_base: str) -> tuple[str, str, str]:
    """Separa `relatorio[__escopo]__categoria__momento` em suas partes.

    O separador é `__` (duplo) justamente porque tanto a categoria
    (`aderencia_contexto`) quanto o escopo (`web-a1b2c3d4-exec0`) podem conter
    `_` e `-` — separar por caractere simples quebraria os dois.
    """
    partes = nome_base.split("__")
    if len(partes) >= 4:
        return partes[1], partes[2], partes[3]  # escopo, categoria, momento
    if len(partes) == 3:
        return "", partes[1], partes[2]
    return "", "", ""


@app.get("/api/relatorios", response_model=list[esquemas.ResumoRelatorio])
def listar_relatorios(categoria: str | None = None) -> list[esquemas.ResumoRelatorio]:
    """Relatórios gravados, do mais recente para o mais antigo.

    Um arquivo por categoria, por execução — nada é sobrescrito. Por isso a
    lista cresce e precisa ser navegável por categoria e por instante, em vez
    de mostrar só "o resultado atual", que não existe.
    """
    resumos: list[esquemas.ResumoRelatorio] = []
    for caminho in config.DIR_LOGS.glob("relatorio__*.json"):
        try:
            conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Um relatório corrompido não pode derrubar a listagem inteira:
            # os outros continuam sendo dado válido.
            continue
        escopo, cat_nome, momento = _partes_do_nome(caminho.stem)
        proc = conteudo.get("procedencia") or {}
        cat = proc.get("categoria") or cat_nome
        if categoria and cat != categoria:
            continue
        vereditos: dict[str, int] = {}
        for bloco in conteudo.get("categorias") or []:
            for m in bloco.get("metricas") or []:
                s = m.get("status") or "?"
                vereditos[s] = vereditos.get(s, 0) + 1
        resumos.append(
            esquemas.ResumoRelatorio(
                nome=caminho.stem,
                categoria=cat,
                escopo=escopo,
                momento=momento,
                gerado_em=conteudo.get("gerado_em"),
                usou_juiz=bool(proc.get("usou_juiz")),
                juiz=proc.get("juiz"),
                n_turnos=proc.get("n_turnos"),
                n_arquivos_log=len(proc.get("arquivos_de_log") or []),
                vereditos=vereditos,
            )
        )
    return sorted(resumos, key=lambda r: r.momento, reverse=True)


@app.get("/api/relatorios/{nome}")
def detalhar_relatorio(nome: str) -> dict:
    """Conteúdo completo de um relatório, como foi gravado."""
    # `nome` vem da URL: barrar separadores impede sair de logs/ por
    # "../../algum/arquivo".
    if "/" in nome or "\\" in nome or ".." in nome:
        raise HTTPException(status_code=400, detail="Nome de relatorio invalido.")
    caminho = config.DIR_LOGS / f"{nome}.json"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail=f"Relatorio nao encontrado: {nome}")
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    escopo, cat_nome, momento = _partes_do_nome(caminho.stem)
    conteudo["_arquivo"] = caminho.name
    conteudo["_escopo"] = escopo
    conteudo["_momento"] = momento
    conteudo["_categoria"] = (conteudo.get("procedencia") or {}).get("categoria") or cat_nome
    return conteudo


@app.get("/api/avaliacoes/{momento}/planilha")
def baixar_planilha(momento: str):
    """Planilha Excel da avaliação inteira (todas as categorias do instante).

    Gerada sob demanda a partir dos relatórios gravados, então serve também às
    avaliações anteriores à planilha. Não chama juiz.
    """
    from fastapi.responses import FileResponse
    from eval import planilha

    if not momento.replace("T", "").replace("Z", "").isdigit():
        raise HTTPException(status_code=400, detail="Instante invalido.")
    try:
        caminho = planilha.gerar_planilha(config.DIR_LOGS, momento)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(
        caminho, filename=caminho.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Disparo da bateria ----------------------------------------------------
@app.post("/api/bateria/plano")
def planejar_bateria(pedido: esquemas.PedidoBateria) -> dict:
    """Quanto custaria esta rodada, sem executar nada.

    Existe como endpoint separado porque a estimativa precisa aparecer ANTES
    da confirmação, e calcular no cliente duplicaria a regra de repetições —
    a mesma que já errou uma vez por conta de `n_repeticoes: null`.
    """
    return bateria.plano(**pedido.model_dump())


@app.post("/api/bateria", status_code=202)
def iniciar_bateria(pedido: esquemas.PedidoBateria) -> dict:
    """Dispara a bateria em segundo plano.

    202 e não 201: o trabalho foi ACEITO, não concluído — ele vai levar
    dezenas de minutos. Acompanhe por GET /api/bateria.
    """
    if not config.chave_do_provedor(config.BOT_PROVEDOR):
        raise HTTPException(
            status_code=503,
            detail=f"Chave de API do provedor '{config.BOT_PROVEDOR}' nao configurada.",
        )
    try:
        return bateria.iniciar(pedido.model_dump())
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/bateria")
def status_bateria() -> dict:
    """Progresso da rodada atual (ou da última), lido do estado em disco."""
    return bateria.status()


@app.delete("/api/bateria")
def parar_bateria() -> dict:
    """Interrompe a rodada. O que já rodou permanece gravado e a próxima
    execução retoma de onde parou."""
    if not bateria.parar():
        raise HTTPException(status_code=409, detail="Nenhuma bateria em andamento.")
    return bateria.status()


# --- Saídas de rodadas anteriores ------------------------------------------
@app.get("/api/saidas/{tipo}")
def listar_saidas(tipo: str) -> dict:
    """Saídas de terminal guardadas das rodadas anteriores (`logs/saidas/`)."""
    if tipo not in ("bateria", "avaliacao"):
        raise HTTPException(status_code=404, detail="Tipo de rodada desconhecido.")
    return {"saidas": saidas.listar(tipo)}


@app.get("/api/saidas/{tipo}/{arquivo}")
def ler_saida(tipo: str, arquivo: str) -> dict:
    linhas = saidas.ler(tipo, arquivo)
    if linhas is None:
        raise HTTPException(status_code=404, detail="Saída não encontrada.")
    return {"arquivo": arquivo, "linhas": linhas}


# --- Disparo da avaliação --------------------------------------------------
@app.post("/api/avaliacao/plano")
def planejar_avaliacao(pedido: esquemas.PedidoAvaliacaoBateria) -> dict:
    """Quais logs este recorte selecionaria, sem julgar nada."""
    return avaliacao.plano(pedido.model_dump())


@app.post("/api/avaliacao", status_code=202)
def iniciar_avaliacao(pedido: esquemas.PedidoAvaliacaoBateria) -> dict:
    """Dispara `avaliar_bateria.py` em segundo plano.

    Sem juiz, roda só as camadas determinísticas: sai rápido e não custa nada.
    """
    if pedido.com_juiz:
        provedor = (pedido.juiz_modelo or "").split(":")[0] or config.JUIZ_PROVEDOR
        if not config.chave_do_provedor(provedor):
            raise HTTPException(
                status_code=503,
                detail=f"Chave de API do provedor '{provedor}' nao configurada.",
            )
    try:
        return avaliacao.iniciar(pedido.model_dump())
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/avaliacao")
def status_avaliacao() -> dict:
    """Situação da avaliação atual (ou da última)."""
    return avaliacao.status()


@app.delete("/api/avaliacao")
def parar_avaliacao() -> dict:
    """Interrompe a avaliação. Relatórios já gravados permanecem."""
    if not avaliacao.parar():
        raise HTTPException(status_code=409, detail="Nenhuma avaliacao em andamento.")
    return avaliacao.status()


# --- Execuções da bateria (testes automatizados) ---------------------------
@app.get("/api/execucoes")
def listar_execucoes(via: str | None = None) -> list[dict]:
    """Logs gerados pela bateria: um arquivo por estímulo × modelo.

    Fonte separada do histórico manual de propósito. São coisas diferentes —
    uma pessoa conversando com o bot versus um teste automatizado, às vezes
    com uma LLM fazendo o papel do cliente — e misturá-las na mesma lista faria
    perder de vista qual é qual.
    """
    saida = []
    for caminho in config.DIR_LOGS.glob("bateria__*.jsonl"):
        turnos = carregar_turnos(caminho)
        if not turnos:
            continue
        meta = turnos[0].get("meta", {})
        via_log = meta.get("via", "")
        if via and via_log != via:
            continue
        # `partes[1]` é o id do estímulo; `partes[2]`, provedor-modelo.
        partes = caminho.stem.split("__")
        # Uma linha por RODADA, não por arquivo. Rodadas novas acrescentam ao
        # mesmo log (o nome depende só do estímulo e do modelo); com uma linha
        # por arquivo, a rodada de 26/10 sumia dentro da de 28/10.
        for rodada in _rodadas_do_log(turnos):
            execucoes = rodada["execucoes"]
            dela = [t for t in turnos if t.get("execucao_id", 0) in execucoes]
            saida.append({
                "nome": caminho.stem,
                "estimulo_id": meta.get("origem_id") or (partes[1] if len(partes) > 1 else ""),
                "modelo": meta.get("modelo_bot") or f"{meta.get('provedor')}/{meta.get('modelo')}",
                "via": via_log,
                "execucoes": execucoes,
                "repeticoes": len(execucoes),
                "turnos": len(dela),
                "turnos_vazios": sum(
                    1 for t in dela if not str(t.get("resposta_final", "")).strip()
                ),
                "inicio": rodada["inicio"],
                "fim": rodada["fim"],
                "acordos": sum(
                    1 for e in execucoes
                    if any(t.get("estado", {}).get("acordo_id")
                           for t in dela if t.get("execucao_id", 0) == e)
                ),
            })
    # Ordena pelo ÚLTIMO turno: quem rodou por último aparece primeiro.
    return sorted(saida, key=lambda x: x["fim"] or "", reverse=True)


# Intervalo sem turnos que separa uma rodada da seguinte no mesmo log. Dentro
# de uma rodada, as repetições de um estímulo saem a minutos uma da outra;
# entre rodadas, passam-se horas ou dias.
_PAUSA_ENTRE_RODADAS = timedelta(hours=2)


def _rodadas_do_log(turnos: list[dict]) -> list[dict]:
    """Agrupa as execuções de um log em rodadas, pela pausa entre elas."""
    por_execucao: dict[int, list[str]] = {}
    for t in turnos:
        if t.get("timestamp"):
            por_execucao.setdefault(t.get("execucao_id", 0), []).append(t["timestamp"])
    janelas = sorted((min(ts), max(ts), e) for e, ts in por_execucao.items())
    rodadas: list[dict] = []
    for inicio, fim, e in janelas:
        if rodadas and (datetime.fromisoformat(inicio)
                        - datetime.fromisoformat(rodadas[-1]["fim"])) < _PAUSA_ENTRE_RODADAS:
            r = rodadas[-1]
            r["execucoes"].append(e)
            r["fim"] = max(r["fim"], fim)
        else:
            rodadas.append({"inicio": inicio, "fim": fim, "execucoes": [e]})
    return rodadas


@app.get("/api/execucoes/{nome}")
def detalhar_execucao(nome: str) -> dict:
    """Turnos de uma execução da bateria, agrupados por repetição."""
    if "/" in nome or "\\" in nome or ".." in nome or not nome.startswith("bateria__"):
        raise HTTPException(status_code=400, detail="Nome de execucao invalido.")
    caminho = config.DIR_LOGS / f"{nome}.jsonl"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail=f"Execucao nao encontrada: {nome}")
    turnos = carregar_turnos(caminho)
    meta = turnos[0].get("meta", {}) if turnos else {}
    return {
        "nome": nome,
        "arquivo_log": caminho.name,
        "via": meta.get("via", ""),
        "estimulo_id": meta.get("origem_id", ""),
        "modelo_bot": meta.get("modelo_bot"),
        "modelo_simulador": meta.get("modelo_simulador"),
        "execucoes": sorted({t.get("execucao_id", 0) for t in turnos}),
        "turnos": turnos,
    }


# --- Avaliação sob demanda -------------------------------------------------
def _juiz_escolhido(juiz_modelo: str | None) -> tuple[str, str]:
    """`(provedor, modelo)` do juiz desta chamada.

    Interpreta "provedor:modelo" vindo da interface e cai no `.env` quando
    nada foi escolhido. Centralizado porque a checagem de chave, a construção
    do cliente e a procedência do relatório precisam concordar sobre QUAL
    juiz está em jogo — divergir entre os três produziria um 503 citando um
    provedor e uma medição feita por outro.
    """
    if juiz_modelo and ":" in juiz_modelo:
        provedor, _, modelo = juiz_modelo.partition(":")
        return provedor.strip(), modelo.strip()
    return config.JUIZ_PROVEDOR, config.JUIZ_MODELO


@app.post("/api/sessoes/{sessao_id}/tom")
def avaliar_tom(sessao_id: str, pedido: esquemas.PedidoAvaliacao) -> dict:
    """Avalia o tom da conversa inteira — uma chamada ao juiz por sessão.

    Fica atrás de uma ação explícita porque custa uma chamada de API paga.
    """
    juiz_provedor, juiz_modelo = _juiz_escolhido(pedido.juiz_modelo)
    if not config.chave_do_provedor(juiz_provedor):
        raise HTTPException(
            status_code=503,
            detail=f"Chave de API do juiz ('{juiz_provedor}') nao configurada.",
        )
    caminho = _caminho_log(sessao_id)
    turnos = [
        t for t in carregar_turnos(caminho)
        if t.get("execucao_id", 0) == pedido.execucao_id
    ]
    if not turnos:
        raise HTTPException(status_code=400, detail="Nenhum turno para avaliar.")

    cliente = criar_cliente(juiz_provedor, juiz_modelo) if pedido.juiz_modelo else None
    julgamento = AvaliadorTom(cliente_llm=cliente).avaliar_sessao(turnos)
    Instrumentador(
        sessao_id, execucao_id=pedido.execucao_id, dir_logs=config.DIR_LOGS_MANUAIS
    ).registrar_avaliacao_tom(julgamento)
    return julgamento


@app.post(
    "/api/sessoes/{sessao_id}/avaliacao",
    response_model=esquemas.RespostaAvaliacao,
)
def avaliar_categorias(
    sessao_id: str, pedido: esquemas.PedidoAvaliacao
) -> esquemas.RespostaAvaliacao:
    """Avalia esta conversa nas seis categorias e grava um relatório por
    categoria — um arquivo por execução, como os da bateria, nunca sobrescrito.

    `com_juiz=False` roda só as camadas determinísticas: sai na hora e não
    gasta token. É o caminho para olhar antes de decidir se vale pagar.
    """
    juiz_provedor, juiz_modelo = _juiz_escolhido(pedido.juiz_modelo)
    if pedido.com_juiz and not config.chave_do_provedor(juiz_provedor):
        raise HTTPException(
            status_code=503,
            detail=f"Chave de API do juiz ('{juiz_provedor}') nao configurada.",
        )
    caminho = _caminho_log(sessao_id)
    turnos = [
        t for t in carregar_turnos(caminho)
        if t.get("execucao_id", 0) == pedido.execucao_id
    ]
    if not turnos:
        raise HTTPException(status_code=400, detail="Nenhum turno para avaliar.")

    cliente = (
        criar_cliente(juiz_provedor, juiz_modelo)
        if pedido.com_juiz and pedido.juiz_modelo else None
    )
    secoes = relatorio.avaliar_categorias(
        turnos, usar_juiz=pedido.com_juiz, cliente_juiz=cliente
    )
    momento = datetime.now(timezone.utc)
    escopo = f"{sessao_id}-exec{pedido.execucao_id}"

    por_categoria: dict[str, list] = {}
    for s in secoes:
        por_categoria.setdefault(s.categoria, []).append(s)

    gravados: list[str] = []
    for categoria, secoes_cat in por_categoria.items():
        base = config.DIR_RELATORIOS_MANUAIS / relatorio.nome_relatorio(categoria, momento, escopo)
        procedencia = {
            "categoria": categoria,
            "origem": "conversa manual (interface web)",
            "sessao_id": sessao_id,
            "execucao_id": pedido.execucao_id,
            "usou_juiz": pedido.com_juiz,
            # O juiz REALMENTE usado, que pode ter vindo da interface e não do
            # .env. Gravar o configurado faria a procedência mentir sobre quem
            # julgou, que é o dado sem o qual dois relatórios divergentes não
            # se explicam.
            "juiz": f"{juiz_provedor}:{juiz_modelo}" if pedido.com_juiz else None,
            "n_turnos": len(turnos),
        }
        relatorio.escrever_categorias_csv(secoes_cat, base.with_suffix(".csv"))
        relatorio.escrever_categorias_json(secoes_cat, base.with_suffix(".json"), procedencia)
        gravados.append(base.name)

    return esquemas.RespostaAvaliacao(
        usou_juiz=pedido.com_juiz,
        juiz=(
            f"{config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}"
            if pedido.com_juiz else None
        ),
        n_turnos=len(turnos),
        metricas=[
            esquemas.MetricaAvaliada(
                categoria=s.categoria,
                metrica=s.metrica,
                valor=s.valor,
                limiar=s.limiar,
                operador=s.operador,
                status=s.status,
                n_amostras=s.n_amostras,
                falhas_juiz=s.falhas_juiz,
                nao_aplicavel=s.nao_aplicavel,
                justificativas=(s.justificativas or [])[:3],
                ocorrencias=s.ocorrencias or [],
            )
            for s in secoes
        ],
        relatorios_gravados=gravados,
    )


# --- Camada 4: rotulagem humana e κ ----------------------------------------
# O veredito do juiz NÃO é devolvido por /itens. É a diferença entre a tela e
# o CSV: no arquivo a coluna está lá e o que protege o cegamento é a instrução
# de não olhar; aqui o dado não chega ao navegador. Ver api/kappa.py.
@app.get("/api/kappa")
def listar_amostras() -> list[dict]:
    """Amostras de rotulagem disponíveis, com o progresso de cada uma."""
    return kappa.listar()


@app.get("/api/kappa/{nome}")
def itens_da_amostra(nome: str, apenas_pendentes: bool = False) -> dict:
    """Itens para rotular, sem o veredito do juiz."""
    try:
        return kappa.itens(nome, apenas_pendentes)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/kappa/{nome}/rotulos")
def gravar_rotulo(nome: str, pedido: esquemas.PedidoRotulo) -> dict:
    """Grava o rótulo humano de um item e devolve o progresso."""
    try:
        return kappa.rotular(nome, pedido.id, pedido.rotulo)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/kappa/{nome}/resultado")
def resultado_da_amostra(nome: str, contra: str | None = None) -> dict:
    """κ por métrica, com as divergências item a item. Revela o juiz.

    `contra`: julgamentos de um segundo juiz, para o κ humano × juiz B com os
    mesmos rótulos.
    """
    try:
        return kappa.resultado(nome, contra)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/julgamentos")
def listar_julgamentos() -> list[dict]:
    """Avaliações com juiz já feitas: juiz, data, itens por métrica, custo."""
    return kappa.listar_julgamentos()


@app.post("/api/kappa-amostras", status_code=201)
def gerar_amostra_kappa(pedido: dict) -> dict:
    """Sorteia a amostra de rotulagem dos julgamentos de uma avaliação.

    Não chama o juiz: usa os vereditos que entraram no relatório.
    """
    try:
        return kappa.gerar_amostra(
            pedido.get("julgamentos", ""), int(pedido.get("por_metrica") or 20),
            outros=[n for n in (pedido.get("outros") or []) if n],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/comparacao-juizes")
def comparar_juizes(a: str, b: str) -> dict:
    """κ entre dois juízes sobre os mesmos logs, com divergências e custo."""
    try:
        return kappa.comparar(a, b)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# --- Limiares ---------------------------------------------------------------
def _limiares_para_tela() -> dict:
    """Métricas na ordem das categorias do framework, com nome e modalidade."""
    vigentes = relatorio.carregar_limiares()
    ordem = {c: i for i, c in enumerate(relatorio.CATEGORIAS)}
    metricas = []
    for m, padrao in relatorio.LIMIARES_PADRAO.items():
        categoria, nome, modalidade = relatorio.DESCRICAO_METRICA.get(m, ("", m, ""))
        metricas.append({
            "metrica": m,
            "categoria": categoria,
            "nome": nome,
            "modalidade": modalidade,
            "valor": vigentes[m],
            "padrao": padrao,
            "operador": ">=",
            "criterio": relatorio.CRITERIO_LIMIAR.get(m, ""),
        })
    metricas.sort(key=lambda x: ordem.get(x["categoria"], 99))
    return {"limiar_juiz_padrao": relatorio.LIMIAR_JUIZ_PADRAO, "metricas": metricas}


@app.get("/api/limiares")
def listar_limiares() -> dict:
    """Limiar vigente de cada métrica, com o padrão e o critério que o sustenta.

    Os limiares são parâmetros da instanciação. Valem para as PRÓXIMAS
    avaliações; cada relatório guarda na procedência os que usou, então
    mudar aqui não reescreve relatório já gerado.
    """
    return _limiares_para_tela()


@app.put("/api/limiares")
def salvar_limiares(valores: dict[str, float]) -> dict:
    """Grava os limiares. Métrica desconhecida ou valor fora de 0 a 1 → 400."""
    try:
        relatorio.gravar_limiares(valores)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _limiares_para_tela()
