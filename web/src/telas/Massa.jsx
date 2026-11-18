import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'

const brl = (v) =>
  v == null ? '—' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

function dataBR(iso) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

function Oferta({ rotulo, o, destaque }) {
  if (!o) return null
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '120px 110px 1fr', gap: 10, fontSize: 13, padding: '3px 0' }}>
      <span style={{ color: 'var(--texto-fraco)' }}>{rotulo}</span>
      <span className="mono" style={{ fontWeight: destaque ? 700 : 400, color: destaque ? 'var(--acento)' : 'var(--texto)' }}>
        {brl(o.valor_total_com_desconto)}
      </span>
      <span style={{ color: 'var(--texto-fraco)', fontSize: 12 }}>
        {o.desconto_percentual > 0
          ? `${(o.desconto_percentual * 100).toFixed(0)}% de desconto`
          : `${o.num_parcelas}× de ${brl(o.valor_parcela)}`}
        {' · vence '}{dataBR(o.data_primeiro_vencimento)}
      </span>
    </div>
  )
}

function Divida({ d }) {
  return (
    <div style={{ borderTop: '1px solid var(--borda-suave)', padding: '12px 0' }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 8 }}>
        <span className="mono" style={{ fontSize: 13, fontWeight: 700 }}>{d.id}</span>
        <span style={{ fontSize: 13 }}>{d.credor}</span>
        <span className="chip" style={{ fontSize: 11, color: 'var(--texto-fraco)', borderColor: 'var(--borda)' }}>
          {d.status}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 13, marginBottom: 10 }}>
        <span><span style={{ color: 'var(--texto-fraco)' }}>Original: </span><span className="mono">{brl(d.valor_original)}</span></span>
        <span><span style={{ color: 'var(--texto-fraco)' }}>Atualizado: </span><span className="mono" style={{ fontWeight: 700 }}>{brl(d.valor_atualizado)}</span></span>
        <span><span style={{ color: 'var(--texto-fraco)' }}>Atraso: </span><span className="mono">{d.dias_atraso} dias</span></span>
        <span title="Derivada do dia atual menos os dias de atraso — nunca gravada">
          <span style={{ color: 'var(--texto-fraco)' }}>Venceu em: </span>
          <span className="mono">{dataBR(d.data_vencimento_original)}</span>
        </span>
        <span>
          <span style={{ color: 'var(--texto-fraco)' }}>Teto de parcelas: </span>
          <span className="mono">{d.max_parcelas}×</span>
        </span>
      </div>

      <div style={{ background: '#f6f7f9', border: '1px solid var(--borda-suave)', borderRadius: 2, padding: '10px 12px' }}>
        <div className="rotulo" style={{ marginBottom: 6 }}>O que o bot deve oferecer</div>
        <Oferta rotulo="1ª à vista" o={d.ofertas.primeira_a_vista} destaque />
        <Oferta rotulo="2ª à vista" o={d.ofertas.segunda_a_vista} />
        {d.ofertas.parcelamento_exemplos?.map((o) => (
          <Oferta key={o.num_parcelas} rotulo={`parcelado ${o.num_parcelas}×`} o={o} />
        ))}
      </div>
    </div>
  )
}

export default function Massa() {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [busca, setBusca] = useState('')

  useEffect(() => {
    api.massa().then(setDados).catch((e) => setErro(e.message))
  }, [])

  const termo = busca.trim().toLowerCase()
  const clientes = (dados?.clientes ?? []).filter((c) =>
    !termo ||
    c.nome.toLowerCase().includes(termo) ||
    c.cpf.includes(termo) ||
    c.dividas.some((d) => d.credor.toLowerCase().includes(termo)))

  return (
    <>
      <Cabecalho
        titulo="Massa de dados"
        legenda={dados ? `${dados.total_clientes} clientes · ${dados.total_dividas} dívidas · ${dados.arquivo}` : ''}
      >
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar por nome, CPF ou credor…"
          style={{
            width: 260, padding: '9px 12px', fontSize: 13, fontFamily: 'inherit',
            border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
          }}
        />
      </Cabecalho>

      <div style={{ padding: '20px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        <div className="aviso" style={{ marginBottom: 16, maxWidth: 900 }}>
          <strong>Dados 100% fictícios.</strong> Use um destes CPFs para se
          identificar no chat. As condições abaixo saem de{' '}
          <span className="mono">dados/regras.py</span> — o mesmo código que o bot
          usa —, então servem de gabarito: se o bot disser outro valor, ele errou.
        </div>

        {dados && (
          <div style={{ fontSize: 12, color: 'var(--texto-tenue)', marginBottom: 14 }}>
            Datas calculadas para hoje ({dataBR(dados.data_referencia)}). Elas mudam
            com o dia real; os dias de atraso, não — são o parâmetro do cenário.
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {clientes.map((c) => (
            <div key={c.id} className="painel" style={{ padding: '14px 18px' }}>
              <div style={{ display: 'flex', gap: 14, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 15, fontWeight: 700 }}>{c.nome}</span>
                <span
                  className="mono"
                  title="Clique para copiar"
                  onClick={() => navigator.clipboard?.writeText(c.cpf)}
                  style={{ fontSize: 14, color: 'var(--acento)', cursor: 'pointer' }}
                >
                  {c.cpf}
                </span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>{c.id}</span>
                <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>{c.email}</span>
              </div>

              {c.dividas.length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--texto-tenue)', marginTop: 8 }}>
                  Sem dívidas — serve para testar o caminho de cliente sem pendência.
                </div>
              ) : (
                c.dividas.map((d) => <Divida key={d.id} d={d} />)
              )}
            </div>
          ))}
          {dados && clientes.length === 0 && (
            <div style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>Nada encontrado.</div>
          )}
        </div>
      </div>
    </>
  )
}
