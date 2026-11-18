/* Barra de titulo de cada tela, conforme o mockup: titulo + legenda mono a
   esquerda, acoes a direita.

   `subtitulo` existe para desfazer jargao: alguns titulos usam o termo interno
   do projeto ("estimulo", "bateria") e precisam de uma linha dizendo o que
   aquilo e para quem chega de fora. */
export default function Cabecalho({ titulo, subtitulo, legenda, children }) {
  return (
    <div
      style={{
        background: 'var(--painel)',
        borderBottom: '1px solid var(--borda)',
        padding: '20px 30px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 20,
        flex: 'none',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-.01em' }}>{titulo}</div>
          {legenda && (
            <div className="mono" style={{ fontSize: 12, color: 'var(--texto-fraco)' }}>
              {legenda}
            </div>
          )}
        </div>
        {subtitulo && (
          <div style={{ fontSize: 12.5, color: 'var(--texto-fraco)', marginTop: 3 }}>
            {subtitulo}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, flex: 'none' }}>{children}</div>
    </div>
  )
}
