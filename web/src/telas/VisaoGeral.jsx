import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'
import {
  NOME_CATEGORIA, descreverLimiar, estiloChip, formatarValor, infoStatus, preenchimento,
} from '../metricas.js'

function formatarMomento(m) {
  if (!m || m.length < 16) return '—'
  const [d, h] = [m.slice(0, 8), m.slice(9, 15)]
  return `${d.slice(6, 8)}/${d.slice(4, 6)} ${h.slice(0, 2)}:${h.slice(2, 4)}`
}

function Contador({ rotulo, valor, dica }) {
  return (
    <div title={dica}>
      <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>{rotulo}</div>
      <div className="mono" style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.2 }}>{valor}</div>
    </div>
  )
}

const Divisor = () => <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--borda)' }} />

function LinhaCategoria({ cat }) {
  const nunca = cat.status === 'nunca_avaliada'
  const info = nunca
    ? { rotulo: 'nunca avaliada', cor: 'var(--texto-tenue)', fundo: 'transparent', borda: 'var(--borda-forte)', tracejado: true }
    : infoStatus(cat.status)

  return (
    <div style={{ borderBottom: '1px solid var(--borda-suave)', padding: '12px 18px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(130px, 1fr) 96px minmax(0, 4fr) auto', gap: 14, alignItems: 'center' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>
          {NOME_CATEGORIA[cat.categoria] ?? cat.categoria}
        </div>

        <div>
          <span className="chip" style={{
            color: info.cor, background: info.fundo,
            border: `1px ${info.tracejado ? 'dashed' : 'solid'} ${info.borda}`,
          }}>
            {info.rotulo}
          </span>
        </div>

        {/* Todas as metricas da categoria, nao so uma: e a soma delas que
            produz o veredito, e esconder as outras faria o veredito parecer
            arbitrario. */}
        {/* Grade com colunas fixas: o nome mais longo
            (confiabilidade_consistencia_total) passava da largura antiga e
            invadia o valor; e com larguras iguais as barras ficam alinhadas
            entre as linhas. */}
        <div style={{ display: 'grid', gridTemplateColumns: '216px 56px 54px minmax(0, 1fr)', columnGap: 10, rowGap: 6, alignItems: 'center', fontSize: 12 }}>
          {cat.metricas.map((m) => (
            <div key={m.metrica} style={{ display: 'contents' }}>
              <span style={{ color: 'var(--texto-fraco)', overflowWrap: 'anywhere' }}>{m.metrica}</span>
              <span className="mono" style={{ color: infoStatus(m.status).cor }}>
                {formatarValor(m.valor)}
              </span>
              <div style={{ height: 5, background: 'var(--trilho)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  width: `${preenchimento(m.valor, m.operador) * 100}%`,
                  height: '100%',
                  background: m.valor == null ? 'transparent' : infoStatus(m.status).cor,
                }} />
              </div>
              <span style={{ color: 'var(--texto-tenue)', fontSize: 11 }}>
                {descreverLimiar(m.limiar, m.operador)}
              </span>
            </div>
          ))}
          {nunca && (
            <span style={{ gridColumn: '1 / -1', fontSize: 12, color: 'var(--texto-tenue)' }}>
              Nenhum relatório gravado para esta categoria.
            </span>
          )}
        </div>

        <div style={{ textAlign: 'right' }}>
          {!nunca && (
            <>
              <div className="mono" style={{ fontSize: 11, color: 'var(--texto-fraco)' }}>
                {formatarMomento(cat.momento)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>
                {cat.de_bateria ? `automação · ${cat.n_turnos} turnos` : `conversa avulsa`}
                {cat.usou_juiz === false && ' · sem juiz'}
              </div>
              <Link to="/relatorios" style={{ fontSize: 12, fontWeight: 600 }}>ver relatório →</Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function VisaoGeral() {
  const [d, setD] = useState(null)
  const [erro, setErro] = useState(null)
  const navegar = useNavigate()

  useEffect(() => {
    api.visaoGeral().then(setD).catch((e) => setErro(e.message))
  }, [])

  const c = d?.contadores
  // Se alguma categoria esta lendo de conversa avulsa, o painel nao esta
  // representando o sistema — e isso precisa aparecer, nao ficar implicito.
  const avulsas = (d?.categorias ?? []).filter((x) => x.de_bateria === false)

  return (
    <>
      <Cabecalho titulo="Visão geral" legenda={d ? 'estado atual do sistema' : ''}>
        <button className="botao" onClick={() => navegar('/bateria')}>Executar automação</button>
        <button className="botao botao-primario" onClick={() => navegar('/avaliar')}>Rodar avaliação</button>
      </Cabecalho>

      <div style={{ padding: '22px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        {!d && !erro && (
          <div className="pulsando" style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>Carregando…</div>
        )}

        {d && (
          <>
            <div style={{ display: 'flex', gap: 26, alignItems: 'stretch', marginBottom: 24, flexWrap: 'wrap' }}>
              <Contador rotulo="Conversas manuais" valor={c.sessoes_manuais} />
              <Divisor />
              <Contador rotulo="Execuções da automação" valor={c.execucoes_bateria}
                dica="um arquivo de log por estímulo × modelo" />
              <Divisor />
              <Contador rotulo="Episódios" valor={c.episodios_bateria}
                dica="cada repetição de um estímulo conta um episódio" />
              <Divisor />
              <Contador rotulo="Turnos medidos" valor={c.turnos_bateria} />
              <Divisor />
              <Contador rotulo="Casos de teste" valor={c.estimulos}
                dica="cada caso é um estímulo: a entrada que a automação envia ao bot" />
              <Divisor />
              <Contador rotulo="Prompts" valor={c.prompts} />
              <Divisor />
              <Contador rotulo="Relatórios" valor={c.relatorios}
                dica="nada é sobrescrito: cada execução grava os seus" />
            </div>

            <div className="painel" style={{ overflow: 'hidden', marginBottom: 20 }}>
              <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--borda-suave)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700 }}>Estado das 6 categorias</div>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 2 }}>
                    Só a avaliação <strong>mais recente</strong>, seja qual for o juiz; as
                    anteriores e as dos outros juízes estão em Relatórios.
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 2 }}>
                    O veredito de cada uma é o <strong>pior</strong> das suas métricas — uma
                    categoria com uma métrica reprovada não passa.
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--texto-fraco)' }}>
                  {/* `nao_aplicavel` entrou na legenda porque passou a ocorrer:
                      numa conversa avulsa, as taxas de seguranca por estimulo
                      nao se aplicam, e um status sem legenda viraria um circulo
                      sem nome na tela. */}
                  {['atende', 'nao_atende', 'sem_dados', 'nao_aplicavel'].map((s) => (
                    <span key={s} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{
                        width: 9, height: 9, borderRadius: '50%',
                        background: infoStatus(s).tracejado ? 'transparent' : infoStatus(s).cor,
                        border: infoStatus(s).tracejado ? `1.5px dashed ${infoStatus(s).borda}` : 'none',
                      }} />
                      {infoStatus(s).rotulo}
                    </span>
                  ))}
                </div>
              </div>
              {d.categorias.map((cat) => <LinhaCategoria key={cat.categoria} cat={cat} />)}
            </div>

            {avulsas.length > 0 && (
              <div className="aviso" style={{ marginBottom: 20, maxWidth: 900 }}>
                {avulsas.length === 1 ? 'Uma categoria está' : `${avulsas.length} categorias estão`}{' '}
                mostrando o resultado de uma <strong>conversa avulsa</strong>, não da automação
                ({avulsas.map((x) => NOME_CATEGORIA[x.categoria]).join(', ')}). Uma conversa
                mede alguns turnos; a automação mede centenas. Não leia como estado do sistema.
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 14 }}>
              <div className="painel" style={{ padding: '14px 18px' }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>Últimas conversas manuais</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {d.ultimas_sessoes.map((s) => (
                    <Link key={s.sessao_id} to={`/sessoes/${s.sessao_id}`}
                      style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--texto-medio)' }}>
                      <span className="mono">{s.sessao_id}</span>
                      <span style={{ color: 'var(--texto-fraco)' }}>
                        {s.turnos} turnos · {s.acordo_fechado ? 'acordo fechado' : 'sem acordo'}
                      </span>
                    </Link>
                  ))}
                  {d.ultimas_sessoes.length === 0 && (
                    <span style={{ fontSize: 13, color: 'var(--texto-tenue)' }}>Nenhuma ainda.</span>
                  )}
                </div>
              </div>

              <div className="painel" style={{ padding: '14px 18px' }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>
                  Tom <span style={{ fontWeight: 400, color: 'var(--texto-fraco)' }}>— fora das 6 categorias</span>
                </div>
                {d.tom.media != null ? (
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}>
                    <div className="mono" style={{ fontSize: 32, fontWeight: 700, lineHeight: 1 }}>
                      {d.tom.media.toFixed(2).replace('.', ',')}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.5 }}>
                      nota 1–5 de cordialidade<br />
                      média de {d.tom.n_sessoes} sessão(ões) avaliada(s) sob demanda
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 13, color: 'var(--texto-tenue)', lineHeight: 1.5 }}>
                    Nenhuma sessão teve o tom avaliado. É medida auxiliar e sob demanda:
                    custa uma chamada ao juiz por conversa.
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
