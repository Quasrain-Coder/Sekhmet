import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface SeatInfo {
  seat_idx: number;
  name: string;
  is_human: boolean;
  bot_level: number | null;
  stack: number;
}

interface TableInfo {
  table_id: string;
  phase: string;
  max_seats: number;
  config: { small_blind: number; big_blind: number; default_buyin: number; max_seats: number };
  seats: SeatInfo[];
}

const BLIND_TIERS = [
  { label: '1/2', sb: 1, bb: 2 },
  { label: '5/10', sb: 5, bb: 10 },
  { label: '10/20', sb: 10, bb: 20 },
  { label: '25/50', sb: 25, bb: 50 },
];

export default function Lobby() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [name, setName] = useState(() => localStorage.getItem('pokerName') || '');
  const [tier, setTier] = useState(BLIND_TIERS[1]);
  const [buyin, setBuyin] = useState(BLIND_TIERS[1].bb * 100);
  const [maxSeats, setMaxSeats] = useState(9);
  const navigate = useNavigate();

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
      const resp = await fetch('/api/game/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          small_blind: tier.sb,
          big_blind: tier.bb,
          default_buyin: buyin,
          max_seats: maxSeats,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        alert(err.detail ?? 'Create failed');
        return;
      }
      const data = await resp.json();
      localStorage.setItem('pokerName', name);
      navigate(`/game/${data.table_id}`);
    } catch { alert('Cannot reach server'); }
  };

  return (
    <div className="lobby">
      <h1 className="page-title">♠ Sekhmet Poker</h1>

      <div className="lobby-actions">
        <input className="input" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} />
        <select className="input" value={tier.label}
                onChange={e => {
                  const t = BLIND_TIERS.find(x => x.label === e.target.value)!;
                  setTier(t);
                  setBuyin(t.bb * 100);
                }}>
          {BLIND_TIERS.map(t => <option key={t.label} value={t.label}>Blinds {t.label}</option>)}
        </select>
        <input className="input" type="number" placeholder="Default buy-in" value={buyin}
               onChange={e => setBuyin(Number(e.target.value))} style={{ width: 130 }} />
        <select className="input" value={maxSeats} onChange={e => setMaxSeats(Number(e.target.value))}>
          {[2, 3, 4, 5, 6, 7, 8, 9].map(n => <option key={n} value={n}>{n} seats</option>)}
        </select>
        <button className="btn" onClick={create} disabled={!name}>+ New Table</button>
      </div>

      <div className="table-list">
        {tables.length === 0 && <div className="waiting-text">No active tables. Create one!</div>}
        {tables.map(t => (
          <div key={t.table_id} className="table-card"
               onClick={() => { localStorage.setItem('pokerName', name); navigate(`/game/${t.table_id}`); }}>
            <span className="id">{t.table_id}</span>
            <span className="info">
              {t.config.small_blind}/{t.config.big_blind} · {t.seats.length}/{t.max_seats} · {t.phase}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
