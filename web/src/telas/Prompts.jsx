import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA } from '../metricas.js'

const ORDEM_GRUPOS = ['bot', 'politicas', 'juiz', 'simulador']

const ABAS = [
  ['composto', 'Enviado ao juiz'],
  ['nucleo', 'Núcleo (genérico)'],
  ['dominio', 'Apêndice de domínio'],
]

/* O conteudo e mostrado LITERAL, em monoespacada, e nao renderizado como
   markdown. Num visualizador de prompt o que importa e exatamente o texto que
   chega ao modelo -- inclusive os "##", as listas e o espacamento, que fazem
   parte da instrucao. Renderizar esconderia justamente isso.

   O unico realce e nos titulos de secao, para dar para varrer um arquivo de
   14 KB sem transformar o texto. */
function Conteudo({ texto }) {
  return (
    <pre
      className="mono"
      style={{
        margin: 0, padding: '16px 18px', background: '#f6f7f9',
        border: '1px solid var(--borda-suave)', borderRadius: 2,
        fontSize: 12, lineHeight: 1.65, whiteSpace: 'pre-wrap',
        wordBreak: 'break-word', color: 'var(--texto-medio)',
      }}
    >
      {texto.split('\n').map((linha, i) => {
        const titulo = /^#{1,6}\s/.test(linha)
        return (
          <div
            key={i}
            style={titulo
              ? { color: 'var(--texto)', fontWeight: 700, marginTop: i ? 12 : 0 }
              : undefined}
          >
            {linha || ' '}
          </div>
        )
      })}
    </pre>
  )
}

export default function Prompts() {
  const [lista, setLista] = useState([])
  const [selecionado, setSelecionado] = useState(null)
  const [detalhe, setDetalhe] = useState(null)
  const [erro, setErro] = useState(null)
  const [aba, setAba] = useState('composto')

  useEffect(() => {
    api.listarPrompts()
      .then((ps) => {
        setLista(ps)
        if (ps.length) setSelecionado(ps[0].id)
      })
      .catch((e) => setErro(e.message))
  }, [])

  useEffect(() => {
    if (!selecionado) return
    setDetalhe(null)
    api.detalharPrompt(selecionado)
      .then((d) => { setDetalhe(d); setErro(null) })
      .catch((e) => setErro(e.message))
  }, [selecionado])

  const grupos = ORDEM_GRUPOS
    .map((g) => ({ grupo: g, itens: lista.filter((p) => p.grupo === g) }))
    .filter((g) => g.itens.length > 0)

  return (
    <>
      <Cabecalho titulo="Biblioteca de prompts" legenda={`${lista.length} arquivos versionados · somente leitura`} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* --- Lista --- */}
        <div style={{ width: 330, flex: 'none', borderRight: '1px solid var(--borda)', overflowY: 'auto', background: 'var(--painel)' }}>
          {grupos.map(({ grupo, itens }) => (
            <div key={grupo}>
              <div
                className="rotulo"
                style={{ padding: '14px 18px 6px', borderBottom: '1px solid var(--borda-suave)' }}
              >
                {itens[0].grupo_titulo}
              </div>
              {itens.map((p) => {
                const ativo = p.id === selecionado
                return (
                  <div
                    key={p.id}
                    onClick={() => setSelecionado(p.id)}
                    style={{
                      padding: '11px 18px',
                      borderBottom: '1px solid var(--borda-suave)',
                      cursor: 'pointer',
                      background: ativo ? 'var(--item-hover)' : 'transparent',
                      borderLeft: `3px solid ${ativo ? 'var(--acento)' : 'transparent'}`,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: ativo ? 700 : 600 }}>{p.titulo}</span>
                      {!p.existe && (
                        <span className="chip" style={{ color: 'var(--vermelho)', border: '1px solid #e8c3be', fontSize: 11 }}>
                          ausente
                        </span>
                      )}
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)', marginTop: 3 }}>
                      {p.arquivo}
                      {p.dominio && <><br />+ {p.dominio}</>}
                    </div>
                    {p.categoria && (
                      <div style={{ fontSize: 11, color: 'var(--acento)', marginTop: 3 }}>
                        mede {NOME_CATEGORIA[p.categoria] ?? p.categoria}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* --- Detalhe --- */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '22px 26px' }}>
          {erro && (
            <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
              {erro}
            </div>
          )}

          {detalhe && (
            <>
              <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{detalhe.titulo}</div>
              <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 14 }}>
                {detalhe.arquivo}
              </div>

              <div style={{ fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.6, marginBottom: 8, maxWidth: 760 }}>
                {detalhe.papel}
              </div>

              {detalhe.sem_prompt && (
                <div className="aviso" style={{ marginBottom: 14, maxWidth: 760 }}>
                  <strong>Sem prompt nesta categoria:</strong> {detalhe.sem_prompt}
                </div>
              )}

              {detalhe.grupo === 'politicas' && (
                <div className="aviso" style={{ marginBottom: 14, maxWidth: 760 }}>
                  Não é um prompt: é a <strong>política</strong> que o bot consulta. A cada
                  turno, os trechos mais próximos da mensagem do cliente são recuperados e
                  entram no contexto. É também contra este texto que o juiz de groundedness
                  confere o que o bot afirma sobre regras.
                </div>
              )}

              {detalhe.grupo === 'simulador' && (
                <div className="aviso" style={{ marginBottom: 14, maxWidth: 760 }}>
                  É um <strong>template</strong>: os campos entre chaves são preenchidos
                  com os dados de cada persona antes de ir ao modelo. O que aparece
                  abaixo é o template bruto, não o prompt final.
                </div>
              )}

              <div style={{ fontSize: 12, color: 'var(--texto-tenue)', marginBottom: 14 }}>
                Somente leitura nesta fase — editar prompt pela interface mudaria
                o sistema sob teste no meio da medição.
              </div>

              {detalhe.conteudo_composto ? (
                <>
                  <div style={{ fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.6, marginBottom: 10, maxWidth: 760 }}>
                    O juiz recebe o <strong>núcleo</strong> (genérico, do framework) seguido do{' '}
                    <strong>apêndice de domínio</strong> (desta aplicação). A primeira aba mostra
                    o texto composto, exatamente como vai ao modelo.
                  </div>
                  <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                    {ABAS.map(([id, rotulo]) => (
                      <button key={id} className={`botao${aba === id ? ' botao-primario' : ''}`}
                        style={{ padding: '5px 12px', fontSize: 12 }} onClick={() => setAba(id)}>
                        {rotulo}
                      </button>
                    ))}
                  </div>
                  {aba === 'dominio' && (
                    <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 8 }}>{detalhe.dominio}</div>
                  )}
                  <Conteudo texto={
                    aba === 'nucleo' ? detalhe.conteudo
                      : aba === 'dominio' ? (detalhe.conteudo_dominio || '')
                        : detalhe.conteudo_composto
                  } />
                </>
              ) : (
                <Conteudo texto={detalhe.conteudo} />
              )}
            </>
          )}

          {!detalhe && !erro && (
            <div className="pulsando" style={{ color: 'var(--texto-fraco)', fontSize: 13 }}>Carregando…</div>
          )}
        </div>
      </div>
    </>
  )
}
