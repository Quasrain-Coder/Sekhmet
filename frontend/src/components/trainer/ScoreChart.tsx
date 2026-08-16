import { useMemo } from 'react';

/** Score trend — history lives in localStorage (no backend persistence yet). */
export default function ScoreChart() {
  const history = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('trainerScores') ?? '[]') as number[];
    } catch { return []; }
  }, []);

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
