/* Leitura de metricas.
 *
 * Desde 24/10/2026 toda metrica nova vai de 0 a 1 na MESMA direcao: quanto
 * maior, melhor, e atende se valor >= limiar. As de alvo zero passaram a sair
 * como complemento (`seguranca_sem_toxicidade`, `equidade_sem_disparidade`).
 *
 * O operador "==" continua tratado abaixo so para os relatorios ANTIGOS, em
 * que `seguranca_toxicidade = 0,0000` era o melhor resultado e pintaria de
 * vermelho se a cor saisse do valor. Por isso a cor continua saindo de
 * `status`, que o backend calcula, e nunca do valor bruto.
 */

export const STATUS = {
  atende: { rotulo: 'atende', cor: 'var(--verde)', fundo: '#e7f2ec', borda: '#bcd9cb' },
  nao_atende: { rotulo: 'não atende', cor: 'var(--vermelho)', fundo: '#fbeae8', borda: '#e8c3be' },
  // "sem dados" NAO e neutro-positivo: e "nao ha amostra suficiente para dizer
  // nada" (ex.: metrica de juiz numa avaliacao rodada sem juiz). Precisa ser
  // visualmente distinto dos outros dois, nao um meio-termo na escala de cor.
  sem_dados: { rotulo: 'sem dados', cor: 'var(--texto-fraco)', fundo: 'transparent', borda: 'var(--texto-tenue)', tracejado: true },
  // A metrica nao faz sentido para este recorte — confiabilidade e equidade
  // exigem reexecucao da mesma entrada e variantes pareadas, coisas que uma
  // conversa avulsa nao tem. Nao e falha nem aprovacao.
  nao_aplicavel: { rotulo: 'não se aplica', cor: 'var(--texto-tenue)', fundo: 'transparent', borda: 'var(--borda-forte)', tracejado: true },
  sem_limiar: { rotulo: 'sem limiar', cor: 'var(--texto-fraco)', fundo: 'transparent', borda: 'var(--borda-forte)', tracejado: true },
}

export function infoStatus(status) {
  return STATUS[status] || { rotulo: status, cor: 'var(--texto-fraco)', fundo: 'transparent', borda: 'var(--borda)' }
}

export function estiloChip(status) {
  const s = infoStatus(status)
  return {
    color: s.cor,
    background: s.fundo,
    border: `1px ${s.tracejado ? 'dashed' : 'solid'} ${s.borda}`,
  }
}

/** Numero com 4 casas e virgula decimal; travessao quando nao ha valor. */
export function formatarValor(valor) {
  if (valor === null || valor === undefined) return '—'
  return valor.toFixed(4).replace('.', ',')
}

/** Como o limiar deve ser lido, em palavras. */
export function descreverLimiar(limiar, operador) {
  if (limiar === null || limiar === undefined || !operador) return '—'
  const alvo = limiar.toFixed(2).replace('.', ',')
  return operador === '=='
    ? `alvo ${alvo} · quanto menor, melhor`
    : `mínimo ${alvo} · quanto maior, melhor`
}

/**
 * Quanto da barra preencher, ja corrigido pela direcao.
 * Numa metrica "==", o valor 0 (ideal) enche a barra; 1 (pessimo) esvazia.
 * Sem essa inversao o medidor mentiria exatamente nas metricas de seguranca.
 */
export function preenchimento(valor, operador) {
  if (valor === null || valor === undefined) return 0
  const p = operador === '==' ? 1 - valor : valor
  return Math.max(0, Math.min(1, p))
}

/** Segundos em texto curto: "45 s", "3 min", "1 h 12 min". */
export function duracao(segundos) {
  if (segundos == null) return '—'
  const s = Math.max(0, Math.round(segundos))
  if (s < 60) return `${s} s`
  const min = Math.round(s / 60)
  if (min < 60) return `${min} min`
  return `${Math.floor(min / 60)} h ${min % 60} min`
}

/** Nome legivel das categorias, na ordem em que o framework as define. */
export const NOME_CATEGORIA = {
  confiabilidade: 'Confiabilidade',
  precisao: 'Precisão',
  aderencia_contexto: 'Aderência ao contexto',
  seguranca: 'Segurança',
  equidade: 'Equidade',
  robustez: 'Robustez',
}
