"""Rotulagem humana pela interface, e o κ que sai dela (camada 4).

O artefato continua sendo o MESMO CSV que `scripts/kappa.py` gera e lê. A tela
não cria um segundo formato nem um banco paralelo: quem exporta pela linha de
comando pode rotular pela tela e calcular pela linha de comando, em qualquer
ordem. Duplicar o armazenamento criaria duas verdades sobre o que já foi
rotulado, que é o defeito que o arquivo de estado da bateria já cometeu uma
vez neste projeto.

**O cegamento aqui é estrutural, e é a razão de a tela existir.** No CSV a
coluna `rotulo_juiz` está visível, e o que protege a rotulagem é a instrução
de não olhar. `itens()` simplesmente NÃO devolve o veredito do juiz: ele não
chega ao navegador, então não há como ver antes de rotular, nem por descuido
nem por curiosidade. O veredito só aparece em `resultado()`, depois de o
rótulo humano estar gravado — é o cuidado de protocolo que a avaliação humana
exige (ver `Elangovan2024`, citado no capítulo de estado da arte).
"""
from __future__ import annotations

import csv
import threading
from pathlib import Path

import config
from eval import concordancia

_lock = threading.Lock()
PREFIXO = "kappa__amostra__"
PREFIXO_JULGAMENTOS = "julgamentos__"
PREFIXO_ORIGEM = "# JULGAMENTOS:"


def _caminho_julgamentos(nome: str) -> Path:
    """Mesma proteção contra travessia de `_caminho`, para os julgamentos."""
    seguro = Path(nome).name
    if not seguro.startswith(PREFIXO_JULGAMENTOS) or not seguro.endswith(".jsonl"):
        raise ValueError(f"Nome de julgamentos invalido: {nome}")
    caminho = config.DIR_LOGS / seguro
    if not caminho.exists():
        raise FileNotFoundError(f"Julgamentos nao encontrados: {seguro}")
    return caminho


def listar_julgamentos() -> list[dict]:
    """Avaliações com juiz já feitas, da mais recente para a mais antiga."""
    saida = []
    for caminho in sorted(config.DIR_LOGS.glob(f"{PREFIXO_JULGAMENTOS}*.jsonl"), reverse=True):
        cabecalho, itens_ = concordancia.carregar_julgamentos(caminho)
        por_metrica: dict[str, int] = {}
        for i in itens_:
            por_metrica[i.get("metrica", "")] = por_metrica.get(i.get("metrica", ""), 0) + 1
        saida.append({
            "nome": caminho.name,
            "juiz": cabecalho.get("juiz"),
            "coletado_em": cabecalho.get("coletado_em"),
            "categorias": cabecalho.get("categorias"),
            "uso_do_juiz": cabecalho.get("uso_do_juiz"),
            "total": len(itens_),
            "por_metrica": por_metrica,
        })
    return saida


def gerar_amostra(julgamentos: str, por_metrica: int = 20, semente: int = 42,
                  outros: list[str] | None = None) -> dict:
    """Sorteia a amostra de rotulagem dos julgamentos de uma avaliação.

    Não chama o juiz: os vereditos são os que entraram no relatório daquela
    avaliação. A origem fica registrada no CSV, para o resultado saber de que
    juiz é o κ e para a comparação contra um segundo juiz casar os itens.

    `outros` são julgamentos de outros juízes sobre os mesmos logs: o que eles
    acusaram também entra no enriquecimento, para que a amostra não favoreça
    o juiz de origem na comparação (ver `concordancia.amostrar_por_metrica`).
    """
    from datetime import datetime, timezone
    origem = _caminho_julgamentos(julgamentos)
    _, itens_ = concordancia.carregar_julgamentos(origem)
    if not itens_:
        raise ValueError("Esta avaliação não tem vereditos para sortear.")
    momento = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    caminho = config.DIR_LOGS / f"{PREFIXO}{momento}.csv"
    acusados: set = set()
    for nome in outros or []:
        if nome and nome != origem.name:
            _, itens_outro = concordancia.carregar_julgamentos(_caminho_julgamentos(nome))
            acusados |= concordancia.chaves_acusadas(itens_outro)
    avisos: list[str] = []
    concordancia.exportar_amostra(itens_, caminho, por_metrica=por_metrica, semente=semente,
                                  acusados_por_outros=acusados or None, avisos=avisos)
    with open(caminho, encoding="utf-8") as f:
        conteudo = f.read()
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(f"{PREFIXO_ORIGEM} {origem.name}\n" + conteudo)
    # Itens cujo turno não foi achado no log para remontar o material do juiz
    # (ver `concordancia.completar_item_julgado`); também ficam no topo do CSV.
    return {"nome": caminho.name, "origem": origem.name, "avisos": avisos,
            **_progresso(_ler(caminho))}


def comparar(a: str, b: str) -> dict:
    """κ entre dois juízes sobre os mesmos logs, com custo e tempo de cada um."""
    cab_a, itens_a = concordancia.carregar_julgamentos(_caminho_julgamentos(a))
    cab_b, itens_b = concordancia.carregar_julgamentos(_caminho_julgamentos(b))
    if (cab_a.get("arquivos_de_log") or []) != (cab_b.get("arquivos_de_log") or []):
        aviso = ("As duas avaliações não leram exatamente os mesmos arquivos de log: "
                 "só os itens presentes nas duas entram no κ.")
    else:
        aviso = None
    return {
        "a": {"nome": Path(a).name, **cab_a},
        "b": {"nome": Path(b).name, **cab_b},
        "aviso": aviso,
        **concordancia.comparar_juizes(itens_a, itens_b),
    }


def _caminho(nome: str) -> Path:
    """Resolve o nome da amostra em caminho, barrando travessia de diretório.

    O nome vem da URL, então precisa ser tratado como entrada hostil: sem
    esta checagem, um `../` daria leitura e ESCRITA em qualquer arquivo que o
    servidor alcance.
    """
    seguro = Path(nome).name
    if not seguro.startswith(PREFIXO) or not seguro.endswith(".csv"):
        raise ValueError(f"Nome de amostra invalido: {nome}")
    caminho = config.DIR_LOGS / seguro
    if not caminho.exists():
        raise FileNotFoundError(f"Amostra nao encontrada: {seguro}")
    return caminho


def _ler(caminho: Path) -> list[dict]:
    return concordancia.carregar_amostra(caminho)


def _comentarios(caminho: Path) -> list[str]:
    """As linhas `#` do topo: instrução, aviso de amostra enriquecida, origem."""
    topo = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            if not linha.startswith("#"):
                break
            topo.append(linha.rstrip("\n"))
    return topo


def _origem(caminho: Path) -> str | None:
    """Arquivo de julgamentos de onde a amostra foi sorteada, se registrado."""
    for linha in _comentarios(caminho):
        if linha.startswith(PREFIXO_ORIGEM):
            return linha[len(PREFIXO_ORIGEM):].strip()
    return None


def _gravar(caminho: Path, linhas: list[dict]) -> None:
    """Reescreve o CSV inteiro, preservando as linhas de comentário do topo.

    Antes só a instrução era reescrita, e o aviso de amostra enriquecida sumia
    no primeiro rótulo gravado pela tela.
    """
    topo = _comentarios(caminho) or [f"# {concordancia.INSTRUCAO}"]
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        for linha in topo:
            f.write(linha + "\n")
        escritor = csv.DictWriter(
            f, fieldnames=concordancia.COLUNAS_AMOSTRA, extrasaction="ignore"
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def _rotulos(metrica: str) -> list[str]:
    """Rótulos que esta métrica admite, com a abstenção sempre no fim.

    O vocabulário vem da métrica, nunca dos valores presentes na amostra:
    derivar das respostas do juiz revelaria a distribuição dele a quem
    deveria rotular às cegas.
    """
    base = list(concordancia.ROTULOS_POSSIVEIS.get(metrica, ()))
    if concordancia.ROTULO_ABSTENCAO not in base:
        base.append(concordancia.ROTULO_ABSTENCAO)
    return base


def _progresso(linhas: list[dict]) -> dict:
    """Quanto da amostra já foi rotulado, no total e por métrica."""
    por_metrica: dict[str, dict] = {}
    for l in linhas:
        m = por_metrica.setdefault(
            l.get("metrica", ""), {"total": 0, "rotuladas": 0}
        )
        m["total"] += 1
        if (l.get("rotulo_humano") or "").strip():
            m["rotuladas"] += 1
    return {
        "total": len(linhas),
        "rotuladas": sum(m["rotuladas"] for m in por_metrica.values()),
        "por_metrica": por_metrica,
    }


def listar() -> list[dict]:
    """Amostras disponíveis, da mais recente para a mais antiga."""
    saida = []
    for caminho in sorted(config.DIR_LOGS.glob(f"{PREFIXO}*.csv"), reverse=True):
        try:
            linhas = _ler(caminho)
        except OSError:
            continue
        saida.append({
            "nome": caminho.name,
            # O instante está no nome: AAAAMMDDTHHMMSSZ, entre o prefixo e .csv
            "momento": caminho.stem[len(PREFIXO):],
            "origem": _origem(caminho),
            **_progresso(linhas),
        })
    return saida


def itens(nome: str, apenas_pendentes: bool = False) -> dict:
    """Itens da amostra para rotular — SEM o veredito do juiz.

    A omissão é o ponto: o que não é enviado não pode ser visto antes de
    rotular. `rotulos_possiveis` vem do vocabulário da métrica, nunca dos
    valores presentes na amostra, para não revelar a distribuição do juiz.
    """
    caminho = _caminho(nome)
    linhas = _ler(caminho)
    fora = []
    for l in linhas:
        rotulo = (l.get("rotulo_humano") or "").strip()
        if apenas_pendentes and rotulo:
            continue
        metrica = l.get("metrica", "")
        fora.append({
            "id": l.get("id"),
            "metrica": metrica,
            "pergunta": concordancia.PERGUNTA.get(metrica, ""),
            # Toda métrica oferece a abstenção, inclusive as binárias: forçar
            # um sim/não sobre evidência truncada produz um rótulo inventado,
            # e o κ mediria esse chute em lugar da concordância.
            "rotulos_possiveis": _rotulos(metrica),
            "sessao_id": l.get("sessao_id", ""),
            "execucao_id": l.get("execucao_id", ""),
            "turno_id": l.get("turno_id", ""),
            "mensagem_usuario": l.get("mensagem_usuario", ""),
            "resposta_bot": l.get("resposta_bot", ""),
            "item_julgado": l.get("item_julgado", ""),
            "rotulo_humano": rotulo,
        })
    return {"nome": caminho.name, "origem": _origem(caminho), "itens": fora,
            **_progresso(linhas)}


def rotular(nome: str, item_id: str, rotulo: str) -> dict:
    """Grava o rótulo humano de UM item e devolve o progresso.

    Recusa rótulo fora do vocabulário da métrica: um valor digitado errado
    viraria uma categoria nova no cálculo do κ, baixando a concordância por
    erro de digitação em vez de discordância real.
    """
    with _lock:
        caminho = _caminho(nome)
        linhas = _ler(caminho)
        alvo = next((l for l in linhas if str(l.get("id")) == str(item_id)), None)
        if alvo is None:
            raise KeyError(f"Item {item_id} nao existe nesta amostra.")

        metrica = alvo.get("metrica", "")
        # A validação usa a MESMA lista oferecida na tela, abstenção incluída:
        # divergir faria o servidor recusar um botão que ele mesmo exibiu.
        permitidos = _rotulos(metrica)
        valor = concordancia._normalizar(rotulo)
        if metrica in concordancia.ROTULOS_POSSIVEIS and valor not in permitidos:
            raise ValueError(
                f"Rotulo '{rotulo}' invalido para {metrica}. "
                f"Validos: {', '.join(permitidos)}"
            )

        alvo["rotulo_humano"] = valor
        _gravar(caminho, linhas)
        return {"nome": caminho.name, "id": item_id, "rotulo_humano": valor,
                **_progresso(linhas)}


def resultado(nome: str, contra: str | None = None) -> dict:
    """κ por métrica. É aqui que o veredito do juiz aparece, e não antes.

    `contra` aponta os julgamentos de um SEGUNDO juiz: os mesmos rótulos
    humanos são comparados com ele, casando os itens pela chave. Uma única
    rotulagem serve aos dois juízes.
    """
    caminho = _caminho(nome)
    linhas = _ler(caminho)
    resultados = concordancia.calcular_kappa(linhas)
    contra_juiz = None
    if contra:
        cab, itens_ = concordancia.carregar_julgamentos(_caminho_julgamentos(contra))
        contra_juiz = {
            "nome": Path(contra).name,
            "juiz": cab.get("juiz"),
            "metricas": [r.to_dict() for r in concordancia.kappa_humano_contra(linhas, itens_)],
        }
    return {
        "nome": caminho.name,
        "origem": _origem(caminho),
        **_progresso(linhas),
        "metricas": [r.to_dict() for r in resultados],
        "contra_segundo_juiz": contra_juiz,
        # Depois de rotulado, comparar item a item é o que permite olhar as
        # discordâncias uma por uma — é delas que sai a revisão do critério
        # do juiz quando o κ fica baixo.
        "divergencias": [
            {
                "id": l.get("id"),
                "metrica": l.get("metrica", ""),
                "rotulo_humano": concordancia._normalizar(l.get("rotulo_humano")),
                "rotulo_juiz": concordancia._normalizar(l.get("rotulo_juiz")),
                "item_julgado": l.get("item_julgado", ""),
                "mensagem_usuario": l.get("mensagem_usuario", ""),
                "resposta_bot": l.get("resposta_bot", ""),
            }
            for l in linhas
            if (l.get("rotulo_humano") or "").strip()
            and concordancia._normalizar(l.get("rotulo_humano"))
            != concordancia._normalizar(l.get("rotulo_juiz"))
        ],
    }
