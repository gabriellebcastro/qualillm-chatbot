import { useEffect, useState } from 'react'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA } from '../metricas.js'

/* Limiares sao parametros da instanciacao, nao constantes do codigo. Toda
   metrica se le na mesma direcao (0 a 1, quanto maior melhor, atende se
   valor >= limiar), entao a tela so precisa de um numero por linha.

   Organizada pelas seis categorias do framework. Cada linha diz o que a
   metrica mede e a MODALIDADE que a produz (deterministica, juiz LLM ou as
   duas). A justificativa de cada valor fica no texto do trabalho, nao aqui.

   Mudar aqui vale para as PROXIMAS avaliacoes. Relatorio ja gerado guarda na
   procedencia os limiares que usou e nao e reescrito. */

const virgula = (v) => v.toFixed(2).replace('.', ',')

const COR_MODALIDADE = {
  'Determinística': { cor: 'var(--texto-suave)', borda: 'var(--borda-forte)' },
  'Juiz LLM': { cor: 'var(--acento)', borda: 'var(--acento)' },
  'Determinística + Juiz LLM': { cor: 'var(--texto)', borda: 'var(--texto-fraco)' },
}

const COLUNAS = '1fr 210px 130px 90px'

export default function Limiares() {
  const [dados, setDados] = useState(null)
  const [edicao, setEdicao] = useState({})
  const [erro, setErro] = useState(null)
  const [salvo, setSalvo] = useState(false)

  const carregar = (d) => {
    setDados(d)
    setEdicao(Object.fromEntries(d.metricas.map((m) => [m.metrica, virgula(m.valor)])))
  }

  useEffect(() => {
    api.limiares().then(carregar).catch((e) => setErro(e.message))
  }, [])

  const numero = (texto) => Number(String(texto).replace(',', '.'))
  const invalidos = Object.entries(edicao).filter(([, t]) => {
    const n = numero(t)
    return t === '' || Number.isNaN(n) || n < 0 || n > 1
  }).map(([m]) => m)
  const alterados = dados
    ? dados.metricas.filter((m) => numero(edicao[m.metrica]) !== m.valor).length
    : 0

  const salvar = () => {
    setErro(null); setSalvo(false)
    const corpo = Object.fromEntries(Object.entries(edicao).map(([m, t]) => [m, numero(t)]))
    api.salvarLimiares(corpo)
      .then((d) => { carregar(d); setSalvo(true) })
      .catch((e) => setErro(e.message))
  }

  const restaurar = () => {
    setSalvo(false)
    setEdicao(Object.fromEntries(dados.metricas.map((m) => [m.metrica, virgula(m.padrao)])))
  }

  const categorias = []
  for (const m of dados?.metricas ?? []) {
    let c = categorias.find((x) => x.categoria === m.categoria)
    if (!c) categorias.push(c = { categoria: m.categoria, metricas: [] })
    c.metricas.push(m)
  }

  return (
    <>
      <Cabecalho
        titulo="Limiares"
        subtitulo="A nota mínima que cada métrica precisa atingir para a categoria ser considerada conforme."
      >
        <button className="botao" onClick={restaurar} disabled={!dados}>Restaurar padrão</button>
        <button className="botao botao-primario" onClick={salvar} disabled={!dados || invalidos.length > 0 || alterados === 0}>
          Salvar{alterados ? ` (${alterados})` : ''}
        </button>
      </Cabecalho>

      <div style={{ padding: '20px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}
        {salvo && (
          <div className="aviso" style={{ marginBottom: 16 }}>
            Limiares salvos. Valem para as próximas avaliações; relatórios já gerados não mudam.
          </div>
        )}

        <div style={{ fontSize: 13, color: 'var(--texto-fraco)', marginBottom: 18, maxWidth: 900, lineHeight: 1.55 }}>
          Toda métrica vai de 0 a 1, quanto maior melhor, e atende quando o valor é
          maior ou igual ao limiar.
        </div>

        <div className="painel" style={{ maxWidth: 940 }}>
          <div className="rotulo" style={{
            display: 'grid', gridTemplateColumns: COLUNAS, gap: 12,
            padding: '10px 18px', borderBottom: '1px solid var(--borda-suave)',
          }}>
            <div>Métrica</div><div>Modalidade</div><div>Limiar</div><div>Padrão</div>
          </div>

          {categorias.map(({ categoria, metricas }) => (
            <div key={categoria}>
              <div style={{
                padding: '12px 18px 6px', fontSize: 14, fontWeight: 700,
                borderTop: '1px solid var(--borda-suave)', background: 'var(--fundo-suave, #f6f7f9)',
              }}>
                {NOME_CATEGORIA[categoria] || categoria}
              </div>
              {metricas.map((m) => {
                const invalido = invalidos.includes(m.metrica)
                const estilo = COR_MODALIDADE[m.modalidade] || {}
                return (
                  <div key={m.metrica} style={{
                    display: 'grid', gridTemplateColumns: COLUNAS, gap: 12, alignItems: 'center',
                    padding: '9px 18px', borderTop: '1px solid var(--borda-suave)', fontSize: 14,
                  }}>
                    <div>
                      <div>{m.nome}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>{m.metrica}</div>
                    </div>
                    <div>
                      <span className="chip" style={{ fontSize: 11, color: estilo.cor, borderColor: estilo.borda }}>
                        {m.modalidade}
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: 'var(--texto-fraco)' }}>≥</span>
                      <input
                        value={edicao[m.metrica] ?? ''}
                        onChange={(e) => { setSalvo(false); setEdicao({ ...edicao, [m.metrica]: e.target.value }) }}
                        className="mono"
                        title={invalido ? 'use um valor de 0 a 1' : undefined}
                        style={{
                          width: 70, padding: '6px 8px', fontSize: 13, fontFamily: 'inherit',
                          border: `1px solid ${invalido ? 'var(--vermelho)' : 'var(--borda-forte)'}`, borderRadius: 2,
                        }}
                      />
                    </div>
                    <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>{virgula(m.padrao)}</div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
