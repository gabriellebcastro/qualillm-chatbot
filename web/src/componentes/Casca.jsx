import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { api } from '../api.js'

/* Estrutura da navegacao conforme design/QA LLM.dc.html: rotulo de grupo em
   maiuscula pequena, itens abaixo, e o rodape com os tres papeis de modelo. */
// Os grupos sao numerados na ordem em que o framework e usado, para quem
// chega de fora ler o menu como um roteiro: preparar, executar, avaliar e,
// por ultimo, validar o proprio juiz. A interacao manual fica a parte porque
// nao e etapa do fluxo.
const GRUPOS = [
  { titulo: '', itens: [{ para: '/visao-geral', rotulo: 'Visão geral' }] },
  {
    // A massa de dados e a fonte de verdade da automacao e do chat, por isso
    // abre o fluxo em vez de ficar sob a interacao manual.
    titulo: '1 · Preparar',
    itens: [
      { para: '/massa', rotulo: 'Massa de dados' },
      { para: '/prompts', rotulo: 'Biblioteca de prompts' },
      { para: '/estimulos', rotulo: 'Inventário de casos' },
    ],
  },
  {
    // "Bateria" continua sendo o termo interno -- nome dos scripts, do padrao
    // dos logs e do estado de retomada -- mas nao aparece nas telas: quem
    // chega de fora nao tem como saber que significa execucao automatizada.
    // As telas traduzem; o codigo nao muda.
    titulo: '2 · Executar',
    itens: [
      { para: '/bateria', rotulo: 'Executar automação' },
      { para: '/execucoes', rotulo: 'Execuções' },
    ],
  },
  {
    titulo: '3 · Avaliar',
    itens: [
      { para: '/limiares', rotulo: 'Limiares' },
      { para: '/avaliar', rotulo: 'Rodar avaliação' },
      { para: '/relatorios', rotulo: 'Relatórios' },
    ],
  },
  {
    titulo: '4 · Validar o juiz',
    itens: [
      { para: '/comparar-juizes', rotulo: 'Comparar juízes' },
      { para: '/kappa', rotulo: 'Rotulagem humana' },
    ],
  },
  {
    titulo: 'Interação manual',
    itens: [
      { para: '/chat', rotulo: 'Chat manual' },
      { para: '/historico', rotulo: 'Histórico de conversas' },
    ],
  },
]

function estiloItem({ isActive }) {
  return {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 12px',
    fontSize: 14,
    borderRadius: 2,
    cursor: 'pointer',
    color: isActive ? 'var(--texto)' : 'var(--texto-suave)',
    fontWeight: isActive ? 700 : 400,
    background: isActive ? 'var(--item-hover)' : 'transparent',
  }
}

export default function Casca({ children }) {
  const [saude, setSaude] = useState(null)

  useEffect(() => {
    api.saude().then(setSaude).catch(() => setSaude(null))
  }, [])

  return (
    <div style={{ display: 'flex', height: '100vh', minWidth: 1100, overflow: 'hidden' }}>
      <nav
        style={{
          width: 'var(--largura-nav)',
          flex: 'none',
          background: 'var(--painel)',
          borderRight: '1px solid var(--borda)',
          display: 'flex',
          flexDirection: 'column',
          padding: '20px 0',
          overflowY: 'auto',
        }}
      >
        <div style={{ padding: '0 18px 18px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          <div
            className="mono"
            style={{ fontSize: 12, letterSpacing: '.1em', fontWeight: 700 }}
          >
            QualiLLM · local
          </div>
          {/* Aviso permanente, exigido pelo briefing e mantido do prototipo. */}
          <div className="aviso">Todos os dados manipulados são fictícios.</div>
        </div>

        {GRUPOS.map((grupo, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '0 8px 10px' }}>
            {grupo.titulo && (
              <div className="rotulo" style={{ padding: '10px 12px 4px' }}>
                {grupo.titulo}
              </div>
            )}
            {grupo.itens.map((item) => (
              <NavLink key={item.para} to={item.para} style={estiloItem}>
                {item.rotulo}
              </NavLink>
            ))}
          </div>
        ))}

        <div
          className="mono"
          style={{
            marginTop: 'auto',
            padding: '14px 18px 0',
            borderTop: '1px solid var(--borda-suave)',
            fontSize: 11,
            color: 'var(--texto-fraco)',
            lineHeight: 1.7,
          }}
        >
          {saude ? (
            <>
              bot {saude.bot.modelo}
              <br />
              {/* "padrao": e o juiz configurado, nao necessariamente o da
                  avaliacao mais recente que a Visao geral mostra. */}
              juiz padrão {saude.juiz.modelo}
              <br />
              simulador {saude.simulador.modelo}
              <br />
              <span style={{ color: 'var(--texto-tenue)' }}>hoje {saude.data_referencia}</span>
            </>
          ) : (
            <span style={{ color: 'var(--vermelho)' }}>API fora do ar</span>
          )}
        </div>
      </nav>

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {children}
      </main>
    </div>
  )
}
