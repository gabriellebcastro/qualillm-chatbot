"""Gera o relatório por categoria a partir dos logs da bateria.

Consome tudo que `scripts/rodar_bateria.py` gravou (`logs/bateria__*.jsonl`) e
produz o relatório das seis categorias do framework, com a métrica de cada
uma, o status contra o limiar de docs/especificacao_metricas.md e uma amostra
de justificativas.

Uso:
    python scripts/avaliar_bateria.py                       # todas as categorias
    python scripts/avaliar_bateria.py --categoria seguranca # só uma
    python scripts/avaliar_bateria.py --sem-juiz            # sem custo de API
    python scripts/avaliar_bateria.py --listar-categorias
    python scripts/avaliar_bateria.py --manuais             # conversas manuais, à parte

O `--sem-juiz` existe para inspecionar uma bateria antes de gastar chamadas de
API: as métricas que dependem do juiz aparecem como "sem_dados", nunca como
aprovadas.

O `--categoria` existe porque o relatório completo custa centenas de chamadas
ao juiz e dezenas de minutos. Cada categoria consome os logs de forma
independente, então medir uma de cada vez dá o mesmo resultado de medir todas
juntas.

CADA EXECUÇÃO GERA O SEU PRÓPRIO RELATÓRIO, geral ou de uma categoria só —
mesma lógica do log por sessão. O nome do arquivo carrega o escopo e o
instante (`relatorio__seguranca__20260814T103045Z.json`), e o JSON registra a
procedência da medição. Nada é sobrescrito: como o juiz é não determinístico,
duas execuções da mesma categoria podem divergir, e o histórico é justamente
o que permite perceber isso.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

import config
from eval import concordancia, juiz, relatorio
from instrumentacao.logger import carregar_turnos, execucoes_concluidas

# Execuções interrompidas descartadas na carga, para a procedência declarar.
DESCARTADAS: set = set()


def carregar_bateria(
    dir_logs: Path,
    modelo: str | None = None,
    via: str | None = None,
    origem_id: str | None = None,
    desde: str | None = None,
) -> tuple[list[dict], list[str]]:
    """Lê os turnos da bateria e devolve `(turnos, nomes dos arquivos lidos)`.

    Os nomes vão para a procedência do relatório: saber QUAIS logs entraram
    na medição é o que permite reproduzi-la depois.

    Sem filtro, lê TUDO — o comportamento histórico. Os filtros existem porque
    "tudo" deixa de ser uma medição legítima em dois casos concretos:

    - **Dois modelos de bot no acervo.** O relatório misturaria dois sistemas
      diferentes num número só, e comparar modelos é justamente o motivo de a
      bateria aceitar `--modelo`.
    - **Reexecução com `--recomecar`.** O `Instrumentador` abre o log em modo
      append e o nome do arquivo depende só do estímulo e do modelo, então a
      rodada nova SOMA à antiga no mesmo arquivo. Sem recorte, a avaliação leria
      as duas execuções como se fossem uma amostra maior.

    O filtro é aplicado por TURNO (via `meta`), e não por arquivo, porque um
    mesmo arquivo pode conter execuções de datas diferentes.
    """
    turnos: list[dict] = []
    arquivos: list[str] = []
    for arquivo in sorted(dir_logs.glob("bateria__*.jsonl")):
        selecionados = []
        # Execução sem marcador de conclusão foi interrompida no meio: entra
        # truncada se não for filtrada, e uma conversa pela metade comparada
        # com as completas vira divergência que é da queda, não do bot.
        completas = execucoes_concluidas(arquivo)
        for t in carregar_turnos(arquivo):
            if completas is not None and t.get("execucao_id") not in completas:
                DESCARTADAS.add((arquivo.name, t.get("execucao_id")))
                continue
            meta = t.get("meta", {})
            modelo_do_turno = meta.get("modelo_bot") or f"{meta.get('provedor')}:{meta.get('modelo')}"
            if modelo and modelo_do_turno != modelo:
                continue
            if via and meta.get("via") != via:
                continue
            if origem_id and meta.get("origem_id") != origem_id:
                continue
            if desde and (t.get("timestamp") or "") < desde:
                continue
            selecionados.append(t)
        if selecionados:
            turnos.extend(selecionados)
            arquivos.append(arquivo.name)
    return turnos, arquivos


def imprimir(metricas: list[dict], motivos_falha: list[dict] | None = None) -> None:
    """Imprime a tabela das métricas medidas e o que não atendeu ao limiar."""
    print(f"\n{'categoria':20s} {'metrica':32s} {'valor':>8s} {'limiar':>7s} "
          f"{'n':>5s} {'falhas':>6s}  status")
    print("-" * 96)
    for m in metricas:
        valor = "-" if m["valor"] is None else f"{m['valor']:.4f}"
        limiar = "-" if m["limiar"] is None else f"{m['limiar']:.2f}"
        print(f"{m['categoria']:20s} {m['metrica']:32s} {valor:>8s} "
              f"{limiar:>7s} {m['n_amostras']:>5d} {m['falhas_juiz']:>6d}  {m['status']}")

    problemas = [m for m in metricas if m["status"] == "nao_atende"]
    if problemas:
        print("\nAmostra de justificativas (métricas que não atenderam):")
        for m in problemas:
            for j in (m.get("justificativas") or [])[:3]:
                print(f"  [{m['metrica']}] {j[:150]}")

    sem_dados = [m["metrica"] for m in metricas if m["status"] == "sem_dados"]
    if sem_dados:
        print(f"\nSem dados (nenhuma amostra avaliável): {', '.join(sem_dados)}")

    # Imprime a CAUSA junto da tabela, e não só no JSON: a coluna "falhas"
    # mostra o tamanho do problema, e quem está lendo o terminal precisa saber
    # se perdeu julgamentos por um juiz mal configurado ou por azar da rede.
    if motivos_falha:
        print("\nMotivos das falhas de juiz:")
        for item in motivos_falha:
            print(f"  {item['ocorrencias']}x  {item['motivo'][:160]}")


def avaliar_manuais(args) -> None:
    """Avalia as conversas manuais de `logs/manuais/`, nunca a bateria.

    É a mesma avaliação que a tela da conversa faz, pelo terminal e com o juiz
    do ambiente, inclusive pela assinatura. Cada execução de cada conversa é
    avaliada à parte, com relatórios próprios: conversas diferentes repetem os
    mesmos `execucao_id`, e juntá-las fundiria conversas distintas numa só.
    Sem `origem_id` nos turnos, confiabilidade e equidade saem como
    `nao_aplicavel`, como na tela.
    """
    pela_assinatura = config.JUIZ_PROVEDOR == "anthropic-assinatura"
    if args.dir_saida:
        dir_saida = RAIZ / args.dir_saida
    elif pela_assinatura:
        dir_saida = config.DIR_LOGS / "assinatura" / "manuais"
    else:
        dir_saida = config.DIR_RELATORIOS_MANUAIS

    arquivos = sorted(config.DIR_LOGS_MANUAIS.glob("*.jsonl"))
    if args.sessoes:
        arquivos = [a for a in arquivos if a.stem in args.sessoes]
    if not arquivos:
        print(f"Nenhuma conversa manual em {config.DIR_LOGS_MANUAIS}"
              + (f" com as sessões {args.sessoes}." if args.sessoes else "."))
        return

    escolhidas = args.categorias or list(relatorio.CATEGORIAS)
    usar_juiz = not args.sem_juiz
    juiz_id = f"{config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}" if usar_juiz else None
    momento = datetime.now(timezone.utc)
    instante = momento.strftime("%Y%m%dT%H%M%SZ")
    rotulo_juiz = f"{config.JUIZ_PROVEDOR}-{config.JUIZ_MODELO}".replace(":", "-")
    print(f"Conversas manuais: {len(arquivos)} arquivo(s) em {config.DIR_LOGS_MANUAIS}")
    print(f"Categorias a avaliar: {', '.join(escolhidas)}"
          f"{' (sem juiz)' if args.sem_juiz else f' | juiz {juiz_id}'}")

    juiz.limpar_falhas()
    for arquivo in arquivos:
        todos = [t for t in carregar_turnos(arquivo)
                 if not args.desde or (t.get("timestamp") or "") >= args.desde]
        for execucao in sorted({t.get("execucao_id", 0) for t in todos}):
            turnos = [t for t in todos if t.get("execucao_id", 0) == execucao]
            escopo = f"{arquivo.stem}-exec{execucao}"
            coletor = concordancia.Coletor() if usar_juiz else None
            secoes = relatorio.avaliar_categorias(
                turnos, usar_juiz=usar_juiz, categorias=escolhidas, coletor=coletor
            )
            print(f"\n=== {escopo}: {len(turnos)} turno(s)")
            imprimir([s.to_dict() for s in secoes])

            arquivo_julgamentos = None
            if coletor is not None and coletor.itens:
                arquivo_julgamentos = f"julgamentos__{escopo}__{rotulo_juiz}__{instante}.jsonl"
                concordancia.gravar_julgamentos(
                    coletor.itens, dir_saida / arquivo_julgamentos,
                    {
                        "juiz": juiz_id,
                        "coletado_em": momento.isoformat(),
                        "categorias": escolhidas,
                        "arquivos_de_log": [arquivo.name],
                        "versoes_das_instrucoes": juiz.versoes_das_instrucoes(),
                    },
                )

            por_categoria: dict[str, list] = defaultdict(list)
            for s in secoes:
                por_categoria[s.categoria].append(s)
            for categoria, secoes_da_categoria in por_categoria.items():
                base = dir_saida / relatorio.nome_relatorio(categoria, momento, escopo)
                procedencia = {
                    "categoria": categoria,
                    "origem": "conversa manual (terminal)",
                    "sessao_id": arquivo.stem,
                    "execucao_id": execucao,
                    "usou_juiz": usar_juiz,
                    "juiz": juiz_id,
                    "n_turnos": len(turnos),
                    "coletado_em": momento.isoformat(),
                    "versoes_das_instrucoes": (
                        juiz.versoes_das_instrucoes() if usar_juiz else None
                    ),
                    "arquivo_de_julgamentos": arquivo_julgamentos,
                    "via_do_juiz": (None if not usar_juiz
                                    else "assinatura (claude -p), para testes"
                                    if pela_assinatura else "API"),
                }
                relatorio.escrever_categorias_csv(secoes_da_categoria, base.with_suffix(".csv"))
                relatorio.escrever_categorias_json(
                    secoes_da_categoria, base.with_suffix(".json"), procedencia
                )

    if usar_juiz:
        uso = juiz.uso_registrado()
        print(f"\nUso do juiz: {uso['chamadas']} chamadas, {uso['tokens_entrada']} tokens "
              f"de entrada, {uso['tokens_saida']} de saída"
              + (", sem custo de API (juiz pela assinatura)" if pela_assinatura
                 else f", ~US$ {uso['custo_estimado_usd']:.4f}"
                 if uso["custo_estimado_usd"] is not None else ""))
        motivos = juiz.falhas_registradas()
        if motivos:
            print("Motivos das falhas de juiz:")
            for item in motivos:
                print(f"  {item['ocorrencias']}x  {item['motivo'][:160]}")
    print(f"\nRelatórios em: {dir_saida}")


def main() -> None:
    """Roda os avaliadores sobre os logs da bateria e grava CSV + JSON."""
    p = argparse.ArgumentParser(description="Relatório por categoria da bateria.")
    p.add_argument("--categoria", action="append", dest="categorias",
                   choices=list(relatorio.CATEGORIAS),
                   help="avalia só esta categoria (pode repetir a opção)")
    p.add_argument("--listar-categorias", action="store_true",
                   help="lista as categorias disponíveis e sai")
    p.add_argument("--sem-juiz", action="store_true",
                   help="só as camadas determinísticas (sem custo de API)")
    # --- Recorte dos LOGS a julgar (eixo diferente de --categoria, que
    # escolhe quais METRICAS rodar sobre o que foi selecionado aqui) ---
    p.add_argument("--modelo", help='so os turnos deste bot ("provedor:modelo")')
    p.add_argument("--via", choices=["reinjecao", "roteiro", "simulador"],
                   help="so os turnos gerados por esta via")
    p.add_argument("--origem-id", dest="origem_id",
                   help="so os turnos deste estimulo")
    p.add_argument("--desde", help="so os turnos a partir desta data (AAAA-MM-DD)")
    p.add_argument("--dir-saida", default=None,
                   help="diretório onde gravar os relatórios desta execução "
                        "(padrão: logs/, ou logs/assinatura/ com o juiz pela assinatura)")
    # --- Conversas manuais, à parte da bateria ---
    p.add_argument("--manuais", action="store_true",
                   help="avalia as conversas manuais de logs/manuais/ em vez da bateria; "
                        "grava em logs/manuais/relatorios/ (ou logs/assinatura/manuais/)")
    p.add_argument("--sessao", action="append", dest="sessoes",
                   help="com --manuais: só esta conversa (ex.: web-ce09ce37); pode repetir")
    args = p.parse_args()

    if args.listar_categorias:
        print("Categorias disponíveis:")
        for c in relatorio.CATEGORIAS:
            metricas = [m for m in relatorio.LIMIARES if m.startswith(c[:9])]
            print(f"  {c:20s} {len(metricas)} métrica(s)")
        return

    if args.manuais:
        if args.modelo or args.via or args.origem_id:
            p.error("--modelo, --via e --origem-id recortam a bateria; com --manuais, use --sessao")
        avaliar_manuais(args)
        return
    if args.sessoes:
        p.error("--sessao só vale com --manuais")

    recorte = {
        "modelo": args.modelo, "via": args.via,
        "origem_id": args.origem_id, "desde": args.desde,
    }
    turnos, arquivos = carregar_bateria(config.DIR_LOGS, **recorte)
    if not turnos:
        aplicados = {k: v for k, v in recorte.items() if v}
        print(f"Nenhum log de bateria encontrado em {config.DIR_LOGS}"
              + (f" com o recorte {aplicados}." if aplicados else "."))
        return
    escolhidas = args.categorias or list(relatorio.CATEGORIAS)
    aplicados = {k: v for k, v in recorte.items() if v}
    print(f"Turnos carregados: {len(turnos)} de {len(arquivos)} arquivo(s) de log"
          + (f" | recorte: {aplicados}" if aplicados else " | sem recorte (tudo)"))
    print(f"Categorias a avaliar: {', '.join(escolhidas)}"
          f"{' (sem juiz)' if args.sem_juiz else ''}")

    # Parâmetros DERIVADOS dos logs, para a procedência descrever a medição e
    # não a configuração do momento em que o relatório foi gerado.
    modelos_bot = {
        t.get("meta", {}).get("modelo_bot") for t in turnos
    } - {None}
    repeticoes = {t.get("meta", {}).get("repeticao") for t in turnos} - {None}
    n_reexecucoes = max(repeticoes) if repeticoes else None
    # Nível da hierarquia de independência (ver scripts/rodar_bateria.py): o
    # bloqueio de modelo igual é verificado na execução, e aqui registra-se o
    # que a medição de fato alcançou.
    provedores_bot = {m.split(":")[0] for m in modelos_bot if ":" in m}
    if args.sem_juiz:
        nivel_independencia = None
    elif f"{config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}" in modelos_bot:
        nivel_independencia = "nenhuma (mesmo modelo)"
    elif config.JUIZ_PROVEDOR in provedores_bot:
        nivel_independencia = "modelo distinto, provedor compartilhado"
    else:
        nivel_independencia = "provedor distinto"

    if not args.sem_juiz:
        estimadas = relatorio.estimar_chamadas_juiz(turnos, escolhidas)
        print(f"PROGRESSO_ESTIMADO {estimadas}", flush=True)
        print(f"Chamadas ao juiz estimadas: {estimadas}")

    juiz.limpar_falhas()
    # Os vereditos item a item saem da MESMA rodada que produz o relatório: é
    # deles que a rotulagem humana e a comparação entre juízes partem.
    coletor = None if args.sem_juiz else concordancia.Coletor()
    secoes = relatorio.avaliar_categorias(
        turnos, usar_juiz=not args.sem_juiz, categorias=escolhidas, coletor=coletor
    )
    motivos_falha = juiz.falhas_registradas()
    uso_juiz = None if args.sem_juiz else juiz.uso_registrado()
    imprimir([s.to_dict() for s in secoes], motivos_falha)

    # O veredito é GLOBAL, sobre as categorias que entraram nesta rodada. Com
    # escopo parcial ele não chega a `conforme`, porque certificar o que não
    # se mediu é o mesmo erro de tratar falta de dado como aprovação.
    vd = relatorio.veredito(secoes, escolhidas)
    ROTULO = {"conforme": "CONFORME",
              "conforme_com_ressalva": "CONFORME COM RESSALVA",
              "sem_dados": "SEM DADOS",
              "nao_conforme": "NAO CONFORME"}
    print()
    print(f"Veredito: {ROTULO[vd['estado']]}")
    if vd["falhas_limiar_maximo"]:
        print(f"  falha em limiar maximo: "
              f"{', '.join(vd['falhas_limiar_maximo'])}")
    if vd["falhas_limiar_tolerancia"]:
        print(f"  falha em limiar de tolerancia (pode ser do juiz; ler as ocorrencias): "
              f"{', '.join(vd['falhas_limiar_tolerancia'])}")
    if vd["metricas_sem_dados"]:
        print(f"  sem dados: {', '.join(vd['metricas_sem_dados'])}")
    if not vd["escopo_completo"]:
        print(f"  escopo parcial, nao medidas: "
              f"{', '.join(vd['categorias_ausentes'])}")

    # Um relatório por categoria. Todos os arquivos desta execução
    # compartilham o mesmo instante no nome, então continuam agrupados.
    momento = datetime.now(timezone.utc)
    # O juiz pela assinatura (terceira via, para testes) não é o mesmo
    # instrumento da API: grava à parte, para nunca se misturar às avaliações
    # de medição nem ser pego como "julgamentos mais recentes" pelo κ.
    pela_assinatura = config.JUIZ_PROVEDOR == "anthropic-assinatura"
    dir_saida = RAIZ / (args.dir_saida or ("logs/assinatura" if pela_assinatura else "logs"))
    por_categoria: dict[str, list] = defaultdict(list)
    for s in secoes:
        por_categoria[s.categoria].append(s)

    arquivo_julgamentos = None
    if coletor is not None:
        escopo = "geral" if not args.categorias else "-".join(sorted(escolhidas))
        rotulo_juiz = f"{config.JUIZ_PROVEDOR}-{config.JUIZ_MODELO}".replace(":", "-")
        arquivo_julgamentos = (
            f"julgamentos__{escopo}__{rotulo_juiz}__{momento.strftime('%Y%m%dT%H%M%SZ')}.jsonl"
        )
        concordancia.gravar_julgamentos(
            coletor.itens, dir_saida / arquivo_julgamentos,
            {
                "juiz": f"{config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}",
                "coletado_em": momento.isoformat(),
                "categorias": escolhidas,
                "recorte": aplicados or None,
                "arquivos_de_log": arquivos,
                "uso_do_juiz": uso_juiz,
                "versoes_das_instrucoes": juiz.versoes_das_instrucoes(),
            },
        )
        print(f"\nUso do juiz: {uso_juiz['chamadas']} chamadas, "
              f"{uso_juiz['tokens_entrada']} tokens de entrada, "
              f"{uso_juiz['tokens_saida']} de saída, {uso_juiz['latencia_total_s']} s"
              + (f", ~US$ {uso_juiz['custo_estimado_usd']:.4f}"
                 if uso_juiz["custo_estimado_usd"] is not None
                 else ", sem custo de API (juiz pela assinatura)"
                 if config.JUIZ_PROVEDOR == "anthropic-assinatura"
                 else ", custo: preço não cadastrado"))
        print(f"Julgamentos item a item: {arquivo_julgamentos}")

    print()
    for categoria, secoes_da_categoria in por_categoria.items():
        base = dir_saida / relatorio.nome_relatorio(categoria, momento)
        procedencia = {
            "categoria": categoria,
            "usou_juiz": not args.sem_juiz,
            "juiz": None if args.sem_juiz
                    else f"{config.JUIZ_PROVEDOR}:{config.JUIZ_MODELO}",
            "n_turnos": len(turnos),
            # Sem isto, dois relatorios com numeros diferentes ficariam
            # indistinguiveis de uma variacao do juiz, quando na verdade
            # mediram recortes diferentes do acervo.
            "recorte": aplicados or None,
            "arquivos_de_log": arquivos,
            "execucoes_interrompidas_descartadas": len(DESCARTADAS),
            # PARÂMETROS DA INSTANCIAÇÃO. Sem eles o veredito não é
            # reauditável: a aferição do avaliador vale para o instrumento com
            # que foi feita, e dois relatórios com números diferentes ficariam
            # indistinguíveis de uma variação do juiz.
            "coletado_em": momento.isoformat(),
            # Derivados dos próprios logs, e não da configuração atual: o que
            # importa é o que produziu AQUELES turnos, que pode não ser o que
            # está no .env agora.
            "modelos_do_bot": sorted(modelos_bot),
            "n_reexecucoes": n_reexecucoes,
            "independencia_do_avaliador": nivel_independencia,
            # Impressão digital do prompt COMPOSTO de cada avaliador, núcleo
            # mais apêndice de domínio. Hash e não número de versão, para o
            # relatório não declarar uma versão que o arquivo já não tem.
            "versoes_das_instrucoes": (
                None if args.sem_juiz else juiz.versoes_das_instrucoes()
            ),
            # O veredito da rodada inteira vai em TODOS os relatórios dela,
            # porque é global e os arquivos são por categoria: ler um só não
            # pode dar a impressão de que a categoria decide sozinha.
            "veredito": vd,
            "limiares": {
                m: {
                    "valor": v[0],
                    "operador": v[1],
                    "criterio": relatorio.CRITERIO_LIMIAR.get(m, ""),
                    "maximo": relatorio.CRITERIO_LIMIAR.get(m, "")
                              in relatorio.CRITERIOS_LIMIAR_MAXIMO,
                }
                for m, v in relatorio.LIMIARES.items()
            },
            # POR QUÊ as falhas de juiz aconteceram. A contagem já aparece por
            # métrica; o motivo é da rodada inteira, porque a mesma causa
            # derruba todas as categorias de uma vez. Sem isto, `sem_dados`
            # com `falhas_juiz` alto não distingue um juiz mal configurado de
            # um estímulo que nunca rodou.
            "falhas_juiz_motivos": motivos_falha or None,
            # Custo e tempo do juiz na rodada inteira, e o arquivo com os
            # vereditos item a item que a rodada produziu.
            "uso_do_juiz": uso_juiz,
            "arquivo_de_julgamentos": arquivo_julgamentos,
            # O mesmo para todo juiz; ver `juiz.TETO_TOKENS_JUIZ`. Pela
            # assinatura o CLI não aceita teto, e o registro diz isso.
            "teto_tokens_juiz": None if pela_assinatura else juiz.TETO_TOKENS_JUIZ,
            "via_do_juiz": (None if args.sem_juiz
                            else "assinatura (claude -p), para testes" if pela_assinatura
                            else "API"),
        }
        relatorio.escrever_categorias_csv(secoes_da_categoria, base.with_suffix(".csv"))
        relatorio.escrever_categorias_json(
            secoes_da_categoria, base.with_suffix(".json"), procedencia
        )
        print(f"  {base.name}.csv / .json")

    # A avaliação inteira num arquivo só, para LER: resumo, métricas e cada
    # falha com lugar e motivo. Lê o que acabou de ser gravado; não mede nada.
    from eval import planilha
    caminho = planilha.gerar_planilha(dir_saida, momento.strftime("%Y%m%dT%H%M%SZ"))
    print(f"Planilha da avaliação: {caminho.name}")


if __name__ == "__main__":
    main()
