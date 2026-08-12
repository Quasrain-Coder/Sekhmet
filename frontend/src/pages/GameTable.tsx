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
  const [rebuyAmount, setRebuyAmount] = useState(200);
  const [selectedSeat, setSelectedSeat] = useState<number | null>(null);
  // Seat we optimistically claimed via sit_down but the server has not yet
  // confirmed (table_state echo).  An 'error' while pending means the sit
  // was rejected — revert mySeat so the user is not stranded at the table.
  const pendingSeat = useRef<number | null>(null);

  // Fetch room info for the join panel
  useEffect(() => {
    fetch(`/api/game/tables/${tableId}`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((d: TableDetail) => {
        setDetail(d);
        setBuyin(d.config.default_buyin);
        setRebuyAmount(d.config.default_buyin);
        const taken = new Set(d.seats.map(s => s.seat_idx));
        const free = Array.from({ length: d.max_seats }, (_, i) => i).find(i => !taken.has(i));
        setSelectedSeat(free ?? null);
      })
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
        case 'reclaim_token':
          localStorage.setItem(`reclaimToken_${tableId}`, m.token);
          // The server assigns the seat authoritatively — on reclaim it is
          // the OLD seat, which may differ from the picker selection.
          // Receiving the token also confirms the sit, so drop pendingSeat
          // (its table_state/error handlers are no-ops once null).
          pendingSeat.current = null;
          dispatch({ type: 'SET_MY_SEAT', seat: m.seat });
          break;
        case 'room_closed':
          alert('Room was closed due to inactivity');
          navigate('/');
          break;
        case 'error':
          if (pendingSeat.current !== null) {
            pendingSeat.current = null;
            dispatch({ type: 'SET_MY_SEAT', seat: null });
          }
          alert(m.message);  // never fail silently
          break;
      }
    });
  }, [onMessage, dispatch, tableId, navigate]);

  useEffect(() => {
    dispatch({ type: 'SET_TABLE', tableId });
    dispatch({ type: 'SET_CONNECTED', connected });
  }, [tableId, connected, dispatch]);

  const joinTable = () => {
    if (!detail || detail === 'not-found' || selectedSeat === null) return;
    localStorage.setItem('pokerName', name);
    pendingSeat.current = selectedSeat;
    const reclaimToken = localStorage.getItem(`reclaimToken_${tableId}`);
    send({ type: 'sit_down', seat_idx: selectedSeat, name, buyin,
           ...(reclaimToken ? { reclaim_token: reclaimToken } : {}) });
    dispatch({ type: 'SET_MY_SEAT', seat: selectedSeat });
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
    // Reclaim must stay reachable mid-hand (that's its core value: a
    // disconnected player rejoins the hand in progress).  The midHand
    // disable only blocks FRESH joins.
    const selectedOcc = detail.seats.find(s => s.seat_idx === selectedSeat);
    const selectedIsReclaimable = !!selectedOcc && !selectedOcc.connected
      && selectedOcc.name === name;
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
        <div className="seat-picker">
          {Array.from({ length: detail.max_seats }, (_, i) => {
            const occ = detail.seats.find(s => s.seat_idx === i);
            // A disconnected seat whose name matches the typed name can be
            // reclaimed — the server runs try_reclaim on same-name sit_down.
            const reclaimable = occ && !occ.connected && occ.name === name;
            return (
              <button
                key={i}
                className={`picker-seat seat-${i}${occ ? ' taken' : ''}${reclaimable ? ' reclaim' : ''}${selectedSeat === i ? ' selected' : ''}`}
                disabled={!!occ && !reclaimable}
                title={occ ? occ.name : `Seat ${i}`}
                onClick={() => setSelectedSeat(i)}
              >
                {occ ? occ.name.charAt(0) : i}
              </button>
            );
          })}
        </div>
        <div className="lobby-actions">
          <input className="input" placeholder="Your name" value={name}
                 onChange={e => setName(e.target.value)} />
          <input className="input" type="number" value={buyin} style={{ width: 110 }}
                 onChange={e => setBuyin(Number(e.target.value))} />
          <button className="btn" onClick={joinTable}
                  disabled={!name || !connected || selectedSeat === null
                            || (midHand && !selectedIsReclaimable)}>
            Sit Down
          </button>
          <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        </div>
        {midHand && !selectedIsReclaimable && (
          <p className="join-hint">Hand in progress — wait for it to finish</p>
        )}
      </div>
    );
  }

  // ---- Table view (seated) ----
  const me = state.players.find(p => p.seat_idx === state.mySeat);
  const isOwner = state.seats.find(s => s.seat_idx === state.mySeat)?.is_owner ?? false;

  return (
    <div className="game-table">
      <div className="table-head">
        <button className="btn btn-sm" onClick={() => navigate('/')}>← Lobby</button>
        <span className="logo">♠ Sekhmet</span>
        <span className="phase-label">
          {tableId} · {state.phase}{!connected && ' (disconnected)'}
        </span>
        <button className="btn btn-sm gold" onClick={() => send({ type: 'start_hand' })}
                disabled={!isOwner || (state.phase !== 'WAITING' && state.phase !== 'SHOWDOWN')}
                title={isOwner ? '' : 'Only the table owner can deal'}>
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
        dealerIdx={state.dealerIdx}
        sbSeat={state.sbSeat}
        bbSeat={state.bbSeat}
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

      {me && me.stack === 0 && (state.phase === 'WAITING' || state.phase === 'SHOWDOWN') && (
        <div className="rebuy-panel">
          <span className="rebuy-label">You're busted.</span>
          <input className="input" type="number" value={rebuyAmount}
                 onChange={e => setRebuyAmount(Number(e.target.value))} />
          <button className="btn gold"
                  onClick={() => send({ type: 'rebuy', amount: rebuyAmount })}>
            Rebuy
          </button>
        </div>
      )}

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
