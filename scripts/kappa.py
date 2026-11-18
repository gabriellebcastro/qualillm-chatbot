"""Camada 4 — concordância humano × juiz e juiz × juiz (κ de Cohen).

    python scripts/kappa.py exportar --por-metrica 20          # 1. gera o CSV
    python scripts/kappa.py calcular logs/kappa__....csv       # 3. mede o κ
    python scripts/kappa.py comparar logs/julgamentos__A.jsonl logs/julgamentos__B.jsonl
    python scripts/kappa.py confirmar logs/kappa__....csv      # taxa de confirmação

O passo 2 é humano: alguém preenche a coluna `rotulo_humano` SEM olhar a
`rotulo_juiz`. É a única parte do framework que não dá para automatizar, e é
justamente a que respalda usar o juiz em escala — sem ela, as seis categorias
assentam sobre um modelo avaliando outro modelo, sem âncora externa.

**`exportar` não chama o juiz.** Ele sorteia a amostra do arquivo de
julgamentos que a avaliação (`avaliar_bateria.py`) gravou. Antes, exportar
rodava o juiz de novo: pagava duas vezes e, como o juiz não é determinístico,
a amostra validava vereditos de outra rodada, não os do relatório.

A amostra é estratificada por métrica e sorteada com semente fixa: a mesma
entrada gera sempre a mesma amostra, então o resultado é reproduzível e a
escolha do que rotular não pode ser acusada de ter favorecido os casos
fáceis.

Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import config  # noqa: E402
from eval import concordancia  # noqa: E402


def _mais_recente() -> Path | None:
    arquivos = sorted(config.DIR_LOGS.glob("julgamentos__*.jsonl"))
    return arquivos[-1] if arquivos else None


def exportar(args: argparse.Namespace) -> int:
    caminho_julg = Path(args.julgamentos) if args.julgamentos else _mais_recente()
    if caminho_julg is None or not caminho_julg.exists():
        print("Nenhum arquivo de julgamentos. Rode antes a avaliação com juiz "
              "(scripts/avaliar_bateria.py), que grava logs/julgamentos__*.jsonl.")
        return 1
    cabecalho, itens = concordancia.carregar_julgamentos(caminho_julg)
    if not itens:
        print("O arquivo não tem vereditos: nada a rotular.")
        return 1

    print(f"Julgamentos: {caminho_julg.name} | juiz: {cabecalho.get('juiz')}")
    momento = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    caminho = Path(args.dir_saida or config.DIR_LOGS) / f"kappa__amostra__{momento}.csv"
    # Os casos que OUTROS juízes acusaram sobre os mesmos logs também entram
    # no enriquecimento; sem isso o κ humano × juiz B seria medido sobre os
    # casos do juiz A (ver `concordancia.amostrar_por_metrica`).
    acusados: set = set()
    for outro in args.uniao or []:
        cab_outro, itens_outro = concordancia.carregar_julgamentos(Path(outro))
        acusados |= concordancia.chaves_acusadas(itens_outro)
        print(f"Enriquecida também com o que acusou: {cab_outro.get('juiz')} ({Path(outro).name})")
    cota: "int | dict[str, int]" = args.por_metrica
    if args.cota:
        cota = {}
        for par in args.cota:
            nome, _, n = par.partition("=")
            cota[nome.strip()] = int(n)
        print(f"Cota por metrica: {cota}")
    avisos: list[str] = []
    linhas = concordancia.exportar_amostra(
        itens, caminho, por_metrica=cota, semente=args.semente,
        acusados_por_outros=acusados or None, avisos=avisos,
    )
    # A origem no topo do CSV, como a interface grava (api/kappa.py): sem ela
    # a tela de rotulagem não sabe de que juiz é o kappa.
    conteudo = caminho.read_text(encoding="utf-8")
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(f"# JULGAMENTOS: {caminho_julg.name}\n" + conteudo)
    for aviso in avisos:
        print(f"AVISO: {aviso}")
    print(f"\nAmostra para rotulagem: {len(linhas)} linha(s)")
    print(f"  {caminho}")
    print("\nPreencha a coluna `rotulo_humano` SEM olhar a `rotulo_juiz` e rode:")
    print(f"  python scripts/kappa.py calcular \"{caminho}\"")
    return 0


def _imprimir(resultados) -> None:
    print(f"\n{'metrica':<36} {'n':>4} {'Po':>7} {'Pe':>7} {'kappa':>7}  interpretacao")
    print("-" * 82)
    for r in resultados:
        k = "-" if r.kappa is None else f"{r.kappa:.4f}"
        print(f"{r.metrica:<36} {r.n:>4} {r.concordancia_observada:>7.4f} "
              f"{r.concordancia_esperada:>7.4f} {k:>7}  {r.interpretacao}")


def calcular(args: argparse.Namespace) -> int:
    caminho = Path(args.csv)
    if not caminho.exists():
        print(f"Arquivo não encontrado: {caminho}")
        return 1

    linhas = concordancia.carregar_amostra(caminho)
    rotuladas = [l for l in linhas if (l.get("rotulo_humano") or "").strip()]
    print(f"Linhas: {len(linhas)} | rotuladas: {len(rotuladas)}")
    if not rotuladas:
        print("Nenhuma linha rotulada. O kappa precisa do rotulo humano.")
        return 1

    resultados = concordancia.calcular_kappa(linhas)
    _imprimir(resultados)
    if args.contra:
        _, outro = concordancia.carregar_julgamentos(Path(args.contra))
        print(f"\nOs mesmos rótulos humanos contra o segundo juiz ({Path(args.contra).name}):")
        _imprimir(concordancia.kappa_humano_contra(linhas, outro))

    degeneradas = [r.metrica for r in resultados if r.kappa is None]
    if degeneradas:
        print(f"\nkappa indefinido em: {', '.join(degeneradas)}. Acontece quando os "
              "dois rotuladores usaram uma única categoria em todos os casos — "
              "não há acordo a medir além do acaso. Amostra pequena demais, ou "
              "sem nenhum caso positivo.")
    return 0


def _imprimir_confirmacao(resultados) -> dict:
    print(f"\n{'metrica':<36} {'acusados':>8} {'confirm':>8} {'TC':>7} {'omissoes':>9}")
    print("-" * 72)
    for r in resultados:
        tc = "-" if r.taxa is None else f"{r.taxa:.4f}"
        print(f"{r.metrica:<36} {r.acusados:>8} {r.confirmados:>8} {tc:>7} {r.omissoes:>9}")
    total = {k: sum(getattr(r, k) for r in resultados)
             for k in ("acusados", "confirmados", "omissoes")}
    total["taxa"] = total["confirmados"] / total["acusados"] if total["acusados"] else None
    tc = "-" if total["taxa"] is None else f"{total['taxa']:.4f}"
    print("-" * 72)
    print(f"{'total':<36} {total['acusados']:>8} {total['confirmados']:>8} {tc:>7} {total['omissoes']:>9}")
    return {"metricas": [r.to_dict() for r in resultados], "total": total}


def confirmar(args: argparse.Namespace) -> int:
    """Taxa de confirmação: das acusações do juiz, quantas o humano confirma."""
    caminho = Path(args.csv)
    if not caminho.exists():
        print(f"Arquivo não encontrado: {caminho}")
        return 1
    linhas = concordancia.carregar_amostra(caminho)
    rotuladas = [l for l in linhas if (l.get("rotulo_humano") or "").strip()]
    print(f"Linhas: {len(linhas)} | rotuladas: {len(rotuladas)}")
    if not rotuladas:
        print("Nenhuma linha rotulada. A taxa de confirmação precisa do rótulo humano.")
        return 1

    print("\nJuiz da amostra:")
    saida = {"amostra": caminho.name,
             "juiz_da_amostra": _imprimir_confirmacao(concordancia.taxa_de_confirmacao(linhas))}
    if args.contra:
        cab, outro = concordancia.carregar_julgamentos(Path(args.contra))
        print(f"\nSegundo juiz ({cab.get('juiz')}, {Path(args.contra).name}); "
              "fidelidade e groundedness ficam fora, como no kappa:")
        saida["contra"] = {"arquivo": Path(args.contra).name, "juiz": cab.get("juiz"),
                           **_imprimir_confirmacao(concordancia.taxa_de_confirmacao_contra(linhas, outro))}
    if args.saida:
        Path(args.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nGravado em {args.saida}")
    return 0


def comparar(args: argparse.Namespace) -> int:
    cab_a, itens_a = concordancia.carregar_julgamentos(Path(args.a))
    cab_b, itens_b = concordancia.carregar_julgamentos(Path(args.b))
    resultado = concordancia.comparar_juizes(itens_a, itens_b)
    print(f"A: {cab_a.get('juiz')}  ·  B: {cab_b.get('juiz')}")
    print(f"\n{'metrica':<38} {'n':>5} {'Po':>7} {'kappa':>7} {'diverg':>7} {'so_um':>6}  interpretacao")
    print("-" * 92)
    for m in resultado["metricas"]:
        po = "-" if m["concordancia_observada"] is None else f"{m['concordancia_observada']:.4f}"
        k = "-" if m["kappa"] is None else f"{m['kappa']:.4f}"
        print(f"{m['metrica']:<38} {m['n']:>5} {po:>7} {k:>7} {m['divergentes']:>7} "
              f"{m['so_um_juiz']:>6}  {m['interpretacao']}")
    for rotulo, cab in (("A", cab_a), ("B", cab_b)):
        uso = cab.get("uso_do_juiz") or {}
        custo = uso.get("custo_estimado_usd")
        print(f"\nCusto {rotulo}: {uso.get('chamadas')} chamadas, "
              f"{uso.get('tokens_entrada')}+{uso.get('tokens_saida')} tokens, "
              f"{uso.get('latencia_total_s')} s"
              + (f", ~US$ {custo:.4f}" if custo is not None else ", preço não cadastrado"))
    if args.saida:
        Path(args.saida).write_text(json.dumps(
            {"a": cab_a, "b": cab_b, **resultado}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Concordancia (kappa de Cohen): humano x juiz e juiz x juiz.")
    sub = p.add_subparsers(dest="comando", required=True)

    e = sub.add_parser("exportar", help="sorteia a amostra do arquivo de julgamentos")
    e.add_argument("--julgamentos", help="logs/julgamentos__*.jsonl (padrao: o mais recente)")
    e.add_argument("--por-metrica", type=int, default=20,
                   help="quantos julgamentos sortear de CADA metrica (padrao 20)")
    e.add_argument("--cota", action="append",
                   help="cota de uma metrica, no formato metrica=n (pode repetir); com ela, "
                        "so as metricas listadas entram, e --por-metrica e ignorado")
    e.add_argument("--semente", type=int, default=42,
                   help="semente do sorteio; mudar muda a amostra (padrao 42)")
    e.add_argument("--dir-saida", help="onde gravar o CSV (padrao: logs/)")
    e.add_argument("--uniao", action="append",
                   help="julgamentos de outro juiz sobre os mesmos logs: os casos que ele "
                        "acusou tambem entram no enriquecimento (pode repetir)")
    e.set_defaults(funcao=exportar)

    c = sub.add_parser("calcular", help="le o CSV rotulado e mede o kappa")
    c.add_argument("csv", help="caminho do CSV com a coluna rotulo_humano preenchida")
    c.add_argument("--contra", help="julgamentos de um segundo juiz, para o kappa humano x juiz B")
    c.set_defaults(funcao=calcular)

    t = sub.add_parser("confirmar", help="taxa de confirmacao das acusacoes do juiz pelo humano")
    t.add_argument("csv", help="caminho do CSV com a coluna rotulo_humano preenchida")
    t.add_argument("--contra", help="julgamentos de um segundo juiz, para a mesma taxa contra ele")
    t.add_argument("--saida", help="grava o resultado em JSON")
    t.set_defaults(funcao=confirmar)

    k = sub.add_parser("comparar", help="kappa entre dois juizes sobre os mesmos logs")
    k.add_argument("a", help="julgamentos do juiz A")
    k.add_argument("b", help="julgamentos do juiz B")
    k.add_argument("--saida", help="grava o resultado em JSON")
    k.set_defaults(funcao=comparar)

    args = p.parse_args()
    raise SystemExit(args.funcao(args))


if __name__ == "__main__":
    main()
