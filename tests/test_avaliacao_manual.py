"""Avaliação de uma conversa manual (sem estímulo da bateria).

A interface permite avaliar uma conversa avulsa sob demanda. Duas coisas
precisam valer, e é fácil quebrar uma mexendo na outra:

  - categorias que funcionam TURNO A TURNO (precisão, aderência, segurança,
    robustez) devem ser avaliadas normalmente, mesmo sem `meta.origem_id`;
  - categorias COMPARATIVAS (confiabilidade, equidade) devem sair marcadas
    como `nao_aplicavel`, não como `sem_dados` — a distinção separa "não deu
    para medir" de "não faz sentido medir aqui".

Sem API: só as camadas determinísticas.
"""
from __future__ import annotations

from eval import relatorio


def _turno(turno_id: int, **over) -> dict:
    """Turno sintético no formato do log, sem `meta.origem_id` (manual)."""
    base = {
        "sessao_id": "web-teste",
        "execucao_id": 0,
        "turno_id": turno_id,
        "mensagem_usuario": "oi",
        "resposta_final": "Olá! Qual é o seu CPF?",
        "trechos_rag": [],
        "consultas_dados": [],
        "prompt_completo": [],
        "meta": {"provedor": "x", "modelo": "y"},
    }
    base.update(over)
    return base


def _turno_da_bateria(turno_id: int, origem_id: str) -> dict:
    """Turno com `origem_id`, como o runner da bateria grava."""
    t = _turno(turno_id)
    t["meta"] = {**t["meta"], "origem_id": origem_id, "via": "reinjecao"}
    return t


def test_reconhece_log_sem_estimulo():
    assert relatorio.sem_estimulo([_turno(1), _turno(2)])
    assert not relatorio.sem_estimulo([_turno_da_bateria(1, "caso_x")])


def test_categorias_comparativas_saem_como_nao_aplicaveis():
    """Confiabilidade e equidade não se medem numa conversa avulsa — e o
    status precisa dizer isso, em vez de fingir falta de dados."""
    secoes = relatorio.avaliar_categorias(
        [_turno(1), _turno(2)], inventario={}, usar_juiz=False
    )
    por_categoria = {s.categoria: s for s in secoes}

    for categoria in ("confiabilidade", "equidade"):
        assert por_categoria[categoria].status == "nao_aplicavel"
        assert por_categoria[categoria].nao_aplicavel, "faltou o motivo"


def test_categorias_por_turno_sao_avaliadas_sem_estimulo():
    """Achado real: antes, um log manual saía com TODAS as categorias
    vazias, porque o roteamento exigia `origem_id` no inventário — inclusive
    as que fazem todo sentido turno a turno."""
    turnos = [_turno(1), _turno(2)]
    secoes = {
        s.metrica: s
        for s in relatorio.avaliar_categorias(turnos, inventario={}, usar_juiz=False)
    }

    assert secoes["precisao_deterministica"].n_amostras == 2
    assert secoes["seguranca_sem_vazamento_turnos"].n_amostras == 2
    assert secoes["robustez_resistencia"].n_amostras == 2


def test_taxas_por_estimulo_da_seguranca_nao_se_aplicam_a_conversa_avulsa():
    """As taxas do framework são frações do repertório adversarial agregadas
    sobre as k reexecuções. Uma conversa avulsa não é repertório, e com k=1 a
    agregação degenera na leitura por turno — então elas saem marcadas, e não
    com um denominador de um estímulo fingindo ser repertório."""
    secoes = {
        s.metrica: s
        for s in relatorio.avaliar_categorias(
            [_turno(1), _turno(2)], inventario={}, usar_juiz=False
        )
    }

    for metrica in ("seguranca_sem_toxicidade", "seguranca_sem_vazamento"):
        assert secoes[metrica].status == "nao_aplicavel"
        assert secoes[metrica].nao_aplicavel, "faltou o motivo"
    # ...mas a categoria continua medindo turno a turno.
    assert secoes["seguranca_sem_vazamento_turnos"].status == "atende"


def test_logs_da_bateria_continuam_roteando_pelo_inventario():
    """A tolerância acima não pode afrouxar o roteamento da bateria: lá, só
    as categorias declaradas em `categorias_alvo` são avaliadas."""
    inventario = {"caso_x": {"id": "caso_x", "categorias_alvo": ["seguranca"]}}
    turnos = [_turno_da_bateria(1, "caso_x")]

    secoes = {
        s.metrica: s
        for s in relatorio.avaliar_categorias(turnos, inventario=inventario, usar_juiz=False)
    }

    assert secoes["seguranca_sem_vazamento"].n_amostras == 1
    # robustez não está em categorias_alvo -> não avaliada
    assert secoes["robustez_resistencia"].n_amostras == 0
    # e como HÁ estímulo, comparativas não viram "nao_aplicavel"
    assert secoes["equidade_sem_disparidade"].status != "nao_aplicavel"


def test_nome_do_relatorio_separa_conversa_manual_da_bateria():
    from datetime import datetime, timezone

    momento = datetime(2026, 8, 26, 3, 12, 56, tzinfo=timezone.utc)
    assert relatorio.nome_relatorio("seguranca", momento) == (
        "relatorio__seguranca__20260826T031256Z"
    )
    assert relatorio.nome_relatorio("seguranca", momento, "web-abc-exec0") == (
        "relatorio__web-abc-exec0__seguranca__20260826T031256Z"
    )
