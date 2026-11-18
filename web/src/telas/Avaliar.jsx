import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { VIAS } from '../componentes/ChipVia.jsx'
import SaidasAnteriores from '../componentes/SaidasAnteriores.jsx'
import SeletorModelo from '../componentes/SeletorModelo.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA } from '../metricas.js'

const CATEGORIAS = Object.keys(NOME_CATEGORIA)

const RECORTE_VAZIO = { modelo: '', via: '', origem_id: '', desde: '' }

const estiloEntrada = {
  padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
  border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
}

export default function Avaliar() {
  const [categorias, setCategorias] = useState([])
  const [comJuiz, setComJuiz] = useState(false)
  const [juizModelo, setJuizModelo] = useState('')
  const [recorte, setRecorte] = useState(RECORTE_VAZIO)
  const [plano, setPlano] = useState(null)
  const [estimulos, setEstimulos] = useState([])
  const [estado, setEstado] = useState(null)
  const [erro, setErro] = useState(null)
  const [confirmando, setConfirmando] = useState(false)

  const rodando = Boolean(estado?.rodando)

  useEffect(() => {
    api.listarEstimulos().then((d) => setEstimulos(d.estimulos)).catch(() => {})
  }, [])

  // Replaneja a cada mudanca do recorte: quantos turnos vao ser julgados
  // precisa estar na tela antes de existir botao para confirmar, porque com
  // juiz o custo cresce com o numero de turnos.
  useEffect(() => {
    api.planejarAvaliacao({ ...recorte })
      .then((p) => { setPlano(p); setErro(null) })
      .catch((e) => setErro(e.message))
    setConfirmando(false)
  }, [recorte])

  useEffect(() => {
    let vivo = true
    async function ler() {
      try {
        const s = await api.statusAvaliacao()
        if (vivo) setEstado(s)
      } catch { /* a proxima tentativa resolve */ }
    }
    ler()
    const t = setInterval(ler, 3000)
    return () => { vivo = false; clearInterval(t) }
  }, [])

  function alternar(c) {
    setCategorias((cs) => cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c])
    setConfirmando(false)
  }

  async function disparar() {
    setErro(null)
    try {
      setEstado(await api.iniciarAvaliacao({
        categorias, com_juiz: comJuiz, juiz_modelo: juizModelo || null, ...recorte,
      }))
      setConfirmando(false)
    } catch (e) {
      setErro(e.message)
    }
  }

  async function interromper() {
    try { setEstado(await api.pararAvaliacao()) } catch (e) { setErro(e.message) }
  }

  const alvo = categorias.length === 0 ? 'todas as 6 categorias' : `${categorias.length} categoria(s)`

  return (
    <>
      <Cabecalho
        titulo="Rodar avaliação"
        subtitulo="julga as conversas já gravadas — é aqui que sai o veredito"
        legenda={rodando ? 'em andamento' : ''}
      >
        {rodando && <button className="botao" onClick={interromper}>Interromper</button>}
      </Cabecalho>

      <div style={{ padding: '22px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        {/* --- Andamento --- */}
        {estado?.houve_rodada && (
          <div className="painel" style={{ padding: '16px 18px', marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                {rodando ? 'Avaliação em andamento' : estado.interrompida ? 'Avaliação interrompida' : 'Última avaliação'}
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--texto-fraco)' }}>
                {estado.pid != null && `pid ${estado.pid}`}
                {estado.codigo_saida != null && ` · saiu com código ${estado.codigo_saida}`}
                {estado.terminado_em && `terminou em ${new Date(estado.terminado_em).toLocaleString('pt-BR')}`}
              </div>
            </div>

            {!estado.sem_metadados && (
              <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 10 }}>
                {estado.juiz
                  ? <>juiz <span className="mono">{estado.juiz}</span></>
                  : 'só camadas determinísticas (sem juiz)'}
              </div>
            )}

            {/* Progresso pelas chamadas ao juiz contra um total ESTIMADO antes
                de rodar: a porcentagem e aproximada e para em 99% ate o fim.
                Sem juiz nao ha chamadas a contar; vale a categoria em curso. */}
            {estado.progresso && (
              <div style={{ marginBottom: 10 }}>
                {estado.progresso.percentual != null && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                    <div style={{ flex: 1, height: 10, background: 'var(--trilho)', borderRadius: 5, overflow: 'hidden' }}>
                      <div className={rodando ? 'pulsando' : undefined}
                        style={{ width: `${estado.progresso.percentual}%`, height: '100%', background: 'var(--acento)' }} />
                    </div>
                    <span className="mono" style={{ fontSize: 13 }}>~{estado.progresso.percentual}%</span>
                  </div>
                )}
                <div style={{ fontSize: 12, color: 'var(--texto-fraco)', lineHeight: 1.6 }}>
                  {estado.progresso.categoria && (
                    <>Categoria {estado.progresso.categoria.indice} de {estado.progresso.categoria.total}:{' '}
                      <strong>{NOME_CATEGORIA[estado.progresso.categoria.atual] || estado.progresso.categoria.atual}</strong></>
                  )}
                  {estado.progresso.chamadas_estimadas > 0 && (
                    <> · {estado.progresso.chamadas_feitas} de ~{estado.progresso.chamadas_estimadas} chamadas ao juiz
                      {' '}<span style={{ color: 'var(--texto-tenue)' }}>(total estimado antes de começar)</span></>
                  )}
                </div>
              </div>
            )}
            {rodando && !estado.progresso && (
              <div className="pulsando" style={{ fontSize: 13, color: 'var(--acento)', marginBottom: 10 }}>
                Preparando… carregando os logs.
              </div>
            )}

            {estado.saida?.length > 0 && (
              <pre
                className="mono"
                style={{
                  margin: 0, padding: 12, background: '#f6f7f9', border: '1px solid var(--borda-suave)',
                  borderRadius: 2, fontSize: 11.5, lineHeight: 1.5, maxHeight: 260,
                  overflow: 'auto', whiteSpace: 'pre-wrap', color: 'var(--texto-suave)',
                }}
              >
                {estado.saida.join('\n')}
              </pre>
            )}

            {!rodando && estado.codigo_saida === 0 && (
              <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 10 }}>
                Relatórios novos gravados em <span className="mono">logs/</span> — veja em{' '}
                <a href="/relatorios">Relatórios</a>. Os anteriores continuam lá.
              </div>
            )}
            {!rodando && estado.interrompida && (
              <div className="aviso" style={{ marginTop: 10 }}>
                Interrompida no meio: as categorias já concluídas gravaram relatório,
                as demais não. Diferente da automação, a avaliação não retoma de onde parou.
              </div>
            )}
          </div>
        )}

        <SaidasAnteriores tipo="avaliacao" atualizarCom={estado?.iniciado_em} />

        {/* --- Formulario --- */}
        <div className="painel" style={{ padding: 18, opacity: rodando ? 0.55 : 1, pointerEvents: rodando ? 'none' : 'auto' }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Configurar avaliação</div>
          <div style={{ fontSize: 13, color: 'var(--texto-fraco)', lineHeight: 1.5, marginBottom: 16, maxWidth: 800 }}>
            Lê os logs já gravados e produz um relatório novo por categoria. Nada é
            sobrescrito: cada execução cria arquivos próprios, porque o juiz não é
            determinístico e duas medições da mesma categoria podem divergir.
          </div>

          {/* --- EIXO 1: o que julgar --------------------------------- */}
          <div style={{ border: '1px solid var(--borda-suave)', borderRadius: 2, padding: 14, marginBottom: 16 }}>
            <div className="rotulo" style={{ marginBottom: 4 }}>1 · O que julgar</div>
            <div style={{ fontSize: 12, color: 'var(--texto-fraco)', lineHeight: 1.5, marginBottom: 12, maxWidth: 780 }}>
              Sem recorte, entram <strong>todos</strong> os logs da automação já
              gravados — inclusive de outros modelos de bot e de rodadas antigas.
              Misturar modelos junta dois sistemas diferentes num número só.
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="rotulo">Modelo do bot</span>
                <select style={estiloEntrada} value={recorte.modelo}
                  onChange={(e) => setRecorte({ ...recorte, modelo: e.target.value })}>
                  <option value="">todos</option>
                  {Object.keys(plano?.modelos ?? {}).map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="rotulo">Via</span>
                <select style={estiloEntrada} value={recorte.via}
                  onChange={(e) => setRecorte({ ...recorte, via: e.target.value, origem_id: '' })}>
                  <option value="">todas</option>
                  {Object.keys(VIAS).map((v) => <option key={v} value={v}>{VIAS[v].rotulo}</option>)}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="rotulo">Caso de teste</span>
                <select style={estiloEntrada} value={recorte.origem_id}
                  onChange={(e) => setRecorte({ ...recorte, origem_id: e.target.value })}>
                  <option value="">todos</option>
                  {estimulos.filter((e) => !recorte.via || e.via === recorte.via)
                    .map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="rotulo">Gerado a partir de</span>
                <input type="date" style={estiloEntrada} value={recorte.desde}
                  onChange={(e) => setRecorte({ ...recorte, desde: e.target.value })} />
              </label>
            </div>

            {plano && (
              <div style={{ display: 'flex', gap: 22, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13 }}>
                  <span className="mono" style={{ fontSize: 20, fontWeight: 700, color: plano.turnos ? 'var(--acento)' : 'var(--texto-tenue)' }}>
                    {plano.turnos}
                  </span>{' '}
                  turnos de <span className="mono">{plano.arquivos}</span> arquivo(s)
                </span>
                <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
                  {Object.entries(plano.vias).map(([v, n]) => `${v}: ${n}`).join(' · ') || '—'}
                </span>
                {Object.keys(plano.modelos).length > 0 && (
                  <span className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
                    {Object.keys(plano.modelos).join(', ')}
                  </span>
                )}
              </div>
            )}

            {plano?.mistura_modelos && (
              <div className="aviso" style={{ marginTop: 10, background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)' }}>
                <strong>Este recorte mistura {Object.keys(plano.modelos).length} modelos de bot.</strong> O
                relatório sairia com um número só para sistemas diferentes. Filtre por
                modelo, a menos que a intenção seja exatamente essa.
              </div>
            )}

            {plano?.turnos === 0 && (
              <div className="aviso" style={{ marginTop: 10 }}>
                Nenhum turno neste recorte — não há o que julgar.
              </div>
            )}
          </div>

          {/* --- EIXO 2: quais metricas -------------------------------- */}
          <div className="rotulo" style={{ marginBottom: 4 }}>2 · Quais categorias medir</div>
          <div style={{ fontSize: 12, color: 'var(--texto-fraco)', lineHeight: 1.5, marginBottom: 8, maxWidth: 780 }}>
            Outro eixo: aqui você escolhe <strong>quais métricas rodam</strong> sobre
            os turnos selecionados acima — não quais conversas entram.
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
            {CATEGORIAS.map((c) => {
              const ativo = categorias.includes(c)
              return (
                <button
                  key={c}
                  onClick={() => alternar(c)}
                  className="botao"
                  style={{
                    padding: '6px 11px', fontSize: 12,
                    background: ativo ? 'var(--acento)' : 'var(--painel)',
                    borderColor: ativo ? 'var(--acento)' : 'var(--borda-forte)',
                    color: ativo ? '#fff' : 'var(--texto)',
                  }}
                >
                  {NOME_CATEGORIA[c]}
                </button>
              )
            })}
          </div>
          <div style={{ fontSize: 12, color: 'var(--texto-tenue)', marginBottom: 18 }}>
            Nenhuma selecionada = todas as seis.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 16 }}>
            <div>
              <div className="rotulo" style={{ marginBottom: 6 }}>Camadas</div>
              <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, lineHeight: 1.5 }}>
                <input type="checkbox" checked={comJuiz} style={{ marginTop: 3 }}
                  onChange={(e) => { setComJuiz(e.target.checked); setConfirmando(false) }} />
                <span>
                  <strong>Usar o juiz LLM</strong>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
                    Sem marcar, roda só as camadas determinísticas: sai em segundos
                    e não gasta token. É o caminho para olhar antes de decidir pagar.
                  </div>
                </span>
              </label>
            </div>

            <div style={{ opacity: comJuiz ? 1 : 0.45, pointerEvents: comJuiz ? 'auto' : 'none' }}>
              <div className="rotulo" style={{ marginBottom: 6 }}>Modelo do juiz</div>
              {/* O juiz precisa ser de provedor diferente do bot, para nao
                  medir o sistema contra si mesmo (self-enhancement bias). */}
              <SeletorModelo papel="juiz" valor={juizModelo} onChange={setJuizModelo} />
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--borda-suave)', paddingTop: 14 }}>
            {comJuiz && (
              <div className="aviso" style={{ marginBottom: 12 }}>
                Com o juiz, é ao menos uma chamada paga por turno avaliado — {plano?.turnos ?? '…'} turnos
                neste recorte. Pode levar dezenas de minutos.
              </div>
            )}

            {!confirmando ? (
              <button className="botao botao-primario" disabled={plano?.turnos === 0}
                onClick={() => comJuiz ? setConfirmando(true) : disparar()}>
                {plano?.turnos === 0
                  ? 'Nada a julgar'
                  : comJuiz
                    ? `Avaliar ${alvo} em ${plano?.turnos ?? '…'} turnos, com juiz…`
                    : `Avaliar ${alvo} em ${plano?.turnos ?? '…'} turnos, sem juiz (grátis)`}
              </button>
            ) : (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13 }}>
                  Confirmar avaliação de <strong>{alvo}</strong> com juiz
                  {juizModelo && <> (<span className="mono">{juizModelo}</span>)</>}?
                </span>
                <button className="botao botao-primario" onClick={disparar}>Confirmar</button>
                <button className="botao" onClick={() => setConfirmando(false)}>Cancelar</button>
              </div>
            )}
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--texto-tenue)', marginTop: 14, lineHeight: 1.55, maxWidth: 800 }}>
          Equivale a <span className="mono">python scripts/avaliar_bateria.py</span> no
          terminal. O processo é do servidor: fechar esta aba não interrompe nada.
        </div>
      </div>
    </>
  )
}
