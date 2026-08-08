import { useState } from 'react';
import Lobby from './pages/Lobby';
import GameTablePage from './pages/GameTable';
import './styles/game.css';

interface JoinConfig {
  tableId: string;
  seatIdx: number;
  name: string;
  buyin: number;
}

export default function App() {
  const [join, setJoin] = useState<JoinConfig | null>(null);

  if (join) {
    return (
      <div className="app">
        <GameTablePage
          tableId={join.tableId}
          name={join.name}
          seatIdx={join.seatIdx}
          buyin={join.buyin}
          onBack={() => setJoin(null)}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <Lobby onJoin={(tableId, seatIdx, name, buyin) => setJoin({ tableId, seatIdx, name, buyin })} />
    </div>
  );
}
