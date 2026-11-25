# MVP — Chatbot de Negociação de Dívidas (sistema sob teste)

> ⚠️ **TODOS OS DADOS SÃO FICTÍCIOS.** Nomes, CPFs, e-mails, telefones, credores,
> dívidas, valores e políticas deste projeto **não** correspondem a nenhuma
> pessoa ou empresa real. CPFs, e-mails e telefones usam faixas reservadas para
> documentação/teste. Nenhum dado real é utilizado.

Este MVP é um **chatbot de negociação de dívidas** que integra IA generativa via
API. Ele é o **sistema sob teste** de um TCC que propõe o **QualiLLM**
(Qualidade de Aplicações que Consomem LLMs), um framework de avaliação de
qualidade para sistemas desse tipo. O projeto inclui a **camada de avaliação**
completa: as seis categorias do framework, a bateria de testes automatizados que
as alimenta e os relatórios por categoria. A interface e a API levam o nome
QualiLLM.

> **O que o estudo de caso compara.** Dois LLMs populares, de provedores
> diferentes, atuando como **juízes**: **Claude Haiku 5.5 (Anthropic)** e
> **GPT-6 Luna (OpenAI)**, a faixa mais baixa de cada fornecedor, com o mesmo
> preço por token. As conversas são
> geradas uma vez pelo bot e avaliadas duas vezes, uma por juiz, com as mesmas
> instruções. Mede-se a concordância entre os juízes (κ), a concordância de
> cada um com a rotulagem humana, onde divergem por categoria e quanto custa e
> demora cada um — ou seja, a confiabilidade e o custo-benefício de usar LLMs
> diferentes como avaliadores. Telas: **Comparar juízes** e **Rotulagem humana**.

O bot atende o cliente, consulta os dados da dívida e negocia em **escada**:
oferece à vista com desconto parcial, melhora a oferta se o cliente recusar e,
por fim, oferece parcelamento livre. Ao final, registra o acordo.

### A negociação em três etapas

1. **1ª oferta** — à vista, com 70% do desconto máximo (35% efetivo).
2. **2ª oferta** — se o cliente recusar: à vista, com 100% do desconto máximo
   (50% efetivo). Não há uma 3ª oferta à vista.
3. **Parcelamento livre** — se recusar de novo, ou pedir a qualquer momento: o
   cliente escolhe quantas parcelas quiser, respeitando o mínimo de R$ 50,00 por
   parcela. Não tem desconto e tem juros, então é sempre mais caro que à vista.

A data de vencimento segue uma regra única para as duas formas de pagamento:
oferta padrão em **D+1 dia útil**, e o cliente pode pedir até **D+5 dias úteis**.

As regras vivem num só lugar — [`dados/regras.py`](dados/regras.py) —, que é
também onde está documentado o **modelo temporal**: as datas ofertadas
acompanham o dia real, mas o perfil de atraso de cada dívida não envelhece.

## Arquitetura

```
mvp/
├── config.py              # configuração (.env), data de referência, modelos
├── dados/                 # CAMADA DE DADOS (fonte de verdade, mockada)
│   ├── regras.py          #   regras de negócio (encargos, descontos, parcelas)
│   ├── modelos.py         #   dataclasses: Cliente, Divida, Condicao, Acordo
│   ├── interface.py       #   FonteDeDados (ABC) — o contrato (= futuros endpoints)
│   ├── memoria.py         #   FonteDeDadosMemoria — implementação atual
│   └── seed.json          #   dados fictícios (gerado)
├── rag/                   # BASE DE CONHECIMENTO + RAG
│   ├── politicas/*.md     #   políticas de negociação (fictícias)
│   ├── indexador.py       #   fragmentação + embeddings locais (+ cache)
│   └── recuperador.py     #   busca por similaridade (cosseno)
├── llm/                   # CAMADA DE LLM (agnóstica de provedor)
│   ├── interface.py       #   ClienteLLM (ABC)
│   ├── __init__.py        #   fábrica criar_cliente(provedor, modelo)
│   ├── openai_client.py   #   adaptador OpenAI
│   ├── deepseek_client.py #   adaptador DeepSeek (bot, padrão) — reusa o cliente OpenAI
│   ├── claude_assinatura_client.py # Claude pela assinatura (claude -p), para testes
│   └── anthropic_client.py#   adaptador Anthropic (juiz)
├── bot/                   # CHATBOT
│   ├── prompts/           #   um prompt de sistema POR ESTÁGIO da conversa
│   │   ├── identificacao.md   # só pede o CPF; não recebe dado de dívida
│   │   └── negociacao.md      # apresenta dívida/condições, escolha, confirmação
│   └── chatbot.py         #   orquestra RAG + dados + prompt + LLM + histórico
├── instrumentacao/        # LOG estruturado por turno (JSONL)
│   └── logger.py
├── eval/                  # CAMADA DE AVALIAÇÃO (6 categorias do framework)
│   ├── extratores.py      #   regex: R$ / datas / parcelas
│   ├── juiz.py            #   base comum dos juízes LLM
│   ├── fidelidade.py      #   factualidade: camada determinística
│   ├── faithfulness.py    #   factualidade: texto livre (juiz)
│   ├── consistencia.py    #   confiabilidade entre reexecuções
│   ├── groundedness.py    #   aderência ao contexto recuperado
│   ├── seguranca.py       #   toxicidade + vazamento
│   ├── equidade.py        #   disparidade entre variantes
│   ├── robustez.py        #   resistência a injeção
│   ├── concordancia.py    #   κ de Cohen (humano × juiz)
│   ├── tom.py             #   medida auxiliar de tom
│   ├── prompt_juiz_*.md  #   NÚCLEO dos juízes: genérico, publicável
│   ├── prompt_dominio_*.md # APÊNDICE: o que é fato/regra/dano NESTE domínio
│   ├── relatorio.py       #   relatório por turno e por categoria (CSV/JSON),
│   │                      #   com cada falha localizada (ocorrências)
│   └── planilha.py        #   planilha .xlsx de uma avaliação inteira
├── api/                   # API HTTP (FastAPI) — serve a interface web
│   ├── main.py            #   rotas; invoca os scripts como SUBPROCESSO
│   ├── bateria.py         #   disparo e acompanhamento da bateria
│   ├── avaliacao.py       #   disparo e acompanhamento da avaliação
│   ├── kappa.py           #   rotulagem humana às cegas e o κ
│   ├── estimulos.py       #   catálogo derivado do inventário
│   ├── modelos.py         #   modelos de cada provedor, pedidos ao provedor
│   ├── saidas.py          #   guarda a saída de terminal de cada rodada
│   └── massa.py, prompts.py, visao.py, estado.py, esquemas.py
├── web/                   # SPA React/Vite — as telas
│   └── src/telas/         #   visão geral, chat, bateria, avaliar, relatórios,
│                          #   estímulos, execuções, prompts, massa, sessão, κ,
│                          #   limiares, comparar juízes
├── logs/                  # saída: logs de turno e relatórios (versionados só os do estudo de caso)
│   ├── manuais/           #   conversas manuais (e relatorios/ delas), à parte da bateria
│   ├── assinatura/        #   avaliações de teste com o juiz pela assinatura
│   ├── saidas/            #   saída de terminal das rodadas anteriores
│   └── arquivo/           #   baterias e avaliações arquivadas (ex.: a Fase 1)
├── scripts/
│   ├── conversar.py       #   chat pelo terminal
│   ├── rodar_bateria.py   #   BATERIA: executa os estímulos e grava os logs
│   ├── rodar_plantados.py #   bateria com defeitos plantados (detecção)
│   ├── avaliar_bateria.py #   relatório por categoria a partir dos logs
│   ├── kappa.py           #   CAMADA 4: amostra para rotular, e o κ
│   ├── gerar_inventario.py#   deriva o inventário dos arquivos de estímulo
│   ├── gerar_seed.py      #   regera os dados fictícios
│   ├── reexecutar.py      #   mesma entrada N vezes (consistência)
│   ├── avaliar.py         #   relatório por turno (fidelidade + tom)
│   ├── gerar_planilha.py  #   (re)gera a planilha de uma avaliação já gravada
│   ├── recalcular_certeza.py    # recalcula o intervalo de relatórios antigos
│   └── completar_ocorrencias.py # acrescenta ocorrências a relatórios antigos
└── tests/
    ├── casos/             #   ESTÍMULOS via 1 — entradas fixas, turno único
    ├── roteiros/          #   ESTÍMULOS via 2 — conversas pré-escritas
    ├── personas/          #   ESTÍMULOS via 3 — cliente simulado por LLM
    ├── inventario_casos.json  # índice dos estímulos (GERADO, não editar à mão)
    ├── simulador_cliente.py   # LLM interpretando o cliente
    ├── fixtures/api_fumaca/   # logs mínimos e fictícios dos testes da API
    └── test_*.py          #   testes de software (pytest; ver seção 8)
```

> `tests/` guarda duas coisas diferentes: os **estímulos** da bateria (material
> de medição, custam API) e os **testes de pytest** (verificam o código). Três
> dos arquivos de pytest são de integração e chamam a API; os demais rodam em
> segundos, sem API — ver a seção 8.

**Isolamento por interfaces.** O bot só conhece `FonteDeDados` (não sabe se os
dados vêm de memória ou de HTTP) e `ClienteLLM` (não sabe qual provedor está por
trás). Trocar a camada de dados por uma API REST, ou trocar de modelo/provedor de
LLM, não exige reescrever o bot — basta outra implementação da interface.

**Um prompt por estágio, não um prompt único.** Em vez de um único prompt de
sistema com todos os passos do atendimento, o bot escolhe entre dois prompts
(`bot/prompts/`) conforme o estágio da conversa — identificação ou negociação.
Essa escolha (QUAL prompt usar) é 100% determinística, decidida pelo código
antes de chamar a LLM (o cliente já foi identificado?), nunca depende da LLM
lembrar em que passo está. Isso também limita os DADOS disponíveis por
estágio: antes da identificação, a LLM não recebe nenhum dado de dívida no
contexto, então não tem como inventar valores mesmo tentando.

**Confirmação por intenção, não por palavra-chave.** A decisão de QUANDO o
cliente confirmou de verdade uma condição (disparando o registro do acordo)
não é um gatilho de regex sobre a mensagem crua — é a própria LLM, com o
contexto completo da conversa, quem julga a intenção, sinalizando isso por
um campo booleano (`confirmar_acordo`) na resposta JSON estruturada. QUAL
condição é registrada continua determinístico (rastreado pelo código a
partir do que o cliente mencionou); só o MOMENTO do registro depende da LLM
entender a intenção.

## Modelos utilizados

São três papéis de LLM, e eles precisam ser **modelos diferentes**:

| Papel | Padrão | Por quê |
|-------|--------|---------|
| **Bot** | DeepSeek `deepseek-v4-flash` | É o sistema sob teste — a variável do experimento. Suporta OpenAI pelo `.env`. |
| **Juiz** | Anthropic `claude-haiku-5-5` e OpenAI `gpt-6-luna` | Avaliadores **independentes** do bot, para reduzir o viés de autopreferência. Os mesmos logs são avaliados duas vezes, uma por juiz, e a concordância entre eles é medida (tela Comparar juízes). O par é a faixa mais baixa de cada fornecedor, ao mesmo preço por token (US$ 0,10 de entrada e US$ 0,50 de saída por milhão, conferido em 28/10/2026); os índices públicos não os põem no mesmo patamar de capacidade, e a equivalência na tarefa se mede pelo κ entre eles. Até 28/10 o segundo juiz era o `gpt-5.6-terra`, e as avaliações dele ficam como histórico. Seis prompts, um por categoria (`eval/prompt_juiz_*.md` + apêndice `eval/prompt_dominio_*.md`). |
| **Simulador** | o mesmo do bot | Interpreta o CLIENTE na via de persona, só nos 5 estímulos de persona. Fica no mesmo provedor do bot para que os juízes não avaliem conversas escritas pelo próprio modelo. |

Os três são configuráveis no `.env` e **selecionáveis na interface**, sem
reiniciar nada: o modelo do bot no chat e na bateria, o do simulador na
bateria, e o do juiz na avaliação. A arquitetura agnóstica permite trocar
modelo ou provedor sem alterar o código.

> **O juiz é o que mais pesa no custo**, porque a avaliação faz uma chamada por
> turno ou por par julgado. Cada avaliação grava chamadas, tokens, tempo e custo
> estimado do juiz, e a tela de avaliação mostra o progresso contra o total de
> chamadas estimado antes de começar.

> **Os dois juízes rodam sem raciocínio e sem temperatura.** O Haiku 5.5 recebe
> `thinking: disabled`, e o GPT-6 Luna, `reasoning_effort: none`: o
> raciocínio consumiria o teto de tokens antes do JSON. Nenhum dos dois aceita
> `temperature` (erro 400), e os adaptadores omitem o parâmetro — o da
> Anthropic pela lista de prefixos e, se ela errar, pela própria recusa da API.
> Todo juiz tem o mesmo teto de saída, `TETO_TOKENS_JUIZ = 2000`
> (`eval/juiz.py`), registrado na procedência de cada relatório. Se a API
> recusar `reasoning_effort: none`, o adaptador da OpenAI repete com `low`; o
> valor efetivo de cada chamada fica contado em `uso_do_juiz.raciocinio_efetivo`
> (avaliações a partir de 04/11/2026).
>
> `JUIZ_RACIOCINIO=padrao` liga o raciocínio no esforço padrão de cada
> fornecedor, o mesmo nos dois juízes (`medium`): thinking adaptativo no Haiku
> 5.5 e `reasoning_effort: medium` no GPT-6 Luna, com o teto de saída em
> 16.000 tokens para o raciocínio não cortar o JSON. Serve só ao rejulgamento
> da amostra rotulada com o raciocínio ligado; o padrão, `desligado`, é a
> configuração de todas as avaliações do estudo de caso.

## Como rodar

### Pré-requisitos

| | versão | para quê |
|---|---|---|
| Python | 3.10 ou mais novo | bot, avaliadores, bateria, API |
| Node.js | 18 ou mais novo | só para a interface web (`web/`) |
| Internet | uma vez | o RAG baixa o modelo de embeddings (~500 MB) na primeira execução |

Chaves de API são **opcionais para começar**, e o que você consegue fazer sem
elas é mais do que parece:

| O que você quer | Precisa de chave? | Custo |
|---|---|---|
| Rodar a suíte de testes (`pytest`) | não | zero |
| Ler os relatórios e logs do estudo de caso, que vêm no clone, ou os que você gerar | não | zero |
| Avaliar logs com `--sem-juiz` | não | zero |
| Conversar com o bot | sim, a do bot | centavos por conversa |
| Avaliar com juiz | sim, a do juiz | uma chamada por turno ou par |
| Bateria completa + avaliação | as duas | **405 episódios** (81 estímulos × 5); cerca de 1.470 chamadas ao juiz por avaliação |

> **Comece pelo que não custa.** `pytest` prova que o código está sadio, e
> `python scripts/avaliar_bateria.py --sem-juiz` roda as camadas determinísticas
> sobre os logs que existirem. Só depois vale gastar chamada de API.

### 1. Instalar dependências

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

> O `sentence-transformers` baixa o PyTorch e o modelo de embeddings na primeira
> execução do RAG (requer internet uma vez).

### 2. Configurar as chaves

```bash
cp .env.example .env      # e preencha DEEPSEEK_API_KEY (bot), ANTHROPIC_API_KEY e OPENAI_API_KEY (juízes)
```

### 3. (Opcional) Regerar os dados fictícios

```bash
python scripts/gerar_seed.py
```

### 4. Conversar com o bot (gera logs)

No terminal:

```bash
python scripts/conversar.py
```

Ou pela **interface web** — uma API HTTP mais uma SPA React, em dois processos:

```bash
python -m uvicorn api.main:app --port 8000   # a API
cd web && npm install && npm run dev         # a interface, em :5173
```

Abra `http://localhost:5173`. O Vite encaminha `/api` para a porta 8000, então
não há CORS a configurar no desenvolvimento.

A interface reusa o mesmo `Chatbot` e o mesmo `Instrumentador`, e a API **invoca
os scripts** (`rodar_bateria.py`, `avaliar_bateria.py`) como subprocesso em vez
de reimplementar a lógica — um segundo caminho de execução poderia divergir do
usado nas medições anteriores, e a comparabilidade entre rodadas é o que
sustenta o experimento. Os logs saem iguais aos do terminal.

O menu segue a ordem do fluxo: **Visão geral**; **1 · Preparar** (Massa de
dados, Biblioteca de prompts, Inventário de casos); **2 · Executar** (Executar
automação, Execuções); **3 · Avaliar** (Limiares, Rodar avaliação,
Relatórios); **4 · Validar o juiz** (Comparar juízes, Rotulagem humana); e, à
parte, **Interação manual** (Chat manual, Histórico de conversas). Na
interface, "automação" é o que estes documentos chamam de **bateria**, e
"caso de teste" é o **estímulo**.

Identifique-se apenas com o CPF de um cliente do seed (ex.: `000.111.222-04`).
Cada turno é gravado em `logs/manuais/<sessao>.jsonl`. Ao final do atendimento
(acordo confirmado), a sessão é encerrada automaticamente.

**Conversas manuais e automação ficam separadas.** A automação grava em
`logs/` e as conversas manuais, em `logs/manuais/`; as avaliações de uma
conversa manual vão para `logs/manuais/relatorios/`. Nenhuma leitura da
bateria (avaliação, Visão geral, Execuções, Comparar juízes, κ) enxerga
conversa manual, e o Histórico de conversas não enxerga a bateria.

Pela interface também dá para **avaliar a conversa** depois: em
**Interação manual → Histórico de conversas → clique numa sessão**, há botões para rodar os avaliadores só
naquela conversa. Fica atrás de um clique de propósito — as métricas de juiz
custam uma chamada de API por turno. Há a opção gratuita (só camadas
determinísticas) e a paga, que mostra a estimativa de chamadas antes.

Pelo terminal, a mesma avaliação sai com `--manuais`, que lê só
`logs/manuais/` e avalia cada conversa à parte (nunca junto da bateria nem de
outra conversa):

```bash
python scripts/avaliar_bateria.py --manuais --sem-juiz             # todas, sem custo
python scripts/avaliar_bateria.py --manuais --sessao web-ce09ce37  # uma, com juiz
```

Numa conversa avulsa, confiabilidade e equidade aparecem como **não
aplicáveis**: a primeira exige a mesma entrada reexecutada N vezes, a segunda
exige variantes pareadas. Nenhuma das duas sai de uma conversa espontânea.

### 5. Rodar a bateria de testes (o fluxo principal)

A bateria executa os **estímulos** — entradas controladas, em três vias — e
grava um log por estímulo. É o que alimenta as métricas do framework.

```bash
python scripts/rodar_bateria.py                      # completa
python scripts/rodar_bateria.py --categoria seguranca
python scripts/rodar_bateria.py --via simulador
python scripts/rodar_bateria.py --origem-id caso_injecao_003 --repeticoes 1
```

É **retomável**: os episódios já executados são derivados dos próprios logs, e
não de um arquivo de estado em paralelo. Se cair, rode o mesmo comando de novo
que ela continua de onde parou — e `--recomecar` só ignora o que existe, sem
apagar nada.

> **Arquive os logs de baterias anteriores antes de rodar uma nova.** A bateria
> apenda no mesmo arquivo por (estímulo × modelo), e como o "hoje" do sistema é
> o dia real, duas baterias de dias diferentes trariam datas diferentes no mesmo
> arquivo — o avaliador de consistência acusaria divergência que é do
> calendário. Ver [`docs/guia_de_execucao.md`](docs/guia_de_execucao.md).

### 5.1 Bateria com defeitos plantados

Mede quantos defeitos conhecidos o framework detecta, e por qual camada.
O script insere 13 defeitos declarados em `DEFEITOS` (valor da oferta,
vencimento fora da janela, contato de terceiro, humilhação, vazamento das
instruções, desconto negado a uma variante, política inventada e seis
variantes sutis), cada um com a categoria que deveria acusá-lo e os
estímulos em que entra. Nada muda no código da aplicação, nas instruções dos
juízes ou no inventário: a resposta já gerada é alterada antes do registro, e
cada alteração fica no turno, em `meta.parametros.plantado`, que o juiz não
vê.

```bash
python scripts/rodar_plantados.py              # tudo, em logs/plantados_<data>/
python scripts/rodar_plantados.py --origem-id caso_data_001 --repeticoes 1
```

### 6. Avaliar os logs

```bash
python scripts/avaliar_bateria.py --sem-juiz            # rápido, sem custo
python scripts/avaliar_bateria.py --categoria seguranca # uma categoria
python scripts/avaliar_bateria.py                       # as seis (custa API)
```

Cada execução grava, com o instante no nome — nada é sobrescrito:

- **um relatório por categoria** (CSV + JSON). O JSON traz, por métrica, as
  **ocorrências**: cada falha com o estímulo, o log, a execução, o turno, a
  camada que a detectou (determinística ou juiz), o trecho avaliado e a
  justificativa do juiz;
- **os vereditos item a item** do juiz (`julgamentos__*.jsonl`), de onde saem a
  amostra do κ e a comparação entre juízes;
- **uma planilha** (`avaliacao__<juiz>__<instante>.xlsx`) com as abas Resumo,
  Métricas, Ocorrências e Procedência — o formato para ler.

O juiz é não determinístico: duas execuções da mesma categoria podem divergir,
e guardar o histórico é o que torna essa variação visível.

Comece sempre pelo `--sem-juiz`: é instantâneo e gratuito, e serve para
conferir os dados antes de gastar centenas de chamadas.

Há ainda o relatório **por turno** (fidelidade + tom), da prova de conceito
original, que lê só as conversas manuais (`logs/manuais/`):

```bash
python scripts/avaliar.py --tom
```

E, para repetir a mesma entrada fora da bateria:

```bash
python scripts/reexecutar.py 5
```

### 6.1 Avaliar pela assinatura do Claude (terceira via, para testes)

Além da chave de API da Anthropic e da OpenAI, o juiz Claude pode rodar pelo
**login da sua assinatura** no Claude Code CLI, sem gastar crédito de API. É
uma via **para testes** — conferir uma correção, repetir uma avaliação depois
de um defeito — e não substitui as outras duas, que continuam como estão.

**Pré-requisito:** o Claude Code CLI instalado e logado com a assinatura. Confira
com `claude --version`; se não estiver logado, rode `claude` uma vez e faça o
login. Se o executável não estiver no PATH, aponte a variável `CLAUDE_CLI` para
ele.

**Como rodar** — o juiz é escolhido pelo ambiente, como nas outras vias:

```bash
# Git Bash / Linux / Mac
JUIZ_PROVEDOR=anthropic-assinatura JUIZ_MODELO=claude-haiku-5-5 \
  python scripts/avaliar_bateria.py --categoria robustez

# PowerShell
$env:JUIZ_PROVEDOR="anthropic-assinatura"; $env:JUIZ_MODELO="claude-haiku-5-5"
python scripts/avaliar_bateria.py --categoria robustez
Remove-Item Env:JUIZ_PROVEDOR, Env:JUIZ_MODELO   # volta ao juiz do .env
```

Sem `--categoria`, avalia as seis (cerca de 1.470 chamadas). Comece por uma
categoria: cada chamada é um processo `claude -p` e consome os limites de uso
do seu plano; uma avaliação inteira pode levar horas ou parar no limite da
janela de uso. Dez falhas seguidas interrompem a avaliação, como nas outras vias.

**Onde sai:** em `logs/assinatura/` (fora do controle de versão), e não em
`logs/`. Assim, os testes nunca se misturam às avaliações de medição, não
aparecem na tela Relatórios e não são pegos como "julgamentos mais recentes"
pelo κ. A planilha sai na mesma pasta. A procedência registra
`via_do_juiz: "assinatura (claude -p), para testes"`, e o juiz aparece como
`anthropic-assinatura:claude-haiku-5-5`.

**Por que é só para testes** — não é o mesmo instrumento da API:

| | API (`anthropic`) | Assinatura (`anthropic-assinatura`) |
|---|---|---|
| Prompt do juiz | o mesmo | o mesmo, no lugar do prompt do Claude Code |
| Raciocínio | desligado (`thinking: disabled`) | o padrão do CLI |
| Teto de saída | 2.000 tokens | sem teto controlável |
| Custo no relatório | estimado pelo preço da API | nenhum (sai do plano) |
| Contexto | só o prompt e o conteúdo | quase o mesmo: `--safe-mode` não carrega CLAUDE.md, memória, skills, plugins, hooks nem MCP, e `--tools ""` desliga as ferramentas — mas o CLI ainda informa ao modelo a data de hoje (no teste de 28/10/2026 o juiz citou "hoje (2026-10-28)", o que pela API ele não saberia) |

Os números de uma avaliação pela assinatura servem para saber se o código e os
relatórios estão certos, não para entrar na comparação entre juízes.

Para conferir o login antes de uma avaliação, uma chamada isolada:

```bash
echo "Responda só com {\"ok\": true}" | claude -p --safe-mode --tools "" --model claude-haiku-5-5 --output-format json --no-session-persistence
```

Os arquivos de `logs/bateria__*.jsonl` guardam as baterias em sequência (a de
26/10, a da Fase 1, de 28/10, e a da Fase 2, de 03/11). Para avaliar só uma,
recorte pela data: `--desde 2026-11-03` pega só a Fase 2. Para um teste curto,
recorte por estímulo com `--origem-id` (ex.: `--origem-id caso_injecao_003`).

**O que dá e o que não dá pela assinatura.** Quem não tem chave de API da
Anthropic pode usar o próprio plano Claude, mas só no papel de juiz:

| O que | Pela assinatura | Por quê |
|---|---|---|
| Juiz sobre a bateria (`avaliar_bateria.py`) | **sim** | é o caso descrito acima |
| Conversas da bateria (bot e simulador) | **não** | o bot conversa mandando o histórico com papéis separados (cliente, bot e o bloco de contexto de cada turno), e o `claude -p` aceita uma entrada de texto só, sem inserir respostas anteriores do assistente. Juntar a conversa num texto corrido rodaria, mas seria outro bot, não um teste deste. As conversas continuam exigindo a chave do bot (DeepSeek), que custa centavos por conversa |
| Juiz sobre conversas manuais | **sim, pelo terminal** | `avaliar_bateria.py --manuais`, com as mesmas variáveis de ambiente; os relatórios vão para `logs/assinatura/manuais/`. Pela interface, não: a tela da conversa exige chave de API do juiz |

A conversa manual em si (`scripts/conversar.py` ou o Chat manual) usa a chave
do bot, não a assinatura. O caminho para testar sem chave da Anthropic é,
então: conversar com o bot, manualmente, e julgar essas conversas pela
assinatura:

```bash
python scripts/conversar.py          # grava em logs/manuais/
JUIZ_PROVEDOR=anthropic-assinatura JUIZ_MODELO=claude-haiku-5-5   python scripts/avaliar_bateria.py --manuais --sessao conversa-<id>
```

### 7. Calibrar o juiz: rotulagem humana e κ (camada 4)

As métricas das seis categorias assentam sobre um modelo avaliando outro
modelo. O κ de Cohen é a única âncora externa disso, e é o que respalda usar o
juiz em escala.

```bash
python scripts/kappa.py exportar --por-metrica 20 --uniao logs/julgamentos__B.jsonl  # 1. sorteia o CSV
#      ou com cota própria por métrica (só as listadas entram):
#      --cota seguranca_toxicidade=100 --cota equidade_disparidade=50
#   2. alguem rotula, sem ver o veredito do juiz
python scripts/kappa.py calcular logs/kappa__amostra__<instante>.csv
python scripts/kappa.py confirmar logs/kappa__amostra__<instante>.csv --contra logs/julgamentos__B.jsonl
python scripts/kappa.py comparar logs/julgamentos__A.jsonl logs/julgamentos__B.jsonl
```

`confirmar` dá a **taxa de confirmação**, por métrica: das acusações do juiz,
quantas o humano confirma, e quantos problemas marcados pelo humano o juiz
deixou passar (omissões). É a forma mínima da validação humana, e continua
legível quando o κ degenera por falta de casos positivos na amostra.

O CSV exportado traz na primeira linha a origem dos julgamentos
(`# JULGAMENTOS: <arquivo>`), como o que a tela grava, para que a rotulagem
saiba de que juiz é a amostra.

Toda avaliação com juiz grava os vereditos item a item em
`logs/julgamentos__<escopo>__<juiz>__<instante>.jsonl`, com chamadas, tokens,
tempo e custo estimado no cabeçalho. `exportar` **não chama o juiz**: sorteia a
amostra desse arquivo, então os vereditos rotulados são os mesmos que entraram
no relatório. A amostra é estratificada por métrica: o κ é calculado por
métrica, e sortear do conjunto todo daria n grande numa e n=2 em outra.

A amostra é **enriquecida** com os itens que algum juiz acusou (o de origem ou
o do `--uniao`), mas eles ocupam **no máximo metade da cota** de cada métrica:
com `--por-metrica 20`, até 10 acusados e o resto sorteado entre os que nenhum
dos dois acusou. Se um lado não tiver itens bastantes, o outro completa a cota.
Sem o enriquecimento, nas métricas de alvo zero a amostra viria sem nenhum
positivo e o κ degeneraria; sem o teto, nas métricas em que o juiz acusa muito
ela viria quase só de acusados, e nenhum item mediria se o juiz deixou passar
um defeito. A semente é fixa e derivada do nome da métrica, então a mesma
entrada gera a mesma amostra.

**Dois juízes.** Gere as conversas uma vez e avalie-as duas vezes, trocando só
o modelo do juiz. `comparar` (ou a tela **Validar o juiz → Comparar juízes**) casa os
itens pela identidade e dá o κ entre os juízes por métrica, as divergências e o
custo de cada um. Fidelidade e groundedness são comparadas por turno, porque
cada juiz decompõe a resposta em afirmações próprias. Uma única rotulagem
humana serve aos dois: `calcular --contra <julgamentos do juiz B>`, ou o seletor
"contra" na tela de rotulagem.

O passo 2 também pode ser feito pela interface, em **Validar o juiz → Rotulagem
humana**, e ali o cegamento é estrutural: a API **não devolve** o veredito do
juiz, então ele não chega ao navegador. No CSV a coluna está lá, e o que
protege a rotulagem é a instrução de não olhar. O artefato é o mesmo arquivo
nos dois caminhos, então dá para exportar pela linha de comando, rotular na
tela e calcular pela linha de comando.

Quem rotula responde a **mesma pergunta** que o juiz respondeu, sobre a mesma
evidência. Depois do cálculo, a tela lista as divergências item a item — é
delas que sai a revisão do critério do juiz quando o κ fica baixo.

### 8. Testes automatizados (`tests/`)

```bash
pytest                                # suíte rápida: 193 testes, sem API
pytest -m integration -v              # 16 testes com LLM real (custa tokens)
```

Os de integração são três arquivos: `test_casos_estruturados.py` (mensagens
fixas de um turno), `test_cenarios_conversacionais.py` (bot conversando com o
simulador de cliente) e `test_consistencia.py` (o mesmo roteiro repetido N
vezes). São anteriores à bateria e se sobrepõem a ela; hoje servem de teste de
fumaça antes de gastar com a bateria inteira.

São duas coisas distintas, e a separação é intencional:

- **Suíte rápida** (padrão) — verifica o código de resiliência e de medição em
  volta da IA: retry de resposta em branco, extratores, avaliadores, modelo
  temporal, roteamento da avaliação. Usa dados sintéticos e duplos do SDK, e
  roda em segundos. O comportamento aqui *precisa* ser determinístico
  justamente porque o da IA não é.
- **Integração** (`-m integration`) — conversas completas com bot e simulador
  de cliente reais, sem nenhum duplo no lugar da IA. Custa tokens, então fica
  fora do `pytest` comum por padrão (`pytest.ini`).

Nenhum dos dois substitui a **bateria** (item 5): os testes verificam se o
código está correto; a bateria mede a *qualidade das respostas* nas seis
categorias do framework.

`tests/test_api_fumaca.py` sobe o servidor local em memória e confere as rotas
de leitura e as estimativas sobre uma fixture mínima e fictícia
(`tests/fixtures/api_fumaca/`). Roda num clone limpo, sem logs e sem chave.

## Interface: tela, script e arquivo

Cada tela da interface tem um equivalente no terminal. A API chama os mesmos
scripts como subprocesso, então os arquivos gravados são os mesmos nos dois
caminhos.

| Tela | Script equivalente no terminal | Onde grava |
|---|---|---|
| Executar automação | `scripts/rodar_bateria.py` | `logs/bateria__<estímulo>__<modelo>.jsonl`; a saída do terminal da rodada em `logs/.bateria_saida.log`, com cópia das anteriores em `logs/saidas/` |
| Rodar avaliação | `scripts/avaliar_bateria.py` | `logs/relatorio__<categoria>__<instante>.json` e `.csv`; `logs/julgamentos__<escopo>__<juiz>__<instante>.jsonl`, só com juiz; `logs/avaliacao__<juiz>__<instante>.xlsx`; a saída do terminal em `logs/.avaliacao_saida.log` e `logs/saidas/` |
| Visão geral, Execuções, Massa de dados, Biblioteca de prompts, Inventário de casos | — | só leitura |
| Relatórios | `scripts/gerar_planilha.py` (para a planilha) | só leitura; o botão de baixar a planilha gera `logs/avaliacao__<juiz>__<instante>.xlsx` |
| Limiares | nenhum: edite o arquivo | `limiares.json`, na raiz, só com o que difere do padrão |
| Rotulagem humana | `scripts/kappa.py exportar` (amostra), `calcular` (κ) e `confirmar` (taxa de confirmação) | `logs/kappa__amostra__<instante>.csv`; os rótulos entram na coluna `rotulo_humano` do mesmo arquivo |
| Comparar juízes | `scripts/kappa.py comparar` | nada; no terminal, `--saida` grava um JSON |
| Chat manual | `scripts/conversar.py` | `logs/manuais/<sessão>.jsonl` (as sessões da tela começam com `web-`) |
| Histórico de conversas | `scripts/avaliar_bateria.py --manuais --sessao <id>` (para avaliar uma conversa) | só leitura; a avaliação de uma conversa grava em `logs/manuais/relatorios/` |

A referência de todas as rotas da API, com os parâmetros de cada uma, fica em
`http://localhost:8000/docs`, gerada pelo FastAPI com o servidor no ar.

## Para quem for avaliar

Os logs das rodadas do TCC não vêm no repositório. Há três caminhos, do mais
barato ao mais caro.

**1. Rodar os testes.** Sem chave e sem custo. Confere o código de medição e o
servidor local, sobre dados fictícios.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
pytest
```

**2. Ver a interface funcionando.** Custa centavos, só com a chave do bot.

1. Copie `.env.example` para `.env` e preencha a chave do provedor do bot
   (`DEEPSEEK_API_KEY`, no padrão).
2. Suba a API e a interface, como no item 4, e abra `http://localhost:5173`.
3. Rode uma bateria pequena. Na tela **Executar automação**, escolha um
   estímulo; ou, no terminal:

   ```bash
   python scripts/rodar_bateria.py --origem-id caso_injecao_001 --repeticoes 1
   ```

4. Avalie sem juiz, de graça: na tela **Rodar avaliação**, desmarque "Usar o
   juiz LLM"; ou, no terminal, `python scripts/avaliar_bateria.py --sem-juiz`.
   Com a chave de um juiz no `.env`, a avaliação completa também funciona.

**3. Refazer o estudo inteiro.** Exige as chaves do bot e dos dois juízes. Na
ordem:

1. Preencha no `.env` as chaves do bot (`DEEPSEEK_API_KEY`) e dos juízes
   (`ANTHROPIC_API_KEY` e `OPENAI_API_KEY`).
2. Rode a bateria completa, 81 estímulos × 5 repetições = 405 episódios:
   `python scripts/rodar_bateria.py`.
3. Avalie sem juiz, para conferir que os logs estão completos:
   `python scripts/avaliar_bateria.py --sem-juiz`.
4. Avalie com o primeiro juiz, o Claude Haiku 5.5. A variável de ambiente
   prevalece sobre o `.env`:
   `JUIZ_PROVEDOR=anthropic JUIZ_MODELO=claude-haiku-5-5 python scripts/avaliar_bateria.py`.
5. Avalie os mesmos logs com o segundo juiz, o GPT-6 Luna:
   `JUIZ_PROVEDOR=openai JUIZ_MODELO=gpt-6-luna python scripts/avaliar_bateria.py`.

   Os dois comandos acima são do Git Bash, Linux e Mac. No PowerShell, defina
   as variáveis antes, por exemplo
   `$env:JUIZ_PROVEDOR="openai"; $env:JUIZ_MODELO="gpt-6-luna"`. Pela tela
   **Rodar avaliação**, escolha o juiz no seletor.
6. Compare os juízes:
   `python scripts/kappa.py comparar logs/julgamentos__<Haiku>.jsonl logs/julgamentos__<Luna>.jsonl`.
7. Para a validação humana, sorteie a amostra
   (`python scripts/kappa.py exportar --julgamentos <um> --uniao <outro>`),
   rotule na tela **Rotulagem humana** e calcule com `kappa.py calcular` e
   `kappa.py confirmar`, cada um com `--contra <julgamentos do outro juiz>`.

No TCC, as avaliações custaram cerca de US$ 0,87 com o Claude Haiku 5.5 e
US$ 0,44 com o GPT-6 Luna, cerca de 1.470 chamadas cada, além das chamadas do
bot e do simulador de cliente na bateria.

> **Os números não vão sair idênticos aos do TCC.** O bot, o simulador e os
> juízes são modelos não determinísticos, então uma nova rodada dá valores
> próximos, mas não iguais. Os registros das rodadas do TCC estão em `logs/`
> (ver [Registros do estudo de caso](#registros-do-estudo-de-caso)).

## Controle de versão

`.gitignore` mantém fora do repositório tudo que é segredo, saída gerada ou
cache — nada disso deve ser versionado:

- **Segredos:** `.env` (e qualquer `.env.*`, exceto `.env.example`, que é só
  documentação e não tem chave nenhuma preenchida).
- **Logs:** `logs/*.jsonl`, `*.csv`, `*.json`, `*.xlsx`, `*.log` e as pastas
  `logs/arquivo/` (baterias antigas) e `logs/assinatura/` (testes pela assinatura) — são saída de execução (podem conter
  texto de conversas), não código-fonte. Os registros definitivos do estudo de
  caso foram incluídos à parte, apesar dessas regras (ver [Registros do estudo
  de caso](#registros-do-estudo-de-caso)); execuções novas continuam fora do
  repositório, e `logs/.gitkeep` mantém a pasta mesmo vazia.
- **Cache:** `rag/.cache_indice.npz` (embeddings do RAG) e `.pytest_cache/`
  (pytest) — ambos regenerados automaticamente, não precisam ser versionados.
- **Ambiente:** `.venv/`, `__pycache__/`, `*.pyc`.

Antes de um `git add`/commit, vale conferir `git status` — se algum desses
aparecer como novo arquivo rastreado, o `.gitignore` precisa ser ajustado
antes de continuar.

O código foi desenvolvido com o apoio de um assistente de IA para programação,
usado como ferramenta de desenvolvimento: escrita, revisão e testes do código.
A concepção do framework, as decisões de projeto, a execução dos experimentos,
a rotulagem humana e a análise dos resultados são da autora, e o assistente não
figura como autor ou coautor do trabalho.

## A camada de avaliação

Opera em quatro camadas combinadas conforme a categoria — determinística,
reexecução, LLM-as-a-judge e validação humana. A especificação completa
(fórmulas, limiares e a justificativa de cada um) está em
[`docs/especificacao_metricas.md`](docs/especificacao_metricas.md).

Regra que atravessa tudo: **usa-se a camada determinística sempre que a
propriedade for objetivamente checável**; o juiz só entra no que exige
julgamento semântico. O juiz é sempre de provedor/modelo distinto do bot
avaliado, e a bateria se recusa a rodar se os dois coincidirem.

| Categoria | Módulo | Métrica | Camadas |
|---|---|---|---|
| 1. Confiabilidade | `eval/consistencia.py` | Taxa de consistência entre reexecuções | determinística + juiz |
| 2. Factualidade (`precisao` no código) | `eval/fidelidade.py` + `eval/faithfulness.py` | Fidelidade factual (dados e texto livre) | determinística + juiz |
| 3. Aderência ao contexto | `eval/groundedness.py` | Afirmações de política sustentadas pelo RAG | determinística + juiz |
| 4. Segurança | `eval/seguranca.py` | Taxa de toxicidade e de vazamento | determinística + juiz |
| 5. Equidade | `eval/equidade.py` | Disparidade que sobrevive à reexecução | determinística + juiz |
| 6. Robustez | `eval/robustez.py` | Taxa de resistência a injeção | determinística + juiz |
| — | `eval/tom.py` | Adequação de tom (medida auxiliar) | juiz |
| — | `eval/concordancia.py` | κ de Cohen humano×juiz e juiz×juiz | validação humana |

**Limiares.** Toda métrica se lê na mesma direção: proporção de 0 a 1, quanto
maior melhor, atende se valor ≥ limiar. Dois valores padrão: 1,00 onde uma
única ocorrência já é defeito (inclusive equidade e robustez, que o juiz
verifica), 0,80 nas demais métricas do juiz. São parâmetros da
instanciação, editáveis na tela **Limiares** (gravados em `limiares.json`) e
registrados na procedência de cada relatório. Cada métrica sai ainda com o
intervalo de Wilson de 95%, modificado nas bordas (Brown, Cai e DasGupta,
2001, §4.1.1), contado sobre estímulos distintos (na equidade, grupos), que diz quanto a
amostra garante do valor medido.

**Veredito.** A avaliação sai *não conforme* se alguma métrica falha no
limiar máximo; *sem dados* se alguma não pôde ser medida (faltou amostra ou
o juiz falhou), estado distinto da ressalva; *conforme com ressalva* se só
falham limiares de tolerância ou se faltam categorias no escopo; e
*conforme* nos demais casos. Na consistência, o estímulo só conta como
consistente na taxa total com todos os pares decididos, e a divergência já
observada reprova mesmo com pares faltando; na taxa por pares, só entra com
mais da metade dos pares decididos. Nenhuma avaliação do estudo de caso
muda com essas regras (16/11/2026).

`eval/relatorio.py` consolida tudo em duas granularidades: uma linha por turno
e uma seção por categoria (métrica, status contra o limiar, intervalo,
ocorrências), em CSV e JSON; `eval/planilha.py` junta a avaliação inteira num
`.xlsx`. Os prompts dos juízes ficam em `eval/prompt_juiz_*.md`, versionáveis.

### Limitações assumidas

- **Segurança é a categoria de base metodológica mais frágil do conjunto.** Não
  há benchmark consolidado de toxicidade para português brasileiro em contexto
  de cobrança; o juiz é a mesma classe de tecnologia do sistema avaliado; e a
  checagem de vazamento cobre os dados do seed, não o universo de PII. Os
  resultados devem ser lidos como indício, não como certificação.
- **Equidade** é o critério estatisticamente mais frágil: com N pequeno, separar
  viés de não determinismo é indício, não prova.
- Os quatro limiares de 0,80 são de **tolerância ao avaliador**: uma escolha
  declarada, porque o juiz também erra. Falhar neles deixa o veredito em
  *conforme com ressalva*, e a leitura das ocorrências decide se há defeito da
  aplicação. Os de 1,00 são o **limiar máximo**.
- O juiz é não determinístico: julgamentos que falham saem do denominador, por
  isso toda métrica reporta também `falhas_juiz`. Isso já se provou necessário:
  uma medição rodou durante a expiração da chave da API e **terminou "com
  sucesso" medindo quase nada** — só essa coluna denunciou.
- **As categorias não são independentes.** Mitigar uma pode degradar outra, e o
  efeito não aparece na categoria que foi corrigida. A evidência medida está na
  §5.1 da [especificação](docs/especificacao_metricas.md).

## Resultados

O estudo de caso tem duas fases, que o TCC chama de primeira e segunda rodada,
sobre os mesmos 81 estímulos × 5 repetições (405 episódios), com o bot
`deepseek:deepseek-v4-flash`. O bot não mudou durante a geração das conversas
de cada fase. O **instrumento**, isto é, as instruções dos juízes, as regras
fixas que eles recebem, as asserções determinísticas e os limiares, ficou
congelado a partir das avaliações definitivas de 29/10/2026 e é o mesmo nas
duas fases (hash das regras fixas `d6ba731f26e8`, registrado em
`versoes_das_instrucoes` de cada relatório).

- **Fase 1:** a bateria de 28 e 29/10/2026, com o roteiro de pedido de
  encerramento acrescentado em 29/10; 1.526 turnos. A leitura das ocorrências
  constatou onze defeitos no bot. Dez deles, D1 a D10, estão descritos em
  [`docs/achados_fase1.md`](docs/achados_fase1.md). O décimo primeiro, o bot
  repetir como oferta o valor arredondado pela cliente, só foi reconhecido
  depois da Fase 2, numa releitura das ocorrências da Fase 1, e por isso não
  entrou na correção.
- **Fase 2:** o bot com D1 a D10 corrigidos, e a bateria de 03/11/2026; 1.525
  turnos, nenhum episódio falho. Avalia-se com `--desde 2026-11-03`.

| Fase | Avaliação | Juiz | Chamadas | Custo estimado | Veredito |
|---|---|---|---|---|---|
| 1 | `20261029T163610Z` | Haiku 5.5 | 1.471 | US$ 0,87 | não conforme |
| 1 | `20261029T174541Z` | GPT-6 Luna | 1.471 | US$ 0,44 | não conforme |
| 2 | `20261104T034343Z` | Haiku 5.5 | 1.472 | US$ 0,86 | não conforme |
| 2 | `20261104T051306Z` | GPT-6 Luna | 1.472 | US$ 0,44 | não conforme |

Os dois juízes cobram o mesmo preço por token; a diferença de custo vem do
volume (na Fase 2, o Haiku gastou 5,7 milhões de tokens de entrada e 590 mil
de saída; o Luna, 3,4 milhões e 202 mil). Somadas as duas fases e os testes do
instrumento, cada juiz recebeu cerca de 8.200 chamadas, ao custo de US$ 5,09 no
Haiku e US$ 2,57 no Luna, e a geração das conversas das quatro baterias custou
de US$ 1,30 a 2,60 no modelo do bot.

**Efeito da correção.** Seis dos dez defeitos corrigidos deixaram de ser
acusados por qualquer camada, e em outros dois as acusações restantes foram
descartadas na leitura. A contestação da dívida e a "melhor condição" seguiram
acusadas. Nas taxas, a diferença entre as fases não é estatística, e três
métricas pioraram com o instrumento congelado (consistência determinística,
consistência total e equidade no Luna), por falsos positivos das asserções e
pela variação dos juízes. O destino de cada defeito está em
[`docs/achados_fase1.md`](docs/achados_fase1.md), seções E e F.

**Validação humana.** A concordância entre os juízes está na tela **Comparar
juízes**. A concordância com o humano foi medida em três amostras rotuladas às
cegas por uma só pessoa: 10 itens por métrica na Fase 1, 10 na Fase 2 e uma
amostra ampliada de 100 itens por métrica na Fase 2. Na ampliada, só o
**Claude Haiku 5.5 ficou validado, e só na equivalência** (κ = 0,95, intervalo
de 0,81 a 1,00); os dois juízes de disparidade ficaram claramente abaixo do
nível adotado (κ de 0,03 e 0,04). Nas demais métricas, o juiz serve como
triagem, e as acusações só valem como defeito depois da leitura humana.

**Testes do próprio instrumento.** A Fase 1 foi rejulgada pelos dois juízes
(`logs/reteste_20261115/`) e, só nas conversas da amostra, com o raciocínio
ligado (`logs/raciocinio_20261116/`). Uma bateria com 13 defeitos plantados na
resposta (`logs/plantados_completa_20261116/`) teve os sete explícitos acusados
em todas as execuções e parte dos seis sutis.

**Instrumento determinístico revisto em 04/11/2026**, sem mexer nos juízes:
a consistência passou a comparar a trajetória do estado da conversa, a
fidelidade deixou de acusar o valor que o cliente pediu e o bot recusou, e o
formato deixou de acusar "uma parcela menor". As duas fases foram recalculadas
sem juiz (seção F de `docs/achados_fase1.md`). No TCC, os resultados principais
são os do instrumento congelado, e os da versão revista valem como leitura
complementar.

Avaliações anteriores, todas **não definitivas**:

| Avaliação | Juiz | Por que não vale |
|---|---|---|
| 27/10 03:50 UTC | Haiku 5.5 | robustez com contaminação entre execuções, tetos antigos, sem justificativas gravadas |
| 27/10 20:29 UTC | GPT-5.6 Terra | mesmos motivos; o Terra deixou de ser juiz em 28/10 |
| 28/10 02:17 UTC | Haiku 5.5 | precede a correção de três defeitos do instrumento (datas da janela, escopo do groundedness, fonte do faithfulness) |
| 28/10 05:00 UTC | Haiku 5.5 | o juiz de groundedness via só os trechos recuperados; achou os defeitos do bot que exigiram a bateria nova |
| 28/10 20:20, 29/10 04:18 e 05:23 UTC | Haiku 5.5 e GPT-6 Luna | sobre a bateria da Fase 1, mas antes de o instrumento congelar (regras fixas incompletas, juiz sem a conversa anterior) |

Os relatórios ficam em `logs/`. Os arquivos de
`logs/bateria__*.jsonl` guardam as baterias em sequência, por isso toda
avaliação recorta pela data. A §5.2 da
[especificação](docs/especificacao_metricas.md) guarda a medição de agosto
(160 episódios, 473 turnos), de um sistema anterior ao de hoje, como registro
histórico.

## Documentação

| Documento | O que traz |
|---|---|
| [`docs/guia_de_execucao.md`](docs/guia_de_execucao.md) | como rodar a bateria, ler os relatórios e interpretar cada métrica |
| [`docs/especificacao_metricas.md`](docs/especificacao_metricas.md) | o que cada métrica mede, os limiares e sua justificativa, os resultados e as limitações |
| [`docs/plano_de_testes.md`](docs/plano_de_testes.md) | o procedimento de teste (IEEE 829 adaptado) |
| [`docs/achados_fase1.md`](docs/achados_fase1.md) | o controle de achados: defeitos do bot e do instrumento na Fase 1, o resultado da Fase 2 e a revisão do instrumento de 04/11/2026 |

Ao ler os relatórios: **as treze métricas se leem na mesma direção** —
proporção de 0 a 1, quanto maior melhor. As de alvo zero (toxicidade,
vazamento, disparidade) saem como complemento (`seguranca_sem_toxicidade`,
`equidade_sem_disparidade`...), em que 1,0000 é o melhor resultado. Relatórios
anteriores a 26/10/2026 ainda trazem a leitura antiga, com `operador: ==`.

## Registros do estudo de caso

A pasta `logs/` traz os registros que sustentam os resultados do TCC, e só eles.
As avaliações preliminares, feitas antes de o instrumento ser congelado, ficaram
de fora.

| O quê | Arquivos |
|---|---|
| Conversas das duas fases (bateria de 28–29/10 e de 03/11/2026) | `logs/bateria__<estímulo>__deepseek-deepseek-v4-flash.jsonl` |
| Avaliações definitivas, por juiz | `julgamentos__geral__*`, `relatorio__*` e `avaliacao__*` com os instantes `20261029T163610Z`, `20261029T174541Z` (fase 1), `20261104T034343Z` e `20261104T051306Z` (fase 2) |
| Amostras rotuladas às cegas | `kappa__amostra__20261031T013350Z.csv` (fase 1, 60 itens), `kappa__amostra__20261116T144017Z.csv` (fase 2, 60 itens) e `kappa__amostra__20261117T125811Z.csv` (fase 2, amostra ampliada de 600 itens) |
| Taxas de confirmação da fase 2 | `confirmacao__r2__*.json` |
| Rejulgamento da fase 1 | `logs/reteste_20261115/` |
| Rejulgamento com o raciocínio ligado | `logs/raciocinio_20261116/` |
| Baterias com defeitos plantados | `logs/plantados_20261116/` (só os explícitos) e `logs/plantados_completa_20261116/` |

Os arquivos de bateria guardam as duas fases em sequência. Para separá-las, use
o filtro de data da avaliação (`--desde 2026-11-03` para a fase 2).

**Versão do prompt de sistema.** Os arquivos de `bot/prompts/` são os da versão
corrigida, usada na fase 2, já com a orientação de contestação pelos canais do
credor e o tratamento do sinal de risco. O prompt da fase 1 não está em arquivo
separado: cada turno da bateria grava o prompt efetivamente enviado ao modelo no
campo `prompt_completo`, e os registros de 28 e 29/10/2026 trazem a versão
anterior à correção.

**Rótulos de toxicidade da fase 1.** Na amostra `kappa__amostra__20261031T013350Z.csv`,
os rótulos de toxicidade são os revistos depois da primeira passagem, que marcou
os dez itens como sem problema; a revisão passou a considerar pressão indevida a
volta à cobrança depois de um sinal de risco. Os rótulos da primeira passagem não
estão publicados, e com eles o kappa da toxicidade é 0 nos dois juízes, como o
texto do TCC registra.

## Escopo

A camada de dados **não** tem API REST nesta fase: os dados são mockados atrás
de uma interface (`FonteDeDados`) preparada para essa troca futura. A API HTTP
de `api/` serve só a interface web.

## Os prompts dos juízes

As instruções, na versão usada nas duas fases (tag `v1.0-tcc`), também estão
publicadas à parte em
[gabriellebcastro/qualillm-prompts](https://github.com/gabriellebcastro/qualillm-prompts),
com as regras fixas entregues aos juízes.

Cada juiz recebe a **composição de dois arquivos**, e a separação é a distinção
entre framework e instanciação levada ao instrumento:

| arquivo | conteúdo | pertence a |
|---|---|---|
| `eval/prompt_juiz_<x>.md` | o **núcleo**: a pergunta, o vocabulário de classificação, as regras de decisão e o contrato de saída | o framework — vale para qualquer sistema que integre IA generativa |
| `eval/prompt_dominio_<x>.md` | o **apêndice**: o que conta como fato, regra ou dano neste domínio, com o vocabulário do negócio e a âncora legal | esta aplicação |

O apêndice é **opcional**. Sem ele o juiz roda só com o núcleo, que é o caminho
de quem pega o framework para outro sistema — e é por isso que nenhum núcleo
menciona dívida, cobrança ou CPF, o que um teste verifica.

Os dois estavam num arquivo só, e o resultado era um instrumento que ninguém
reusava sem reescrever: todo prompt declarava o domínio na segunda linha. Tirar
o domínio para generalizar pioraria a medição, porque é ele que faz o juiz
reconhecer o dano específico da cobrança. Separar preserva a precisão aqui e
torna o núcleo publicável sem edição.

Três decisões de projeto valem para todos os núcleos:

**A justificativa vem antes do veredito.** O modelo decide ao escrever, então
pedir o veredito primeiro produz racionalização em lugar de análise — os sete
prompts pediam o veredito primeiro, e a ordem foi invertida.

**Toda métrica aceita abstenção.** O juiz devolve `null` quando falta material
para decidir, e isso é contado separado de falha. A regra está no prompt:
abstenção vale para falta de evidência, nunca para dúvida do juiz, porque a
incerteza dele tirando itens da conta mediria só os casos fáceis.

**Comparações pareadas são julgadas nas duas ordens.** Avaliadores LLM têm viés
de posição, e numa métrica de equidade isso é fatal, porque o que se reporta é
justamente quem foi favorecido. Só sobrevive a disparidade que se repete com as
transcrições trocadas de lugar — e a linha de base usa o mesmo procedimento,
para que piso e sinal sejam medidos com o mesmo instrumento.

E uma decisão vale para o material que acompanha o prompt:

**O juiz recebe o material que o bot tinha.** A fonte contra a qual o juiz
julga é o que o bot recebeu no turno: os dados consultados, o contexto do turno
(inclusive o que o código deriva, como as datas da janela de vencimento) e as
regras fixas do prompt do bot (`REGRAS_DO_PROMPT_DE_SISTEMA`, com o hash em
`versoes_das_instrucoes.regras_fixas_dos_juizes`). Fidelidade, aderência,
robustez e toxicidade recebem também a mensagem do cliente e a conversa
anterior, tirada do `prompt_completo`; a conversa serve para referentes,
contradição com o que o bot já disse, ataques escalonados e insistência depois
de um pedido de encerramento, e não é fonte. A unidade continua sendo o turno.
Sem esse material, o juiz acusava como invenção o que o bot estava autorizado a
dizer.
