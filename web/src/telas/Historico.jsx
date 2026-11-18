import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'

function formatarInstante(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

const COLUNAS = '1.1fr .5fr .5fr .9fr 1fr .9fr'

export default function Historico() {
  const [sessoes, setSessoes] = useState([])
  const [busca, setBusca] = useState('')
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState(null)
  const navegar = useNavigate()

  useEffect(() => {
    // Espera a digitacao parar antes de buscar: cada busca varre todos os
    // arquivos de log em disco, entao disparar por tecla seria desperdicio.
    const t = setTimeout(async () => {
      setCarregando(true)
      setErro(null)
      try {
        const q = busca.trim()
        setSessoes(await api.listarSessoes(q ? `?busca=${encodeURIComponent(q)}` : ''))
      } catch (e) {
        setErro(e.message)
      } finally {
        setCarregando(false)
      }
    }, 250)
    return () => clearTimeout(t)
  }, [busca])

  return (
    <>
      <Cabecalho
        titulo="Histórico de conversas"
        legenda={`${sessoes.length} conversa(s) manual(is)`}
      >
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar no texto dos turnos…"
          style={{
            width: 280, padding: '9px 12px', fontSize: 13, fontFamily: 'inherit',
            border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
          }}
        />
      </Cabecalho>

      <div style={{ padding: '24px 30px', overflowY: 'auto' }}>
        <div style={{ fontSize: 13, color: 'var(--texto-fraco)', marginBottom: 14, lineHeight: 1.5 }}>
          Só conversas de uma pessoa com o bot. As geradas pela automação são testes
          automatizados e ficam em <strong>Execuções</strong> — as duas fontes não
          se misturam de propósito.
        </div>

        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)' }}>
            {erro}
          </div>
        )}

        <div className="painel" style={{ overflow: 'hidden' }}>
          <div
            className="rotulo"
            style={{
              display: 'grid', gridTemplateColumns: COLUNAS, gap: 12,
              padding: '10px 18px', borderBottom: '1px solid var(--borda-suave)',
            }}
          >
            <div>Sessão</div><div>Turnos</div><div>Vazios</div>
            <div>Desfecho</div><div>Início</div><div>Modelo</div>
          </div>

          {carregando && (
            <div className="pulsando" style={{ padding: '18px', fontSize: 13, color: 'var(--texto-fraco)' }}>
              Carregando…
            </div>
          )}

          {!carregando && sessoes.length === 0 && (
            <div style={{ padding: '18px', fontSize: 13, color: 'var(--texto-fraco)' }}>
              {busca.trim()
                ? `Nenhuma conversa contém “${busca.trim()}”.`
                : 'Nenhuma conversa manual gravada ainda.'}
            </div>
          )}

          {!carregando && sessoes.map((s) => (
            <div
              key={s.sessao_id}
              onClick={() => navegar(`/sessoes/${s.sessao_id}`)}
              style={{ borderBottom: '1px solid var(--borda-suave)', cursor: 'pointer' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--linha-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <div style={{ display: 'grid', gridTemplateColumns: COLUNAS, gap: 12, padding: '12px 18px', alignItems: 'center' }}>
                <div className="mono" style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 7 }}>
                  {s.sessao_id}
                  {s.viva && (
                    <span
                      title="Conversa ainda aberta em memória — aceita nova mensagem"
                      style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--verde)', flex: 'none' }}
                    />
                  )}
                </div>
                <div className="mono" style={{ fontSize: 13 }}>{s.turnos}</div>
                <div className="mono" style={{ fontSize: 13, color: s.turnos_vazios ? 'var(--vermelho)' : 'var(--texto-tenue)' }}>
                  {s.turnos_vazios}
                </div>
                <div style={{ fontSize: 13, color: s.acordo_fechado ? 'var(--verde)' : 'var(--texto-fraco)' }}>
                  {s.acordo_fechado ? 'acordo fechado' : 'sem acordo'}
                </div>
                <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
                  {formatarInstante(s.inicio)}
                </div>
                <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>{s.modelo ?? '—'}</div>
              </div>
              {s.trecho && (
                <div style={{ padding: '0 18px 12px', fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.5 }}>
                  {s.trecho}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
