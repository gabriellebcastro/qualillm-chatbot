import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'

/* Concordancia entre dois juizes que avaliaram os MESMOS logs.

   Cada avaliacao com juiz grava os vereditos item a item; aqui duas delas
   sao casadas pela identidade do item e o kappa sai por metrica. Juntos, o
   custo e o tempo de cada juiz, que e a outra metade do custo-beneficio.

   Fidelidade e groundedness sao comparadas por TURNO ("tem alguma afirmacao
   nao sustentada?"), porque cada juiz decompoe a resposta em afirmacoes
   proprias e nao ha afirmacao comum aos dois. */

const ROTULO = {
  true: 'sim', false: 'não', com_falha: 'com falha', sem_falha: 'sem falha',
}

const NOME = {
  seguranca_toxicidade: 'Toxicidade (turno)',
  robustez_resistencia: 'Resistência a ataques (turno)',
  confiabilidade_equivalencia_par: 'Equivalência (par de respostas)',
  equidade_disparidade: 'Disparidade (par de variantes)',
  precisao_faithfulness_turno: 'Fidelidade factual (turno)',
  aderencia_groundedness_turno: 'Groundedness (turno)',
}

const num = (v, casas = 4) => (v === null || v === undefined ? '—' : v.toFixed(casas).replace('.', ','))

function Custo({ titulo, cab }) {
  const u = cab?.uso_do_juiz || {}
  return (
    <div className="painel" style={{ padding: '12px 16px', flex: 1, minWidth: 260 }}>
      <div className="rotulo" style={{ marginBottom: 6 }}>{titulo}</div>
      <div className="mono" style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{cab?.juiz}</div>
      <div style={{ fontSize: 13, color: 'var(--texto-suave)', lineHeight: 1.7 }}>
        {u.chamadas ?? '—'} chamadas · {(u.tokens_entrada ?? 0).toLocaleString('pt-BR')} tokens de entrada ·{' '}
        {(u.tokens_saida ?? 0).toLocaleString('pt-BR')} de saída<br />
        tempo somado {num(u.latencia_total_s, 1)} s ·{' '}
        {u.custo_estimado_usd != null
          ? <strong>US$ {num(u.custo_estimado_usd, 4)}</strong>
          : <span style={{ color: 'var(--texto-tenue)' }}>custo: preço não cadastrado</span>}
      </div>
    </div>
  )
}

export default function CompararJuizes() {
  const [lista, setLista] = useState(null)
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [res, setRes] = useState(null)
  const [erro, setErro] = useState(null)
  const [aberta, setAberta] = useState(null)

  useEffect(() => {
    api.listarJulgamentos()
      .then((js) => {
        setLista(js)
        if (js.length > 1) { setA(js[1].nome); setB(js[0].nome) }
      })
      .catch((e) => setErro(e.message))
  }, [])

  const comparar = () => {
    setErro(null); setRes(null)
    api.compararJuizes(a, b).then(setRes).catch((e) => setErro(e.message))
  }

  const seletor = (valor, set) => (
    <select value={valor} onChange={(e) => { set(e.target.value); setRes(null) }}
      style={{ padding: '8px 10px', fontSize: 13, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff', maxWidth: 380 }}>
      {(lista || []).map((j) => (
        <option key={j.nome} value={j.nome}>
          {j.juiz} · {(j.coletado_em || '').slice(0, 16)} · {j.total} vereditos
        </option>
      ))}
    </select>
  )

  return (
    <>
      <Cabecalho
        titulo="Comparar juízes"
        subtitulo="Concordância entre dois juízes que avaliaram as mesmas conversas, com o custo de cada um."
      />
      <div style={{ padding: '20px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>{erro}</div>
        )}

        <div className="aviso" style={{ marginBottom: 18, maxWidth: 940 }}>
          Gere as conversas uma vez e avalie-as duas vezes, em <strong>Rodar avaliação</strong>,
          trocando só o modelo do juiz. Cada avaliação grava os vereditos item a item; aqui
          os dois conjuntos são casados e o <strong>κ de Cohen</strong> mede quanto os juízes
          concordam além do acaso. Concordância bruta alta com κ baixo quer dizer acordo
          que o acaso já explicaria.
        </div>

        {lista !== null && lista.length < 2 && (
          <div style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>
            São precisas pelo menos duas avaliações com juiz. Hoje há {lista.length}.
          </div>
        )}

        {lista !== null && lista.length >= 2 && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginBottom: 20 }}>
            <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Juiz A</span>{seletor(a, setA)}
            <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Juiz B</span>{seletor(b, setB)}
            <button className="botao botao-primario" onClick={comparar} disabled={!a || !b || a === b}>Comparar</button>
          </div>
        )}

        {res && (
          <>
            {res.aviso && <div className="aviso" style={{ marginBottom: 14 }}>{res.aviso}</div>}
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 18 }}>
              <Custo titulo="Juiz A" cab={res.a} />
              <Custo titulo="Juiz B" cab={res.b} />
            </div>

            <div className="painel">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--texto-fraco)', fontSize: 12 }}>
                    <th style={{ padding: '10px 18px' }}>métrica</th>
                    <th style={{ padding: '10px 8px' }}>itens comuns</th>
                    <th style={{ padding: '10px 8px' }}>concordância bruta</th>
                    <th style={{ padding: '10px 8px' }}>κ</th>
                    <th style={{ padding: '10px 8px' }}>leitura</th>
                    <th style={{ padding: '10px 8px' }}>divergências</th>
                    <th style={{ padding: '10px 18px' }}>só um juiz</th>
                  </tr>
                </thead>
                <tbody>
                  {res.metricas.map((m) => (
                    <tr key={m.metrica} style={{ borderTop: '1px solid var(--borda-suave)' }}>
                      <td style={{ padding: '10px 18px' }}>
                        {NOME[m.metrica] || m.metrica}
                        <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>{m.metrica}</div>
                      </td>
                      <td style={{ padding: '10px 8px' }}>{m.n}</td>
                      <td style={{ padding: '10px 8px' }}>{num(m.concordancia_observada)}</td>
                      <td style={{ padding: '10px 8px', fontWeight: 700 }}>{num(m.kappa)}</td>
                      <td style={{ padding: '10px 8px' }}>{m.interpretacao}</td>
                      <td style={{ padding: '10px 8px' }}>
                        {m.divergentes ? (
                          <button className="botao" style={{ padding: '3px 10px' }}
                            onClick={() => setAberta(aberta === m.metrica ? null : m.metrica)}>
                            {m.divergentes} {aberta === m.metrica ? '▴' : '▾'}
                          </button>
                        ) : '0'}
                      </td>
                      <td style={{ padding: '10px 18px', color: 'var(--texto-fraco)' }}
                        title="Itens que só um dos juízes julgou (o outro falhou ou se absteve). Ficam fora do κ.">
                        {m.so_um_juiz}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ padding: '12px 18px', fontSize: 12, color: 'var(--texto-tenue)', borderTop: '1px solid var(--borda-suave)' }}>
                Escala de Landis &amp; Koch: &lt; 0,00 pobre · 0,00–0,20 leve · 0,21–0,40 razoável ·
                0,41–0,60 moderada · 0,61–0,80 substancial · 0,81–1,00 quase perfeita.
              </div>
            </div>

            {aberta && (
              <div className="painel" style={{ marginTop: 16, padding: '14px 18px' }}>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                  Onde os juízes discordaram — {NOME[aberta] || aberta}
                </div>
                {res.metricas.find((m) => m.metrica === aberta).divergencias.map((d) => (
                  <div key={d.chave} style={{ borderTop: '1px solid var(--borda-suave)', padding: '10px 0' }}>
                    <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 6 }}>
                      A <strong>{ROTULO[d.rotulo_a] || d.rotulo_a}</strong> · B{' '}
                      <strong>{ROTULO[d.rotulo_b] || d.rotulo_b}</strong>
                      <span className="mono" style={{ marginLeft: 8, color: 'var(--texto-tenue)' }}>{d.chave}</span>
                    </div>
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 13, color: 'var(--texto-suave)' }}>
                      {d.item_julgado || `${d.mensagem_usuario}\n\n${d.resposta_bot}`}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
