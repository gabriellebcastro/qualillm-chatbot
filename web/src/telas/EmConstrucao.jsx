import { Link } from 'react-router-dom'

/* Rota desconhecida. Antes servia de aviso para as telas do design que ainda
   nao existiam; todas foram construidas, entao sobrou este uso. */
export default function EmConstrucao({ titulo = 'Página não encontrada' }) {
  return (
    <div style={{ padding: '60px 30px', maxWidth: 560 }}>
      <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>{titulo}</div>
      <p style={{ color: 'var(--texto-suave)', lineHeight: 1.6, fontSize: 14 }}>
        Este endereço não corresponde a nenhuma tela. Use a navegação à esquerda,
        ou volte para a <Link to="/visao-geral">Visão geral</Link>.
      </p>
    </div>
  )
}
