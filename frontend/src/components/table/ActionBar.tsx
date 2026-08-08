import { useState } from 'react';

interface Props {
  isMyTurn: boolean;
  currentBet: number;
  myStack: number;
  myCurrentBet: number;
  bigBlind: number;
  onAction: (action: string, amount?: number) => void;
}

export default function ActionBar({ isMyTurn, currentBet, myStack, myCurrentBet, bigBlind, onAction }: Props) {
  const toCall = Math.max(0, currentBet - myCurrentBet);
  const canCheck = toCall === 0;
  const minRaise = currentBet > 0 ? currentBet + bigBlind : bigBlind;
  const maxRaise = myStack + myCurrentBet;  // total commit this street
  const [raiseTo, setRaiseTo] = useState(minRaise);

  if (!isMyTurn) {
    return <div className="action-bar"><span className="waiting-text">Waiting for others...</span></div>;
  }

  const effectiveRaise = Math.min(Math.max(raiseTo, minRaise), maxRaise);

  return (
    <div className="action-bar">
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
        min={minRaise}
        max={Math.max(maxRaise, minRaise)}
        value={effectiveRaise}
        onChange={e => setRaiseTo(Number(e.target.value))}
        disabled={maxRaise < minRaise}
      />
      <button
        className="btn raise"
        onClick={() => onAction(currentBet > 0 ? 'RAISE' : 'BET', effectiveRaise)}
        disabled={maxRaise < minRaise}
      >
        {currentBet > 0 ? `Raise to ${effectiveRaise}` : `Bet ${effectiveRaise}`}
      </button>
      <button className="btn allin" onClick={() => onAction('ALL_IN')} disabled={myStack <= 0}>
        All-in
      </button>
    </div>
  );
}
