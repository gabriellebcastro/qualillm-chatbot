import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import ChipVia, { VIAS } from '../componentes/ChipVia.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA } from '../metricas.js'

/* O corpo de cada estimulo muda por via, e e isso que a tela precisa mostrar:
   a entrada fixa de um caso, a lista de mensagens de um roteiro, o perfil de
   uma persona. Um unico "conteudo" generico esconderia a diferenca entre as
   tres, que e o ponto do inventario. */
function Corpo({ estimulo }) {
  const c = estimulo.conteudo || {}
  const bloco = { fontSize: 13, lineHeight: 1.55, color: 'var(--texto-medio)' }

  if (estimulo.via === 'reinjecao') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div>
          <div className="rotulo" style={{ marginBottom: 3 }}>Entrada</div>
          <div style={bloco}>{c.entrada}</div>
        </div>
        {c.setup && (
          <div>
            <div className="rotulo" style={{ marginBottom: 3 }}>Estado inicial</div>
            <pre className="mono" style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5, color: 'var(--texto-fraco)', whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(c.setup, null, 2)}
            </pre>
          </div>
        )}
      </div>
    )
  }

  if (estimulo.via === 'roteiro') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div>
          <div className="rotulo" style={{ marginBottom: 5 }}>
            Mensagens ({(c.mensagens || []).length})
          </div>
          <ol style={{ margin: 0, paddingLeft: 20, ...bloco }}>
            {(c.mensagens || []).map((m, i) => <li key={i} style={{ marginBottom: 3 }}>{m}</li>)}
          </ol>
        </div>
        {c.parada_esperada && (
          <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
            Parada esperada: <span className="mono">{c.parada_esperada}</span>
          </div>
        )}
      </div>
    )
  }

  // simulador
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {c.perfil && (
        <div>
          <div className="rotulo" style={{ marginBottom: 3 }}>Perfil</div>
          <pre className="mono" style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5, color: 'var(--texto-fraco)', whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(c.perfil, null, 2)}
          </pre>
        </div>
      )}
      {c.comportamento && (
        <div><div className="rotulo" style={{ marginBottom: 3 }}>Comportamento</div><div style={bloco}>{c.comportamento}</div></div>
      )}
      {c.objetivo && (
        <div><div className="rotulo" style={{ marginBottom: 3 }}>Objetivo</div><div style={bloco}>{c.objetivo}</div></div>
      )}
      {c.encerramento && (
        <div><div className="rotulo" style={{ marginBottom: 3 }}>Encerramento</div><div style={bloco}>{c.encerramento}</div></div>
      )}
    </div>
  )
}

export default function Estimulos() {
  const [dados, setDados] = useState(null)
  const [via, setVia] = useState('')
  const [categoria, setCategoria] = useState('')
  const [aberto, setAberto] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    api.listarEstimulos(via, categoria)
      .then((d) => { setDados(d); setErro(null) })
      .catch((e) => setErro(e.message))
  }, [via, categoria])

  const lista = dados?.estimulos ?? []
  const categorias = Object.keys(dados?.por_categoria ?? {})

  function botaoFiltro(valor, atual, setar, rotulo, contagem) {
    const ativo = valor === atual
    return (
      <button
        key={valor || 'todos'}
        onClick={() => setar(valor)}
        className="botao"
        style={{
          padding: '6px 11px', fontSize: 12,
          background: ativo ? 'var(--acento)' : 'var(--painel)',
          borderColor: ativo ? 'var(--acento)' : 'var(--borda-forte)',
          color: ativo ? '#fff' : 'var(--texto)',
        }}
      >
        {rotulo}{contagem != null && ` (${contagem})`}
      </button>
    )
  }

  return (
    <>
      <Cabecalho
        titulo="Inventário de casos de teste"
        subtitulo="cada caso é um estímulo: a entrada que a automação envia ao bot"
        legenda={dados ? `${lista.length} de ${dados.total} · ${dados.episodios_do_filtro} episódios` : ''}
      />

      <div style={{ padding: '20px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        <div style={{ fontSize: 13, color: 'var(--texto-fraco)', lineHeight: 1.55, marginBottom: 14, maxWidth: 820 }}>
          Derivado dos arquivos em <span className="mono">tests/</span> a cada
          carregamento, não do inventário gravado — assim a tela nunca mostra um
          conjunto diferente do que a automação executaria. O <strong>id</strong> de
          cada estímulo é o mesmo <span className="mono">meta.origem_id</span> do
          log, que liga todo resultado ao caso planejado.
        </div>

        {/* --- Filtros --- */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className="rotulo" style={{ width: 66 }}>Via</span>
            {botaoFiltro('', via, setVia, 'todas', dados?.total)}
            {Object.keys(VIAS).map((v) =>
              botaoFiltro(v, via, setVia, VIAS[v].rotulo, dados?.por_via?.[v]))}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className="rotulo" style={{ width: 66 }}>Categoria</span>
            {botaoFiltro('', categoria, setCategoria, 'todas')}
            {categorias.map((c) =>
              botaoFiltro(c, categoria, setCategoria, NOME_CATEGORIA[c] ?? c, dados.por_categoria[c]))}
          </div>
        </div>

        {/* --- Lista --- */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {lista.map((e) => {
            const expandido = aberto === e.id
            return (
              <div key={e.id} className="painel">
                <div
                  onClick={() => setAberto(expandido ? null : e.id)}
                  style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', gap: 14, alignItems: 'flex-start' }}
                >
                  <span style={{ color: 'var(--acento)', fontSize: 13, marginTop: 2 }}>
                    {expandido ? '▾' : '▸'}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4 }}>
                      <span className="mono" style={{ fontSize: 13, fontWeight: 700 }}>{e.id}</span>
                      <ChipVia via={e.via} />
                      <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
                        {e.n_repeticoes} episódio(s)
                      </span>
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.5 }}>
                      {e.descricao}
                    </div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                      {e.categorias_alvo.map((c) => (
                        <span key={c} className="chip" style={{ fontSize: 11, color: 'var(--texto-fraco)', borderColor: 'var(--borda)' }}>
                          {NOME_CATEGORIA[c] ?? c}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {expandido && (
                  <div style={{ padding: '0 16px 14px 44px', borderTop: '1px solid var(--borda-suave)', paddingTop: 12 }}>
                    <Corpo estimulo={e} />
                    <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)', marginTop: 12 }}>
                      {e.arquivo_origem}
                      {e.n_repeticoes_declarado == null &&
                        ` · repetições não declaradas no arquivo, usando o padrão (${e.n_repeticoes})`}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          {dados && lista.length === 0 && (
            <div style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>
              Nenhum estímulo com esses filtros.
            </div>
          )}
        </div>
      </div>
    </>
  )
}
