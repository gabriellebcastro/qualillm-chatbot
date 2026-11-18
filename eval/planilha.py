"""Planilha Excel de uma avaliação: resumo, métricas, ocorrências e procedência.

Os relatórios JSON são o registro completo e auditável; esta planilha é a
forma de LER uma avaliação inteira num arquivo só, e de tirar dela as tabelas
do trabalho. Por isso tudo vai em português, com rótulos no lugar de códigos,
porcentagem formatada e as falhas uma por linha, com lugar e motivo.

Lê apenas o que já está gravado (relatórios da avaliação e o cabeçalho do
arquivo de julgamentos). Não chama juiz nem refaz medição.
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from eval.relatorio import DESCRICAO_METRICA

ORDEM_CATEGORIAS = [
    "confiabilidade", "precisao", "aderencia_contexto", "seguranca", "equidade", "robustez",
]
NOME_CATEGORIA = {
    "confiabilidade": "Confiabilidade",
    "precisao": "Precisão",
    "aderencia_contexto": "Aderência ao contexto",
    "seguranca": "Segurança",
    "equidade": "Equidade",
    "robustez": "Robustez",
}
STATUS = {
    "atende": "Atende",
    "nao_atende": "Não atende",
    "sem_dados": "Sem dados",
    "nao_aplicavel": "Não se aplica",
    "sem_limiar": "Sem limiar",
}
CRITERIO = {
    "base_externa": "Base externa",
    "natureza_do_risco": "Natureza do risco",
    "tolerancia_ao_avaliador": "Tolerância ao avaliador",
    # Nome antigo, nos relatórios gravados antes da troca de terminologia.
    "ruido_do_avaliador": "Tolerância ao avaliador",
}
LEITURA = {
    "acima_do_limiar": "Acima do limiar",
    "abaixo_do_limiar": "Abaixo do limiar",
    "inconclusivo": "Inconclusivo",
}
VEREDITO = {
    "nao_conforme": "Não conforme",
    "sem_dados": "Sem dados",
    "conforme_com_ressalva": "Conforme com ressalva",
    "conforme": "Conforme",
}
CAMADA = {"deterministica": "Determinística", "juiz": "Juiz LLM"}
TIPO = {"falha": "Falha do sistema", "falha_juiz": "Falha do juiz", "abstencao": "Abstenção do juiz"}

_CABECALHO = Font(bold=True, color="FFFFFF")
_FUNDO_CABECALHO = PatternFill("solid", fgColor="2F4F6F")
_COR_STATUS = {
    "Atende": PatternFill("solid", fgColor="DDF0DD"),
    "Não atende": PatternFill("solid", fgColor="F6DADA"),
    "Sem dados": PatternFill("solid", fgColor="EEEEEE"),
    "Não se aplica": PatternFill("solid", fgColor="EEEEEE"),
}
_QUEBRA = Alignment(wrap_text=True, vertical="top")
_TOPO = Alignment(vertical="top")


def _tabela(aba, cabecalhos: list[tuple[str, int]], linhas: list[list], quebrar: set[int] = frozenset()):
    """Cabeçalho formatado e fixo, larguras, filtro e quebra de texto."""
    for col, (titulo, largura) in enumerate(cabecalhos, start=1):
        c = aba.cell(row=1, column=col, value=titulo)
        c.font, c.fill = _CABECALHO, _FUNDO_CABECALHO
        c.alignment = Alignment(wrap_text=True, vertical="center")
        aba.column_dimensions[get_column_letter(col)].width = largura
    for lin, valores in enumerate(linhas, start=2):
        for col, valor in enumerate(valores, start=1):
            c = aba.cell(row=lin, column=col, value=valor)
            c.alignment = _QUEBRA if col in quebrar else _TOPO
    aba.freeze_panes = "A2"
    if linhas:
        aba.auto_filter.ref = f"A1:{get_column_letter(len(cabecalhos))}{len(linhas) + 1}"


def _formatar_porcentagem(aba, colunas: list[int], n_linhas: int, casas: int = 1):
    formato = "0." + "0" * casas + "%" if casas else "0%"
    for col in colunas:
        for lin in range(2, n_linhas + 2):
            aba.cell(row=lin, column=col).number_format = formato


# Limite de uma célula do Excel. Só um texto maior que isso é cortado, e o
# corte fica avisado na própria célula; o texto inteiro continua no JSON.
_MAX_CELULA = 32767
_AVISO_CORTE = "\n[… cortado no limite de célula do Excel; texto inteiro no relatório JSON]"


def _celula(texto: str | None) -> str:
    texto = texto or ""
    if len(texto) <= _MAX_CELULA:
        return texto
    return texto[: _MAX_CELULA - len(_AVISO_CORTE)] + _AVISO_CORTE


def _data(iso: str) -> str:
    """'2026-10-27T20:29:52.13+00:00' -> '27/10/2026 20:29 (UTC)'."""
    if len(iso) < 16:
        return iso
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]} {iso[11:16]} (UTC)"


# Chaves do veredito antes da troca de terminologia, para abrir os relatórios
# já gravados (Fase 1 e Fase 2) sem reescrevê-los.
_FALHAS_ANTIGAS = {"maximo": "falhas_definitivas", "tolerancia": "falhas_provisorias"}


def _falhas(veredito: dict, tipo: str) -> list[str]:
    """Métricas que falharam em limiar `maximo` ou de `tolerancia`."""
    nova = veredito.get(f"falhas_limiar_{tipo}")
    return (nova if nova is not None else veredito.get(_FALHAS_ANTIGAS[tipo])) or []


def carregar_avaliacao(dir_logs: Path, instante: str) -> tuple[list[dict], dict]:
    """Relatórios de uma avaliação (por instante) e o cabeçalho dos julgamentos."""
    relatorios = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(dir_logs.glob(f"relatorio__*__{instante}.json"))
    ]
    cabecalho: dict = {}
    for p in dir_logs.glob(f"julgamentos__*__{instante}.jsonl"):
        with open(p, encoding="utf-8") as f:
            cabecalho = json.loads(f.readline())
    return relatorios, cabecalho


def gerar_planilha(dir_logs: Path, instante: str, destino: Path | None = None) -> Path:
    """Grava `avaliacao__<instante>.xlsx` em `dir_logs` (ou em `destino`)."""
    relatorios, cabecalho = carregar_avaliacao(dir_logs, instante)
    if not relatorios:
        raise FileNotFoundError(f"nenhum relatório com o instante {instante}")

    proc = relatorios[0].get("procedencia") or {}
    metricas: list[dict] = []
    for rel in relatorios:
        for bloco in rel.get("categorias") or []:
            metricas.extend(bloco.get("metricas") or [])
    ordem = {c: i for i, c in enumerate(ORDEM_CATEGORIAS)}
    metricas.sort(key=lambda m: (ordem.get(m["categoria"], 99), m["metrica"]))

    wb = Workbook()

    # --- Resumo -------------------------------------------------------------
    resumo = wb.active
    resumo.title = "Resumo"
    veredito = proc.get("veredito") or {}
    uso = proc.get("uso_do_juiz") or cabecalho.get("uso_do_juiz") or {}
    minutos = (uso.get("latencia_total_s") or 0) / 60
    linhas_resumo = [
        ["Juiz", proc.get("juiz") or "não usado"],
        ["Avaliação feita em", _data(proc.get("coletado_em", ""))],
        ["Modelo do bot", ", ".join(proc.get("modelos_do_bot") or [])],
        ["Independência do avaliador", proc.get("independencia_do_avaliador", "")],
        ["Conversas avaliadas (arquivos de log)", len(proc.get("arquivos_de_log") or [])],
        ["Turnos avaliados", proc.get("n_turnos")],
        ["Repetições por estímulo", proc.get("n_reexecucoes")],
        ["Veredito global", VEREDITO.get(veredito.get("estado"), veredito.get("estado", ""))],
        ["Falhas em limiar máximo", ", ".join(_falhas(veredito, "maximo")) or "—"],
        ["Falhas em limiar de tolerância", ", ".join(_falhas(veredito, "tolerancia")) or "—"],
        ["Métricas sem dados", ", ".join(veredito.get("metricas_sem_dados") or []) or "—"],
        ["Chamadas ao juiz", uso.get("chamadas")],
        ["Tokens de entrada", uso.get("tokens_entrada")],
        ["Tokens de saída", uso.get("tokens_saida")],
        ["Tempo do juiz (min)", round(minutos, 1) if minutos else None],
        ["Custo estimado (US$)", uso.get("custo_estimado_usd")],
        ["Métricas que atendem", sum(1 for m in metricas if m["status"] == "atende")],
        ["Métricas que não atendem", sum(1 for m in metricas if m["status"] == "nao_atende")],
        ["Total de ocorrências registradas", sum(len(m.get("ocorrencias") or []) for m in metricas)],
    ]
    _tabela(resumo, [("Item", 38), ("Valor", 70)], linhas_resumo, quebrar={2})
    resumo.auto_filter.ref = None
    for lin in range(2, len(linhas_resumo) + 2):
        resumo.cell(row=lin, column=1).font = Font(bold=True)
    celula_veredito = resumo.cell(row=9, column=2)
    celula_veredito.font = Font(bold=True)
    celula_veredito.fill = _COR_STATUS.get(
        "Atende" if veredito.get("estado") == "conforme" else "Não atende", PatternFill())

    # --- Métricas -----------------------------------------------------------
    aba_m = wb.create_sheet("Métricas")
    linhas_m = []
    for m in metricas:
        _, nome, modalidade = DESCRICAO_METRICA.get(m["metrica"], ("", m["metrica"], ""))
        c = m.get("certeza") or {}
        intervalo = c.get("intervalo") or [None, None]
        ocs = m.get("ocorrencias") or []
        linhas_m.append([
            NOME_CATEGORIA.get(m["categoria"], m["categoria"]),
            nome,
            m["metrica"],
            modalidade,
            m.get("valor"),
            m.get("limiar"),
            STATUS.get(m["status"], m["status"]),
            intervalo[0],
            intervalo[1],
            LEITURA.get(c.get("leitura"), c.get("leitura") or ""),
            m.get("n_amostras"),
            c.get("n") or m.get("n_estimulos"),
            m.get("falhas_juiz"),
            m.get("abstencoes"),
            sum(1 for o in ocs if o.get("tipo") == "falha"),
            CRITERIO.get(m.get("criterio_limiar"), m.get("criterio_limiar") or ""),
            m.get("observacao", ""),
        ])
    _tabela(aba_m, [
        ("Categoria", 20), ("Métrica", 40), ("Código", 30), ("Verificação", 22),
        ("Valor", 9), ("Limiar", 9), ("Status", 12), ("Intervalo 95% (inf.)", 11),
        ("Intervalo 95% (sup.)", 11), ("Leitura da certeza", 16), ("Nº de observações", 12),
        ("Estímulos (n do intervalo)", 13), ("Falhas do juiz", 9), ("Abstenções", 10),
        ("Falhas registradas", 10), ("Critério do limiar", 18), ("Observação", 80),
    ], linhas_m, quebrar={2, 17})
    _formatar_porcentagem(aba_m, [5, 6, 8, 9], len(linhas_m))
    for lin in range(2, len(linhas_m) + 2):
        c = aba_m.cell(row=lin, column=7)
        c.fill = _COR_STATUS.get(c.value, PatternFill())
        c.font = Font(bold=True)

    # --- Ocorrências --------------------------------------------------------
    aba_o = wb.create_sheet("Ocorrências")
    linhas_o = []
    for m in metricas:
        _, nome, _ = DESCRICAO_METRICA.get(m["metrica"], ("", m["metrica"], ""))
        for o in m.get("ocorrencias") or []:
            linhas_o.append([
                NOME_CATEGORIA.get(m["categoria"], m["categoria"]),
                nome,
                TIPO.get(o.get("tipo"), o.get("tipo", "")),
                CAMADA.get(o.get("camada"), o.get("camada", "")),
                o.get("estimulo", ""),
                str(o.get("execucao_id", "")),
                o.get("turno_id", ""),
                o.get("detalhe", ""),
                _celula(o.get("evidencia")),
                _celula(o.get("justificativa")),
                o.get("sessao_id", ""),
            ])
    _tabela(aba_o, [
        ("Categoria", 18), ("Métrica", 32), ("Tipo", 16), ("Camada", 14),
        ("Estímulo", 30), ("Execução", 10), ("Turno", 7), ("O que falhou", 45),
        ("Trecho / texto avaliado", 60), ("Justificativa do juiz", 60), ("Log da conversa", 50),
    ], linhas_o, quebrar={8, 9, 10})

    # --- Procedência --------------------------------------------------------
    aba_p = wb.create_sheet("Procedência")
    linhas_p = []
    for chave, valor in proc.items():
        # `categoria` é do arquivo de onde a procedência foi lida, não da
        # avaliação; os demais já estão no Resumo ou vêm abaixo, um por linha.
        if chave in ("categoria", "arquivos_de_log", "limiares", "veredito", "uso_do_juiz"):
            continue
        texto = valor if isinstance(valor, (str, int, float)) or valor is None else json.dumps(
            valor, ensure_ascii=False)
        linhas_p.append([chave, texto])
    for chave, info in (relatorios[0].get("limiares") or {}).items():
        linhas_p.append([f"limiar · {chave}", info.get("valor")])
    for nome in proc.get("arquivos_de_log") or []:
        linhas_p.append(["arquivo de log", nome])
    _tabela(aba_p, [("Campo", 42), ("Valor", 100)], linhas_p, quebrar={2})

    juiz = (proc.get("juiz") or "sem-juiz").replace(":", "-")
    destino = destino or dir_logs / f"avaliacao__{juiz}__{instante}.xlsx"
    wb.save(destino)
    return destino
