import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Lobby from './pages/Lobby';
import GameTablePage from './pages/GameTable';
import './styles/game.css';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<Lobby />} />
          <Route path="/game/:tableId" element={<GameTablePage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
