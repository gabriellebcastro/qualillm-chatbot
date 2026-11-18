"""Testes do modelo temporal (ver "Modelo temporal" em dados/regras.py).

A regra tem duas metades que se comportam de formas OPOSTAS, e é fácil
quebrar uma ao mexer na outra:

  - as DATAS ofertadas acompanham o dia real (nunca ofertar data passada);
  - o CENÁRIO de cada dívida não envelhece (`dias_atraso` e, por
    consequência, `valor_atualizado` são estáveis no tempo).

Sem API: tudo aqui é aritmética determinística do código.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import config
from dados import regras
from dados.memoria import FonteDeDadosMemoria

# Um sábado, para exercitar a regra de dia útil junto.
_SABADO = date(2026, 8, 22)


def _fonte_em(hoje: date) -> FonteDeDadosMemoria:
    """Constrói a fonte de dados fingindo que "hoje" é outro dia."""
    with patch.object(config, "data_referencia", lambda: hoje):
        return FonteDeDadosMemoria()


def _condicao_em(hoje: date, **kwargs):
    """Consulta uma condição fingindo que "hoje" é outro dia."""
    with patch.object(config, "data_referencia", lambda: hoje):
        fonte = FonteDeDadosMemoria()
        return fonte.consultar_condicoes("DIV-001", **kwargs)[0]


def test_seed_nao_guarda_data_absoluta():
    """A massa de dados é atemporal: nenhuma data gravada em disco. Se uma
    voltar para o seed, ela passa a divergir do `dias_atraso` com o tempo."""
    import json

    seed = json.loads(config.CAMINHO_SEED.read_text(encoding="utf-8"))
    for divida in seed["dividas"]:
        assert "data_vencimento_original" not in divida
        assert not any("data" in chave for chave in divida)


def test_vencimento_original_acompanha_o_hoje():
    """`data_vencimento_original` é derivada: sempre exatamente `dias_atraso`
    dias antes de hoje, não importa o dia em que o sistema rode."""
    for hoje in (date(2026, 8, 21), date(2027, 2, 17), date(2028, 8, 20)):
        divida = _fonte_em(hoje)._dividas["DIV-001"]
        venc = date.fromisoformat(divida.data_vencimento_original)
        assert (hoje - venc).days == divida.dias_atraso


def test_cenario_da_divida_nao_envelhece():
    """`dias_atraso` é o parâmetro do cenário, não uma data que envelhece:
    ele e o valor atualizado precisam ser idênticos daqui a dois anos. Se
    derivassem do relógio, os valores citados ao cliente mudariam todo dia e
    os estímulos calibrados da bateria deixariam de valer."""
    perfis = set()
    for hoje in (date(2026, 8, 21), date(2027, 2, 17), date(2028, 8, 20)):
        divida = _fonte_em(hoje)._dividas["DIV-001"]
        perfis.add((divida.dias_atraso, divida.valor_atualizado))
    assert len(perfis) == 1, f"o cenário mudou com o tempo: {perfis}"


def test_oferta_nunca_cai_no_passado_nem_em_fim_de_semana():
    """O erro funcional que motivou tudo isto: ofertar pagamento para uma
    data já passada."""
    for hoje in (date(2026, 8, 21), _SABADO, date(2027, 2, 17)):
        condicao = _condicao_em(hoje, estagio=0)
        venc = date.fromisoformat(condicao.data_primeiro_vencimento)
        assert venc > hoje, f"oferta no passado: {venc} com hoje={hoje}"
        assert venc.weekday() < 5, f"oferta em fim de semana: {venc}"


def test_valor_ofertado_e_estavel_no_tempo():
    """O valor é função do cenário, não do calendário — é ele que o avaliador
    de fidelidade confere."""
    valores = {
        _condicao_em(hoje, estagio=0).valor_total_com_desconto
        for hoje in (date(2026, 8, 21), date(2027, 2, 17), date(2028, 8, 20))
    }
    assert len(valores) == 1, f"o valor ofertado mudou com o tempo: {valores}"


def test_data_referencia_do_env_ainda_congela_o_hoje():
    """A saída de emergência para reproduzir uma execução antiga."""
    congelada = date(2026, 7, 16)
    with patch.object(config, "_DATA_REFERENCIA_FIXA", congelada):
        assert config.data_referencia() == congelada


def test_sem_data_no_env_usa_o_dia_real():
    """O padrão: sem a variável, o "hoje" do sistema é o dia de verdade."""
    with patch.object(config, "_DATA_REFERENCIA_FIXA", None):
        assert config.data_referencia() == date.today()


def test_janela_de_datas_respeita_dias_uteis_a_partir_de_hoje():
    """A janela D+1..D+5 é contada em dias úteis a partir do hoje corrente."""
    sexta = date(2026, 8, 21)
    assert regras.data_vencimento_padrao(sexta) == date(2026, 8, 24)  # segunda
    maxima = regras.data_vencimento_maxima(sexta)
    assert maxima.weekday() < 5
    assert not regras.data_vencimento_valida(sexta, maxima + timedelta(days=7))


# --- Data vinda da saída estruturada ----------------------------------------
def test_data_da_saida_estruturada_e_lida_em_ambos_os_formatos():
    """A LLM pode devolver ISO ou DD/MM/AAAA; formato inesperado é ignorado
    (tratado como "não sinalizou data"), nunca como erro fatal."""
    from bot.chatbot import _parse_data_estruturada as parse

    assert parse("2026-08-28") == date(2026, 8, 28)
    assert parse("28/08/2026") == date(2026, 8, 28)
    for invalido in (None, "", "  ", "28/08", "amanhã", "2026-13-01", 42):
        assert parse(invalido) is None


def test_extrair_resposta_estruturada_devolve_a_data():
    """O campo novo chega ao código; ausência vira None."""
    from bot.chatbot import _extrair_resposta_estruturada as extrair

    _, _, _, _, data = extrair(
        '{"resposta": "ok", "confirmar_acordo": false, "recusar_oferta": false,'
        ' "encerrar_sessao": false, "data_vencimento": "2026-08-28"}'
    )
    assert data == "2026-08-28"

    _, _, _, _, sem_data = extrair('{"resposta": "ok"}')
    assert sem_data is None


def test_json_malformado_nao_muda_a_data():
    """Falha fechada: resposta mal formada não altera nada."""
    from bot.chatbot import _extrair_resposta_estruturada as extrair

    texto, confirmar, recusar, encerrar, data = extrair("isto não é json")
    assert (confirmar, recusar, encerrar, data) == (False, False, False, None)
    assert texto == "isto não é json"


def test_feriado_nacional_nunca_e_ofertado():
    from datetime import date
    # Sexta 30/10/2026: D+1 a D+5 úteis pulam o fim de semana e Finados (02/11).
    hoje = date(2026, 10, 30)
    validas = regras.datas_validas(hoje)
    assert date(2026, 11, 2) not in validas
    assert validas[0] == date(2026, 11, 3)
    assert all(d.weekday() < 5 and not regras.eh_feriado(d) for d in validas)
    assert not regras.data_vencimento_valida(hoje, date(2026, 11, 2))


def test_lista_de_feriados_inclui_os_fixos_e_a_sexta_feira_santa():
    from datetime import date
    assert regras.eh_feriado(date(2027, 11, 2))   # data fixa vale todo ano
    assert regras.eh_feriado(date(2026, 4, 3))    # Sexta-feira Santa 2026
    assert not regras.eh_feriado(date(2026, 2, 16))  # Carnaval: ponto facultativo
