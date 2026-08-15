import { useEffect, useState } from 'react';

const ACTION_TIMEOUT_S = 30;  // must match backend app_config.game.action_timeout_seconds
const WARN_AT_S = 10;

interface Props {
  isMyTurn: boolean;
  currentBet: number;
  myStack: number;
  myCurrentBet: number;
  bigBlind: number;
  // Server-authoritative minimum raise-to (current_bet + engine min_raise,
  // which grows with the last full raise).  Fall back to the blind-based
  // approximation only until the first broadcast arrives.
  minRaise: number;
  // Bumped by the reducer when the server re-arms the countdown (reclaim
  // mid-turn) — restarting the local timer keeps it aligned with the
  // server's auto check/fold deadline.
  turnEpoch?: number;
  onAction: (action: string, amount?: number) => void;
}

export default function ActionBar({ isMyTurn, currentBet, myStack, myCurrentBet, bigBlind, minRaise, turnEpoch = 0, onAction }: Props) {
  const toCall = Math.max(0, currentBet - myCurrentBet);
  const canCheck = toCall === 0;
  const minRaiseTo = minRaise > 0 ? minRaise : (currentBet > 0 ? currentBet + bigBlind : bigBlind);
  const maxRaise = myStack + myCurrentBet;  // total commit this street
  const [raiseTo, setRaiseTo] = useState(minRaiseTo);
  const [remaining, setRemaining] = useState(ACTION_TIMEOUT_S);

  // Local countdown mirror of the server's timeout: the backend silently
  // auto-folds after 30s (and kicks after 3 in a row), so the player must
  // be able to see the clock running out.
  useEffect(() => {
    if (!isMyTurn) return;
    setRemaining(ACTION_TIMEOUT_S);
    const started = Date.now();
    const id = setInterval(() => {
      const left = ACTION_TIMEOUT_S - Math.floor((Date.now() - started) / 1000);
      setRemaining(Math.max(0, left));
    }, 250);
    return () => clearInterval(id);
  }, [isMyTurn, turnEpoch]);

  if (!isMyTurn) {
    return <div className="action-bar"><span className="waiting-text">Waiting for others...</span></div>;
  }

  const effectiveRaise = Math.min(Math.max(raiseTo, minRaiseTo), maxRaise);

  return (
    <div className="action-bar">
      <span className={`action-timer${remaining <= WARN_AT_S ? ' warn' : ''}`}>
        ⏱ {remaining}s
      </span>
      <button className="btn fold" onClick={() => onAction('FOLD')}>Fold</button>
      {canCheck ? (
        <button className="btn check" onClick={() => onAction('CHECK')}>Check</button>
      ) : (
        <button className="btn check" onClick={() => onAction('CALL')} disabled={toCall > myStack}>
          Call {toCall}
        </button>
      )}
      <input
        className="raise-slider"
        type="range"
        min={minRaiseTo}
        max={Math.max(maxRaise, minRaiseTo)}
        value={effectiveRaise}
        onChange={e => setRaiseTo(Number(e.target.value))}
        disabled={maxRaise < minRaiseTo}
      />
      <button
        className="btn raise"
        onClick={() => onAction(currentBet > 0 ? 'RAISE' : 'BET', effectiveRaise)}
        disabled={maxRaise < minRaiseTo}
      >
        {currentBet > 0 ? `Raise to ${effectiveRaise}` : `Bet ${effectiveRaise}`}
      </button>
      <button className="btn allin" onClick={() => onAction('ALL_IN')} disabled={myStack <= 0}>
        All-in
      </button>
    </div>
  );
}
