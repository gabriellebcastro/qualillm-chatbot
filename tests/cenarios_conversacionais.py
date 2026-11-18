"""Cenários conversacionais para o teste com LLM real
(test_cenarios_conversacionais.py).

Cada cenário define um CLIENTE SIMULADO (interpretado por uma LLM, via
SimuladorCliente) que conversa com o bot de verdade. Ao contrário de um
roteiro fixo de frases ("Meu CPF é X" / "Quero 6x" / "Sim"), a LLM gera a
conversa dinamicamente a partir da persona — produz diálogos mais variados
e realistas (hesitação, perguntas, mudança de ideia).

Os CPFs usados são os do seed (dados/seed.json) — clientes e dívidas
diferentes em cada cenário, para exercitar faixas de desconto distintas.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cenario:
    nome: str
    persona: str
    resultado_esperado: str  # "acordo" ou "recusa"
    max_turnos: int = 8


CENARIOS: list[Cenario] = [
    Cenario(
        nome="identifica_no_primeiro_turno",
        persona=(
            "Você é Felipe Souza, CPF 000.111.222-06. Você já abre a "
            "conversa informando seu CPF diretamente, junto com o pedido de "
            "negociar a dívida — não espera ser perguntado. Depois disso, "
            "ouve a proposta e aceita a primeira opção de parcelamento que "
            "fizer sentido, confirmando quando o atendente pedir."
        ),
        resultado_esperado="acordo",
    ),
    Cenario(
        nome="aceite_direto",
        persona=(
            "Você é Ana Ribeiro, CPF 000.111.222-01. Você sabe que tem uma "
            "dívida em atraso e já entra em contato disposta a resolver "
            "logo. Você se identifica com o CPF assim que perguntado, ouve "
            "a proposta e aceita a primeira opção de parcelamento que "
            "fizer sentido, sem enrolar. Confirme o acordo quando o "
            "atendente pedir confirmação."
        ),
        resultado_esperado="acordo",
    ),
    Cenario(
        nome="negocia_e_aceita",
        persona=(
            "Você é Bruno Costa, CPF 000.111.222-02. Você quer negociar, "
            "mas antes de decidir faz 1 ou 2 perguntas sobre as opções "
            "(por exemplo, se dá para parcelar mais vezes, ou qual seria o "
            "valor total). Depois de entender as opções, você escolhe "
            "parcelar em mais vezes (não à vista) e confirma o acordo "
            "quando pedido."
        ),
        resultado_esperado="acordo",
    ),
    Cenario(
        nome="indeciso_depois_aceita",
        persona=(
            "Você é Henrique Dias, CPF 000.111.222-08. Você está inseguro, "
            "hesita bastante, faz várias perguntas (sobre valores, prazos, "
            "se pode mudar de ideia depois) e parece que vai desistir. Mas "
            "depois de ouvir as opções com calma, você muda de ideia, "
            "escolhe uma das condições oferecidas e confirma o acordo."
        ),
        resultado_esperado="acordo",
        max_turnos=10,
    ),
    Cenario(
        nome="recusa_educada",
        persona=(
            "Você é Carla Mendes, CPF 000.111.222-03. Você atende, se "
            "identifica com o CPF quando pedido, ouve a situação da dívida "
            "e as condições oferecidas, mas decide que não pode fechar "
            "nada agora. Recuse educadamente, diga que vai pensar e quer "
            "encerrar por hoje, sem fechar nenhum acordo."
        ),
        resultado_esperado="recusa",
    ),
    Cenario(
        nome="recusa_direta",
        persona=(
            "Você é Eduarda Lima, CPF 000.111.222-05. Você não está com "
            "paciência para negociar dívida hoje. Assim que o atendente "
            "perguntar o CPF, você até informa, mas logo em seguida deixa "
            "claro que não quer negociar agora e pede para encerrar o "
            "atendimento."
        ),
        resultado_esperado="recusa",
        max_turnos=5,
    ),
]
