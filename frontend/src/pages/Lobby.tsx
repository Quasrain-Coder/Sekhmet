import { useState, useCallback, useEffect } from 'react';

interface TableInfo {
  table_id: string;
  phase: string;
  n_players: number;
  max_seats: number;
}

interface Props {
  onJoin: (tableId: string, seatIdx: number, name: string, buyin: number) => void;
}

export default function Lobby({ onJoin }: Props) {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [name, setName] = useState(() => localStorage.getItem('pokerName') || '');
  const [buyin, setBuyin] = useState(200);

  const refresh = useCallback(async () => {
    try {
      const resp = await fetch('/api/game/tables');
      const data = await resp.json();
      setTables(data.tables || []);
    } catch { /* server may not be running */ }
  }, []);

  useEffect(() => { refresh(); const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [refresh]);

  const create = async () => {
    try {
      const resp = await fetch('/api/game/tables', { method: 'POST' });
      const data = await resp.json();
      const tid = data.table_id;
      localStorage.setItem('pokerName', name);
      onJoin(tid, 0, name, buyin);
    } catch { alert('Cannot reach server'); }
  };

  const join = (tid: string) => {
    localStorage.setItem('pokerName', name);
    const seat = tables.find(t => t.table_id === tid)?.n_players ?? 0;
    onJoin(tid, seat, name, buyin);
  };

  return (
    <div className="lobby">
      <h1 className="page-title">♠ Sekhmet Poker</h1>

      <div className="lobby-actions">
        <input className="input" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} />
        <input className="input" type="number" placeholder="Buy-in" value={buyin} onChange={e => setBuyin(Number(e.target.value))} style={{width:100}} />
        <button className="btn" onClick={create} disabled={!name}>+ New Table</button>
      </div>

      <div className="table-list">
        {tables.length === 0 && <div className="waiting-text">No active tables. Create one!</div>}
        {tables.map(t => (
          <div key={t.table_id} className="table-card" onClick={() => join(t.table_id)}>
            <span className="id">{t.table_id}</span>
            <span className="info">{t.n_players}/{t.max_seats} players · {t.phase}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
