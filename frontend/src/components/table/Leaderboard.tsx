import { useState } from 'react';
import type { SeatInfo } from '../../hooks/useGameState';

interface Props {
  seats: SeatInfo[];
}

export default function Leaderboard({ seats }: Props) {
  const [open, setOpen] = useState(false);
  const ranked = [...seats].sort((a, b) => b.net_chips - a.net_chips);

  return (
    <div className="leaderboard">
      <button className="lb-toggle" onClick={() => setOpen(!open)}>
        🏆 Leaderboard {open ? '▾' : '▸'}
      </button>
      {open && (
        <table className="lb-table">
          <thead>
            <tr><th>#</th><th>Player</th><th>Hands</th><th>Wins</th><th>Win%</th><th>Net</th></tr>
          </thead>
          <tbody>
            {ranked.map((s, i) => (
              <tr key={s.seat_idx}>
                <td>{i + 1}</td>
                <td>{s.name}{!s.is_human && <span className="lb-bot"> L{s.bot_level ?? 2}</span>}</td>
                <td>{s.hands}</td>
                <td>{s.wins}</td>
                <td>{s.hands > 0 ? Math.round((s.wins / s.hands) * 100) : 0}%</td>
                <td className={s.net_chips >= 0 ? 'lb-pos' : 'lb-neg'}>
                  {s.net_chips >= 0 ? '+' : ''}{s.net_chips}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
