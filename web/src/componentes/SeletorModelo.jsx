import { useEffect, useState } from 'react'
import { api } from '../api.js'

/* Seletor de modelo reutilizavel, usado nos tres papeis (bot, juiz,
   simulador). Estava previsto no Bloco 0 do briefing como um componente unico,
   e nao como um campo por tela, justamente para que acrescentar um provedor
   apareca nos tres lugares de uma vez.

   Nao e um <select> de opcoes fixas: a lista vem do proprio provedor. Um
   catalogo escrito a mao envelhece em silencio e passa a oferecer modelos que
   a conta nao tem mais. */

// Uma requisicao para todos os seletores da tela, nao uma por instancia.
let promessa = null
function carregar(forcar = false) {
  if (forcar || !promessa) promessa = api.catalogoModelos(forcar)
  return promessa
}

const AVISO_CHAVE = {
  false: 'Chave inválida ou sem permissão — este provedor vai recusar as chamadas.',
  null: 'Sem chave no .env — este provedor não pode ser usado.',
}

/* Anota o que o nome do modelo ja diz, para a escolha nao depender de quem le
   reconhecer a convencao do provedor. "-exp" e "-vision" importam aqui: o bot
   sob teste conversa em texto, entao um modelo experimental de visao roda,
   mas mede outra coisa. */
function anotar(id) {
  const marcas = []
  if (/-exp\b|-exp$|-preview|-beta/.test(id)) marcas.push('experimental')
  if (/vision|-vl\b/.test(id)) marcas.push('visão')
  return marcas.length ? ` — ${marcas.join(', ')}` : ''
}

export default function SeletorModelo({ papel, valor, onChange, aoDetectar }) {
  const [catalogo, setCatalogo] = useState(null)
  const [erro, setErro] = useState(null)

  useEffect(() => {
    carregar()
      .then((c) => { setCatalogo(c); aoDetectar?.(c) })
      .catch((e) => setErro(e.message))
  }, [])

  if (erro) {
    return <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)' }}>{erro}</div>
  }
  if (!catalogo) {
    return <div className="pulsando" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>carregando modelos…</div>
  }

  const doPapel = catalogo.papeis?.[papel]
  const provedores = catalogo.provedores || {}
  // O provedor configurado para este papel vem primeiro; os outros continuam
  // disponiveis, porque trocar de provedor e uma comparacao legitima.
  const ordem = Object.keys(provedores).sort((a, b) =>
    (a === doPapel?.provedor ? -1 : 0) - (b === doPapel?.provedor ? -1 : 0))

  const provedorSelecionado = valor ? valor.split(':')[0] : doPapel?.provedor
  const info = provedores[provedorSelecionado]
  const aviso = info && info.chave_valida !== true ? AVISO_CHAVE[info.chave_valida] : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <select
        value={valor || ''}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
          border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
        }}
      >
        <option value="">
          padrão do .env{doPapel ? ` (${doPapel.provedor}:${doPapel.modelo})` : ''}
        </option>
        {ordem.map((prov) => (
          <optgroup
            key={prov}
            label={
              `${prov}` +
              (provedores[prov].chave_valida === true ? '' :
               provedores[prov].chave_configurada ? ' — chave inválida' : ' — sem chave')
            }
          >
            {provedores[prov].modelos.map((m) => {
              const ehPadrao = prov === doPapel?.provedor && m === doPapel?.modelo
              return (
                <option key={`${prov}:${m}`} value={`${prov}:${m}`}>
                  {prov}:{m}{anotar(m)}{ehPadrao ? ' — padrão do .env' : ''}
                </option>
              )
            })}
          </optgroup>
        ))}
      </select>

      {aviso && (
        <span style={{ fontSize: 11, color: 'var(--vermelho)', lineHeight: 1.4 }}>{aviso}</span>
      )}
      {info?.origem === 'catalogo_reserva' && info.chave_valida !== false && (
        <span style={{ fontSize: 11, color: 'var(--texto-tenue)', lineHeight: 1.4 }}>
          Lista de reserva — o provedor não confirmou quais modelos a conta tem.
        </span>
      )}
      {info?.origem === 'provedor' && (
        <span style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>
          {info.modelos.length} modelo(s) confirmado(s) pelo provedor.
        </span>
      )}
    </div>
  )
}
