import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import Cabecalho from '../componentes/Cabecalho.jsx'
import SeletorModelo from '../componentes/SeletorModelo.jsx'
import TabelaMetricas from '../componentes/TabelaMetricas.jsx'
import Turno from '../componentes/Turno.jsx'
import { api } from '../api.js'

export default function Sessao() {
  const { sessaoId } = useParams()
  /* Chegada a partir de uma ocorrencia do relatorio: `execucao` e `turno`
     apontam a interacao que falhou. O log da bateria guarda as N execucoes do
     estimulo juntas; sem o recorte, o turno procurado se perde entre elas. */
  const [busca] = useSearchParams()
  const execucaoAlvo = busca.get('execucao')
  const turnoAlvo = busca.get('turno')
  const [todasExecucoes, setTodasExecucoes] = useState(false)
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [avaliacao, setAvaliacao] = useState(null)
  const [rodando, setRodando] = useState(null) // 'sem-juiz' | 'com-juiz' | 'tom'
  // Vazio = o juiz do .env. Escolher aqui importa porque o modelo que julga
  // muda o veredito e o custo: o padrao e um Sonnet, e um Haiku custa cerca
  // de vinte vezes menos por token no mesmo papel.
  const [juizModelo, setJuizModelo] = useState('')

  async function carregar() {
    setErro(null)
    try {
      setDados(await api.detalharSessao(sessaoId))
    } catch (e) {
      setErro(e.message)
    }
  }

  useEffect(() => { carregar() }, [sessaoId])

  const turnos = dados?.turnos ?? []
  const filtrarExecucao = execucaoAlvo && !todasExecucoes
  const visiveis = filtrarExecucao
    ? turnos.filter((t) => String(t.execucao_id) === execucaoAlvo)
    : turnos

  useEffect(() => {
    if (!turnoAlvo || !dados) return
    const el = document.getElementById(`turno-${execucaoAlvo ?? ''}-${turnoAlvo}`)
    if (el) el.scrollIntoView({ block: 'center' })
  }, [dados, turnoAlvo, execucaoAlvo])
  const tom = dados?.avaliacoes_tom?.['0']

  /* Aproximacao por cima do custo, so para decidir antes de gastar: um
     julgamento por turno em faithfulness (turnos com fonte), groundedness
     (turnos com contexto), toxicidade e robustez. */
  const chamadasEstimadas =
    turnos.filter((t) => t.consultas_dados?.length || t.trechos_rag?.length).length +
    turnos.filter((t) => t.trechos_rag?.length).length +
    2 * turnos.length

  async function avaliar(comJuiz) {
    setRodando(comJuiz ? 'com-juiz' : 'sem-juiz')
    setErro(null)
    try {
      setAvaliacao(await api.avaliarCategorias(sessaoId, comJuiz, 0, juizModelo))
    } catch (e) {
      setErro(e.message)
    } finally {
      setRodando(null)
    }
  }

  async function avaliarTom() {
    setRodando('tom')
    setErro(null)
    try {
      await api.avaliarTom(sessaoId, 0, juizModelo)
      await carregar()
    } catch (e) {
      setErro(e.message)
    } finally {
      setRodando(null)
    }
  }

  return (
    <>
      <Cabecalho titulo={`Sessão ${sessaoId}`} legenda={dados ? `${turnos.length} turnos · ${dados.arquivo_log}` : ''}>
        <Link to="/historico" className="botao" style={{ textDecoration: 'none' }}>
          Voltar ao histórico
        </Link>
      </Cabecalho>

      <div style={{ padding: '24px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        {/* --- Avaliacao sob demanda --- */}
        <div className="painel" style={{ marginBottom: 22 }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--borda-suave)' }}>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Avaliação desta conversa</div>
            <div style={{ fontSize: 13, color: 'var(--texto-fraco)', lineHeight: 1.5 }}>
              Fica atrás de um clique de propósito: as métricas de juiz custam uma
              chamada de API por turno, e não faz sentido gastá-las toda vez que
              alguém abre esta página. Cada execução grava um relatório novo por
              categoria — os anteriores continuam disponíveis.
            </div>
          </div>

          {/* O seletor fica ANTES dos botoes porque a escolha vale para os
              tres: quem ja clicou nao tem como voltar atras do gasto. */}
          <div style={{ padding: '14px 18px 0', display: 'flex', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div style={{ minWidth: 300 }}>
              <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 4 }}>
                Modelo do juiz
              </div>
              <SeletorModelo papel="juiz" valor={juizModelo} onChange={setJuizModelo} />
            </div>
          </div>

          <div style={{ padding: '14px 18px', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="botao" onClick={() => avaliar(false)} disabled={Boolean(rodando) || !turnos.length}>
              {rodando === 'sem-juiz' ? 'Avaliando…' : 'Avaliar sem juiz (grátis)'}
            </button>
            <button className="botao botao-primario" onClick={() => avaliar(true)} disabled={Boolean(rodando) || !turnos.length}>
              {rodando === 'com-juiz' ? 'Consultando o juiz…' : `Avaliar com juiz (~${chamadasEstimadas} chamadas)`}
            </button>
            <button className="botao" onClick={avaliarTom} disabled={Boolean(rodando) || !turnos.length}>
              {rodando === 'tom' ? 'Consultando o juiz…' : 'Avaliar tom (1 chamada)'}
            </button>
            {tom && (
              <span style={{ fontSize: 13, color: 'var(--texto-suave)', marginLeft: 4 }}>
                Tom: <strong>{tom.tom_nota}/5</strong>{' '}
                <span style={{ color: tom.tom_adequado ? 'var(--verde)' : 'var(--vermelho)' }}>
                  {tom.tom_adequado ? 'adequado' : 'inadequado'}
                </span>
              </span>
            )}
          </div>

          {tom?.tom_justificativa && (
            <div style={{ padding: '0 18px 14px', fontSize: 13, color: 'var(--texto-fraco)', lineHeight: 1.5 }}>
              {tom.tom_justificativa}
            </div>
          )}

          {avaliacao && (
            <>
              <div style={{ borderTop: '1px solid var(--borda-suave)' }}>
                <TabelaMetricas metricas={avaliacao.metricas} />
              </div>
              <div style={{ padding: '12px 18px', fontSize: 12, color: 'var(--texto-fraco)' }}>
                {avaliacao.usou_juiz ? `Juiz: ${avaliacao.juiz}. ` : 'Só camadas determinísticas. '}
                {avaliacao.relatorios_gravados.length} relatório(s) gravado(s) em{' '}
                <span className="mono">logs/manuais/relatorios/</span>.
              </div>
            </>
          )}
        </div>

        {/* --- Timeline --- */}
        <div className="rotulo" style={{ marginBottom: 10 }}>Conversa, turno a turno</div>
        {execucaoAlvo && (
          <div className="aviso" style={{ marginBottom: 12, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <span>
              Aberto a partir de uma ocorrência do relatório: execução <strong className="mono">{execucaoAlvo}</strong>
              {turnoAlvo && <>, turno <strong className="mono">{turnoAlvo}</strong> (destacado)</>}.
            </span>
            <button className="botao" onClick={() => setTodasExecucoes(!todasExecucoes)}>
              {todasExecucoes ? 'Só esta execução' : 'Mostrar todas as execuções'}
            </button>
          </div>
        )}
        {visiveis.map((t) => {
          const alvo = turnoAlvo && String(t.turno_id) === turnoAlvo
            && (!execucaoAlvo || String(t.execucao_id) === execucaoAlvo)
          return (
            <div
              key={`${t.execucao_id}-${t.turno_id}`}
              id={`turno-${t.execucao_id}-${t.turno_id}`}
              style={alvo ? { outline: '2px solid var(--vermelho)', outlineOffset: 4, borderRadius: 2 } : undefined}
            >
              {execucaoAlvo == null && turnos.some((x) => x.execucao_id !== turnos[0].execucao_id) && (
                <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>execução {t.execucao_id}</div>
              )}
              <Turno t={t} />
            </div>
          )
        })}
        {dados && turnos.length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>Nenhum turno gravado nesta sessão.</div>
        )}
      </div>
    </>
  )
}
