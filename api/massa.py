"""Massa de dados fictícia: clientes, dívidas e o que cada uma renderia.

Serve a dois usos que hoje exigiam abrir `dados/seed.json` na mão:

1. **Saber com que CPF se identificar** para testar uma conversa. Era a
   pergunta mais banal e a mais chata de responder.
2. **Conferir o que o bot deveria oferecer.** As condições vêm calculadas por
   `dados/regras.py` — o mesmo código que o bot usa —, então a tela funciona
   como oráculo: se o bot disser um valor diferente do que está aqui, ele
   errou, e dá para ver isso sem rodar avaliador nenhum.

As condições são recalculadas a cada chamada, não guardadas: as datas ofertadas
acompanham o dia real (D+1 útil), então um valor congelado ficaria errado no
dia seguinte. Ver a seção "Modelo temporal" em `dados/regras.py`.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import timedelta

import config
from bot.chatbot import ETAPA_MAX_A_VISTA
from dados import FonteDeDadosMemoria
from dados.regras import max_parcelas_possivel

# A LISTAGEM vem do arquivo de seed, não da porta `FonteDeDados`.
#
# A porta expõe só o que o bot precisa — consultar um cliente por CPF,
# consultar as dívidas de um cliente —, e nunca "liste todos", porque o bot
# nunca faz isso. Alcançar o `_clientes` interno do adaptador para contornar
# isso furaria a fronteira que o resto do projeto respeita.
#
# E a fronteira nem é o que interessa aqui: esta tela mostra a MASSA DE TESTE,
# que é o arquivo, e não a visão que o bot tem dela. Ler o arquivo é a leitura
# correta do que a tela se propõe a exibir. As CONDIÇÕES, essas sim, saem da
# porta — é o cálculo real que o bot usa.


def _condicao(fonte: FonteDeDadosMemoria, divida_id: str, estagio: int) -> dict | None:
    """Primeira condição ofertada num estágio da escada, como dict serializável."""
    condicoes = fonte.consultar_condicoes(divida_id, estagio=estagio)
    if not condicoes:
        return None
    d = asdict(condicoes[0])
    for chave, valor in list(d.items()):
        if hasattr(valor, "isoformat"):
            d[chave] = valor.isoformat()
    return d


#

# Números de parcelas mostrados como exemplo. Não são "as opções": o cliente
# pede quantas quiser entre 1 e o teto da dívida. Os valores cobrem as duas
# pontas da regra — perto do mínimo e no limite da política.
_EXEMPLOS_N = (2, 6, 12, 24)


def _exemplos_parcelado(fonte: FonteDeDadosMemoria, divida_id: str) -> list[dict]:
    """Algumas condições parceladas, para dar a ordem de grandeza dos juros."""
    exemplos = []
    for n in _EXEMPLOS_N:
        condicoes = fonte.consultar_condicoes(
            divida_id, estagio=ETAPA_MAX_A_VISTA + 1, num_parcelas=n
        )
        if condicoes:
            exemplos.append(asdict(condicoes[0]))
    return exemplos


def catalogo() -> dict:
    """Clientes com suas dívidas e as ofertas que cada dívida geraria hoje."""
    fonte = FonteDeDadosMemoria()
    hoje = config.data_referencia()
    seed = json.loads(config.CAMINHO_SEED.read_text(encoding="utf-8"))

    por_cliente: dict[str, list[dict]] = {}
    for divida in seed.get("dividas", []):
        # Derivada, nunca gravada: `dias_atraso` é o parâmetro do cenário e não
        # envelhece; a data de origem é lida a partir do dia atual.
        vencimento_original = hoje - timedelta(days=divida["dias_atraso"])
        por_cliente.setdefault(divida["cliente_id"], []).append({
            **divida,
            "data_vencimento_original": vencimento_original.isoformat(),
            "max_parcelas": max_parcelas_possivel(divida["valor_atualizado"]),
            "ofertas": {
                "primeira_a_vista": _condicao(fonte, divida["id"], 0),
                "segunda_a_vista": _condicao(fonte, divida["id"], ETAPA_MAX_A_VISTA),
                # O parcelamento não tem uma condição única: quem escolhe o
                # número de parcelas é o cliente, e por isso `consultar_condicoes`
                # devolve vazio sem `num_parcelas`. Mostrar exemplos evita dar a
                # impressão de que existe "a" oferta parcelada.
                "parcelamento_exemplos": _exemplos_parcelado(fonte, divida["id"]),
            },
        })

    clientes = [
        {**cliente, "dividas": por_cliente.get(cliente["id"], [])}
        for cliente in seed.get("clientes", [])
    ]

    return {
        "data_referencia": hoje.isoformat(),
        "arquivo": str(config.CAMINHO_SEED.relative_to(config.RAIZ)).replace("\\", "/"),
        "total_clientes": len(clientes),
        "total_dividas": sum(len(c["dividas"]) for c in clientes),
        "clientes": clientes,
    }
