"""Runner da bateria de testes — executa as três vias de estímulo.

    python scripts/rodar_bateria.py                          # bateria completa
    python scripts/rodar_bateria.py --via reinjecao          # só a via 1
    python scripts/rodar_bateria.py --origem-id caso_injecao_001
    python scripts/rodar_bateria.py --modelo deepseek:deepseek-v4-flash
    python scripts/rodar_bateria.py --repeticoes 2           # bateria mínima

Executa `casos (via 1) + roteiros (via 2) + personas (via 3) × MODELOS_BOT × N`,
conforme VIAS_DE_ESTIMULO e docs/plano_de_testes.md. Chama a API real do bot
(e do simulador, na via 3) — custa tokens.

Propriedades exigidas pela especificação:
  - Gravação incremental: cada episódio é gravado ao terminar, nunca em lote.
  - Retomada: o progresso vai para um arquivo de estado; reexecutar o script
    continua de onde parou, sem repetir episódios já concluídos.
  - Controle de ritmo: intervalo mínimo entre chamadas ao mesmo provedor.
  - Backoff em erro de cota (429), com parada limpa se a cota não liberar.

Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))  # simulador_cliente vive junto das personas

# O console do Windows usa cp1252 por padrão: sem isto, um caractere fora
# dessa codificação num print derruba a bateria no meio, depois de já ter
# gasto chamadas de API.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
from bot import Chatbot  # noqa: E402
from dados import FonteDeDadosMemoria  # noqa: E402
from eval.relatorio import CATEGORIAS  # noqa: E402
from instrumentacao import Instrumentador, carregar_turnos  # noqa: E402
from instrumentacao.logger import execucoes_concluidas  # noqa: E402
from llm import criar_cliente  # noqa: E402
from rag import RecuperadorRAG  # noqa: E402
from simulador_cliente import SimuladorCliente, listar_personas  # noqa: E402

DIR_CASOS = RAIZ / "tests" / "casos"
DIR_ROTEIROS = RAIZ / "tests" / "roteiros"

# Mensagens fixas usadas para levar o bot ao `estado_inicial` pedido por um
# caso da via 1. São padronizadas de propósito: o estímulo sob medição é a
# `entrada` do caso, não o caminho até ela.
MSG_IDENTIFICACAO = "Meu CPF é {cpf}."
# Recusa genérica, sem citar valor: faz a escada avançar um degrau (a LLM
# julga a recusa e o código promove a próxima oferta — ver bot/chatbot.py).
MSG_RECUSAR_OFERTA = "Esse valor está alto para mim, não tem nada melhor?"
MSG_PEDIR_PARCELAMENTO = "Prefiro parcelar. Pode ser em {n} vezes?"
PARCELAS_SETUP_PADRAO = 6

# Estados iniciais possíveis para a via 1, espelhando os degraus da escada de
# negociação (ver dados/regras.py). Cada um é preparado programaticamente por
# `executar_reinjecao`, com mensagens fixas, antes de injetar o estímulo.
#
#   inicio           — nada ainda; o cliente nem se identificou.
#   identificado     — CPF informado. O bot já apresentou a dívida E a 1ª
#                      oferta à vista no mesmo turno, então não existe mais um
#                      estado "oferta_apresentada" separado: identificar-se JÁ
#                      traz a oferta.
#   segunda_oferta   — cliente recusou a 1ª oferta; o bot já ofereceu a 2ª
#                      (desconto máximo).
#   parcelamento     — cliente pediu para parcelar e informou o número de
#                      parcelas (`setup.num_parcelas`, padrão 6).
ESTADOS_INICIAIS = ("inicio", "identificado", "segunda_oferta", "parcelamento")

# Índice do RAG construído uma vez e reaproveitado por todos os episódios
# (a construção é lazy: só acontece na primeira recuperação).
_RECUPERADOR = RecuperadorRAG()


# ---------------------------------------------------------------------------
# Carregamento dos estímulos
# ---------------------------------------------------------------------------
def carregar_casos() -> list[dict]:
    """Carrega todos os casos da via 1 (tests/casos/*.json)."""
    casos: list[dict] = []
    for caminho in sorted(DIR_CASOS.glob("*.json")):
        casos.extend(json.loads(caminho.read_text(encoding="utf-8")))
    return sorted(casos, key=lambda c: c["id"])


def carregar_roteiros() -> list[dict]:
    """Carrega todos os roteiros da via 2 (tests/roteiros/*.json).

    Um arquivo pode trazer UM roteiro ou uma LISTA deles — mesmo contrato de
    `scripts/gerar_inventario.py`. Os dois liam o mesmo diretório com
    contratos diferentes: um arquivo em lista entrava no inventário e
    quebrava a execução aqui, com `KeyError: 'id'` sobre uma lista. Aceitar
    as duas formas nos dois lugares fecha a divergência, e é o que permite
    manter um grupo de roteiros irmãos num arquivo só.
    """
    roteiros: list[dict] = []
    for p in sorted(DIR_ROTEIROS.glob("*.json")):
        dados = json.loads(p.read_text(encoding="utf-8"))
        roteiros.extend(dados if isinstance(dados, list) else [dados])
    return sorted(roteiros, key=lambda r: r["id"])


def coletar_estimulos(
    via: str | None,
    origem_id: str | None,
    categoria: str | None = None,
) -> list[tuple[str, dict]]:
    """Monta a lista `(via, estimulo)` a ser executada, aplicando os filtros.

    `categoria` seleciona pelos `categorias_alvo` do próprio estímulo. Note
    que um estímulo costuma endereçar mais de uma categoria, então rodar
    "só segurança" traz também turnos que servem a robustez — o recorte
    reduz o custo, não isola a medição.
    """
    todos: list[tuple[str, dict]] = []
    if via in (None, "reinjecao"):
        todos += [("reinjecao", c) for c in carregar_casos()]
    if via in (None, "roteiro"):
        todos += [("roteiro", r) for r in carregar_roteiros()]
    if via in (None, "simulador"):
        todos += [("simulador", p) for p in listar_personas()]
    if origem_id:
        todos = [(v, e) for v, e in todos if e["id"] == origem_id]
    if categoria:
        todos = [(v, e) for v, e in todos
                 if categoria in (e.get("categorias_alvo") or [])]
    return todos


# ---------------------------------------------------------------------------
# Estado da bateria (retomada)
# ---------------------------------------------------------------------------
def chave_episodio(via: str, origem_id: str, provedor: str, modelo: str, rep: int) -> str:
    """Identificador único de um episódio, usado para retomada."""
    return f"{via}|{origem_id}|{provedor}:{modelo}|rep{rep}"


def episodios_concluidos(dir_logs: Path | None = None, desde: str | None = None) -> set[str]:
    """Reconstrói, A PARTIR DOS LOGS, o conjunto de episódios já executados.

    DERIVADO, nunca mantido em arquivo. Antes havia um
    `logs/.bateria_estado.json` guardando essa lista em paralelo, e os dois
    divergiram exatamente como o inventário divergia antes de
    `scripts/gerar_inventario.py`: um `--recomecar` zerou o arquivo e ele
    passou a declarar 4 episódios concluídos quando os logs registravam 160.
    Quem rodasse a bateria depois disso reexecutaria 156 episódios já
    existentes — gastando chamadas de API e acrescentando repetições
    duplicadas aos próprios logs.

    A informação já estava inteira no log: cada turno grava `meta.via`,
    `meta.origem_id`, `meta.modelo_bot` e `meta.repeticao`, que são os quatro
    componentes da chave. Duplicar um dado que pode divergir em silêncio é o
    problema; derivar resolve na raiz.

    Custo: varrer os arquivos de bateria leva menos de um segundo, pago uma
    vez por rodada — contra uma classe inteira de bug silencioso.

    `desde` (instante ISO em UTC) conta só o que rodou a partir dele. É o
    progresso de uma rodada com `--recomecar`: ela repete as mesmas chaves
    das rodadas anteriores, que já estão nos logs, e sem o corte a barra da
    tela nascia em 100%.
    """
    dir_logs = dir_logs or config.DIR_LOGS
    concluidos: set[str] = set()
    for arquivo in sorted(dir_logs.glob("bateria__*.jsonl")):
        # Só conta o episódio cujo marcador de conclusão foi gravado. Uma
        # execução interrompida no meio não tem marcador, fica de fora, e a
        # retomada a refaz com novo id; a avaliação descarta a truncada pelo
        # id. Log anterior ao marcador (None) segue a regra antiga.
        completas = execucoes_concluidas(arquivo)
        for turno in carregar_turnos(arquivo):
            if completas is not None and turno.get("execucao_id") not in completas:
                continue
            if desde and (turno.get("timestamp") or "") < desde:
                continue
            meta = turno.get("meta", {})
            partes = (
                meta.get("via"), meta.get("origem_id"),
                meta.get("modelo_bot"), meta.get("repeticao"),
            )
            if all(p is not None for p in partes):
                via, origem, modelo_bot, rep = partes
                concluidos.add(f"{via}|{origem}|{modelo_bot}|rep{rep}")
    return concluidos


def proximo_id_global(dir_logs: Path | None = None) -> int:
    """Maior `execucao_id` já gravado em qualquer log de bateria, mais um.

    Piso global para os ids, de modo que episódios de rodadas diferentes nunca
    colidam. `proximo_execucao_id` ainda ancora no máximo do arquivo da sessão
    — ver o docstring dela.
    """
    dir_logs = dir_logs or config.DIR_LOGS
    maior = 0
    for arquivo in sorted(dir_logs.glob("bateria__*.jsonl")):
        for turno in carregar_turnos(arquivo):
            maior = max(maior, turno.get("execucao_id") or 0)
    return maior + 1


# ---------------------------------------------------------------------------
# Controle de ritmo e cota
# ---------------------------------------------------------------------------
_ultima_chamada: dict[str, float] = {}


def aguardar_ritmo(provedor: str) -> None:
    """Respeita o intervalo mínimo entre chamadas ao mesmo provedor."""
    intervalo = config.INTERVALO_ENTRE_CHAMADAS_S
    if intervalo <= 0:
        return
    agora = time.monotonic()
    anterior = _ultima_chamada.get(provedor)
    if anterior is not None:
        espera = intervalo - (agora - anterior)
        if espera > 0:
            time.sleep(espera)
    _ultima_chamada[provedor] = time.monotonic()


def e_erro_de_cota(erro: Exception) -> bool:
    """Heurística de erro de cota/limite de taxa (429), agnóstica de provedor."""
    texto = f"{type(erro).__name__} {erro}".lower()
    return any(t in texto for t in ("429", "rate limit", "rate_limit", "quota", "too many requests"))


class CotaEsgotada(RuntimeError):
    """Cota não liberou após todas as tentativas — a bateria para de forma limpa."""


def com_retentativa(fn, provedor: str, tentativas: int = 5):
    """Executa `fn`, respeitando o ritmo e reagindo a erro de cota com backoff
    exponencial. Erros que não são de cota sobem imediatamente."""
    espera = 5.0
    for tentativa in range(1, tentativas + 1):
        aguardar_ritmo(provedor)
        try:
            return fn()
        except Exception as erro:  # noqa: BLE001
            if not e_erro_de_cota(erro):
                raise
            if tentativa == tentativas:
                raise CotaEsgotada(
                    f"cota não liberou após {tentativas} tentativas: {erro}"
                ) from erro
            print(f"    [cota] tentativa {tentativa}/{tentativas}; aguardando {espera:.0f}s")
            time.sleep(espera)
            espera *= 2


# ---------------------------------------------------------------------------
# Execução de um episódio
# ---------------------------------------------------------------------------
def montar_bot(provedor: str, modelo: str) -> Chatbot:
    """Cria um bot novo (sessão limpa) para o modelo informado."""
    return Chatbot(
        FonteDeDadosMemoria(),
        _RECUPERADOR,
        criar_cliente(provedor, modelo),
        temperatura=config.BOT_TEMPERATURA,
        k_rag=config.RAG_K,
        max_tokens=config.BOT_MAX_TOKENS,
    )


def meta_base(via: str, estimulo: dict, provedor: str, modelo: str, rep: int) -> dict:
    """Campos de rastreio comuns a todo turno da bateria (vão dentro de `meta`)."""
    return {
        "via": via,
        "origem_id": estimulo["id"],
        "repeticao": rep,
        "modelo_bot": f"{provedor}:{modelo}",
        "temperatura_bot": config.BOT_TEMPERATURA,
        "status": "ok",
    }


def registrar_turno(inst, resultado, extra: dict) -> None:
    """Grava o turno, sinalizando em `meta.resposta_vazia` quando o bot não
    produziu texto algum para o cliente.

    Acontece de verdade: o modelo devolve `finish_reason: stop` com um
    conteúdo só de espaços, o parser falha fechado e `resposta_final` sai
    vazia. Sem essa marca o episódio passaria como normal e o turno vazio
    entraria nas médias dos avaliadores (o juiz pontuando uma string vazia)
    como se fosse uma resposta legítima.
    """
    if not (resultado.resposta_final or "").strip():
        extra = {**extra, "resposta_vazia": True}
    inst.registrar(resultado, meta_extra=extra)


def executar_reinjecao(bot, inst, caso, meta, provedor) -> None:
    """Via 1: prepara o estado inicial e injeta a entrada literal do caso.

    Os turnos de preparação também são gravados (marcados como `etapa=setup`):
    eles carregam as consultas à fonte de verdade, sem as quais o avaliador de
    fidelidade não teria o gabarito para conferir a resposta do estímulo.
    """
    setup = caso.get("setup", {})
    estado_inicial = setup.get("estado_inicial", "inicio")
    if estado_inicial not in ESTADOS_INICIAIS:
        raise ValueError(f"estado_inicial desconhecido: {estado_inicial!r}")

    # Passos de preparação, acumulados conforme o degrau da escada pedido —
    # cada estado inclui os anteriores (ver ESTADOS_INICIAIS).
    passos: list[str] = []
    if estado_inicial != "inicio":
        cpf = setup.get("cliente_id")
        if not cpf:
            raise ValueError(f"caso {caso['id']}: estado {estado_inicial} exige setup.cliente_id")
        passos.append(MSG_IDENTIFICACAO.format(cpf=cpf))
    if estado_inicial in ("segunda_oferta", "parcelamento"):
        passos.append(MSG_RECUSAR_OFERTA)
    if estado_inicial == "parcelamento":
        n = setup.get("num_parcelas", PARCELAS_SETUP_PADRAO)
        passos.append(MSG_PEDIR_PARCELAMENTO.format(n=n))

    for mensagem in passos:
        r = com_retentativa(lambda m=mensagem: bot.processar_turno(m), provedor)
        registrar_turno(inst, r, {**meta, "etapa": "setup"})

    r = com_retentativa(lambda: bot.processar_turno(caso["entrada"]), provedor)
    registrar_turno(inst, r, {**meta, "etapa": "estimulo"})


def executar_roteiro(bot, inst, roteiro, meta, provedor) -> None:
    """Via 2: envia as mensagens na ordem, uma por turno, independentemente do
    que o bot responder. Marca no último turno se a parada esperada ocorreu."""
    mensagens = roteiro["mensagens"][: config.MAX_TURNOS]
    ultimo_indice = len(mensagens) - 1
    for i, msg in enumerate(mensagens):
        r = com_retentativa(lambda m=msg: bot.processar_turno(m), provedor)
        extra = {**meta, "etapa": "estimulo"}
        # O desfecho é conferido no último turno ENVIADO: se o bot fechar o
        # acordo antes do fim do roteiro, a conversa para ali, e conferir só
        # no último turno previsto perdia exatamente o desfecho esperado.
        if i == ultimo_indice or bot.finalizada:
            extra["parada_atingida"] = _parada_atingida(bot, roteiro.get("parada_esperada"))
        registrar_turno(inst, r, extra)
        if bot.finalizada and i < ultimo_indice:
            # O bot encerrou antes do fim do roteiro: os turnos restantes
            # seriam respondidos com "sessão encerrada". Interrompe e registra.
            break


def _parada_atingida(bot, parada_esperada: str | None) -> bool:
    """Confere se o desfecho esperado pelo roteiro de fato ocorreu."""
    if parada_esperada == "acordo_registrado":
        return bot.acordo is not None
    if parada_esperada == "sessao_encerrada_sem_acordo":
        return bot.finalizada and bot.acordo is None
    return False


def executar_simulador(bot, inst, persona, meta, provedor, provedor_sim, modelo_sim) -> None:
    """Via 3: loop adaptativo entre o simulador (cliente) e o bot, até o
    simulador emitir [FIM], o fluxo encerrar, ou MAX_TURNOS."""
    simulador = SimuladorCliente.de_persona(persona, provedor=provedor_sim, modelo=modelo_sim)
    extra = {
        **meta,
        "etapa": "estimulo",
        "modelo_simulador": f"{simulador.provedor}:{simulador.modelo}",
        "temperatura_simulador": config.SIMULADOR_TEMPERATURA,
    }

    fala_bot = None
    for _ in range(config.MAX_TURNOS):
        fala_cliente = com_retentativa(
            lambda f=fala_bot: simulador.responder(f), simulador.provedor
        )
        r = com_retentativa(lambda m=fala_cliente: bot.processar_turno(m), provedor)
        registrar_turno(inst, r, extra)
        fala_bot = r.resposta_final
        if simulador.encerrou or bot.finalizada:
            break


# ---------------------------------------------------------------------------
# Bateria
# ---------------------------------------------------------------------------
def nome_sessao(estimulo_id: str, provedor: str, modelo: str) -> str:
    """Um arquivo de log por (estímulo × modelo): é o agrupamento que o
    avaliador de consistência precisa (mesma entrada, N execuções)."""
    modelo_slug = f"{provedor}-{modelo}".replace(":", "-").replace("/", "-")
    return f"bateria__{estimulo_id}__{modelo_slug}"


def proximo_execucao_id(sessao: str, minimo: int) -> int:
    """Devolve um `execucao_id` que ainda não existe no log desta sessão.

    O contador do arquivo de estado sozinho não basta: com `--recomecar` (ou
    se o estado for perdido) ele volta a 1, enquanto o log continua lá e é
    apendado — duas execuções diferentes acabariam com o mesmo id no mesmo
    arquivo. Como o avaliador de consistência agrupa os turnos por
    `execucao_id`, essa colisão fundiria episódios distintos e falsearia
    justamente a métrica que a via 1 existe para medir. Por isso o id também
    é ancorado no maior valor já gravado no arquivo (VIAS_DE_ESTIMULO,
    "Regras de execucao_id": nunca reutilizar).
    """
    caminho = config.DIR_LOGS / f"{sessao}.jsonl"
    if not caminho.exists():
        return minimo
    maior = 0
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                valor = json.loads(linha).get("execucao_id")
            except json.JSONDecodeError:
                continue
            if isinstance(valor, int):
                maior = max(maior, valor)
    return max(minimo, maior + 1)


def main() -> None:
    """Executa a bateria conforme os filtros da linha de comando."""
    p = argparse.ArgumentParser(description="Runner da bateria de testes (3 vias).")
    p.add_argument("--via", choices=["reinjecao", "roteiro", "simulador"])
    p.add_argument("--origem-id", dest="origem_id")
    p.add_argument("--categoria", choices=list(CATEGORIAS),
                   help="só os estímulos que endereçam esta categoria")
    p.add_argument("--modelo", help='"provedor:modelo"; padrão: config.MODELOS_BOT')
    p.add_argument("--repeticoes", type=int)
    p.add_argument("--recomecar", action="store_true", help="ignora o estado e roda tudo de novo")
    args = p.parse_args()

    if args.modelo:
        if ":" not in args.modelo:
            print('ERRO: --modelo deve estar no formato "provedor:modelo".')
            return
        provedor_arg, modelo_arg = args.modelo.split(":", 1)
        modelos = [(provedor_arg.strip(), modelo_arg.strip())]
    else:
        modelos = config.MODELOS_BOT
    estimulos = coletar_estimulos(args.via, args.origem_id, args.categoria)
    if not estimulos:
        print("Nenhum estímulo corresponde aos filtros.")
        return

    # Independência do avaliador, em três níveis (ver docs/guia_de_execucao.md).
    #
    # MESMO MODELO bloqueia. Zheng et al. observaram juízes favorecendo as
    # próprias saídas (win rate 10% maior no GPT-4 e 25% no Claude-v1), mas
    # declaram que os dados não bastam para confirmar o efeito como viés. O
    # bloqueio se justifica pela cautela, que custa só escolher outro modelo,
    # e não por uma medida estabelecida.
    #
    # MESMO PROVEDOR avisa, e não bloqueia. O risco aqui é outro, e é erro
    # CORRELACIONADO: modelos da mesma família compartilham corpus, alinhamento
    # e convenções de estilo, e o menor costuma ser destilado do maior, então o
    # juiz pode ficar cego exatamente onde o bot erra. Autopreferência infla a
    # nota; cegueira compartilhada torna a falha invisível, que é pior. Não há,
    # porém, medição publicada do ganho de trocar de provedor sobre trocar de
    # modelo — é precaução por extrapolação, e bloquear por extrapolação
    # inviabilizaria o framework onde só existe um provedor disponível. O
    # controle que MEDE o risco residual é o kappa da camada 4.
    for provedor, modelo in modelos:
        if (provedor, modelo) == (config.JUIZ_PROVEDOR, config.JUIZ_MODELO):
            print(
                f"ERRO: o juiz ({config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}) é o mesmo modelo "
                f"do bot avaliado. Configure JUIZ_MODELO diferente antes de rodar a bateria."
            )
            return
    for provedor, modelo in modelos:
        if provedor == config.JUIZ_PROVEDOR:
            print(
                f"AVISO: o juiz ({config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}) e o bot "
                f"({provedor}:{modelo}) são do MESMO PROVEDOR. A medição é válida, e a "
                f"independência fica no nível mais fraco da hierarquia — modelo distinto, "
                f"provedor compartilhado. Erro correlacionado entre modelos da mesma família "
                f"não é descartável, e o kappa da camada 4 passa a ser o único controle. "
                f"Declare essa limitação ao reportar."
            )

    # Estado derivado dos logs (ver `episodios_concluidos`). `--recomecar`
    # passa a significar "ignore o que já existe e rode de novo", sem destruir
    # nada: os logs continuam sendo a fonte da verdade.
    concluidos = set() if args.recomecar else episodios_concluidos()
    proximo_id = proximo_id_global()

    total = len(estimulos) * len(modelos) * (args.repeticoes or config.N_EXECUCOES_PADRAO)
    print(f"Bateria: {len(estimulos)} estímulo(s) x {len(modelos)} modelo(s) -> até {total} episódio(s)")
    print(f"Já concluídos em execuções anteriores: {len(concluidos)}")

    feitos = pulados = falhos = 0
    for provedor, modelo in modelos:
        for via, est in estimulos:
            n = args.repeticoes or est.get("n_repeticoes") or config.N_EXECUCOES_PADRAO
            for rep in range(1, n + 1):
                chave = chave_episodio(via, est["id"], provedor, modelo, rep)
                if chave in concluidos:
                    pulados += 1
                    continue

                sessao = nome_sessao(est["id"], provedor, modelo)
                execucao_id = proximo_execucao_id(sessao, proximo_id)
                inst = Instrumentador(
                    sessao,
                    execucao_id=execucao_id,
                    dir_logs=config.DIR_LOGS,
                )
                bot = montar_bot(provedor, modelo)
                meta = meta_base(via, est, provedor, modelo, rep)
                print(f"  [{via}] {est['id']} · {provedor}:{modelo} · rep {rep}/{n}")

                try:
                    if via == "reinjecao":
                        executar_reinjecao(bot, inst, est, meta, provedor)
                    elif via == "roteiro":
                        executar_roteiro(bot, inst, est, meta, provedor)
                    else:
                        executar_simulador(
                            bot, inst, est, meta, provedor,
                            config.SIMULADOR_PROVEDOR, config.SIMULADOR_MODELO,
                        )
                    _registrar_conclusao(inst, meta)
                    feitos += 1
                except CotaEsgotada as erro:
                    # Parada limpa: o que foi concluído já está nos logs, e é
                    # deles que a retomada é derivada — basta rodar de novo.
                    print(f"\nBateria interrompida por cota: {erro}")
                    print("Progresso preservado nos logs. Rode de novo para continuar.")
                    _resumo(feitos, pulados, falhos)
                    return
                except Exception as erro:  # noqa: BLE001
                    # Episódio falho é registrado, nunca descartado em silêncio.
                    falhos += 1
                    print(f"    FALHA: {type(erro).__name__}: {erro}")
                    _registrar_falha(inst, meta, erro)

                # Nada mais a gravar: a retomada é derivada do log. O episódio
                # falho sai desta passada, mas não tem marcador de conclusão,
                # e a próxima execução do script o refaz com novo id.
                concluidos.add(chave)
                proximo_id = max(proximo_id, execucao_id + 1)

    _resumo(feitos, pulados, falhos)


def _registrar_conclusao(inst: Instrumentador, meta: dict) -> None:
    """Marca o episódio como concluído INTEIRO, depois do último turno.

    É o marcador que a retomada e a avaliação consultam. Uma queda no meio
    da conversa deixa turnos no log sem este registro, e a execução é tratada
    como interrompida: refeita com novo id na retomada, e descartada pela
    avaliação em vez de entrar truncada na medição.
    """
    registro = {
        "tipo": "episodio_concluido",
        "sessao_id": inst.sessao_id,
        "execucao_id": inst.execucao_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
    }
    with open(inst.caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _registrar_falha(inst: Instrumentador, meta: dict, erro: Exception) -> None:
    """Grava uma linha marcando o episódio como falho (§7.2 do plano de testes:
    episódios falhos são contabilizados, nunca descartados)."""
    registro = {
        "tipo": "episodio_falho",
        "sessao_id": inst.sessao_id,
        "execucao_id": inst.execucao_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meta": {**meta, "status": "falho", "erro": f"{type(erro).__name__}: {erro}"[:500]},
    }
    with open(inst.caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _resumo(feitos: int, pulados: int, falhos: int) -> None:
    print("\n--- Resumo da bateria ---")
    print(f"Episódios executados: {feitos}")
    print(f"Pulados (já concluídos): {pulados}")
    print(f"Falhos: {falhos}")
    print(f"Logs em: {config.DIR_LOGS}")


if __name__ == "__main__":
    main()
