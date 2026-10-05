import { useEffect, useState } from 'react';

/**
 * Score trend chart.  Logged-in accounts read the server-side attempt
 * history (`/api/trainer/stats`, cross-device, full history); guests and
 * failed requests fall back to the localStorage log the submit page keeps.
 */
export default function ScoreChart() {
  const [serverScores, setServerScores] = useState<number[] | null>(null);

  const token = localStorage.getItem('authToken');
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    fetch(`/api/trainer/stats?token=${encodeURIComponent(token)}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!cancelled && d?.recent?.length) {
          setServerScores(d.recent.map((x: { score: number }) => x.score));
        }
      })
      .catch(() => { /* server may not be running */ });
    return () => { cancelled = true; };
  }, [token]);

  const [localScores, setLocalScores] = useState<number[]>(() => {
    try { return JSON.parse(localStorage.getItem('trainerScores') ?? '[]') as number[]; }
    catch { return []; }
  });

  // Re-read localStorage when the tab regains focus — the submit page
  // appends there and the trainer stays mounted in between.
  useEffect(() => {
    const reread = () => {
      try { setLocalScores(JSON.parse(localStorage.getItem('trainerScores') ?? '[]') as number[]); }
      catch { /* ignore */ }
    };
    window.addEventListener('focus', reread);
    return () => window.removeEventListener('focus', reread);
  }, []);

  const history = serverScores ?? localScores;
  const recent = history.slice(-20);
  if (recent.length === 0) return null;

  const avg = Math.round(recent.reduce((a, b) => a + b, 0) / recent.length);
  const max = Math.max(...recent, 100);
  const W = 220, H = 48;

  return (
    <div className="score-chart">
      <div className="score-chart-meta">
        <span>最近 {recent.length} 题均分 <b>{avg}</b></span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden>
        {recent.map((score, i) => {
          const x = (i / Math.max(recent.length - 1, 1)) * (W - 8) + 4;
          const y = H - 6 - (score / max) * (H - 12);
          const color = score >= 80 ? 'var(--gold)' : score >= 60 ? 'var(--cyan)' : 'var(--rose)';
          return (
            <line key={i}
                  x1={x} y1={H - 6} x2={x} y2={y}
                  stroke={color} strokeWidth={3} strokeLinecap="round" />
          );
        })}
      </svg>
    </div>
  );
}
