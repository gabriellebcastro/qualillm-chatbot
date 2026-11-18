import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  NOME_CATEGORIA, descreverLimiar, estiloChip, formatarValor, infoStatus, preenchimento,
} from '../metricas.js'

const COLUNAS = '1.5fr 1fr .7fr 1.4fr .5fr .6fr'

/* Tabela de metricas usada tanto na avaliacao de uma conversa (telas/Sessao)
   quanto na leitura de um relatorio gravado (telas/Relatorios). As duas
   mostram exatamente a mesma coisa, e a regra de direcao e delicada demais
   para viver em duas copias que podem divergir. */

const pct = (v) => `${(v * 100).toFixed(0)}%`
const dec = (v) => v.toFixed(2).replace('.', ',')

/* Grau de certeza: o que a amostra garante do valor medido. Nao muda o
   veredito; diz quanto confiar nele.

   Os numeros do intervalo aparecem sempre; a FRASE so quando ha algo a
   ponderar (leitura inconclusiva: o limiar cai dentro da faixa). Nas
   metricas firmes, so os numeros, para nao encher a tabela de ressalvas. */
function Certeza({ c, valor }) {
  if (!c) return null
  const [inf, sup] = c.intervalo
  const semFalha = valor >= 1 && sup >= 1
  const frase = c.leitura !== 'inconclusivo' ? null
    : semFalha
      ? `nenhuma falha na amostra, mas a falha real pode chegar a ${pct(1 - inf)} — zero na amostra não é zero no mundo.`
      : 'o limiar cai dentro do intervalo: a amostra não basta para decidir com segurança.'
  return (
    <div style={{ fontSize: 12, color: frase && !semFalha ? 'var(--acento)' : 'var(--texto-fraco)', marginTop: 6, lineHeight: 1.5 }}
      title="Intervalo de Wilson de 95%, modificado nas bordas (Brown, Cai e DasGupta, 2001, §4.1.1), contado sobre estímulos distintos (na equidade, grupos).">
      <span className="mono">intervalo 95%: {dec(inf)} – {dec(sup)}</span>
      <span style={{ color: 'var(--texto-tenue)' }}> · {c.n} estímulos</span>
      {frase && <> · {frase}</>}
    </div>
  )
}

/* Ocorrencias: TODAS as falhas da metrica, cada uma com o lugar onde ocorreu
   e a camada que a detectou. As tres `justificativas` sao amostra; isto e o
   que permite conferir a falha, uma a uma, ate a conversa. */
const ROTULO_CAMADA = { deterministica: 'determinística', juiz: 'juiz' }
const ROTULO_TIPO = { falha: 'falha', falha_juiz: 'falha do juiz', abstencao: 'abstenção' }

function linkConversa(o) {
  if (!o.sessao_id) return null
  // Execucao composta ("11×12", par de consistencia) nao e uma execucao so:
  // abre o estimulo inteiro.
  const params = new URLSearchParams()
  if (o.execucao_id !== '' && /^\d+$/.test(String(o.execucao_id))) {
    params.set('execucao', o.execucao_id)
    if (o.turno_id !== '') params.set('turno', o.turno_id)
  }
  const q = params.toString()
  return `/sessoes/${encodeURIComponent(o.sessao_id)}${q ? `?${q}` : ''}`
}

function baixarCsv(metrica, ocorrencias) {
  const campos = ['tipo', 'camada', 'estimulo', 'sessao_id', 'execucao_id', 'turno_id', 'detalhe', 'evidencia', 'justificativa']
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const linhas = [campos.join(';'), ...ocorrencias.map((o) => campos.map((c) => esc(o[c])).join(';'))]
  const blob = new Blob(['﻿' + linhas.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `ocorrencias__${metrica}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

function Ocorrencias({ m }) {
  const todas = m.ocorrencias || []
  const [aberto, setAberto] = useState(false)
  const [camada, setCamada] = useState('')
  const [tipo, setTipo] = useState('')
  const [estimulo, setEstimulo] = useState('')
  if (!todas.length) return null

  const falhas = todas.filter((o) => o.tipo === 'falha').length
  const outras = todas.length - falhas
  const estimulos = [...new Set(todas.map((o) => o.estimulo).filter(Boolean))].sort()
  const visiveis = todas.filter((o) =>
    (!camada || o.camada === camada) && (!tipo || o.tipo === tipo) && (!estimulo || o.estimulo === estimulo))
  const sel = { padding: '5px 8px', fontSize: 12, fontFamily: 'inherit', border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff' }

  return (
    <div style={{ marginTop: 8 }}>
      <button className="botao" onClick={() => setAberto(!aberto)} style={{ fontSize: 12, padding: '4px 10px' }}>
        {aberto ? 'Fechar ocorrências' : `Ver ocorrências (${falhas} falha${falhas === 1 ? '' : 's'}${outras ? ` + ${outras} do juiz` : ''})`}
      </button>
      {aberto && (
        <div style={{ marginTop: 8, border: '1px solid var(--borda-suave)', borderRadius: 2 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', padding: '8px 10px', borderBottom: '1px solid var(--borda-suave)' }}>
            <select value={camada} onChange={(e) => setCamada(e.target.value)} style={sel}>
              <option value="">Todas as camadas</option>
              <option value="deterministica">Determinística</option>
              <option value="juiz">Juiz</option>
            </select>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={sel}>
              <option value="">Todos os tipos</option>
              <option value="falha">Falha do sistema</option>
              <option value="falha_juiz">Falha do juiz</option>
              <option value="abstencao">Abstenção</option>
            </select>
            <select value={estimulo} onChange={(e) => setEstimulo(e.target.value)} style={sel}>
              <option value="">Todos os estímulos</option>
              {estimulos.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
            <span style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>{visiveis.length} de {todas.length}</span>
            <button className="botao" style={{ fontSize: 12, padding: '4px 10px', marginLeft: 'auto' }}
              onClick={() => baixarCsv(m.metrica, visiveis)}>
              Baixar CSV
            </button>
          </div>
          <div style={{ maxHeight: 420, overflowY: 'auto' }}>
            {visiveis.map((o, i) => {
              const link = linkConversa(o)
              return (
                <div key={i} style={{ padding: '9px 10px', borderTop: i ? '1px solid var(--borda-suave)' : 'none', fontSize: 12, lineHeight: 1.5 }}>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
                    <span className="chip" style={{ fontSize: 11, padding: '0 6px' }}>{ROTULO_CAMADA[o.camada] || o.camada}</span>
                    {o.tipo !== 'falha' && (
                      <span className="chip" style={{ fontSize: 11, padding: '0 6px', color: 'var(--texto-fraco)' }}>{ROTULO_TIPO[o.tipo] || o.tipo}</span>
                    )}
                    <span className="mono">{o.estimulo || o.sessao_id || '—'}</span>
                    {o.execucao_id !== '' && <span className="mono" style={{ color: 'var(--texto-fraco)' }}>exec {o.execucao_id}</span>}
                    {o.turno_id !== '' && <span className="mono" style={{ color: 'var(--texto-fraco)' }}>turno {o.turno_id}</span>}
                    {link && <Link to={link} style={{ marginLeft: 'auto', color: 'var(--acento)' }}>abrir conversa →</Link>}
                  </div>
                  <div style={{ marginTop: 3, fontWeight: 600 }}>{o.detalhe}</div>
                  {o.evidencia && (
                    <div className="mono" style={{ marginTop: 3, color: 'var(--texto-suave)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{o.evidencia}</div>
                  )}
                  {o.justificativa && (
                    <div style={{ marginTop: 3, color: 'var(--texto-fraco)', whiteSpace: 'pre-wrap' }}>{o.justificativa}</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function Linha({ m }) {
  const info = infoStatus(m.status)
  const motivo = m.nao_aplicavel
  const justificativas = m.justificativas || []
  return (
    <div style={{ borderBottom: '1px solid var(--borda-suave)', padding: '11px 18px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: COLUNAS, gap: 12, alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{m.metrica}</div>
          <div style={{ fontSize: 12, color: 'var(--texto-tenue)' }}>
            {NOME_CATEGORIA[m.categoria] ?? m.categoria}
          </div>
        </div>
        <div><span className="chip" style={estiloChip(m.status)}>{info.rotulo}</span></div>
        <div className="mono" style={{ fontSize: 14 }}>{formatarValor(m.valor)}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* O medidor le a direcao pelo operador, nunca pelo valor bruto:
              numa metrica "==" o 0 e o melhor resultado e enche a barra. */}
          <div style={{ width: 70, height: 6, background: 'var(--trilho)', borderRadius: 3, overflow: 'hidden', flex: 'none' }}>
            <div
              style={{
                width: `${preenchimento(m.valor, m.operador) * 100}%`,
                height: '100%',
                background: m.valor === null || m.valor === undefined ? 'transparent' : info.cor,
              }}
            />
          </div>
          <span style={{ fontSize: 11, color: 'var(--texto-fraco)' }}>
            {descreverLimiar(m.limiar, m.operador)}
          </span>
        </div>
        {/* Os DOIS numeros de amostra. As metricas que agregam por turno
            contam as N reexecucoes do mesmo estimulo como observacoes
            independentes, entao um n alto pode vir de poucos estimulos --
            e o limiar se le contra o segundo numero. */}
        <div className="mono" style={{ fontSize: 13, color: 'var(--texto-fraco)' }}>
          {m.n_amostras}
          {m.n_estimulos > 0 && m.n_estimulos !== m.n_amostras && (
            <span
              style={{ fontSize: 11, color: 'var(--texto-tenue)' }}
              title="Estímulos distintos que originaram essas observações. As reexecuções do mesmo estímulo não são observações independentes."
            >
              {' '}/ {m.n_estimulos} est.
            </span>
          )}
        </div>
        <div
          className="mono"
          style={{ fontSize: 13, color: m.falhas_juiz ? 'var(--vermelho)' : 'var(--texto-tenue)' }}
          title="Julgamentos que o juiz não devolveu ou que não puderam ser interpretados"
        >
          {m.falhas_juiz}
          {m.abstencoes > 0 && (
            <span
              style={{ fontSize: 11, color: 'var(--texto-tenue)' }}
              title="Abstenções do juiz por falta de evidência. Saem do denominador como as falhas, mas a causa é outra: falha é do avaliador, abstenção é da evidência."
            >
              {' '}+{m.abstencoes} abst.
            </span>
          )}
        </div>
      </div>

      <Certeza c={m.certeza} valor={m.valor} />
      {m.observacao && (
        <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 6, lineHeight: 1.5 }}>
          {m.observacao}
        </div>
      )}
      {m.status === 'nao_aplicavel' && motivo && (
        <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 6, lineHeight: 1.5, fontStyle: 'italic' }}>
          Não se aplica: {motivo}
        </div>
      )}
      {m.status === 'nao_atende' && justificativas.length > 0 && (
        <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 12, color: 'var(--texto-suave)', lineHeight: 1.5 }}>
          {justificativas.map((j, i) => <li key={i}>{j}</li>)}
        </ul>
      )}
      <Ocorrencias m={m} />
      {m.falhas_juiz > 0 && m.n_amostras === 0 && (
        <div className="aviso" style={{ marginTop: 8 }}>
          Nada foi medido: o juiz falhou em {m.falhas_juiz} de {m.falhas_juiz} chamadas.
          Não conta como aprovação nem como reprovação.
        </div>
      )}
    </div>
  )
}

export default function TabelaMetricas({ metricas }) {
  return (
    <div>
      <div
        className="rotulo"
        style={{
          display: 'grid', gridTemplateColumns: COLUNAS, gap: 12,
          padding: '10px 18px', borderBottom: '1px solid var(--borda-suave)',
        }}
      >
        <div>Métrica</div><div>Veredito</div><div>Valor</div>
        <div>Direção</div><div>n</div><div>Falhas juiz</div>
      </div>
      {metricas.map((m) => <Linha key={`${m.categoria}-${m.metrica}`} m={m} />)}
    </div>
  )
}
