import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import ChipVia, { VIAS } from '../componentes/ChipVia.jsx'
import Turno from '../componentes/Turno.jsx'
import { api } from '../api.js'

function formatarInstante(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

// Dia local (AAAA-MM-DD), no formato do input date, para o filtro.
const dia = (iso) => (iso ? new Date(iso).toLocaleDateString('sv-SE') : '')
const chave = (e) => `${e.nome}#${e.execucoes[0]}`

const estiloData = {
  padding: '5px 7px', fontSize: 12, fontFamily: 'inherit',
  border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
}

export default function Execucoes() {
  const [lista, setLista] = useState([])
  const [via, setVia] = useState('')
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')
  // A linha escolhida: o log E as execuções da rodada dela.
  const [selecionado, setSelecionado] = useState(null)
  const [detalhe, setDetalhe] = useState(null)
  const [repeticao, setRepeticao] = useState(null)
  const [erro, setErro] = useState(null)

  const [rodando, setRodando] = useState(false)

  function recarregar() {
    return api.listarExecucoes(via)
      .then((l) => { setLista(l); setErro(null) })
      .catch((e) => setErro(e.message))
  }

  useEffect(() => { recarregar() }, [via])

  /* Uma rodada da automação ACRESCENTA ao log do estímulo em vez de criar um
     arquivo novo — o nome depende só do estímulo e do modelo. Sem recarregar,
     a tela continua mostrando os números de antes e a execução parece não ter
     acontecido. Enquanto há rodada em andamento, atualiza sozinha; ao terminar,
     recarrega uma última vez. */
  useEffect(() => {
    let vivo = true
    let anterior = false
    const t = setInterval(async () => {
      try {
        const s = await api.statusBateria()
        if (!vivo) return
        setRodando(s.rodando)
        if (s.rodando || anterior) recarregar()
        anterior = s.rodando
      } catch { /* a proxima tentativa resolve */ }
    }, 5000)
    return () => { vivo = false; clearInterval(t) }
  }, [via])

  useEffect(() => {
    if (!selecionado) { setDetalhe(null); return }
    setDetalhe(null)
    api.detalharExecucao(selecionado.nome)
      .then((d) => {
        // Só as repetições da rodada escolhida; o log tem as de todas.
        const daRodada = d.execucoes.filter((id) => selecionado.execucoes.includes(id))
        setDetalhe({ ...d, execucoes: daRodada })
        setRepeticao(daRodada[0] ?? null)
      })
      .catch((e) => setErro(e.message))
  }, [selecionado])

  const turnosDaRepeticao = (detalhe?.turnos ?? [])
    .filter((t) => t.execucao_id === repeticao)
    .sort((a, b) => a.turno_id - b.turno_id)

  const visiveis = lista.filter((e) =>
    (!de || dia(e.inicio) >= de) && (!ate || dia(e.inicio) <= ate))
  const rodadas = new Set(lista.map((e) => dia(e.inicio))).size

  return (
    <>
      <Cabecalho
        titulo="Execuções da automação"
        subtitulo="conversas geradas pelos casos de teste"
        legenda={`${visiveis.length} de ${lista.length} execução(ões) · ${rodadas} dia(s) de rodada`}
      >
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {rodando && (
            <span className="pulsando" style={{ fontSize: 12, color: 'var(--acento)', marginRight: 4 }}>
              automação rodando…
            </span>
          )}
          <button className="botao" style={{ padding: '7px 11px', fontSize: 12 }} onClick={recarregar}>
            Atualizar
          </button>
          {['', ...Object.keys(VIAS)].map((v) => (
            <button
              key={v || 'todas'}
              onClick={() => { setVia(v); setSelecionado(null) }}
              className="botao"
              style={{
                padding: '7px 11px', fontSize: 12,
                background: v === via ? 'var(--acento)' : 'var(--painel)',
                borderColor: v === via ? 'var(--acento)' : 'var(--borda-forte)',
                color: v === via ? '#fff' : 'var(--texto)',
              }}
            >
              {v ? VIAS[v].rotulo : 'todas'}
            </button>
          ))}
        </div>
      </Cabecalho>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* --- Lista --- */}
        <div style={{ width: 400, flex: 'none', borderRight: '1px solid var(--borda)', overflowY: 'auto', background: 'var(--painel)' }}>
          <div style={{ padding: '13px 18px', fontSize: 12, color: 'var(--texto-fraco)', lineHeight: 1.5, borderBottom: '1px solid var(--borda-suave)' }}>
            Conversas geradas por teste automatizado. Não se misturam com o
            <strong> Histórico</strong>, que é conversa de uma pessoa com o bot.
            <div style={{ marginTop: 6 }}>
              Uma linha por estímulo em cada rodada. As rodadas dividem o mesmo
              arquivo de log; a tela as separa pela data. Ordenado pela mais recente.
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
              de <input type="date" style={estiloData} value={de} onChange={(ev) => setDe(ev.target.value)} />
              até <input type="date" style={estiloData} value={ate} onChange={(ev) => setAte(ev.target.value)} />
              {(de || ate) && (
                <button className="botao" style={{ padding: '4px 9px', fontSize: 12 }}
                  onClick={() => { setDe(''); setAte('') }}>limpar</button>
              )}
            </div>
          </div>

          {visiveis.map((e) => {
            const ativo = selecionado && chave(e) === chave(selecionado)
            return (
              <div
                key={chave(e)}
                onClick={() => setSelecionado(e)}
                style={{
                  padding: '12px 18px', borderBottom: '1px solid var(--borda-suave)', cursor: 'pointer',
                  background: ativo ? 'var(--item-hover)' : 'transparent',
                  borderLeft: `3px solid ${ativo ? 'var(--acento)' : 'transparent'}`,
                }}
              >
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 5, flexWrap: 'wrap' }}>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{e.estimulo_id}</span>
                  <ChipVia via={e.via} comIcone={false} />
                </div>
                <div style={{ fontSize: 12, color: 'var(--texto-fraco)', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <span>{e.repeticoes} repetição(ões)</span>
                  <span>{e.turnos} turnos</span>
                  <span style={{ color: e.acordos ? 'var(--verde)' : undefined }}>{e.acordos} acordo(s)</span>
                  {e.turnos_vazios > 0 && (
                    <span style={{ color: 'var(--vermelho)' }}>{e.turnos_vazios} vazio(s)</span>
                  )}
                </div>
                <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)', marginTop: 4 }}>
                  {e.modelo}
                </div>
                <div style={{ fontSize: 11, color: 'var(--texto-tenue)', marginTop: 2 }}>
                  rodada de <span style={{ color: 'var(--texto-fraco)', fontWeight: 600 }}>{formatarInstante(e.inicio)}</span>
                  {' '}· último turno {formatarInstante(e.fim)}
                </div>
              </div>
            )
          })}
          {visiveis.length === 0 && (
            <div style={{ padding: 18, fontSize: 13, color: 'var(--texto-fraco)' }}>
              Nenhuma execução com esse filtro.
            </div>
          )}
        </div>

        {/* --- Detalhe --- */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '22px 26px' }}>
          {erro && (
            <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
              {erro}
            </div>
          )}

          {!selecionado && !erro && (
            <div style={{ color: 'var(--texto-fraco)', fontSize: 14, lineHeight: 1.6, maxWidth: 480, marginTop: 40 }}>
              Escolha uma execução à esquerda.
            </div>
          )}

          {detalhe && (
            <>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                <span className="mono" style={{ fontSize: 18, fontWeight: 700 }}>{detalhe.estimulo_id}</span>
                <ChipVia via={detalhe.via} />
              </div>
              <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 14 }}>
                bot {detalhe.modelo_bot}
                {detalhe.modelo_simulador && ` · simulador ${detalhe.modelo_simulador}`}
              </div>

              {detalhe.via === 'simulador' && (
                <div className="aviso" style={{ marginBottom: 14, maxWidth: 780 }}>
                  <strong>Nenhum lado desta conversa é uma pessoa.</strong> O
                  “cliente” é uma LLM interpretando uma persona contra o bot sob
                  teste — é dado sintético, gerado para medir, não interação de campo.
                </div>
              )}

              {/* Cada repeticao e uma execucao independente do MESMO estimulo:
                  compara-las e o ponto da via de reinjecao. */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
                <span className="rotulo" style={{ marginRight: 4 }}>Repetição</span>
                {detalhe.execucoes.map((id, i) => (
                  <button
                    key={id}
                    onClick={() => setRepeticao(id)}
                    className="botao"
                    style={{
                      padding: '5px 11px', fontSize: 12,
                      background: id === repeticao ? 'var(--acento)' : 'var(--painel)',
                      borderColor: id === repeticao ? 'var(--acento)' : 'var(--borda-forte)',
                      color: id === repeticao ? '#fff' : 'var(--texto)',
                    }}
                    title={`execucao_id ${id} no log`}
                  >
                    {i + 1}
                  </button>
                ))}
                <span style={{ fontSize: 12, color: 'var(--texto-tenue)', marginLeft: 6 }}>
                  {turnosDaRepeticao.length} turnos · execucao_id {repeticao}
                </span>
              </div>

              {turnosDaRepeticao.map((t) => (
                <Turno key={`${t.execucao_id}-${t.turno_id}`} t={t} via={detalhe.via} />
              ))}
            </>
          )}
        </div>
      </div>
    </>
  )
}
