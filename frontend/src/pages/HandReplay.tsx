import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import CardView from '../components/table/CardView';

// 形状与 GET /api/history/hands/{id}/replay 的响应对齐
export interface ReplayPlayer {
  seat_idx: number;
  name: string;
  is_human: boolean;
  stack: number;
  current_bet: number;
  is_active: boolean;
  is_all_in: boolean;
  hole_cards: string[] | null;
}

export interface ReplayAction {
  seat: number;
  action: string;
  amount: number;
}

export interface ReplayFrame {
  phase: string;
  board: string[];
  pot: number;
  to_act: number | null;
  players: ReplayPlayer[];
  last_action: ReplayAction | null;
}

export interface ReplayData {
  id: number;
  table_id: string;
  created_at: string;
  small_blind: number | null;
  big_blind: number | null;
  awards: { seat_idx: number; amount: number; hand: string }[];
  frames: ReplayFrame[];
}

const PHASE_LABEL: Record<string, string> = {
  PREFLOP: '翻前', FLOP: '翻牌', TURN: '转牌', RIVER: '河牌',
  SHOWDOWN: '摊牌', HAND_COMPLETE: '结算',
};

const AUTOPLAY_MS = 1200;

export default function HandReplay() {
  const { handId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<ReplayData | null>(null);
  const [error, setError] = useState(false);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch(`/api/history/hands/${handId}/replay`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setError(true));
  }, [handId]);

  const last = (data?.frames.length ?? 1) - 1;
  const step = useCallback((delta: number) => {
    setIdx(i => Math.max(0, Math.min(last, i + delta)));
  }, [last]);

  // 自动播放：到末帧自动停
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      setIdx(i => {
        if (i >= last) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, AUTOPLAY_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing, last]);

  if (error) return (
    <div className="replay-page">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/history')}>← History</button>
        <span className="logo">♠ Replay</span>
      </div>
      <div className="waiting-text">未找到这手牌（#{handId}）</div>
    </div>
  );
  if (!data) return <div className="replay-page"><div className="waiting-text">加载中…</div></div>;

  const frame = data.frames[idx];
  const isFinal = idx === last;
  const winners = new Set(data.awards.map(a => a.seat_idx));
  const seatName = (seat: number) =>
    frame.players.find(p => p.seat_idx === seat)?.name ?? `#${seat}`;

  return (
    <div className="replay-page">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/history')}>← History</button>
        <span className="logo">♠ Replay #{data.id}</span>
        <span className="phase-label">
          {data.table_id} · {data.created_at.slice(0, 16).replace('T', ' ')}
          {data.small_blind != null && ` · 盲注 ${data.small_blind}/${data.big_blind}`}
        </span>
      </div>

      <div className="replay-board">
        <span className="phase-pill playing">{PHASE_LABEL[frame.phase] ?? frame.phase}</span>
        <span className="replay-pot">底池 {frame.pot}</span>
        <span className="replay-community">
          {frame.board.length > 0
            ? frame.board.map(c => <CardView key={c} card={c} />)
            : <span className="waiting-text">翻前</span>}
        </span>
      </div>

      <div className="replay-seats">
        {frame.players.map(p => (
          <div key={p.seat_idx}
               className={`replay-seat${p.is_active ? '' : ' folded'}${
                 frame.last_action?.seat === p.seat_idx ? ' acted' : ''}${
                 isFinal && winners.has(p.seat_idx) ? ' winner' : ''}`}>
            <div className="replay-seat-name">
              {isFinal && winners.has(p.seat_idx) && '🏆 '}{p.name}
              {p.is_all_in && <span className="allin-pill">ALL-IN</span>}
            </div>
            <div className="replay-seat-cards">
              {p.hole_cards
                ? p.hole_cards.map(c => <CardView key={c} card={c} small />)
                : <><CardView small /><CardView small /></>}
            </div>
            <div className="replay-seat-stack">{p.stack}</div>
            {p.current_bet > 0 && <div className="replay-seat-bet">注 {p.current_bet}</div>}
          </div>
        ))}
      </div>

      <div className="replay-ticker">
        {frame.last_action
          ? `${seatName(frame.last_action.seat)} ${frame.last_action.action}` +
            (frame.last_action.amount > 0 ? ` ${frame.last_action.amount}` : '')
          : '发牌'}
      </div>

      {isFinal && data.awards.length > 0 && (
        <div className="replay-awards">
          {data.awards.map((a, i) => (
            <span key={i}>🏆 {seatName(a.seat_idx)} 赢得 {a.amount}（{a.hand}）</span>
          ))}
        </div>
      )}

      <div className="replay-controls">
        <button className="btn btn-sm" onClick={() => { setPlaying(false); setIdx(0); }}>⏮</button>
        <button className="btn btn-sm" onClick={() => { setPlaying(false); step(-1); }}
                disabled={idx === 0}>◀</button>
        <button className="btn btn-sm gold"
                onClick={() => (isFinal ? setIdx(0) : setPlaying(p => !p))}>
          {isFinal ? '↺' : playing ? '⏸' : '▶'}
        </button>
        <button className="btn btn-sm" onClick={() => { setPlaying(false); step(1); }}
                disabled={idx === last}>▶|</button>
        <button className="btn btn-sm" onClick={() => { setPlaying(false); setIdx(last); }}>⏭</button>
        <input className="replay-slider" type="range" min={0} max={last} value={idx}
               onChange={e => { setPlaying(false); setIdx(Number(e.target.value)); }} />
        <span className="phase-label">{idx + 1}/{data.frames.length}</span>
      </div>
    </div>
  );
}
