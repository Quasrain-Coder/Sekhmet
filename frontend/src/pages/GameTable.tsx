import { useCallback, useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useGameState } from '../hooks/useGameState';
import type { GameMsg } from '../hooks/useGameState';
import OvalTable from '../components/table/OvalTable';
import ActionBar from '../components/table/ActionBar';

interface Props {
  tableId: string;
  name: string;
  seatIdx: number;
  buyin: number;
  onBack: () => void;
}

export default function GameTablePage({ tableId, name, seatIdx, buyin, onBack }: Props) {
  const [state, dispatch] = useGameState();
  const { connected, send, onMessage } = useWebSocket(tableId);

  // Dispatch messages to reducer
  useEffect(() => {
    onMessage((msg) => {
      const m = msg as GameMsg;
      switch (m.type) {
        case 'table_state': dispatch({ type: 'TABLE_STATE', data: m as any }); break;
        case 'hand_start': dispatch({ type: 'HAND_START', data: m as any }); break;
        case 'hole_cards': dispatch({ type: 'HOLE_CARDS', cards: m.cards }); break;
        case 'game_state_update': dispatch({ type: 'GAME_UPDATE', data: m as any }); break;
        case 'hand_result': dispatch({ type: 'HAND_RESULT', data: m as any }); break;
      }
    });
  }, [onMessage, dispatch]);

  // Sit down on mount
  useEffect(() => {
    dispatch({ type: 'SET_TABLE', tableId });
    dispatch({ type: 'SET_CONNECTED', connected });
  }, [tableId, connected, dispatch]);

  useEffect(() => {
    if (connected) {
      send({ type: 'sit_down', seat_idx: seatIdx, name, buyin });
      dispatch({ type: 'SET_MY_SEAT', seat: seatIdx });
    }
  }, [connected, send, seatIdx, name, buyin, dispatch]);

  const handleAction = useCallback((action: string, amount?: number) => {
    send({ type: 'player_action', action, amount: amount ?? 0 });
  }, [send]);

  const me = state.players.find(p => p.seat_idx === state.mySeat);

  return (
    <div className="game-table">
      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
        <button className="btn btn-sm" onClick={onBack}>← Lobby</button>
        <span className="phase-label">{state.phase}{!connected && ' (disconnected)'}</span>
        <button className="btn btn-sm" onClick={() => send({ type: 'start_hand' })}
                disabled={state.phase !== 'WAITING' && state.phase !== 'SHOWDOWN'}>
          Deal
        </button>
      </div>

      <OvalTable
        players={state.players}
        communityCards={state.communityCards}
        pot={state.pot}
        currentPlayerIdx={state.currentPlayerIdx}
        mySeat={state.mySeat}
        holeCards={state.holeCards}
        phase={state.phase}
      />

      <ActionBar
        isMyTurn={state.currentPlayerIdx === state.mySeat}
        currentBet={state.currentBet}
        myStack={me?.stack ?? 0}
        myCurrentBet={me?.current_bet ?? 0}
        bigBlind={10}
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
