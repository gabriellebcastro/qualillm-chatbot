import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA } from '../metricas.js'

/* Camada 4 — rotulagem humana as cegas e o kappa que sai dela.

   O veredito do juiz NAO vem nesta tela. Isso nao e economia de espaco: no
   CSV a coluna esta la e o que protege o cegamento e a instrucao de nao
   olhar, enquanto aqui o dado nao chega ao navegador. Ele aparece so na aba
   de resultado, depois de o rotulo estar gravado.

   Quem rotula responde a MESMA pergunta que o juiz respondeu, sobre a MESMA
   evidencia (`item_julgado`). Se as perguntas divergissem, o kappa mediria
   discordancia de enunciado em lugar da qualidade do juiz. */

const ESCALA = [
  ['< 0,00', 'pobre'],
  ['0,00–0,20', 'leve'],
  ['0,21–0,40', 'razoável'],
  ['0,41–0,60', 'moderada'],
  ['0,61–0,80', 'substancial'],
  ['0,81–1,00', 'quase perfeita'],
]

const ROTULO_BONITO = {
  true: 'sim',
  false: 'não',
  sustentada: 'sustentada',
  nao_sustentada: 'não sustentada',
  nao_verificavel: 'não verificável',
  fora_de_escopo: 'fora de escopo',
  evidencia_insuficiente: 'não dá para decidir',
}

function Pre({ children }) {
  return (
    <pre style={{
      margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      fontFamily: 'inherit', fontSize: 13, lineHeight: 1.55,
      color: 'var(--texto-suave)',
    }}>{children}</pre>
  )
}

/* Auxilio de leitura da rotulagem (17/11/2026). Separa o item julgado nas
   secoes que o juiz recebeu e, nas secoes de material (MATERIAL DE POLITICA
   RECEBIDO, FONTE), destaca os termos da AFIRMACAO. Nao sugere rotulo nem
   mostra veredito: e um Ctrl+F automatico, para achar o suporte num material
   longo. O realce fica so no material porque a conversa anterior e a resposta
   nao contam como suporte. */
const PARADAS = new Set(('para pelo pela pelos pelas como mais menos esse essa este esta isso '
  + 'isto aqui voce voces cliente atendente quando onde qual quais seus suas nosso nossa sobre '
  + 'entre depois antes ainda tambem apenas cada todo toda todos todas muito pode posso podem '
  + 'deve devem sera seria foram estao estou sendo fica ficar ficando valor').split(' '))

function base(c) { return c.normalize('NFD')[0].toLowerCase() }
function normaliza(s) { let o = ''; for (const c of s) o += base(c); return o }

function termosDaAfirmacao(afirmacao) {
  const palavras = normaliza(afirmacao).match(/[a-z0-9]+/g) || []
  const termos = new Set()
  for (const p of palavras) {
    if (p.length < 4 || PARADAS.has(p)) continue
    termos.add(p.length >= 7 ? p.slice(0, 6) : p)
  }
  return [...termos]
}

function Realcado({ texto, termos }) {
  if (!termos.length) return texto
  // normaliza char a char: os indices batem com o texto original
  const chars = [...texto]
  const norm = chars.map(base).join('')
  const re = new RegExp(`(?<![a-z0-9])(${termos.join('|')})[a-z0-9]*`, 'g')
  const partes = []
  let ultimo = 0, m
  while ((m = re.exec(norm))) {
    if (m.index > ultimo) partes.push(chars.slice(ultimo, m.index).join(''))
    partes.push(<mark key={m.index} style={{ background: 'var(--aviso-fundo)', color: 'var(--texto)', borderBottom: '1px solid var(--acento)', padding: 0 }}>
      {chars.slice(m.index, m.index + m[0].length).join('')}</mark>)
    ultimo = m.index + m[0].length
  }
  partes.push(chars.slice(ultimo).join(''))
  return partes
}

const SECOES_MATERIAL = ['MATERIAL DE POLÍTICA RECEBIDO', 'FONTE']

function ItemJulgado({ texto }) {
  let afirmacao = ''
  let corpo = texto
  if (texto.startsWith('AFIRMACAO:')) {
    const i = texto.indexOf('\n')
    afirmacao = (i < 0 ? texto : texto.slice(0, i)).replace('AFIRMACAO:', '').trim()
    corpo = i < 0 ? '' : texto.slice(i + 1)
  }
  const termos = afirmacao ? termosDaAfirmacao(afirmacao) : []
  const secoes = []
  for (const bloco of corpo.split(/^## /m)) {
    if (!bloco.trim()) continue
    const j = bloco.indexOf('\n')
    const titulo = (j < 0 ? bloco : bloco.slice(0, j)).trim()
    secoes.push({ titulo, texto: j < 0 ? '' : bloco.slice(j + 1).trim() })
  }
  if (!secoes.length || (secoes.length === 1 && !corpo.trimStart().startsWith('## '))) {
    return <>{afirmacao && <CaixaAfirmacao afirmacao={afirmacao} />}<Pre>{corpo}</Pre></>
  }
  return (
    <>
      {afirmacao && <CaixaAfirmacao afirmacao={afirmacao} />}
      {secoes.map((s, k) => {
        const material = SECOES_MATERIAL.includes(s.titulo)
        return (
          <div key={k} style={{
            marginBottom: 14, padding: material ? '10px 12px' : 0,
            border: material ? '1px solid var(--acento)' : 'none', borderRadius: 6,
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: material ? 'var(--acento-escuro)' : 'var(--texto-fraco)', marginBottom: 4 }}>
              {s.titulo}{material && termos.length ? ' · termos da afirmação destacados' : ''}
            </div>
            {material
              ? s.texto.split(/^(### .*)$/m).map((p, n) => p.startsWith('### ')
                  ? <div key={n} style={{ fontSize: 12, fontWeight: 700, color: 'var(--texto-medio)', margin: '10px 0 2px', borderTop: n ? '1px dashed var(--borda)' : 'none', paddingTop: n ? 8 : 0 }}>{p.slice(4)}</div>
                  : <Pre key={n}><Realcado texto={p.trim()} termos={termos} /></Pre>)
              : <Pre>{s.texto}</Pre>}
          </div>
        )
      })}
    </>
  )
}

function CaixaAfirmacao({ afirmacao }) {
  return (
    <div style={{ marginBottom: 14, padding: '10px 12px', background: 'var(--linha-hover)', borderLeft: '3px solid var(--acento)', borderRadius: 4 }}>
      <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 2 }}>Afirmação a julgar</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--texto)' }}>{afirmacao}</div>
    </div>
  )
}

export default function Kappa() {
  const [amostras, setAmostras] = useState(null)
  const [nome, setNome] = useState('')
  const [dados, setDados] = useState(null)
  const [indice, setIndice] = useState(0)
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState(null)
  const [gravando, setGravando] = useState(false)
  const [julgamentos, setJulgamentos] = useState([])
  const [origemNova, setOrigemNova] = useState('')
  const [porMetrica, setPorMetrica] = useState(20)
  // Julgamentos de OUTRO juiz sobre os mesmos logs: o que ele acusou também
  // entra na amostra, para ela não favorecer o juiz de origem no κ contra B.
  const [uniao, setUniao] = useState('')
  const [contra, setContra] = useState('')

  const carregarAmostras = (selecionar) =>
    api.listarAmostrasKappa()
      .then((as) => {
        setAmostras(as)
        if (selecionar) setNome(selecionar)
        else if (as.length) setNome(as[0].nome)
      })
      .catch((e) => setErro(e.message))

  useEffect(() => {
    carregarAmostras()
    api.listarJulgamentos()
      .then((js) => { setJulgamentos(js); if (js.length) setOrigemNova(js[0].nome) })
      .catch(() => {})
  }, [])

  async function gerarAmostra() {
    setErro(null)
    try {
      const nova = await api.gerarAmostraKappa(origemNova, porMetrica, uniao ? [uniao] : [])
      await carregarAmostras(nova.nome)
    } catch (e) {
      setErro(e.message)
    }
  }

  useEffect(() => {
    if (!nome) return
    setResultado(null)
    setIndice(0)
    api.itensKappa(nome).then(setDados).catch((e) => setErro(e.message))
  }, [nome])

  async function rotular(rotulo) {
    const item = dados.itens[indice]
    setGravando(true)
    setErro(null)
    try {
      await api.rotularKappa(nome, item.id, rotulo)
      const atualizado = { ...dados }
      atualizado.itens = dados.itens.map((i, k) =>
        k === indice ? { ...i, rotulo_humano: rotulo } : i)
      atualizado.rotuladas = atualizado.itens.filter((i) => i.rotulo_humano).length
      setDados(atualizado)
      // Avanca para o proximo PENDENTE, nao para o proximo da lista: rotular
      // em sequencia sem reencontrar o que ja foi feito.
      const proximo = atualizado.itens.findIndex((i, k) => k > indice && !i.rotulo_humano)
      if (proximo >= 0) setIndice(proximo)
      else if (indice < atualizado.itens.length - 1) setIndice(indice + 1)
    } catch (e) {
      setErro(e.message)
    } finally {
      setGravando(false)
    }
  }

  async function verResultado() {
    setErro(null)
    try {
      setResultado(await api.resultadoKappa(nome, contra || null))
    } catch (e) {
      setErro(e.message)
    }
  }

  const item = dados?.itens?.[indice]
  const pendentes = dados ? dados.total - dados.rotuladas : 0

  return (
    <>
      <Cabecalho
        titulo="Rotulagem humana"
        subtitulo="valida o juiz: uma pessoa rotula às cegas e o kappa mede a concordância com ele"
        legenda={dados ? `${dados.rotuladas}/${dados.total} rotulados · ${pendentes} pendentes` : ''}
      >
        {dados && julgamentos.length > 1 && (
          <select
            value={contra}
            onChange={(e) => { setContra(e.target.value); setResultado(null) }}
            title="Os mesmos rótulos humanos, comparados também com outro juiz"
            style={{ padding: '8px 10px', fontSize: 13, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff', maxWidth: 320 }}
          >
            <option value="">sem segundo juiz</option>
            {julgamentos.filter((j) => j.nome !== dados?.origem).map((j) => (
              <option key={j.nome} value={j.nome}>contra {j.juiz} · {(j.coletado_em || '').slice(0, 16)}</option>
            ))}
          </select>
        )}
        {dados && (
          <button className="botao" onClick={verResultado} disabled={!dados.rotuladas}>
            Ver o κ
          </button>
        )}
      </Cabecalho>

      <div style={{ padding: '24px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        <div className="painel" style={{ padding: '14px 18px', marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: 'var(--texto-fraco)', lineHeight: 1.55 }}>
            Você responde aqui a <strong>mesma pergunta que o juiz respondeu</strong>,
            sobre a mesma evidência. O veredito dele <strong>não é enviado para
            esta tela</strong> — ele aparece só depois, no κ. É o que torna a
            rotulagem cega por construção, e não por disciplina.
          </div>
          {Boolean(amostras?.length) && (
            <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Amostra</span>
              <select
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                style={{ padding: '8px 10px', fontSize: 13, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff' }}
              >
                {amostras.map((a) => (
                  <option key={a.nome} value={a.nome}>
                    {a.momento} — {a.rotuladas}/{a.total} rotulados
                  </option>
                ))}
              </select>
            </div>
          )}
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--borda-suave)' }}>
            <div style={{ fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.55, marginBottom: 8 }}>
              <strong>Nova amostra.</strong> Sorteada dos vereditos de uma avaliação já
              feita — os mesmos que entraram no relatório. Não chama o juiz de novo e
              não gasta crédito.
            </div>
            {julgamentos.length ? (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <select
                  value={origemNova}
                  onChange={(e) => { setOrigemNova(e.target.value); setUniao('') }}
                  style={{ padding: '8px 10px', fontSize: 13, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff' }}
                >
                  {julgamentos.map((j) => (
                    <option key={j.nome} value={j.nome}>
                      {j.juiz} · {(j.coletado_em || '').slice(0, 16)} · {j.total} vereditos
                    </option>
                  ))}
                </select>
                {julgamentos.length > 1 && (
                  <select
                    value={uniao}
                    onChange={(e) => setUniao(e.target.value)}
                    title="Os casos que este outro juiz acusou também entram na amostra, para ela não favorecer o juiz de origem na comparação"
                    style={{ padding: '8px 10px', fontSize: 13, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff', maxWidth: 320 }}
                  >
                    <option value="">só os casos acusados por este juiz</option>
                    {julgamentos.filter((j) => j.nome !== origemNova).map((j) => (
                      <option key={j.nome} value={j.nome}>
                        + os acusados por {j.juiz} · {(j.coletado_em || '').slice(0, 16)}
                      </option>
                    ))}
                  </select>
                )}
                <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>itens por métrica</span>
                <input
                  type="number" min="1" value={porMetrica}
                  onChange={(e) => setPorMetrica(Number(e.target.value) || 20)}
                  style={{ width: 64, padding: '7px 8px', fontSize: 13, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2 }}
                />
                <button className="botao" onClick={gerarAmostra} disabled={!origemNova}>Gerar amostra</button>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>
                Nenhuma avaliação com juiz ainda. Rode uma em <strong>Rodar avaliação</strong>,
                com o juiz ligado; os vereditos dela aparecem aqui.
              </div>
            )}
          </div>
        </div>

        {/* --- Resultado (revela o juiz) --- */}
        {resultado && (
          <div className="painel" style={{ marginBottom: 20 }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--borda-suave)' }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>κ de Cohen por métrica</div>
              <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 4, lineHeight: 1.5 }}>
                <strong>Po</strong> é a concordância crua e <strong>Pe</strong> a
                esperada pelo acaso. Po alto com κ baixo significa que o acordo
                se explica pelo acaso — é o motivo de o κ existir.
              </div>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--texto-fraco)', fontSize: 12 }}>
                  <th style={{ padding: '8px 18px' }}>métrica</th>
                  <th style={{ padding: '8px 10px' }}>n</th>
                  <th style={{ padding: '8px 10px' }}>Po</th>
                  <th style={{ padding: '8px 10px' }}>Pe</th>
                  <th style={{ padding: '8px 10px' }}>κ</th>
                  <th style={{ padding: '8px 18px' }}>concordância</th>
                </tr>
              </thead>
              <tbody>
                {resultado.metricas.map((m) => (
                  <tr key={m.metrica} style={{ borderTop: '1px solid var(--borda-suave)' }}>
                    <td style={{ padding: '10px 18px' }}>{m.metrica}</td>
                    <td style={{ padding: '10px 10px' }}>{m.n}</td>
                    <td style={{ padding: '10px 10px' }}>{m.concordancia_observada.toFixed(4)}</td>
                    <td style={{ padding: '10px 10px' }}>{m.concordancia_esperada.toFixed(4)}</td>
                    <td style={{ padding: '10px 10px', fontWeight: 700 }}>
                      {m.kappa === null ? '—' : m.kappa.toFixed(4)}
                    </td>
                    <td style={{ padding: '10px 18px' }}>
                      {m.interpretacao}
                      {m.abstencoes_humanas ? (
                        <span style={{ color: 'var(--texto-tenue)', fontSize: 12 }}> · {m.abstencoes_humanas} abstenção(ões) fora</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {resultado.contra_segundo_juiz && (
              <div style={{ borderTop: '1px solid var(--borda-suave)' }}>
                <div style={{ padding: '14px 18px 6px', fontSize: 14, fontWeight: 700 }}>
                  Os mesmos rótulos contra {resultado.contra_segundo_juiz.juiz}
                </div>
                <div style={{ padding: '0 18px 8px', fontSize: 12, color: 'var(--texto-fraco)', lineHeight: 1.5 }}>
                  Uma rotulagem serve aos dois juízes: os itens são casados pela identidade.
                  Fidelidade e groundedness ficam de fora, porque a afirmação que você rotulou
                  foi recortada pelo primeiro juiz e não existe no segundo.
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <tbody>
                    {resultado.contra_segundo_juiz.metricas.map((m) => (
                      <tr key={m.metrica} style={{ borderTop: '1px solid var(--borda-suave)' }}>
                        <td style={{ padding: '10px 18px' }}>{m.metrica}</td>
                        <td style={{ padding: '10px 10px' }}>n {m.n}</td>
                        <td style={{ padding: '10px 10px' }}>Po {m.concordancia_observada.toFixed(4)}</td>
                        <td style={{ padding: '10px 10px', fontWeight: 700 }}>κ {m.kappa === null ? '—' : m.kappa.toFixed(4)}</td>
                        <td style={{ padding: '10px 18px' }}>{m.interpretacao}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div style={{ padding: '12px 18px', fontSize: 12, color: 'var(--texto-tenue)', borderTop: '1px solid var(--borda-suave)' }}>
              Escala de Landis &amp; Koch: {ESCALA.map(([f, r]) => `${f} ${r}`).join(' · ')}.
              κ aparece como — quando os dois usaram uma única categoria em todos
              os casos: não há acordo a medir além do acaso.
            </div>

            {Boolean(resultado.divergencias.length) && (
              <div style={{ borderTop: '1px solid var(--borda-suave)', padding: '14px 18px' }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>
                  Onde vocês discordaram ({resultado.divergencias.length})
                </div>
                <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 12, lineHeight: 1.5 }}>
                  É daqui que sai a revisão do critério do juiz quando o κ fica baixo.
                </div>
                {resultado.divergencias.map((d) => (
                  <div key={`${d.metrica}-${d.id}`} style={{ borderTop: '1px solid var(--borda-suave)', padding: '12px 0' }}>
                    <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 6 }}>
                      #{d.id} · {d.metrica} · humano{' '}
                      <strong>{ROTULO_BONITO[d.rotulo_humano] || d.rotulo_humano}</strong>
                      {' '}· juiz{' '}
                      <strong>{ROTULO_BONITO[d.rotulo_juiz] || d.rotulo_juiz}</strong>
                    </div>
                    <Pre>{d.item_julgado || `${d.mensagem_usuario}\n\n${d.resposta_bot}`}</Pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* --- Rotulagem --- */}
        {item && (
          <div className="painel">
            <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--borda-suave)', display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700 }}>{item.pergunta}</div>
                <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 4 }}>
                  item #{item.id} de {dados.total} · {NOME_CATEGORIA[item.metrica?.split('_')[0]] || ''}{' '}
                  <span style={{ color: 'var(--texto-tenue)' }}>({item.metrica})</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button className="botao" onClick={() => setIndice(Math.max(0, indice - 1))} disabled={indice === 0}>
                  anterior
                </button>
                <button className="botao" onClick={() => setIndice(Math.min(dados.itens.length - 1, indice + 1))} disabled={indice >= dados.itens.length - 1}>
                  próximo
                </button>
              </div>
            </div>

            <div style={{ padding: '16px 18px' }}>
              {item.item_julgado ? (
                <ItemJulgado texto={item.item_julgado} />
              ) : (
                <>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 4 }}>Cliente</div>
                  <Pre>{item.mensagem_usuario}</Pre>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)', margin: '14px 0 4px' }}>Atendente</div>
                  <Pre>{item.resposta_bot}</Pre>
                </>
              )}
            </div>

            <div style={{ padding: '14px 18px', borderTop: '1px solid var(--borda-suave)', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {item.rotulos_possiveis.map((r) => (
                <button
                  key={r}
                  className={item.rotulo_humano === r ? 'botao botao-primario' : 'botao'}
                  onClick={() => rotular(r)}
                  disabled={gravando}
                >
                  {ROTULO_BONITO[r] || r}
                </button>
              ))}
              {item.rotulo_humano && (
                <span style={{ fontSize: 12, color: 'var(--texto-fraco)', marginLeft: 4 }}>
                  já rotulado — clicar de novo troca o rótulo
                </span>
              )}
            </div>
          </div>
        )}

        {dados && !dados.itens.length && (
          <div className="painel" style={{ padding: '16px 18px', fontSize: 13, color: 'var(--texto-suave)' }}>
            Esta amostra não tem itens.
          </div>
        )}
      </div>
    </>
  )
}
