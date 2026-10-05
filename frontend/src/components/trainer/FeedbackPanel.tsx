interface SubmitResult {
  score: {
    total: number;
    action_match: number;
    sizing_precision: number;
    timing_judgment: number;
    feedback: string;
    detailed_feedback: string;
    is_optimal: boolean;
  };
  analysis: {
    equity_player: number;
    optimal_ev: number;
    player_ev: number;
    ev_loss: number;
    is_gto_deviation: boolean;
    suggestion: string;
    details: string[];
    /** "monte_carlo" | "authored" — set by iteration #2; optional for
     * backward compatibility with cached/old responses. */
    equity_source?: string;
  };
}

interface Props {
  result: SubmitResult;
  timeBudgetMs?: number;
  onRetry: () => void;
}

function scoreTone(total: number): 'good' | 'mid' | 'bad' {
  return total >= 80 ? 'good' : total >= 60 ? 'mid' : 'bad';
}

export default function FeedbackPanel({ result, timeBudgetMs, onRetry }: Props) {
  const s = result.score;
  const a = result.analysis;
  const tone = scoreTone(s.total);
  const elapsedS = result.elapsed_ms != null ? result.elapsed_ms / 1000 : null;
  const timingFull = s.timing_judgment >= 15 - 1e-6;

  return (
    <div className={`feedback-panel fb-${tone}`}>
      <div className="feedback-head">
        <div className={`score-ring score-${tone}`}>{Math.round(s.total)}</div>
        <div className="feedback-summary">
          <b className={s.is_optimal ? 'lb-pos' : 'lb-neg'}>
            {s.is_optimal ? '✓ 最优决策' : '✗ 有更优解'}
          </b>
          <p>{s.feedback}</p>
          {elapsedS != null && (
            <p className="time-used">
              ⏱ 用时 {elapsedS.toFixed(1)}s
              {timeBudgetMs != null && (
                <> / 预算 {Math.round(timeBudgetMs / 1000)}s
                  {' '}（时机 {timingFull ? '满分' : `扣至 ${Math.round(s.timing_judgment)}/15`}）
                </>
              )}
            </p>
          )}
        </div>
      </div>

      <div className="feedback-bars">
        <Bar label="动作匹配" value={s.action_match} max={60} />
        <Bar label="下注尺度" value={s.sizing_precision} max={25} />
        <Bar label="时机判断" value={s.timing_judgment} max={15} />
      </div>

      <p className="feedback-detail">{s.detailed_feedback}</p>

      <div className="analysis-box">
        <div className="analysis-rows">
          <div className="profile-row">
            <span>你的 equity 估计{a.equity_source === 'monte_carlo' ? '（蒙特卡洛模拟）' : ''}</span>
            <b>{Math.round(a.equity_player * 100)}%</b>
          </div>
          <div className="profile-row"><span>最优 EV</span><b>{a.optimal_ev}</b></div>
          <div className="profile-row"><span>你的 EV</span><b>{a.player_ev}</b></div>
          <div className="profile-row">
            <span>EV 损失</span>
            <b className={a.ev_loss > 0.25 ? 'lb-neg' : 'lb-pos'}>
              {a.ev_loss > 0 ? `-${a.ev_loss}` : `+${Math.abs(a.ev_loss)}`}
            </b>
          </div>
          {a.is_gto_deviation && (
            <div className="profile-row"><span>GTO 偏差</span><b className="lb-neg">是</b></div>
          )}
        </div>
        {a.details.length > 0 && (
          <ul className="analysis-details">
            {a.details.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        )}
        {a.suggestion && <p className="analysis-suggestion">📌 {a.suggestion}</p>}
      </div>

      <div className="action-row">
        <button className="btn gold" onClick={onRetry}>再试一次</button>
      </div>
    </div>
  );
}

function Bar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="fb-bar-row">
      <span className="fb-bar-label">{label}</span>
      <div className="fb-bar-track">
        <div className="fb-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="fb-bar-value">{Math.round(value)}/{max}</span>
    </div>
  );
}
