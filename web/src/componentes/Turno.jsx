import { useState } from 'react'

/* Um turno de conversa com os dados brutos de instrumentacao ao lado.
   Usado tanto no detalhe de uma sessao manual quanto no de uma execucao da
   bateria.

   Os ROTULOS mudam conforme a origem, e isso e requisito, nao enfeite: numa
   conversa da via simulador nenhum dos dois lados e uma pessoa -- e uma LLM
   fazendo o papel de cliente contra o bot sob teste. Mostrar o mesmo icone de
   pessoa das conversas manuais faria um dado sintetico passar por dado de
   campo, que e o erro de leitura mais caro que esta interface pode induzir. */
function rotulos(via) {
  return via === 'simulador'
    ? { usuario: '🎭 persona simulada (LLM)', bot: '🤖 bot sob teste' }
    : { usuario: '🧑 você', bot: '🤖 atendente' }
}

function Bruto({ titulo, dados }) {
  const [aberto, setAberto] = useState(false)
  const vazio = !dados || (Array.isArray(dados) && dados.length === 0)
  return (
    <div style={{ borderTop: '1px solid var(--borda-suave)' }}>
      <div
        onClick={() => setAberto((a) => !a)}
        style={{ padding: '8px 0', cursor: 'pointer', fontSize: 13, color: 'var(--texto-suave)', display: 'flex', gap: 8 }}
      >
        <span style={{ color: 'var(--acento)' }}>{aberto ? '▾' : '▸'}</span>
        {titulo}
        <span className="mono" style={{ color: 'var(--texto-tenue)', fontSize: 12 }}>
          {Array.isArray(dados) ? `${dados.length} item(ns)` : vazio ? 'vazio' : ''}
        </span>
      </div>
      {aberto && (
        <pre
          className="mono"
          style={{
            margin: '0 0 10px', padding: 12, background: '#f6f7f9',
            border: '1px solid var(--borda-suave)', borderRadius: 2, fontSize: 11.5,
            lineHeight: 1.5, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap',
          }}
        >
          {JSON.stringify(dados, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function Turno({ t, via }) {
  const vazia = !String(t.resposta_final || '').trim()
  const r = rotulos(via)
  return (
    <div className="painel" style={{ padding: '14px 18px', marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
        <div className="rotulo">turno {t.turno_id}</div>
        <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>
          {t.meta?.latencia_s}s · {t.meta?.tentativas_llm ?? 1} chamada(s)
          {t.meta?.historico_reduzido ? ' · histórico reduzido' : ''}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 8 }}>
        <div>
          <div className="rotulo" style={{ marginBottom: 4 }}>{r.usuario}</div>
          <div style={{ fontSize: 14, lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>{t.mensagem_usuario}</div>
        </div>
        <div>
          <div className="rotulo" style={{ marginBottom: 4 }}>{r.bot}</div>
          {vazia ? (
            <div className="aviso">
              Resposta em branco do provedor. O turno foi gravado assim mesmo — a
              taxa de falha é dado do experimento.
            </div>
          ) : (
            <div style={{ fontSize: 14, lineHeight: 1.55, whiteSpace: 'pre-wrap', color: 'var(--texto-medio)' }}>
              {t.resposta_final}
            </div>
          )}
        </div>
      </div>

      <Bruto titulo="Prompt enviado à LLM" dados={t.prompt_completo} />
      <Bruto titulo="Consultas à fonte de verdade" dados={t.consultas_dados} />
      <Bruto titulo="Trechos recuperados (RAG)" dados={t.trechos_rag} />
      <Bruto titulo="Estado da conversa" dados={t.estado} />
      <Bruto titulo="Resposta bruta da API" dados={t.resposta_bruta} />
    </div>
  )
}
