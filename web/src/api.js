/* Cliente HTTP da API em `api/main.py`.
   Caminhos relativos de proposito: o proxy do Vite (vite.config.js) resolve
   no desenvolvimento e o mesmo codigo funciona servido pelo backend. */

async function pedir(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: { 'Content-Type': 'application/json' },
    ...opcoes,
  })
  if (resposta.status === 204) return null
  const corpo = await resposta.json().catch(() => null)
  if (!resposta.ok) {
    // FastAPI devolve o motivo em `detail`. Propagar essa mensagem em vez de
    // um "erro 500" generico: quase todo erro aqui e acionavel pela usuaria
    // (chave de API faltando, sessao expirada, conversa ja encerrada).
    const detalhe = corpo?.detail || `Erro ${resposta.status}`
    const erro = new Error(typeof detalhe === 'string' ? detalhe : JSON.stringify(detalhe))
    erro.status = resposta.status
    throw erro
  }
  return corpo
}

export const api = {
  saude: () => pedir('/api/saude'),
  visaoGeral: () => pedir('/api/visao-geral'),
  massa: () => pedir('/api/massa'),

  catalogoModelos: (forcar = false) =>
    pedir(`/api/modelos${forcar ? '?forcar=true' : ''}`),

  abrirSessao: (corpo = {}) =>
    pedir('/api/sessoes', { method: 'POST', body: JSON.stringify(corpo) }),

  enviarMensagem: (sessaoId, texto) =>
    pedir(`/api/sessoes/${sessaoId}/mensagens`, {
      method: 'POST',
      body: JSON.stringify({ texto }),
    }),

  fecharSessao: (sessaoId) =>
    pedir(`/api/sessoes/${sessaoId}`, { method: 'DELETE' }),

  // `consulta` e a query string ja montada (ex.: '?busca=parcelamento').
  listarSessoes: (consulta = '') => pedir(`/api/sessoes${consulta}`),
  detalharSessao: (sessaoId) => pedir(`/api/sessoes/${sessaoId}`),

  listarEstimulos: (via = '', categoria = '') => {
    const p = new URLSearchParams()
    if (via) p.set('via', via)
    if (categoria) p.set('categoria', categoria)
    const q = p.toString()
    return pedir(`/api/estimulos${q ? `?${q}` : ''}`)
  },

  planejarBateria: (filtros) =>
    pedir('/api/bateria/plano', { method: 'POST', body: JSON.stringify(filtros) }),
  iniciarBateria: (filtros) =>
    pedir('/api/bateria', { method: 'POST', body: JSON.stringify(filtros) }),
  statusBateria: () => pedir('/api/bateria'),
  pararBateria: () => pedir('/api/bateria', { method: 'DELETE' }),

  planejarAvaliacao: (corpo) =>
    pedir('/api/avaliacao/plano', { method: 'POST', body: JSON.stringify(corpo) }),
  iniciarAvaliacao: (corpo) =>
    pedir('/api/avaliacao', { method: 'POST', body: JSON.stringify(corpo) }),
  statusAvaliacao: () => pedir('/api/avaliacao'),

  // Saidas de terminal das rodadas anteriores; `tipo` e 'bateria' ou 'avaliacao'.
  listarSaidas: (tipo) => pedir(`/api/saidas/${tipo}`),
  lerSaida: (tipo, arquivo) => pedir(`/api/saidas/${tipo}/${encodeURIComponent(arquivo)}`),

  limiares: () => pedir('/api/limiares'),
  salvarLimiares: (valores) =>
    pedir('/api/limiares', { method: 'PUT', body: JSON.stringify(valores) }),
  pararAvaliacao: () => pedir('/api/avaliacao', { method: 'DELETE' }),

  // Camada 4. `itensKappa` NAO devolve o veredito do juiz: ele nao chega ao
  // navegador, entao nao da para ver antes de rotular. So `resultadoKappa`
  // revela, depois de o rotulo humano estar gravado.
  listarAmostrasKappa: () => pedir('/api/kappa'),
  itensKappa: (nome, apenasPendentes = false) =>
    pedir(`/api/kappa/${encodeURIComponent(nome)}`
          + (apenasPendentes ? '?apenas_pendentes=true' : '')),
  rotularKappa: (nome, id, rotulo) =>
    pedir(`/api/kappa/${encodeURIComponent(nome)}/rotulos`, {
      method: 'POST',
      body: JSON.stringify({ id: String(id), rotulo }),
    }),
  resultadoKappa: (nome, contra = null) =>
    pedir(`/api/kappa/${encodeURIComponent(nome)}/resultado`
          + (contra ? `?contra=${encodeURIComponent(contra)}` : '')),
  listarJulgamentos: () => pedir('/api/julgamentos'),
  gerarAmostraKappa: (julgamentos, porMetrica = 20, outros = []) =>
    pedir('/api/kappa-amostras', {
      method: 'POST',
      body: JSON.stringify({ julgamentos, por_metrica: porMetrica, outros }),
    }),
  compararJuizes: (a, b) =>
    pedir(`/api/comparacao-juizes?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),

  listarExecucoes: (via = '') =>
    pedir(`/api/execucoes${via ? `?via=${encodeURIComponent(via)}` : ''}`),
  detalharExecucao: (nome) => pedir(`/api/execucoes/${encodeURIComponent(nome)}`),

  listarPrompts: () => pedir('/api/prompts'),
  detalharPrompt: (id) => pedir(`/api/prompts/${encodeURIComponent(id)}`),

  listarRelatorios: (categoria = '') =>
    pedir(`/api/relatorios${categoria ? `?categoria=${encodeURIComponent(categoria)}` : ''}`),
  detalharRelatorio: (nome) => pedir(`/api/relatorios/${encodeURIComponent(nome)}`),

  // `juizModelo` vazio deixa o backend usar o do .env. O modelo que julga
  // muda o resultado e o custo, entao escolher qual e parte da medicao.
  avaliarTom: (sessaoId, execucaoId = 0, juizModelo = '') =>
    pedir(`/api/sessoes/${sessaoId}/tom`, {
      method: 'POST',
      body: JSON.stringify({
        com_juiz: true, execucao_id: execucaoId, juiz_modelo: juizModelo || null,
      }),
    }),

  avaliarCategorias: (sessaoId, comJuiz, execucaoId = 0, juizModelo = '') =>
    pedir(`/api/sessoes/${sessaoId}/avaliacao`, {
      method: 'POST',
      body: JSON.stringify({
        com_juiz: comJuiz, execucao_id: execucaoId, juiz_modelo: juizModelo || null,
      }),
    }),
}
