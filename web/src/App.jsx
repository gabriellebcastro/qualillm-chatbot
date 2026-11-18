import { Routes, Route, Navigate } from 'react-router-dom'
import Casca from './componentes/Casca.jsx'
import Chat from './telas/Chat.jsx'
import Historico from './telas/Historico.jsx'
import Sessao from './telas/Sessao.jsx'
import Relatorios from './telas/Relatorios.jsx'
import Prompts from './telas/Prompts.jsx'
import Estimulos from './telas/Estimulos.jsx'
import Execucoes from './telas/Execucoes.jsx'
import Bateria from './telas/Bateria.jsx'
import Avaliar from './telas/Avaliar.jsx'
import Massa from './telas/Massa.jsx'
import VisaoGeral from './telas/VisaoGeral.jsx'
import Kappa from './telas/Kappa.jsx'
import Limiares from './telas/Limiares.jsx'
import CompararJuizes from './telas/CompararJuizes.jsx'
import EmConstrucao from './telas/EmConstrucao.jsx'

/* As dez telas do design estao construidas. A rota "/" leva a Visao geral, que
   e o ponto de entrada previsto no mockup: resume o resto e da o caminho para
   as duas acoes caras (rodar bateria, rodar avaliacao).

   EmConstrucao sobrou como pagina de rota desconhecida. */
export default function App() {
  return (
    <Casca>
      <Routes>
        <Route path="/" element={<Navigate to="/visao-geral" replace />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/historico" element={<Historico />} />
        <Route path="/massa" element={<Massa />} />
        <Route path="/sessoes/:sessaoId" element={<Sessao />} />
        <Route path="/visao-geral" element={<VisaoGeral />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/estimulos" element={<Estimulos />} />
        <Route path="/bateria" element={<Bateria />} />
        <Route path="/kappa" element={<Kappa />} />
        <Route path="/execucoes" element={<Execucoes />} />
        <Route path="/relatorios" element={<Relatorios />} />
        <Route path="/avaliar" element={<Avaliar />} />
        <Route path="/limiares" element={<Limiares />} />
        <Route path="/comparar-juizes" element={<CompararJuizes />} />
        <Route path="*" element={<EmConstrucao titulo="Página não encontrada" />} />
      </Routes>
    </Casca>
  )
}
