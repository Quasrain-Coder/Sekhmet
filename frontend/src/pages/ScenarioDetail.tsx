import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import FeedbackPanel from '../components/trainer/FeedbackPanel';
import CardView from '../components/table/CardView';

interface TablePreview {
  phase: string;
  hole_cards: string[];
  community_cards: string[];
  pot: number;
  current_bet: number;
  to_call: number;
  stack: number;
  dealer_idx: number | null;
  sb_seat: number | null;
  bb_seat: number | null;
  player_seat: number | null;
}

interface ScenarioDetailData {
  id: string;
  title: string;
  description: string;
  category: string;
  difficulty: number;
  hints: string[];
  table?: TablePreview | null;
}

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

const CATEGORY_LABEL: Record<string, string> = {
  preflop_range: '翻前范围', postflop_value: '翻后价值',
  bluffing: '诈唬', river_decision: '河牌决策',
  pot_odds: '底池赔率', position: '位置',
};

const ACTIONS = [
  { type: 'FOLD', label: 'Fold' },
  { type: 'CHECK', label: 'Check' },
  { type: 'CALL', label: 'Call' },
  { type: 'BET', label: 'Bet' },
  { type: 'RAISE', label: 'Raise' },
  { type: 'ALL_IN', label: 'All-in' },
] as const;

export default function ScenarioDetail() {
  const { scenarioId = '' } = useParams();
  const navigate = useNavigate();
  const [scenario, setScenario] = useState<ScenarioDetailData | null>(null);
  const [action, setAction] = useState<string>('FOLD');
  const [amount, setAmount] = useState<number>(0);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [hints, setHints] = useState<string[]>([]);
  const [hintLevel, setHintLevel] = useState(-1);  // -1 = no hint shown

  useEffect(() => {
    fetch(`/api/trainer/scenarios/${scenarioId}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setScenario(d))
      .catch(() => {});
  }, [scenarioId]);

  const submit = useCallback(async () => {
    const resp = await fetch(`/api/trainer/scenarios/${scenarioId}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: action, amount }),
    });
    if (!resp.ok) return;
    const data = await resp.json();
    setResult(data);
    // Persist score history for the trend chart.
    try {
      const history = JSON.parse(localStorage.getItem('trainerScores') ?? '[]');
      history.push(data.score.total);
      localStorage.setItem('trainerScores', JSON.stringify(history.slice(-100)));
    } catch { /* ignore */ }
  }, [scenarioId, action, amount]);

  const askHint = useCallback(async () => {
    const next = hintLevel + 1;
    const resp = await fetch(`/api/trainer/scenarios/${scenarioId}/hint?level=${next}`);
    if (!resp.ok) return;
    const data = await resp.json();
    setHintLevel(next);
    setHints(prev => [...prev, data.hint]);
  }, [scenarioId, hintLevel]);

  if (!scenario) return <div className="lobby"><div className="waiting-text">加载中…</div></div>;

  return (
    <div className="lobby">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/trainer')}>← Trainer</button>
        <span className="logo">♠ {CATEGORY_LABEL[scenario.category] ?? scenario.category}</span>
        <span className="phase-label">难度 {'★'.repeat(scenario.difficulty)}</span>
      </div>

      <div className="scenario-card">
        <h2>{scenario.title}</h2>
        <p className="scenario-desc">{scenario.description}</p>

        {scenario.table && (
          <ScenarioTable table={scenario.table} />
        )}

        {hints.length > 0 && (
          <div className="hint-box">
            {hints.map((h, i) => <p key={i}>💡 {h}</p>)}
          </div>
        )}

        {!result ? (
          <>
            <div className="action-row scenario-actions">
              {ACTIONS.map(a => (
                <button key={a.type} className={`btn btn-sm ${action === a.type ? 'gold' : ''}`}
                        onClick={() => setAction(a.type)}>
                  {a.label}
                </button>
              ))}
              {(action === 'BET' || action === 'RAISE' || action === 'ALL_IN') && (
                <input className="input amount-input" type="number" min={0}
                       placeholder="金额" value={amount || ''}
                       onChange={e => setAmount(Number(e.target.value))} />
              )}
            </div>
            <div className="action-row">
              <button className="btn gold" onClick={submit}>提交决策</button>
              <button className="btn btn-sm" onClick={askHint}
                      disabled={hintLevel >= (scenario.hints?.length ?? 0) - 1}>
                Hint（逐步提示）
              </button>
            </div>
          </>
        ) : (
          <FeedbackPanel result={result} onRetry={() => setResult(null)} />
        )}
      </div>
    </div>
  );
}


function ScenarioTable({ table }: { table: TablePreview }) {
  const tag = (seat: number | null) => {
    if (seat === null) return null;
    if (seat === table.dealer_idx) return 'D';
    if (seat === table.sb_seat) return 'SB';
    if (seat === table.bb_seat) return 'BB';
    return null;
  };
  return (
    <div className="scenario-table">
      <div className="scenario-table-head">
        <span className="phase-pill playing">{table.phase}</span>
        <span>底池 <b>{table.pot}</b></span>
        <span>筹码 <b>{table.stack}</b></span>
        {table.to_call > 0 && <span>跟注 <b className="lb-neg">{table.to_call}</b></span>}
      </div>
      <div className="scenario-cards">
        <span className="fb-bar-label">你的手牌</span>
        <div className="scenario-hole">
          {table.hole_cards.map(c => <CardView key={c} card={c} big />)}
        </div>
      </div>
      {table.community_cards.length > 0 && (
        <div className="scenario-cards">
          <span className="fb-bar-label">公共牌</span>
          <div className="scenario-community">
            {table.community_cards.map(c => <CardView key={c} card={c} />)}
          </div>
        </div>
      )}
      <div className="scenario-meta">
        {table.player_seat !== null && (
          <span>
            你的位置：{tag(table.player_seat) ?? `${table.player_seat} 号位`}
            {table.player_seat === table.dealer_idx ? '（按钮位，最后行动）'
             : table.player_seat === table.sb_seat ? '（小盲）'
             : table.player_seat === table.bb_seat ? '（大盲）' : ''}
          </span>
        )}
      </div>
    </div>
  );
}
