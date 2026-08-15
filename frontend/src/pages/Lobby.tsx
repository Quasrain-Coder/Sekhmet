import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Toast from '../components/shared/Toast';
import type { ToastItem } from '../components/shared/Toast';

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
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastId = useRef(0);
  const pushToast = useCallback((kind: 'error' | 'info', text: string) => {
    const id = ++toastId.current;
    setToasts(ts => [...ts, { id, kind, text }]);
  }, []);
  const dismissToast = useCallback((id: number) => {
    setToasts(ts => ts.filter(t => t.id !== id));
  }, []);

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
        pushToast('error', err.detail ?? 'Create failed');
        return;
      }
      const data = await resp.json();
      localStorage.setItem('pokerName', name);
      if (data.owner_token) {
        localStorage.setItem(`ownerToken_${data.table_id}`, data.owner_token);
      }
      navigate(`/game/${data.table_id}`);
    } catch { pushToast('error', 'Cannot reach server'); }
  };

  return (
    <div className="lobby">
      <Toast items={toasts} onDismiss={dismissToast} />
      <div className="lobby-logo">
        <div className="spade">♠</div>
        <h1>SEKHMET</h1>
        <div className="sub">Poker Trainer</div>
      </div>

      <div className="lobby-panel">
        <div className="panel-label">New Table</div>
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
                 onChange={e => setBuyin(Number(e.target.value))} />
          <select className="input" value={maxSeats} onChange={e => setMaxSeats(Number(e.target.value))}>
            {[2, 3, 4, 5, 6, 7, 8, 9].map(n => <option key={n} value={n}>{n} seats</option>)}
          </select>
          <button className="btn gold" onClick={create} disabled={!name}>+ New Table</button>
        </div>
      </div>

      <div className="table-list">
        {tables.length === 0 && <div className="waiting-text">No active tables. Create one!</div>}
        {tables.map(t => (
          <div key={t.table_id} className="table-card"
               onClick={() => { localStorage.setItem('pokerName', name); navigate(`/game/${t.table_id}`); }}>
            <div>
              <span className="id">{t.table_id}</span>
              <div className="info">
                {t.config.small_blind}/{t.config.big_blind} · buy-in {t.config.default_buyin}
              </div>
              <div className="seat-dots">
                {t.seats.map(s => (
                  <span key={s.seat_idx} className={`dot ${s.is_human ? 'full' : 'bot'}`} />
                ))}
                {Array.from({ length: t.max_seats - t.seats.length }, (_, i) => (
                  <span key={`e${i}`} className="dot" />
                ))}
              </div>
            </div>
            <span className={`phase-pill ${t.phase === 'WAITING' ? 'waiting' : 'playing'}`}>
              {t.phase === 'WAITING' ? 'Waiting' : t.phase}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
