import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket';
import { useGameState } from '../hooks/useGameState';
import type { GameMsg, TableConfigData, SeatInfo } from '../hooks/useGameState';
import OvalTable from '../components/table/OvalTable';
import ActionBar from '../components/table/ActionBar';
import Leaderboard from '../components/table/Leaderboard';

interface TableDetail {
  table_id: string;
  phase: string;
  max_seats: number;
  config: TableConfigData;
  seats: SeatInfo[];
}

export default function GameTablePage() {
  const { tableId = '' } = useParams();
  const navigate = useNavigate();
  const [state, dispatch] = useGameState();
  const { connected, send, onMessage } = useWebSocket(tableId);
  const [detail, setDetail] = useState<TableDetail | null | 'not-found'>(null);
  const [name, setName] = useState(() => localStorage.getItem('pokerName') || '');
  const [buyin, setBuyin] = useState(200);
  // Seat we optimistically claimed via sit_down but the server has not yet
  // confirmed (table_state echo).  An 'error' while pending means the sit
  // was rejected — revert mySeat so the user is not stranded at the table.
  const pendingSeat = useRef<number | null>(null);

  // Fetch room info for the join panel
  useEffect(() => {
    fetch(`/api/game/tables/${tableId}`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((d: TableDetail) => { setDetail(d); setBuyin(d.config.default_buyin); })
      .catch(() => setDetail('not-found'));
  }, [tableId]);

  // Dispatch messages to reducer
  useEffect(() => {
    onMessage((msg) => {
      const m = msg as GameMsg;
      switch (m.type) {
        case 'table_state':
          if (pendingSeat.current !== null &&
              m.seats.some(s => s.seat_idx === pendingSeat.current)) {
            pendingSeat.current = null;  // sit confirmed
          }
          dispatch({ type: 'TABLE_STATE', data: m as any });
          break;
        case 'hand_start': dispatch({ type: 'HAND_START', data: m as any }); break;
        case 'hole_cards': dispatch({ type: 'HOLE_CARDS', cards: m.cards }); break;
        case 'game_state_update': dispatch({ type: 'GAME_UPDATE', data: m as any }); break;
        case 'hand_result': dispatch({ type: 'HAND_RESULT', data: m as any }); break;
        case 'error':
          if (pendingSeat.current !== null) {
            pendingSeat.current = null;
            dispatch({ type: 'SET_MY_SEAT', seat: null });
          }
          alert(m.message);  // never fail silently
          break;
      }
    });
  }, [onMessage, dispatch]);

  useEffect(() => {
    dispatch({ type: 'SET_TABLE', tableId });
    dispatch({ type: 'SET_CONNECTED', connected });
  }, [tableId, connected, dispatch]);

  const joinTable = () => {
    if (!detail || detail === 'not-found') return;
    // Use the freshly fetched REST detail for occupancy — the reducer's
    // seats only populate on table_state broadcasts (sit/stand events).
    const taken = new Set(detail.seats.map(s => s.seat_idx));
    const free = Array.from({ length: detail.max_seats }, (_, i) => i)
      .find(i => !taken.has(i));
    if (free === undefined) { alert('Table is full'); return; }
    localStorage.setItem('pokerName', name);
    pendingSeat.current = free;
    send({ type: 'sit_down', seat_idx: free, name, buyin });
    dispatch({ type: 'SET_MY_SEAT', seat: free });
  };

  const addBot = useCallback((seatIdx: number, level: number) => {
    send({ type: 'sit_down', seat_idx: seatIdx, name: `Bot L${level}`,
           buyin: state.config?.default_buyin ?? 200, is_human: false, bot_level: level });
  }, [send, state.config]);

  const kickBot = useCallback((seatIdx: number) => {
    send({ type: 'stand_up', seat_idx: seatIdx });
  }, [send]);

  const handleAction = useCallback((action: string, amount?: number) => {
    send({ type: 'player_action', action, amount: amount ?? 0 });
  }, [send]);

  // ---- Join panel (not seated yet) ----
  if (state.mySeat === null) {
    if (detail === 'not-found') {
      return (
        <div className="join-panel">
          <h2>Table not found</h2>
          <button className="btn" onClick={() => navigate('/')}>← Lobby</button>
        </div>
      );
    }
    if (!detail) return <div className="waiting-text">Loading…</div>;
    const midHand = detail.phase !== 'WAITING' && detail.phase !== 'SHOWDOWN';
    return (
      <div className="join-panel">
        <h2>Table {detail.table_id}</h2>
        <p className="room-meta">Blinds {detail.config.small_blind}/{detail.config.big_blind}
           {' '}· Buy-in {detail.config.default_buyin}
           {' '}· {detail.seats.length}/{detail.max_seats} players
           {' '}· {detail.phase}</p>
        {detail.seats.length > 0 && (
          <p className="room-meta">Seated: {detail.seats.map(s => s.name).join(', ')}</p>
        )}
        <div className="lobby-actions">
          <input className="input" placeholder="Your name" value={name}
                 onChange={e => setName(e.target.value)} />
          <input className="input" type="number" value={buyin} style={{ width: 110 }}
                 onChange={e => setBuyin(Number(e.target.value))} />
          <button className="btn" onClick={joinTable}
                  disabled={!name || !connected || midHand}>
            Sit Down
          </button>
          <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        </div>
        {midHand && (
          <p className="join-hint">Hand in progress — wait for it to finish</p>
        )}
      </div>
    );
  }

  // ---- Table view (seated) ----
  const me = state.players.find(p => p.seat_idx === state.mySeat);

  return (
    <div className="game-table">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        <span className="logo">♠ Sekhmet</span>
        <span className="phase-label">
          {tableId} · {state.phase}{!connected && ' (disconnected)'}
        </span>
        <button className="btn btn-sm gold" onClick={() => send({ type: 'start_hand' })}
                disabled={state.phase !== 'WAITING' && state.phase !== 'SHOWDOWN'}>
          Deal
        </button>
      </div>

      <OvalTable
        seats={state.seats}
        players={state.players}
        maxSeats={state.maxSeats}
        communityCards={state.communityCards}
        pot={state.pot}
        currentPlayerIdx={state.currentPlayerIdx}
        mySeat={state.mySeat}
        holeCards={state.holeCards}
        phase={state.phase}
        onAddBot={addBot}
        onKickBot={kickBot}
      />

      <Leaderboard seats={state.seats} />

      <ActionBar
        isMyTurn={state.currentPlayerIdx === state.mySeat}
        currentBet={state.currentBet}
        myStack={me?.stack ?? 0}
        myCurrentBet={me?.current_bet ?? 0}
        bigBlind={state.config?.big_blind ?? 10}
        onAction={handleAction}
      />

      {state.showdown && (
        <div className="hand-result">
          <h3>Showdown</h3>
          {Object.entries(state.showdown.hands).map(([s, h]) => (
            <div key={s}>Seat {s}: {h}</div>
          ))}
          {state.showdown.awards.map((a, i) => (
            <div key={i} className="award">
              <span className="winner">Seat {a.seat_idx} wins {a.amount}</span>
              <span>{a.hand}</span>
            </div>
          ))}
          {state.phase === 'SHOWDOWN' && (
            <button className="btn gold next-hand"
                    onClick={() => send({ type: 'start_hand' })}>
              Next Hand
            </button>
          )}
        </div>
      )}

      <div className="history">
        {state.roundHistory.map((h, i) => (
          <span key={i}>P{h.seat} {h.action}{h.amount > 0 ? ` ${h.amount}` : ''} · </span>
        ))}
      </div>
    </div>
  );
}
