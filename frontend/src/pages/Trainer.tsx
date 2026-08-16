import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ScoreChart from '../components/trainer/ScoreChart';

export interface ScenarioInfo {
  id: string;
  title: string;
  description: string;
  category: string;
  difficulty: number;
}

const CATEGORY_LABEL: Record<string, string> = {
  preflop_range: '翻前范围',
  postflop_value: '翻后价值',
  bluffing: '诈唬',
  river_decision: '河牌决策',
  pot_odds: '底池赔率',
  position: '位置',
};

export default function Trainer() {
  const navigate = useNavigate();
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [filter, setFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const q = filter ? `?category=${encodeURIComponent(filter)}` : '';
      const resp = await fetch(`/api/trainer/scenarios${q}`);
      const data = await resp.json();
      setScenarios(data.scenarios ?? []);
    } catch { /* server may not be running */ }
    setLoading(false);
  }, [filter]);

  useEffect(() => { refresh(); }, [refresh]);

  const cats = Object.keys(CATEGORY_LABEL);
  const groups = cats
    .map(c => ({ cat: c, label: CATEGORY_LABEL[c], items: scenarios.filter(s => s.category === c) }))
    .filter(g => g.items.length > 0);

  return (
    <div className="trainer">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        <span className="logo">♠ Sekhmet Trainer</span>
        <span className="phase-label">{scenarios.length} 个场景</span>
      </div>

      <div className="trainer-progress">
        <ScoreChart />
      </div>

      <div className="trainer-filter">
        {filter === null
          ? <button className="btn btn-sm gold">全部</button>
          : <button className="btn btn-sm" onClick={() => setFilter(null)}>全部</button>}
        {cats.map(c => (
          filter === c
            ? <button key={c} className="btn btn-sm gold">{CATEGORY_LABEL[c]}</button>
            : <button key={c} className="btn btn-sm" onClick={() => setFilter(c)}>
                {CATEGORY_LABEL[c]}
              </button>
        ))}
      </div>

      {loading && <div className="waiting-text">加载中…</div>}

      {!loading && filter === null && groups.map(g => (
        <div key={g.cat} className="trainer-group">
          <h3 className="trainer-group-title">{g.label}</h3>
          <div className="trainer-cards">
            {g.items.map(s => (
              <div key={s.id} className="trainer-card"
                   onClick={() => navigate(`/trainer/${s.id}`)}>
                <div className="trainer-card-title">{s.title}</div>
                <div className="trainer-card-desc">{s.description}</div>
                <span className={`diff-pill diff-${s.difficulty}`}>
                  {'★'.repeat(s.difficulty)}{'☆'.repeat(5 - s.difficulty)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}

      {!loading && filter !== null && (
        <div className="trainer-cards">
          {scenarios.map(s => (
            <div key={s.id} className="trainer-card"
                 onClick={() => navigate(`/trainer/${s.id}`)}>
              <div className="trainer-card-title">{s.title}</div>
              <div className="trainer-card-desc">{s.description}</div>
              <span className={`diff-pill diff-${s.difficulty}`}>
                {'★'.repeat(s.difficulty)}{'☆'.repeat(5 - s.difficulty)}
              </span>
            </div>
          ))}
          {scenarios.length === 0 && (
            <div className="waiting-text">该分类暂无场景</div>
          )}
        </div>
      )}
    </div>
  );
}
