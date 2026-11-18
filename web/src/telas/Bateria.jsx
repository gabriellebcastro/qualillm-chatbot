import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Cabecalho from '../componentes/Cabecalho.jsx'
import { VIAS } from '../componentes/ChipVia.jsx'
import SaidasAnteriores from '../componentes/SaidasAnteriores.jsx'
import SeletorModelo from '../componentes/SeletorModelo.jsx'
import { api } from '../api.js'
import { NOME_CATEGORIA, duracao } from '../metricas.js'

const VAZIO = { via: '', origem_id: '', categoria: '', modelo: '', simulador_modelo: '', repeticoes: '', recomecar: false }

/* Converte o formulario para o corpo da API: campo em branco vira null, para
   a API distinguir "sem filtro" de "filtro vazio". */
function paraCorpo(f) {
  return {
    via: f.via || null,
    origem_id: f.origem_id || null,
    categoria: f.categoria || null,
    modelo: f.modelo || null,
    simulador_modelo: f.simulador_modelo || null,
    repeticoes: f.repeticoes ? Number(f.repeticoes) : null,
    recomecar: f.recomecar,
  }
}

function Campo({ rotulo, children, dica }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span className="rotulo">{rotulo}</span>
      {children}
      {dica && <span style={{ fontSize: 11, color: 'var(--texto-tenue)' }}>{dica}</span>}
    </label>
  )
}

const estiloEntrada = {
  padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
  border: '1px solid var(--borda-forte)', borderRadius: 2, background: '#fff',
}

export default function Bateria() {
  const [filtros, setFiltros] = useState(VAZIO)
  const [plano, setPlano] = useState(null)
  const [estado, setEstado] = useState(null)
  const [erro, setErro] = useState(null)
  const [confirmando, setConfirmando] = useState(false)
  const [estimulos, setEstimulos] = useState([])

  const rodando = Boolean(estado?.rodando)

  useEffect(() => {
    api.listarEstimulos().then((d) => setEstimulos(d.estimulos)).catch(() => {})
  }, [])

  // Replaneja a cada mudanca de filtro: a estimativa tem que estar na tela
  // antes de existir botao para confirmar.
  useEffect(() => {
    api.planejarBateria(paraCorpo(filtros))
      .then((p) => { setPlano(p); setErro(null) })
      .catch((e) => setErro(e.message))
    setConfirmando(false)
  }, [filtros])

  // Enquanto roda, acompanha. 3s e suficiente: um episodio leva segundos e o
  // progresso vem de arquivo em disco, nao de uma chamada cara.
  useEffect(() => {
    let vivo = true
    async function ler() {
      try {
        const s = await api.statusBateria()
        if (vivo) setEstado(s)
      } catch { /* servidor fora do ar; a proxima tentativa resolve */ }
    }
    ler()
    const t = setInterval(ler, 3000)
    return () => { vivo = false; clearInterval(t) }
  }, [])

  async function disparar() {
    setErro(null)
    try {
      setEstado(await api.iniciarBateria(paraCorpo(filtros)))
      setConfirmando(false)
    } catch (e) {
      setErro(e.message)
    }
  }

  async function interromper() {
    try {
      setEstado(await api.pararBateria())
    } catch (e) {
      setErro(e.message)
    }
  }

  const restantes = plano?.episodios_restantes ?? 0
  const nadaAFazer = plano != null && restantes === 0
  const prog = estado?.progresso

  return (
    <>
      <Cabecalho
        titulo="Executar automação"
        subtitulo="executa os casos de teste contra o bot e grava as conversas — quem julga é a avaliação"
        legenda={rodando ? 'em andamento' : ''}
      >
        {rodando && (
          <button className="botao" onClick={interromper}>Interromper</button>
        )}
      </Cabecalho>

      <div style={{ padding: '22px 30px', overflowY: 'auto' }}>
        {erro && (
          <div className="aviso" style={{ background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)', marginBottom: 16 }}>
            {erro}
          </div>
        )}

        {/* --- Andamento --- */}
        {estado?.houve_rodada && (
          <div className="painel" style={{ padding: '16px 18px', marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                {rodando ? 'Automação em andamento' : estado.interrompida ? 'Rodada interrompida' : 'Última rodada'}
              </div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--texto-fraco)' }}>
                {estado.pid != null && `pid ${estado.pid}`}
                {estado.codigo_saida != null && ` · saiu com código ${estado.codigo_saida}`}
                {estado.terminado_em && `terminou em ${new Date(estado.terminado_em).toLocaleString('pt-BR')}`}
              </div>
            </div>

            {prog && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                <div style={{ flex: 1, height: 10, background: 'var(--trilho)', borderRadius: 5, overflow: 'hidden' }}>
                  <div
                    className={rodando ? 'pulsando' : undefined}
                    style={{ width: `${prog.percentual}%`, height: '100%', background: 'var(--acento)' }}
                  />
                </div>
                <span className="mono" style={{ fontSize: 13 }}>
                  {prog.feitos}/{prog.alvo} episódios ({prog.percentual}%)
                </span>
              </div>
            )}
            {prog && rodando && (
              <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginBottom: 10, lineHeight: 1.6 }}>
                {prog.episodio_atual && <>Agora: <span className="mono">{prog.episodio_atual}</span><br /></>}
                Decorrido {duracao(prog.decorrido_s)}
                {prog.restante_estimado_s != null && <> · faltam cerca de {duracao(prog.restante_estimado_s)}</>}
                {prog.restante_estimado_s == null && ' · a estimativa de tempo aparece depois do primeiro episódio'}
              </div>
            )}

            {estado.comando && (
              <div className="mono" style={{ fontSize: 11, color: 'var(--texto-tenue)', marginBottom: 10 }}>
                rodar_bateria.py {estado.comando.split('rodar_bateria.py')[1] ?? ''}
              </div>
            )}

            {estado.saida?.length > 0 && (
              <pre
                className="mono"
                style={{
                  margin: 0, padding: 12, background: '#f6f7f9', border: '1px solid var(--borda-suave)',
                  borderRadius: 2, fontSize: 11.5, lineHeight: 1.5, maxHeight: 220,
                  overflow: 'auto', whiteSpace: 'pre-wrap', color: 'var(--texto-suave)',
                }}
              >
                {estado.saida.join('\n')}
              </pre>
            )}

            {!rodando && estado.interrompida && (
              <div style={{ fontSize: 12, color: 'var(--texto-fraco)', marginTop: 10, lineHeight: 1.5 }}>
                O que já rodou está gravado. A próxima execução com os mesmos
                filtros retoma de onde parou.
              </div>
            )}
          </div>
        )}

        <SaidasAnteriores tipo="bateria" atualizarCom={estado?.iniciado_em} />

        {/* --- Formulario --- */}
        <div className="painel" style={{ padding: '18px', opacity: rodando ? 0.55 : 1, pointerEvents: rodando ? 'none' : 'auto' }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Configurar rodada</div>
          <div style={{ fontSize: 13, color: 'var(--texto-fraco)', lineHeight: 1.5, marginBottom: 16, maxWidth: 780 }}>
            Sem nenhum filtro, roda o <Link to="/estimulos">inventário</Link> inteiro.
            Cada episódio é ao menos uma chamada de API paga — a estimativa abaixo é
            atualizada a cada mudança e o botão só libera quando há algo a fazer.
            Nada aqui decide se o bot acertou: isso é{' '}
            <Link to="/avaliar">Rodar avaliação</Link>, depois, sobre estes logs.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 16 }}>
            <Campo rotulo="Via">
              <select style={estiloEntrada} value={filtros.via}
                onChange={(e) => setFiltros({ ...filtros, via: e.target.value, origem_id: '' })}>
                <option value="">todas</option>
                {Object.keys(VIAS).map((v) => <option key={v} value={v}>{VIAS[v].rotulo}</option>)}
              </select>
            </Campo>

            <Campo rotulo="Categoria-alvo">
              <select style={estiloEntrada} value={filtros.categoria}
                onChange={(e) => setFiltros({ ...filtros, categoria: e.target.value })}>
                <option value="">todas</option>
                {Object.keys(NOME_CATEGORIA).map((c) => <option key={c} value={c}>{NOME_CATEGORIA[c]}</option>)}
              </select>
            </Campo>

            <Campo rotulo="Caso de teste" dica="vazio = todos os que passarem nos filtros">
              <select style={estiloEntrada} value={filtros.origem_id}
                onChange={(e) => setFiltros({ ...filtros, origem_id: e.target.value })}>
                <option value="">todos</option>
                {estimulos
                  .filter((e) => !filtros.via || e.via === filtros.via)
                  .map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
              </select>
            </Campo>

            <Campo rotulo="Modelo do bot">
              {/* O bot e a VARIAVEL do experimento: trocar o modelo aqui e
                  como se compara um sistema com outro. */}
              <SeletorModelo
                papel="bot"
                valor={filtros.modelo}
                onChange={(m) => setFiltros({ ...filtros, modelo: m })}
              />
            </Campo>

            <Campo
              rotulo="Modelo do simulador"
              dica="interpreta o CLIENTE na via simulador; ignorado nas outras"
            >
              {/* Segundo papel de LLM da rodada. O plano de testes recomenda
                  aponta-lo para outro provedor que nao o do bot, para nao
                  medir o sistema contra si mesmo -- escolha que antes exigia
                  editar o .env e reiniciar o servidor. */}
              <SeletorModelo
                papel="simulador"
                valor={filtros.simulador_modelo}
                onChange={(m) => setFiltros({ ...filtros, simulador_modelo: m })}
              />
            </Campo>

            <Campo rotulo="Repetições" dica="vazio = o padrão de cada estímulo">
              <input style={estiloEntrada} type="number" min="1" placeholder="padrão" value={filtros.repeticoes}
                onChange={(e) => setFiltros({ ...filtros, repeticoes: e.target.value })} />
            </Campo>

            <Campo rotulo="Retomada">
              <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, padding: '8px 0' }}>
                <input type="checkbox" checked={filtros.recomecar}
                  onChange={(e) => setFiltros({ ...filtros, recomecar: e.target.checked })} />
                refazer tudo do zero
              </label>
            </Campo>
          </div>

          {/* --- Estimativa --- */}
          {plano && (
            <div style={{ borderTop: '1px solid var(--borda-suave)', paddingTop: 14 }}>
              <div style={{ display: 'flex', gap: 26, marginBottom: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Casos de teste</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>{plano.estimulos}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Episódios planejados</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>{plano.episodios_planejados}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Já feitos</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: 'var(--texto-tenue)' }}>
                    {plano.episodios_ja_feitos}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>Vão rodar agora</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: restantes ? 'var(--acento)' : 'var(--texto-tenue)' }}>
                    {restantes}
                  </div>
                </div>
                <div style={{ alignSelf: 'center', fontSize: 12, color: 'var(--texto-fraco)', maxWidth: 260, lineHeight: 1.45 }}>
                  Modelos: <span className="mono">{(plano.modelos || []).join(', ')}</span>
                </div>
              </div>

              {nadaAFazer && !filtros.recomecar && (
                <div className="aviso" style={{ marginBottom: 12 }}>
                  Todos os {plano.episodios_planejados} episódios deste recorte já foram
                  executados. A automação é retomável: rodar de novo não faria nada. Marque
                  <strong> refazer tudo do zero</strong> se a intenção é medir outra vez.
                </div>
              )}

              {filtros.recomecar && restantes > 0 && (
                <div className="aviso" style={{ marginBottom: 12, background: '#fbeae8', borderColor: '#e8c3be', color: 'var(--vermelho)' }}>
                  <strong>Refazer tudo do zero:</strong> os {restantes} episódios serão
                  executados novamente, mesmo os já concluídos. Os logs antigos não são
                  apagados, mas a conta de chamadas pagas é integral.
                </div>
              )}

              {!confirmando ? (
                <button
                  className="botao botao-primario"
                  disabled={restantes === 0}
                  onClick={() => setConfirmando(true)}
                >
                  {restantes === 0 ? 'Nada a executar' : `Executar ${restantes} episódio(s)…`}
                </button>
              ) : (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 13 }}>
                    Confirmar <strong>{restantes} episódio(s)</strong>? Cada um faz ao menos
                    uma chamada paga; isso pode levar dezenas de minutos.
                  </span>
                  <button className="botao botao-primario" onClick={disparar}>Confirmar e executar</button>
                  <button className="botao" onClick={() => setConfirmando(false)}>Cancelar</button>
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ fontSize: 12, color: 'var(--texto-tenue)', marginTop: 14, lineHeight: 1.55, maxWidth: 780 }}>
          A rodada é um processo do servidor, não desta aba: fechar a janela não
          interrompe nada, e o progresso continua sendo gravado. Equivale a rodar{' '}
          <span className="mono">python scripts/rodar_bateria.py</span> no terminal.
        </div>
      </div>
    </>
  )
}
