import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Lobby from './pages/Lobby';
import GameTablePage from './pages/GameTable';
import Trainer from './pages/Trainer';
import ScenarioDetail from './pages/ScenarioDetail';
import History from './pages/History';
import './styles/game.css';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<Lobby />} />
          <Route path="/game/:tableId" element={<GameTablePage />} />
          <Route path="/trainer" element={<Trainer />} />
          <Route path="/trainer/:scenarioId" element={<ScenarioDetail />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
