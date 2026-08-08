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
  const [raiseAmount, setRaiseAmount] = useState('');
  const toCall = Math.max(0, currentBet - myCurrentBet);
  const canCheck = toCall === 0;
  const minRaise = currentBet > 0 ? currentBet + bigBlind : bigBlind;

  if (!isMyTurn) {
    return <div className="action-bar"><span className="waiting-text">Waiting for others...</span></div>;
  }

  return (
    <div className="action-bar">
      <button className="btn fold" onClick={() => onAction('FOLD')}>Fold</button>
      {canCheck ? (
        <button className="btn check" onClick={() => onAction('CHECK')}>Check</button>
      ) : (
        <button className="btn" onClick={() => onAction('CALL')} disabled={toCall > myStack}>
          Call {toCall}
        </button>
      )}
      <input
        className="input raise-input"
        type="number"
        placeholder={String(minRaise)}
        value={raiseAmount}
        onChange={e => setRaiseAmount(e.target.value)}
        min={minRaise}
      />
      <button
        className="btn"
        onClick={() => { onAction(currentBet > 0 ? 'RAISE' : 'BET', Number(raiseAmount) || minRaise); setRaiseAmount(''); }}
        disabled={!isMyTurn}
      >
        {currentBet > 0 ? 'Raise' : 'Bet'}
      </button>
      <button
        className="btn allin"
        onClick={() => onAction('ALL_IN')}
        disabled={myStack <= 0}
      >
        All-in
      </button>
    </div>
  );
}
