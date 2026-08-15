import { useEffect, useState } from 'react';

const ACTION_TIMEOUT_S = 30;  // must match backend app_config.game.action_timeout_seconds
const WARN_AT_S = 10;

// Quick "fraction of the pot" presets.  Pot is measured AFTER calling
// (pot + toCall) — the standard convention — so a full-pot raise is
// call + (pot + call).
const POT_PRESETS: { label: string; fraction: number }[] = [
  { label: '1/3 pot', fraction: 1 / 3 },
  { label: '1/2 pot', fraction: 1 / 2 },
  { label: '2/3 pot', fraction: 2 / 3 },
  { label: 'Pot', fraction: 1 },
];

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
  // Total chips in the pot (main + side pots) — anchor for the pot-fraction
  // presets.
  pot: number;
  // Bumped by the reducer when the server re-arms the countdown (reclaim
  // mid-turn) — restarting the local timer keeps it aligned with the
  // server's auto check/fold deadline.
  turnEpoch?: number;
  onAction: (action: string, amount?: number) => void;
}

export default function ActionBar({ isMyTurn, currentBet, myStack, myCurrentBet, bigBlind, minRaise, pot, turnEpoch = 0, onAction }: Props) {
  const toCall = Math.max(0, currentBet - myCurrentBet);
  const canCheck = toCall === 0;
  const minRaiseTo = minRaise > 0 ? minRaise : (currentBet > 0 ? currentBet + bigBlind : bigBlind);
  const maxRaise = myStack + myCurrentBet;  // total commit this street
  const canRaise = maxRaise >= minRaiseTo;
  const [raiseTo, setRaiseTo] = useState(minRaiseTo);
  // Draft for the direct-input box, kept as a string so the user can type
  // freely (empty / partial values); parsed and clamped on commit.
  const [raiseText, setRaiseText] = useState(String(minRaiseTo));
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

  // Each new turn (or a server re-arm via turnEpoch) starts the draft at
  // the street's minimum raise-to so a stale draft never leaks across
  // streets.
  useEffect(() => {
    if (!isMyTurn) return;
    setRaiseTo(minRaiseTo);
    setRaiseText(String(minRaiseTo));
  }, [isMyTurn, turnEpoch, minRaiseTo]);

  if (!isMyTurn) {
    return <div className="action-bar"><span className="waiting-text">Waiting for others...</span></div>;
  }

  const clampRaise = (v: number) => Math.min(Math.max(v, minRaiseTo), maxRaise);
  const commitRaise = (v: number) => {
    const c = clampRaise(v);
    setRaiseTo(c);
    setRaiseText(String(c));
  };
  // What a Raise click actually sends: the typed draft when it parses,
  // otherwise the slider/preset value.
  const draft = Number(raiseText);
  const displayRaise = Number.isFinite(draft) && draft > 0 ? clampRaise(draft) : raiseTo;

  const applyPreset = (fraction: number) => {
    if (!canRaise) return;
    commitRaise(toCall + Math.round((pot + toCall) * fraction));
  };

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
      <div className="raise-controls">
        <div className="raise-row">
          <input
            className="raise-slider"
            type="range"
            min={minRaiseTo}
            max={Math.max(maxRaise, minRaiseTo)}
            value={raiseTo}
            onChange={e => commitRaise(Number(e.target.value))}
            disabled={!canRaise}
          />
          <input
            className="input raise-input"
            type="number"
            min={minRaiseTo}
            max={maxRaise}
            value={raiseText}
            disabled={!canRaise}
            onChange={e => setRaiseText(e.target.value)}
            onBlur={() => {
              const n = Number(raiseText);
              if (Number.isFinite(n) && n > 0) commitRaise(n);
              else setRaiseText(String(raiseTo));  // revert garbage to committed value
            }}
            onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }}
          />
        </div>
        <div className="raise-presets">
          {POT_PRESETS.map(p => (
            <button key={p.label} className="btn btn-sm" disabled={!canRaise}
                    onClick={() => applyPreset(p.fraction)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <button
        className="btn raise"
        onClick={() => onAction(currentBet > 0 ? 'RAISE' : 'BET', displayRaise)}
        disabled={!canRaise}
      >
        {currentBet > 0 ? `Raise to ${displayRaise}` : `Bet ${displayRaise}`}
      </button>
      <button className="btn allin" onClick={() => onAction('ALL_IN')} disabled={myStack <= 0}>
        All-in
      </button>
    </div>
  );
}
