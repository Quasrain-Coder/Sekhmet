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
  };
}

interface Props {
  result: SubmitResult;
  onRetry: () => void;
}

function scoreTone(total: number): 'good' | 'mid' | 'bad' {
  return total >= 80 ? 'good' : total >= 60 ? 'mid' : 'bad';
}

export default function FeedbackPanel({ result, onRetry }: Props) {
  const s = result.score;
  const a = result.analysis;
  const tone = scoreTone(s.total);

  return (
    <div className={`feedback-panel fb-${tone}`}>
      <div className="feedback-head">
        <div className={`score-ring score-${tone}`}>{Math.round(s.total)}</div>
        <div className="feedback-summary">
          <b className={s.is_optimal ? 'lb-pos' : 'lb-neg'}>
            {s.is_optimal ? '✓ 最优决策' : '✗ 有更优解'}
          </b>
          <p>{s.feedback}</p>
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
          <div className="profile-row"><span>你的 equity 估计</span><b>{Math.round(a.equity_player * 100)}%</b></div>
          <div className="profile-row"><span>最优 EV</span><b>{a.optimal_ev}</b></div>
          <div className="profile-row"><span>你的 EV</span><b>{a.player_ev}</b></div>
          <div className="profile-row"><span>EV 损失</span><b className="lb-neg">{a.ev_loss}</b></div>
          {a.is_gto_deviation && (
            <div className="profile-row"><span>GTO 偏差</span><b className="lb-neg">是</b></div>
          )}
        </div>
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
