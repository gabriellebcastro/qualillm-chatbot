import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import TabelaMetricas from '../componentes/TabelaMetricas.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA, estiloChip, infoStatus } from '../metricas.js'

const CATEGORIAS = Object.keys(NOME_CATEGORIA)

/** Instante do nome do arquivo (UTC) -> data e hora LOCAIS.
    "20261028T021703Z" -> "27/10/2026 23:17" em Brasília. O nome do arquivo
    fica em UTC; mostrar UTC sem avisar fazia uma avaliação da noite de 27/10
    aparecer como 28/10. */
function formatarMomento(m) {
  if (!m || m.length < 16) return m || '—'
  const data = new Date(Date.UTC(
    +m.slice(0, 4), +m.slice(4, 6) - 1, +m.slice(6, 8),
    +m.slice(9, 11), +m.slice(11, 13), +m.slice(13, 15),
  ))
  const p = (n) => String(n).padStart(2, '0')
  return `${p(data.getDate())}/${p(data.getMonth() + 1)}/${data.getFullYear()} ${p(data.getHours())}:${p(data.getMinutes())}`
}

/** O mesmo instante em UTC, como está no nome do arquivo. */
function momentoUtc(m) {
  if (!m || m.length < 16) return ''
  return `${m.slice(6, 8)}/${m.slice(4, 6)}/${m.slice(0, 4)} ${m.slice(9, 11)}:${m.slice(11, 13)} UTC`
}

/* Resumo de vereditos como chips contados, para dar para ler a lista sem
   abrir cada relatorio. */
function Vereditos({ vereditos }) {
  const entradas = Object.entries(vereditos || {})
  if (entradas.length === 0) return <span style={{ color: 'var(--texto-tenue)', fontSize: 12 }}>—</span>
  return (
    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
      {entradas.map(([status, n]) => (
        <span key={status} className="chip" style={{ ...estiloChip(status), fontSize: 11, padding: '1px 6px' }}>
          {n} {infoStatus(status).rotulo}
        </span>
      ))}
    </div>
  )
}

export default function Relatorios() {
  const [relatorios, setRelatorios] = useState([])
  const [filtro, setFiltro] = useState('')
  // Filtro por juiz no próprio navegador: a listagem já traz o juiz de cada
  // relatório, e as opções saem do que existe gravado, sem lista fixa.
  // '__sem__' separa os relatórios só determinísticos.
  const [filtroJuiz, setFiltroJuiz] = useState('')
  const [selecionado, setSelecionado] = useState(null)
  const [detalhe, setDetalhe] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    setCarregando(true)
    api.listarRelatorios(filtro)
      .then((rs) => { setRelatorios(rs); setErro(null) })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false))
  }, [filtro])

  useEffect(() => {
    if (!selecionado) { setDetalhe(null); return }
    api.detalharRelatorio(selecionado)
      .then(setDetalhe)
      .catch((e) => setErro(e.message))
  }, [selecionado])

  const juizes = [...new Set(relatorios.filter((r) => r.usou_juiz && r.juiz).map((r) => r.juiz))].sort()
  const visiveis = relatorios.filter((r) => {
    if (!filtroJuiz) return true
    if (filtroJuiz === '__sem__') return !r.usou_juiz
    return r.usou_juiz && r.juiz === filtroJuiz
  })

  const proc = detalhe?.procedencia ?? {}
  const metricas = (detalhe?.categorias ?? []).flatMap((c) => c.metricas ?? [])
  const limitacao = (detalhe?.categorias ?? []).map((c) => c.limitacao_assumida).filter(Boolean)[0]

  return (
    <>
      <Cabecalho
        titulo="Relatórios"
        legenda={visiveis.length === relatorios.length
          ? `${relatorios.length} gravado(s)`
          : `${visiveis.length} de ${relatorios.length} gravado(s)`}
      >
        <select
          value={filtroJuiz}
          onChange={(e) => { setFiltroJuiz(e.target.value); setSelecionado(null) }}
          style={{
            padding: '9px 12px', fontSize: 13, fontFamily: 'inherit',
            border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
          }}
        >
          <option value="">Todos os juízes</option>
          {juizes.map((j) => <option key={j} value={j}>{j}</option>)}
          <option value="__sem__">Sem juiz</option>
        </select>
        <select
          value={filtro}
          onChange={(e) => { setFiltro(e.target.value); setSelecionado(null) }}
          style={{
            padding: '9px 12px', fontSize: 13, fontFamily: 'inherit',
            border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
          }}
        >
          <option value="">Todas as categorias</option>
          {CATEGORIAS.map((c) => <option key={c} value={c}>{NOME_CATEGORIA[c]}</option>)}
        </select>
      </Cabecalho>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* --- Lista --- */}
        <div style={{ width: 430, flex: 'none', borderRight: '1px solid var(--borda)', overflowY: 'auto', background: 'var(--painel)' }}>
          <div style={{ padding: '14px 18px', fontSize: 12, color: 'var(--texto-fraco)', lineHeight: 1.5, borderBottom: '1px solid var(--borda-suave)' }}>
            Nada é sobrescrito de propósito. Duas execuções da mesma categoria
            podem dar números diferentes — o juiz não é determinístico, e essa
            variação <strong>é dado</strong>, não ruído.
          </div>

          {carregando && (
            <div className="pulsando" style={{ padding: 18, fontSize: 13, color: 'var(--texto-fraco)' }}>Carregando…</div>
          )}
          {!carregando && visiveis.length === 0 && (
            <div style={{ padding: 18, fontSize: 13, color: 'var(--texto-fraco)' }}>
              Nenhum relatório gravado com este filtro.
            </div>
          )}

          {visiveis.map((r) => {
            const ativo = r.nome === selecionado
            return (
              <div
                key={r.nome}
                onClick={() => setSelecionado(r.nome)}
                style={{
                  padding: '12px 18px',
                  borderBottom: '1px solid var(--borda-suave)',
                  cursor: 'pointer',
                  background: ativo ? 'var(--item-hover)' : 'transparent',
                  borderLeft: `3px solid ${ativo ? 'var(--acento)' : 'transparent'}`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, marginBottom: 5 }}>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>
                    {NOME_CATEGORIA[r.categoria] ?? r.categoria}
                  </span>
                  <span className="mono" style={{ fontSize: 11, color: 'var(--texto-fraco)' }}
                    title={`horário local · ${momentoUtc(r.momento)} no nome do arquivo`}>
                    {formatarMomento(r.momento)}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 6 }}>
                  {/* Distinguir bateria de conversa avulsa e essencial: sao
                      recortes de tamanho e natureza muito diferentes. */}
                  {r.escopo
                    ? <>conversa <span className="mono">{r.escopo}</span></>
                    : `automação · ${r.n_arquivos_log} arquivo(s) de log`}
                  {r.n_turnos != null && ` · ${r.n_turnos} turnos`}
                  {' · '}
                  {r.usou_juiz
                    ? <span className="mono" style={{ color: 'var(--acento)' }}>{r.juiz || 'com juiz'}</span>
                    : 'sem juiz'}
                </div>
                <Vereditos vereditos={r.vereditos} />
              </div>
            )
          })}
        </div>

        {/* --- Detalhe --- */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '22px 26px' }}>
          {erro && (
            <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
              {erro}
            </div>
          )}

          {!detalhe && !erro && (
            <div style={{ color: 'var(--texto-fraco)', fontSize: 14, lineHeight: 1.6, maxWidth: 460, marginTop: 40 }}>
              Escolha um relatório à esquerda.
              <div style={{ marginTop: 10, fontSize: 13, color: 'var(--texto-tenue)' }}>
                Lembre que a direção muda por métrica: em algumas o ideal é 1,
                em outras o ideal é exatamente 0. A coluna “Direção” diz qual é
                qual, e a cor segue essa regra — nunca o valor bruto.
              </div>
            </div>
          )}

          {detalhe && (
            <>
              <div style={{ marginBottom: 6, fontSize: 20, fontWeight: 700 }}>
                {NOME_CATEGORIA[detalhe._categoria] ?? detalhe._categoria}
              </div>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 18 }}>
                <span className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>{detalhe._arquivo}</span>
                {/* A planilha cobre a AVALIACAO inteira (as seis categorias do
                    mesmo instante), nao so este relatorio. */}
                {!detalhe._escopo && (
                  <a className="botao" style={{ textDecoration: 'none', marginLeft: 'auto' }}
                    href={`/api/avaliacoes/${detalhe._momento}/planilha`}>
                    Baixar planilha da avaliação (.xlsx)
                  </a>
                )}
              </div>

              {/* Procedencia: sem ela, dois relatorios com numeros diferentes
                  ficam impossiveis de comparar depois. */}
              <div className="painel" style={{ padding: '14px 18px', marginBottom: 16 }}>
                <div className="rotulo" style={{ marginBottom: 10 }}>Procedência da medição</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px 24px', fontSize: 13 }}>
                  <div>
                    <span style={{ color: 'var(--texto-fraco)' }}>Gerado em: </span>{formatarMomento(detalhe._momento)}
                    <span style={{ color: 'var(--texto-tenue)', fontSize: 12 }}> (horário local; {momentoUtc(detalhe._momento)} no nome do arquivo)</span>
                  </div>
                  <div><span style={{ color: 'var(--texto-fraco)' }}>Turnos: </span><span className="mono">{proc.n_turnos ?? '—'}</span></div>
                  <div>
                    <span style={{ color: 'var(--texto-fraco)' }}>Juiz: </span>
                    {proc.usou_juiz ? <span className="mono">{proc.juiz}</span> : 'não usado (só camadas determinísticas)'}
                  </div>
                  <div>
                    <span style={{ color: 'var(--texto-fraco)' }}>Recorte: </span>
                    {detalhe._escopo ? <span className="mono">{detalhe._escopo}</span> : 'automação'}
                  </div>
                  {proc.origem && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <span style={{ color: 'var(--texto-fraco)' }}>Origem: </span>{proc.origem}
                    </div>
                  )}
                </div>

                {Array.isArray(proc.arquivos_de_log) && proc.arquivos_de_log.length > 0 && (
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--acento)' }}>
                      {proc.arquivos_de_log.length} arquivo(s) de log entraram nesta medição
                    </summary>
                    <div className="mono" style={{ fontSize: 11, color: 'var(--texto-fraco)', marginTop: 8, lineHeight: 1.7, maxHeight: 180, overflowY: 'auto' }}>
                      {proc.arquivos_de_log.map((a) => <div key={a}>{a}</div>)}
                    </div>
                  </details>
                )}
              </div>

              {limitacao && (
                <div className="aviso" style={{ marginBottom: 16, padding: '10px 14px' }}>
                  <strong>Limitação assumida desta categoria:</strong> {limitacao}
                </div>
              )}

              <div className="painel" style={{ overflow: 'hidden' }}>
                <TabelaMetricas metricas={metricas} />
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
