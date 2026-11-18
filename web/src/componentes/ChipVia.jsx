/* As tres vias de estimulo sao coisas bem diferentes, e o design pede que a
   interface deixe claro qual e qual. O caso do simulador e o mais importante:
   ali NENHUM lado da conversa e uma pessoa. */
export const VIAS = {
  reinjecao: {
    rotulo: 'reinjeção',
    icone: '⟲',
    descricao: 'entrada fixa, turno único, repetida N vezes',
    cor: '#3f6ea8',
    fundo: '#e8eef7',
    borda: '#c2d3e8',
  },
  roteiro: {
    rotulo: 'roteiro',
    icone: '☰',
    descricao: 'sequência fixa de mensagens, uma conversa pré-escrita',
    cor: '#6a5a9c',
    fundo: '#eeebf7',
    borda: '#d2cae8',
  },
  simulador: {
    rotulo: 'simulador',
    icone: '🎭',
    descricao: 'duas LLMs conversando: uma faz o cliente, a outra é o bot testado',
    cor: '#a06621',
    fundo: '#fdf1d8',
    borda: '#e8d5a8',
  },
}

export default function ChipVia({ via, comIcone = true }) {
  const v = VIAS[via]
  if (!v) return <span className="mono" style={{ fontSize: 12, color: 'var(--texto-tenue)' }}>{via || '—'}</span>
  return (
    <span
      className="chip"
      title={v.descricao}
      style={{ color: v.cor, background: v.fundo, borderColor: v.borda }}
    >
      {comIcone && `${v.icone} `}{v.rotulo}
    </span>
  )
}
