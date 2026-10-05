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

export interface ImportableHand {
  hand_id: number;
  table_id: string;
  created_at: string | null;
  board: string[];
}

interface CategoryStat {
  category: string;
  attempts: number;
  avg_score: number;
  optimal_rate: number;
}

interface TrainerStats {
  total_attempts: number;
  avg_score: number | null;
  optimal_rate: number | null;
  categories: CategoryStat[];
}

interface Mistake {
  scenario_id: string;
  title: string;
  category: string;
  difficulty: number;
  last_score: number;
  attempts: number;
  last_tried_at: string;
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
  const [username] = useState(() => localStorage.getItem('authUser') ?? '');
  const [importable, setImportable] = useState<ImportableHand[]>([]);
  const [importing, setImporting] = useState<number | null>(null);
  const [stats, setStats] = useState<TrainerStats | null>(null);
  const [mistakes, setMistakes] = useState<Mistake[]>([]);

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

  // Importable lost hands for the logged-in account.
  useEffect(() => {
    if (!username) return;
    fetch(`/api/trainer/importable-hands?username=${encodeURIComponent(username)}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setImportable(d?.hands ?? []))
      .catch(() => {});
  }, [username]);

  // Server-side stats + wrong-answer book (logged-in only; guests train
  // without a trail so neither section renders).
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (!token) return;
    const qs = `?token=${encodeURIComponent(token)}`;
    fetch(`/api/trainer/stats${qs}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setStats(d))
      .catch(() => {});
    fetch(`/api/trainer/mistakes${qs}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setMistakes(d?.mistakes ?? []))
      .catch(() => {});
  }, []);

  const importHand = async (handId: number) => {
    setImporting(handId);
    try {
      const resp = await fetch('/api/trainer/scenarios/import-hand', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hand_id: handId, username }),
      });
      const data = await resp.json();
      if (resp.ok && data.scenario_id) {
        navigate(`/trainer/${data.scenario_id}`);
        return;
      }
      alert(data.error ?? '导入失败');
    } catch { alert('无法连接服务器'); }
    setImporting(null);
  };

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

      {stats && stats.total_attempts > 0 && (
        <div className="trainer-group trainer-stats">
          <h3 className="trainer-group-title">训练统计</h3>
          <div className="trainer-stat-overview">
            <span>总题数 <b>{stats.total_attempts}</b></span>
            <span>均分 <b>{stats.avg_score ?? '—'}</b></span>
            <span>最优率 <b>{stats.optimal_rate != null ? `${Math.round(stats.optimal_rate * 100)}%` : '—'}</b></span>
          </div>
          <div className="trainer-weak-list">
            {stats.categories.map(c => (
              <div key={c.category} className="fb-bar-row">
                <span className="fb-bar-label">{CATEGORY_LABEL[c.category] ?? c.category}</span>
                <div className="fb-bar-track">
                  <div className="fb-bar-fill" style={{ width: `${c.avg_score}%` }} />
                </div>
                <span className="fb-bar-value">{c.avg_score}分</span>
                <span className="trainer-weak-count">{c.attempts}题</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {mistakes.length > 0 && (
        <div className="trainer-group">
          <h3 className="trainer-group-title">错题本（最近一次仍非最优，点击重训）</h3>
          <div className="trainer-cards">
            {mistakes.map(m => (
              <div key={m.scenario_id} className="trainer-card mistake"
                   onClick={() => navigate(`/trainer/${m.scenario_id}`)}>
                <div className="trainer-card-title">{m.title}</div>
                <div className="trainer-card-desc">
                  {CATEGORY_LABEL[m.category] ?? m.category} · 上次 {m.last_score} 分
                  {m.attempts > 1 ? ` · 已练 ${m.attempts} 次` : ''}
                </div>
                <span className={`diff-pill diff-${m.difficulty}`}>
                  {'★'.repeat(m.difficulty)}{'☆'.repeat(5 - m.difficulty)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {username && importable.length > 0 && (
        <div className="trainer-group">
          <h3 className="trainer-group-title">复盘你的对局（{username} 最近输掉的手牌）</h3>
          <div className="trainer-cards">
            {importable.map(h => (
              <div key={h.hand_id} className="trainer-card"
                   onClick={() => importHand(h.hand_id)}>
                <div className="trainer-card-title">
                  {importing === h.hand_id ? '生成中…' : '📥 导入这手牌'}
                </div>
                <div className="trainer-card-desc">
                  #{h.hand_id} · {h.board.slice(0, 5).join('') || '翻前结束'}
                  {h.created_at ? ` · ${h.created_at.slice(0, 16).replace('T', ' ')}` : ''}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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
