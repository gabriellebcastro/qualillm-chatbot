import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Cabecalho from '../componentes/Cabecalho.jsx'
import SeletorModelo from '../componentes/SeletorModelo.jsx'
import { api } from '../api.js'

/* A conversa em andamento vive FORA do componente.
 *
 * Sem isso, dois problemas reais: sair do Chat para ver o histórico e voltar
 * descartava a conversa da tela (ela continua no log, mas some da vista, e
 * parece que se perdeu); e o StrictMode do React monta o efeito duas vezes em
 * desenvolvimento, o que criava DUAS sessões no servidor por visita, deixando
 * uma órfã ocupando memória.
 *
 * É estado de tela, não cache de dados: some quando a aba é recarregada, e é
 * exatamente esse o comportamento desejado — aí o servidor também já perdeu a
 * conversa viva. */
const conversaViva = {
  sessao: null,
  mensagens: [],
  ultimo: null,
  aviso: null,
  // Guarda contra abertura concorrente. Fica aqui, e nao num useRef, porque
  // o escopo de modulo sobrevive com certeza a montagem dupla do StrictMode.
  abrindo: false,
  // Modelo escolhido na interface, "provedor:modelo". Vazio = o do .env.
  // Persiste entre visitas junto com o resto: trocar de tela nao devia
  // desfazer a escolha.
  modelo: '',
}

function Bolha({ papel, texto }) {
  const doBot = papel === 'assistant'
  return (
    <div style={{ display: 'flex', justifyContent: doBot ? 'flex-start' : 'flex-end' }}>
      <div
        style={{
          maxWidth: '76%',
          padding: '10px 14px',
          borderRadius: 3,
          fontSize: 14,
          lineHeight: 1.55,
          whiteSpace: 'pre-wrap',
          background: doBot ? 'var(--painel)' : '#e8eaf0',
          border: `1px solid ${doBot ? 'var(--borda)' : '#d3d8e2'}`,
          color: 'var(--texto-medio)',
        }}
      >
        <div className="rotulo" style={{ marginBottom: 5 }}>
          {/* Chat manual: de um lado uma pessoa de verdade, do outro o bot.
              A via simulador (LLM x LLM) usa rotulos diferentes de proposito. */}
          {doBot ? '🤖 atendente' : '🧑 você'}
        </div>
        {texto}
      </div>
    </div>
  )
}

function LinhaEstado({ rotulo, valor, destaque }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13 }}>
      <span style={{ color: 'var(--texto-fraco)' }}>{rotulo}</span>
      <span
        className={destaque ? undefined : 'mono'}
        style={{
          color: valor ? 'var(--texto)' : 'var(--texto-tenue)',
          fontWeight: destaque ? 600 : 400,
          textAlign: 'right',
        }}
      >
        {valor ?? '—'}
      </span>
    </div>
  )
}

export default function Chat() {
  const [sessao, setSessao] = useState(conversaViva.sessao)
  const [mensagens, setMensagens] = useState(conversaViva.mensagens)
  const [texto, setTexto] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState(null)
  const [aviso, setAviso] = useState(conversaViva.aviso)
  const [ultimo, setUltimo] = useState(conversaViva.ultimo)
  const [abrindo, setAbrindo] = useState(false)
  const [modelo, setModelo] = useState(conversaViva.modelo)
  const fimDaLista = useRef(null)

  // O modelo escolhido difere do que a conversa atual esta usando?
  const emUso = sessao ? `${sessao.provedor}:${sessao.modelo}` : ''
  const trocaPendente = Boolean(modelo) && modelo !== emUso

  async function novaSessao(modeloEscolhido = conversaViva.modelo) {
    // Impede a segunda chamada que o StrictMode dispararia.
    if (conversaViva.abrindo) return
    conversaViva.abrindo = true
    setAbrindo(true)
    setErro(null)
    setMensagens([]); conversaViva.mensagens = []
    setUltimo(null); conversaViva.ultimo = null
    setAviso(null); conversaViva.aviso = null
    try {
      // O modelo so pode ser definido ao ABRIR a conversa: o Chatbot ja
      // carrega o cliente da LLM, e trocar no meio faria metade do dialogo
      // sair de um modelo e metade de outro — inutilizando a sessao como
      // unidade de medida.
      const [provedor, mod] = (modeloEscolhido || '').split(':')
      // A primeira abertura paga a carga do indice RAG (alguns segundos).
      const nova = await api.abrirSessao(
        provedor && mod ? { provedor, modelo: mod } : {})
      setSessao(nova)
      conversaViva.sessao = nova
    } catch (e) {
      setErro(e.message)
      setSessao(null)
      conversaViva.sessao = null
    } finally {
      setAbrindo(false)
      conversaViva.abrindo = false
    }
  }

  // Só abre sessão se não houver uma viva: voltar de outra tela retoma a
  // conversa em vez de comecar do zero.
  useEffect(() => {
    if (!conversaViva.sessao) novaSessao()
  }, [])
  useEffect(() => { fimDaLista.current?.scrollIntoView({ behavior: 'smooth' }) }, [mensagens, ocupado])

  async function enviar(e) {
    e.preventDefault()
    const msg = texto.trim()
    if (!msg || ocupado || !sessao) return
    setTexto('')
    setErro(null)
    setMensagens((m) => {
      const novas = [...m, { papel: 'user', texto: msg }]
      conversaViva.mensagens = novas
      return novas
    })
    setOcupado(true)
    try {
      const turno = await api.enviarMensagem(sessao.sessao_id, msg)
      if (!turno.resposta_vazia) {
        setMensagens((m) => {
          const novas = [...m, { papel: 'assistant', texto: turno.resposta }]
          conversaViva.mensagens = novas
          return novas
        })
      }
      // O aviso de resposta vazia nao entra na lista de mensagens: e um recado
      // da interface sobre falha tecnica do provedor, nao uma fala do bot.
      setAviso(turno.aviso); conversaViva.aviso = turno.aviso
      setUltimo(turno); conversaViva.ultimo = turno
      setSessao((s) => {
        const nova = { ...s, estado: turno.estado, estagio_prompt: turno.estagio_prompt }
        conversaViva.sessao = nova
        return nova
      })
    } catch (e) {
      setErro(e.message)
    } finally {
      setOcupado(false)
    }
  }

  const estado = sessao?.estado ?? {}
  const finalizada = Boolean(ultimo?.finalizada || estado.sessao_finalizada)

  return (
    <>
      <Cabecalho
        titulo="Chat manual"
        legenda={sessao ? `${sessao.sessao_id} · ${sessao.modelo}` : abrindo ? 'abrindo sessão…' : ''}
      >
        {/* A troca so vale na proxima sessao, e o rotulo do botao diz isso em
            vez de deixar a pessoa descobrir que nada mudou na conversa atual. */}
        <div style={{ minWidth: 260 }}>
          <SeletorModelo
            papel="bot"
            valor={modelo}
            onChange={(m) => { setModelo(m); conversaViva.modelo = m }}
          />
        </div>
        {sessao && mensagens.length > 0 && (
          <Link to={`/sessoes/${sessao.sessao_id}`} className="botao" style={{ textDecoration: 'none' }}>
            Ver log desta sessão
          </Link>
        )}
        <button
          className="botao botao-primario"
          onClick={() => novaSessao(modelo)}
          disabled={abrindo}
          title={trocaPendente ? 'Abre uma conversa nova com o modelo escolhido' : undefined}
        >
          {trocaPendente ? 'Aplicar modelo (nova sessão)' : 'Nova sessão'}
        </button>
      </Cabecalho>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* --- Conversa --- */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 1, overflowY: 'auto', padding: '22px 30px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {mensagens.length === 0 && !abrindo && !erro && (
              <div style={{ color: 'var(--texto-fraco)', fontSize: 14, lineHeight: 1.6, maxWidth: 520 }}>
                Identifique-se apenas com o CPF para começar — por exemplo{' '}
                <span className="mono" style={{ color: 'var(--texto)' }}>000.111.222-04</span>.
                <div style={{ marginTop: 8, fontSize: 13, color: 'var(--texto-tenue)' }}>
                  Dados 100% fictícios.
                </div>
              </div>
            )}
            {abrindo && (
              <div className="pulsando" style={{ color: 'var(--texto-fraco)', fontSize: 13 }}>
                Abrindo sessão e carregando a base de conhecimento (RAG)…
              </div>
            )}
            {trocaPendente && mensagens.length > 0 && (
              <div className="aviso" style={{ maxWidth: '76%' }}>
                Esta conversa continua em <span className="mono">{emUso}</span>.
                O modelo escolhido só passa a valer na próxima sessão — trocar no
                meio faria metade do diálogo sair de um modelo e metade de outro.
              </div>
            )}
            {mensagens.map((m, i) => <Bolha key={i} {...m} />)}
            {ocupado && (
              <div className="pulsando" style={{ color: 'var(--texto-fraco)', fontSize: 13 }}>
                Consultando políticas, dados e o modelo…
              </div>
            )}
            {aviso && <div className="aviso" style={{ maxWidth: '76%' }}>{aviso}</div>}
            {erro && (
              <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)' }}>
                {erro}
              </div>
            )}
            {finalizada && (
              <div className="aviso" style={{ background: '#e7f2ec', borderColor: '#bcd9cb', color: 'var(--verde)' }}>
                Atendimento encerrado. Clique em <strong>Nova sessão</strong> para negociar de novo.
              </div>
            )}
            <div ref={fimDaLista} />
          </div>

          <form
            onSubmit={enviar}
            style={{ borderTop: '1px solid var(--borda)', background: 'var(--painel)', padding: '14px 30px', display: 'flex', gap: 10, flex: 'none' }}
          >
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={finalizada ? 'Conversa encerrada' : 'Digite sua mensagem…'}
              disabled={ocupado || finalizada || !sessao}
              style={{
                flex: 1, padding: '10px 12px', fontSize: 14, fontFamily: 'inherit',
                border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
              }}
            />
            <button className="botao botao-primario" disabled={ocupado || finalizada || !texto.trim()}>
              Enviar
            </button>
          </form>
        </div>

        {/* --- Estado da conversa --- */}
        <aside
          style={{
            width: 320, flex: 'none', borderLeft: '1px solid var(--borda)',
            background: 'var(--painel)', overflowY: 'auto', padding: '20px 18px',
            display: 'flex', flexDirection: 'column', gap: 20,
          }}
        >
          <div>
            <div className="rotulo" style={{ marginBottom: 10 }}>Estágio ativo</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* Dois "estagios" convivem e sao coisas diferentes: qual PROMPT
                  esta ativo, e em que degrau da escada de desconto a negociacao
                  esta. Mostrar so um deles confunde os dois conceitos. */}
              <div>
                <LinhaEstado rotulo="Prompt do bot" valor={sessao?.estagio_prompt} destaque />
                <div style={{ fontSize: 12, color: 'var(--texto-tenue)', marginTop: 3 }}>
                  escolhido pelo código, não pelo modelo
                </div>
              </div>
              <div>
                <LinhaEstado rotulo="Escada de oferta" valor={`etapa ${estado.estagio_oferta ?? 0}`} destaque />
                <div style={{ fontSize: 12, color: 'var(--texto-suave)', marginTop: 3, lineHeight: 1.45 }}>
                  {ultimo?.estagio_oferta_rotulo ?? '1a oferta a vista — 35% de desconto'}
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="rotulo" style={{ marginBottom: 10 }}>Estado da sessão</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <LinhaEstado rotulo="Cliente" valor={estado.cliente_id} />
              <LinhaEstado rotulo="Dívida" valor={estado.divida_id} />
              <LinhaEstado rotulo="Vencimento escolhido" valor={estado.data_vencimento_escolhida} />
              <LinhaEstado rotulo="Condição escolhida" valor={estado.condicao_escolhida_id} />
              <LinhaEstado rotulo="Acordo" valor={estado.acordo_id} />
            </div>
          </div>

          {ultimo && (
            <div>
              <div className="rotulo" style={{ marginBottom: 10 }}>Último turno</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <LinhaEstado rotulo="Latência" valor={`${ultimo.instrumentacao.latencia_s}s`} />
                <LinhaEstado rotulo="Chamadas à API" valor={String(ultimo.instrumentacao.tentativas_llm)} />
                <LinhaEstado rotulo="Trechos RAG" valor={String(ultimo.instrumentacao.trechos_rag.length)} />
                <LinhaEstado rotulo="Consultas aos dados" valor={String(ultimo.instrumentacao.consultas_dados.length)} />
                {ultimo.instrumentacao.historico_enviado !== null && (
                  <div className="aviso" style={{ marginTop: 6 }}>
                    Histórico reduzido a {ultimo.instrumentacao.historico_enviado} mensagem(ns)
                    nesta chamada — respostas fora de contexto aqui têm causa conhecida.
                  </div>
                )}
              </div>
            </div>
          )}

          {sessao && (
            <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)', marginTop: 'auto' }}>
              log: {sessao.arquivo_log}
            </div>
          )}
        </aside>
      </div>
    </>
  )
}
