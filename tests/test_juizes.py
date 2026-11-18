"""Testes do contrato dos juízes: composição do prompt, abstenção e viés de
posição. Sem API — os juízes recebem um cliente duplo que devolve o JSON
combinado.

O que se verifica aqui é o INSTRUMENTO, não o sistema avaliado: se a abstenção
sai do denominador em lugar de virar reprovação, se o núcleo genérico funciona
sem o apêndice de domínio, e se um veredito que muda com a ordem das
transcrições deixa de ser contado.
"""
import json

import pytest

from eval import concordancia, consistencia, equidade, juiz as mod_juiz, robustez, seguranca
from llm.interface import ClienteLLM, RespostaLLM


class ClienteFixo(ClienteLLM):
    """Devolve sempre a mesma resposta, e registra os prompts recebidos."""
    provedor = "duplo"
    modelo = "fixo"

    def __init__(self, resposta: dict | list):
        # Lista = uma resposta por chamada, na ordem.
        self.respostas = resposta if isinstance(resposta, list) else [resposta]
        self.chamadas: list[str] = []

    def gerar(self, sistema, mensagens, temperatura=None, max_tokens=1024,
              formato_json=False):
        self.chamadas.append(sistema)
        i = min(len(self.chamadas) - 1, len(self.respostas) - 1)
        return RespostaLLM(texto=json.dumps(self.respostas[i]),
                           modelo=self.modelo, provedor=self.provedor)


def _turnos(n_execucoes: int, resposta: str = "Sua dívida é de R$ 100,00."):
    return [
        {"sessao_id": "s", "execucao_id": e, "turno_id": 1,
         "mensagem_usuario": "quanto eu devo?", "resposta_final": resposta,
         "trechos_rag": [], "consultas_dados": [], "prompt_completo": [],
         "estado": {}, "meta": {"provedor": "x", "modelo": "y"}}
        for e in range(1, n_execucoes + 1)
    ]


# --- Composição núcleo + domínio -------------------------------------------
def test_prompt_enviado_junta_nucleo_e_dominio():
    """O juiz recebe os dois arquivos concatenados, o núcleo primeiro."""
    cliente = ClienteFixo({"justificativa": "x", "equivalente": True})
    j = mod_juiz.JuizLLM("prompt_juiz_equivalencia.md", cliente_llm=cliente)

    j.julgar("qualquer coisa")

    enviado = cliente.chamadas[0]
    assert "avaliador de consistência" in enviado          # do núcleo
    assert "Domínio desta aplicação" in enviado            # do apêndice
    assert enviado.index("avaliador de consistência") < enviado.index("Domínio")


def test_nucleo_funciona_sem_apendice_de_dominio(tmp_path):
    """É o caminho de quem aplica o framework a outro sistema: sem o arquivo
    de domínio, o juiz roda só com o núcleo genérico."""
    nucleo = tmp_path / "prompt_juiz_x.md"
    nucleo.write_text("so o nucleo", encoding="utf-8")

    composto = mod_juiz.compor_prompt(nucleo, tmp_path / "prompt_dominio_x.md")

    assert composto.strip() == "so o nucleo"


def test_nenhum_nucleo_declara_o_dominio():
    """O núcleo é publicável como está. Se ele nomear o domínio, deixa de ser
    genérico — e foi assim que os prompts nasceram, todos declarando
    'chabot de negociação de dívidas' na segunda linha."""
    termos = ("dívida", "divida", "cobrança", "cobranca", "CPF",
              "parcelamento", "credor", "inadimplen")
    for nome in sorted(mod_juiz.DIR_PROMPTS.glob("prompt_juiz_*.md")):
        if nome.name in ("prompt_juiz.md", "prompt_juiz_sessao.md"):
            continue   # juízes de tom: medida auxiliar, fora do framework
        texto = nome.read_text(encoding="utf-8")
        achados = [t for t in termos if t in texto]
        assert not achados, f"{nome.name} cita o domínio: {achados}"


def test_todo_nucleo_pede_justificativa_antes_do_veredito():
    """Ordem dos campos: o modelo decide ao escrever, então justificar depois
    de decidir produz racionalização. Todos pediam o veredito primeiro."""
    for nome in sorted(mod_juiz.DIR_PROMPTS.glob("prompt_juiz_*.md")):
        if nome.name in ("prompt_juiz.md", "prompt_juiz_sessao.md"):
            continue
        texto = nome.read_text(encoding="utf-8")
        assert "A ordem dos campos é obrigatória" in texto, nome.name
        assert texto.index('"justificativa"') < max(
            texto.index('"classificacao"') if '"classificacao"' in texto else 0,
            texto.index('"equivalente"') if '"equivalente"' in texto else 0,
            texto.index('"nota"') if '"nota"' in texto else 0,
            texto.index('"resistiu"') if '"resistiu"' in texto else 0,
            texto.index('"disparidade"') if '"disparidade"' in texto else 0,
        ), nome.name


# --- Abstenção --------------------------------------------------------------
def test_abstencao_na_consistencia_sai_do_denominador_sem_virar_divergencia():
    """`bool(None)` daria False, isto é, contaria o par como DIVERGENTE."""
    cliente = ClienteFixo({"justificativa": "resposta truncada", "equivalente": None})
    j = mod_juiz.JuizLLM("prompt_juiz_equivalencia.md", cliente_llm=cliente)

    r = consistencia.avaliar(_turnos(2), origem_id="x", juiz=j)

    assert r.abstencoes == 1
    assert r.falhas_juiz == 0, "abstenção não é falha do avaliador"
    assert r.taxa_equivalencia is None, "o par saiu do denominador"


def test_abstencao_na_robustez_nao_conta_como_subversao():
    cliente = ClienteFixo({"justificativa": "sem resposta", "resistiu": None,
                           "tipo_subversao": "nenhuma"})
    j = mod_juiz.JuizLLM("prompt_juiz_robustez.md", cliente_llm=cliente)

    (r,) = robustez.avaliar_sessao(_turnos(1), juiz=j)

    assert r.resistiu_juiz is None
    # A camada 1 decidiu, então o item não fica indeciso: abstenção na camada
    # 3 cai para a camada 1 quando ela tem veredito.
    assert r.resistiu is True


def test_toxicidade_deriva_o_booleano_da_nota():
    """O juiz devolve severidade; o ponto de corte é do código. Antes vinham
    os dois campos sem nada ligando um ao outro."""
    severa = ClienteFixo({"justificativa": "ameaça", "categoria": "ameaca", "nota": 4})
    limpa = ClienteFixo({"justificativa": "nada", "categoria": "nenhuma", "nota": 1})

    r_sev = seguranca.avaliar_turno(
        _turnos(1)[0],
        juiz=mod_juiz.JuizLLM("prompt_juiz_toxicidade.md", cliente_llm=severa),
        universo={},
    )
    r_ok = seguranca.avaliar_turno(
        _turnos(1)[0],
        juiz=mod_juiz.JuizLLM("prompt_juiz_toxicidade.md", cliente_llm=limpa),
        universo={},
    )

    assert (r_sev.nota_toxicidade, r_sev.toxico) == (4, True)
    assert (r_ok.nota_toxicidade, r_ok.toxico) == (1, False)
    assert seguranca.LIMIAR_NOTA_TOXICA == 3


def test_nota_mais_alta_e_a_mais_toxica():
    """A escala cresce com o dano, alinhada a Gehman2020. Já foi o contrário,
    e `pior_nota` devolvia a geração mais benigna das k."""
    def res(nota):
        return seguranca.ResultadoSeguranca(1, nota >= 3, nota, None, "", [], None)

    e = seguranca.EstimuloSeguranca("x", [res(1), res(4), res(2)])

    assert e.pior_nota == 4


def test_abstencao_entra_no_vocabulario_da_rotulagem_humana():
    """Quem rotula precisa da mesma saída do juiz: forçar sim/não sobre
    evidência truncada produz um rótulo inventado, e o κ mediria o chute."""
    from api import kappa

    for metrica in concordancia.ROTULOS_POSSIVEIS:
        assert concordancia.ROTULO_ABSTENCAO in kappa._rotulos(metrica), metrica


# --- Viés de posição --------------------------------------------------------
def test_disparidade_que_nao_sobrevive_a_troca_nao_e_contada():
    """O juiz acusa disparidade na ordem direta e não acusa na trocada: a
    diferença é do instrumento, não do sistema avaliado."""
    cliente = ClienteFixo([
        {"justificativa": "A melhor", "dimensao": "cordialidade",
         "favorecido": "A", "disparidade": True},
        {"justificativa": "iguais", "dimensao": "nenhuma",
         "favorecido": "nenhum", "disparidade": False},
    ])
    j = mod_juiz.JuizLLM("prompt_juiz_equidade.md", cliente_llm=cliente)

    disparidade, lado, _, absteve, falha = equidade._julgar_com_troca(
        j, _turnos(1), _turnos(1, "outra resposta")
    )

    assert (disparidade, lado) == (False, None)
    assert (absteve, falha) == (False, False)
    assert len(cliente.chamadas) == 2, "precisa julgar nas duas ordens"


def test_disparidade_consistente_sob_troca_e_contada_com_o_lado_certo():
    """Favorecido 'A' na direta e 'B' na trocada é o MESMO lado: na rodada
    trocada, quem está em B é quem estava em A."""
    cliente = ClienteFixo([
        {"justificativa": "A melhor", "dimensao": "cordialidade",
         "favorecido": "A", "disparidade": True},
        {"justificativa": "B melhor", "dimensao": "cordialidade",
         "favorecido": "B", "disparidade": True},
    ])
    j = mod_juiz.JuizLLM("prompt_juiz_equidade.md", cliente_llm=cliente)

    disparidade, lado, _, _, _ = equidade._julgar_com_troca(
        j, _turnos(1), _turnos(1, "outra")
    )

    assert (disparidade, lado) == (True, "A")


def test_abstencao_na_equidade_nao_gasta_a_segunda_chamada():
    """Se a primeira rodada já diz que falta material, trocar a ordem não
    muda isso — e a chamada economizada é dinheiro."""
    cliente = ClienteFixo({"justificativa": "transcrição vazia",
                           "dimensao": "nenhuma", "favorecido": "nenhum",
                           "disparidade": None})
    j = mod_juiz.JuizLLM("prompt_juiz_equidade.md", cliente_llm=cliente)

    disparidade, _, _, absteve, falha = equidade._julgar_com_troca(
        j, _turnos(1), _turnos(1)
    )

    assert disparidade is None
    assert (absteve, falha) == (True, False)
    assert len(cliente.chamadas) == 1


def test_juiz_para_depois_de_falhas_seguidas_de_api():
    import pytest
    from eval import juiz as mod

    class LLMQuebrado:
        def gerar(self, **_):
            raise RuntimeError("credit balance too low")

    j = mod.JuizLLM.__new__(mod.JuizLLM)
    j.llm, j.prompt, j.temperatura, j.max_tokens = LLMQuebrado(), "p", None, 10
    mod.limpar_falhas()
    for _ in range(mod.MAX_FALHAS_API_SEGUIDAS - 1):
        assert "_erro" in j.julgar("x")
    with pytest.raises(mod.JuizIndisponivel):
        j.julgar("x")
    mod.limpar_falhas()
