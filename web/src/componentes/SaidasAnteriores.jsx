import { useEffect, useState } from 'react'
import { api } from '../api.js'

const estiloPre = {
  margin: 0, padding: 12, background: '#f6f7f9', border: '1px solid var(--borda-suave)',
  borderRadius: 2, fontSize: 11.5, lineHeight: 1.5, maxHeight: 320,
  overflow: 'auto', whiteSpace: 'pre-wrap', color: 'var(--texto-suave)',
}

function quando(iso) {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

/* Saidas de terminal das rodadas anteriores, guardadas em logs/saidas/ antes
   de cada rodada nova. A rodada atual (ou a ultima) aparece no painel de
   andamento; aqui fica o historico, que antes era sobrescrito. */
export default function SaidasAnteriores({ tipo, atualizarCom }) {
  const [itens, setItens] = useState(null)
  const [aberto, setAberto] = useState(null)
  const [linhas, setLinhas] = useState([])
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')

  useEffect(() => {
    api.listarSaidas(tipo).then((d) => setItens(d.saidas)).catch(() => setItens([]))
  }, [tipo, atualizarCom])

  async function abrir(arquivo) {
    if (aberto === arquivo) { setAberto(null); return }
    setAberto(arquivo)
    setLinhas([])
    try {
      setLinhas((await api.lerSaida(tipo, arquivo)).linhas)
    } catch (e) {
      setLinhas([e.message])
    }
  }

  if (!itens?.length) return null

  // Filtro pela data local em que a rodada terminou (AAAA-MM-DD, como o input date).
  const dia = (iso) => new Date(iso).toLocaleDateString('sv-SE')
  const visiveis = itens.filter((i) =>
    (!de || dia(i.terminado_em) >= de) && (!ate || dia(i.terminado_em) <= ate))
  const entrada = {
    padding: '6px 8px', fontSize: 12, fontFamily: 'inherit',
    border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
  }

  return (
    <div className="painel" style={{ padding: '16px 18px', marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Rodadas anteriores</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: 'var(--texto-fraco)' }}>
          de <input type="date" style={entrada} value={de} onChange={(e) => setDe(e.target.value)} />
          até <input type="date" style={entrada} value={ate} onChange={(e) => setAte(e.target.value)} />
          {(de || ate) && <button className="botao" onClick={() => { setDe(''); setAte('') }}>limpar</button>}
        </div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--texto-fraco)', margin: '4px 0 12px' }}>
        Saída de terminal de cada rodada, guardada em <span className="mono">logs/saidas/</span>.
        Clique para abrir.
      </div>
      {visiveis.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--texto-tenue)' }}>Nenhuma rodada nesse período.</div>
      )}
      {visiveis.map((i) => (
        <div key={i.arquivo} style={{ borderTop: '1px solid var(--borda-suave)', padding: '8px 0' }}>
          <div
            onClick={() => abrir(i.arquivo)}
            style={{ cursor: 'pointer', display: 'flex', gap: 14, alignItems: 'baseline', flexWrap: 'wrap' }}
          >
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {aberto === i.arquivo ? '▾' : '▸'} terminou em {quando(i.terminado_em)}
            </span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>{i.arquivo}</span>
          </div>
          {aberto !== i.arquivo && i.fim.length > 0 && (
            <div className="mono" style={{ fontSize: 11, color: 'var(--texto-fraco)', marginTop: 4, whiteSpace: 'pre-wrap' }}>
              {i.fim.slice(-3).join('\n')}
            </div>
          )}
          {aberto === i.arquivo && (
            <pre className="mono" style={{ ...estiloPre, marginTop: 8 }}>{linhas.join('\n') || 'Carregando…'}</pre>
          )}
        </div>
      ))}
    </div>
  )
}
