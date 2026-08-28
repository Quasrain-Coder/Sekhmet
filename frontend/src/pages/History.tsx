import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import CardView from '../components/table/CardView';

// 形状与 backend/sekhmet/api/history.py 的 REST 响应对齐
export interface HandPlayer {
  seat_idx: number;
  name: string;
  is_human: boolean;
  stack_before?: number;
  stack_after?: number;
}

export interface HandAction {
  seat: number;
  action: string;
  amount: number;
}

export interface HandAward {
  seat_idx: number;
  amount: number;
  hand: string;
}

export interface HandSummary {
  id: number;
  table_id: string;
  players: HandPlayer[];
  board: string[];
  actions: HandAction[];
  awards: HandAward[];
  created_at: string;
}

export interface PlayerStats {
  name: string;
  hands: number;
  wins: number;
  net_chips: number;
  updated_at: string;
}

const fmtTime = (iso: string) => iso.slice(0, 16).replace('T', ' ');

const fmtNet = (net: number | null) =>
  net === null ? '—' : `${net >= 0 ? '+' : ''}${net}`;

export default function History() {
  const navigate = useNavigate();
  const [hands, setHands] = useState<HandSummary[]>([]);
  const [players, setPlayers] = useState<PlayerStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      fetch('/api/history/hands?limit=50').then(r => r.json()).catch(() => null),
      fetch('/api/history/players').then(r => r.json()).catch(() => null),
    ]).then(([h, p]) => {
      setHands(h?.hands ?? []);
      setPlayers(p?.players ?? []);
      setLoading(false);
    });
  }, []);

  return (
    <div className="history-page">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        <span className="logo">♠ Sekhmet History</span>
        <span className="phase-label">{hands.length} 手牌</span>
      </div>

      <div className="history-group">
        <h3 className="trainer-group-title">玩家战绩</h3>
        {players.length === 0 && !loading && (
          <div className="waiting-text">暂无战绩——登录后对局才会被记录</div>
        )}
        {players.length > 0 && (
          <table className="history-table">
            <thead>
              <tr><th>#</th><th>玩家</th><th>手数</th><th>胜场</th><th>胜率</th><th>净盈亏</th></tr>
            </thead>
            <tbody>
              {players.map((p, i) => (
                <tr key={p.name}>
                  <td>{i + 1}</td>
                  <td>{p.name}</td>
                  <td>{p.hands}</td>
                  <td>{p.wins}</td>
                  <td>{p.hands > 0 ? `${Math.round((p.wins / p.hands) * 100)}%` : '—'}</td>
                  <td className={p.net_chips >= 0 ? 'net-pos' : 'net-neg'}>
                    {fmtNet(p.net_chips)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="history-group">
        <h3 className="trainer-group-title">最近对局</h3>
        {loading && <div className="waiting-text">加载中…</div>}
        {!loading && hands.length === 0 && (
          <div className="waiting-text">暂无对局记录</div>
        )}
        <div className="history-hands">
          {hands.map(h => {
            const winners = new Set(h.awards.map(a => a.seat_idx));
            const seatName = (idx: number) =>
              h.players.find(pl => pl.seat_idx === idx)?.name ?? `#${idx}`;
            const open = expanded === h.id;
            return (
              <div key={h.id} className={`hand-card${open ? ' open' : ''}`}
                   onClick={() => setExpanded(open ? null : h.id)}>
                <div className="hand-card-head">
                  <span className="hand-card-id">#{h.id}</span>
                  <span className="hand-card-meta">
                    {h.table_id} · {fmtTime(h.created_at)}
                  </span>
                  <span className="hand-card-board">
                    {h.board.length > 0
                      ? h.board.map(c => <CardView key={c} card={c} small />)
                      : <span className="waiting-text">翻前结束</span>}
                  </span>
                </div>
                <div className="hand-card-players">
                  {h.players.map(pl => {
                    const net = (pl.stack_before !== undefined && pl.stack_after !== undefined)
                      ? pl.stack_after - pl.stack_before : null;
                    return (
                      <span key={pl.seat_idx} className="hand-player">
                        {winners.has(pl.seat_idx) && '🏆 '}
                        {pl.name}
                        {net !== null && (
                          <b className={net >= 0 ? 'net-pos' : 'net-neg'}> {fmtNet(net)}</b>
                        )}
                      </span>
                    );
                  })}
                </div>
                {open && (
                  <ol className="hand-actions">
                    {h.actions.map((a, i) => (
                      <li key={i}>
                        {seatName(a.seat)} {a.action}
                        {a.amount > 0 && ` ${a.amount}`}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
