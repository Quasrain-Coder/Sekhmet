import { useEffect, useRef, useState } from 'react';
import CardView from './CardView';
import type { PlayerInfo } from '../../hooks/useGameState';

interface Props {
  player: PlayerInfo;
  isCurrent: boolean;
  holeCards?: string[];   // only ever set for the hero
  avatarLabel: string;
  isMe: boolean;
  positionTag?: 'D' | 'SB' | 'BB';
  // A hand is in progress (not WAITING/SHOWDOWN): active opponents show two
  // face-down cards.  The hero's own cards are `holeCards`.
  inHand: boolean;
  // Increments on every deal.  The card elements are keyed by it, so a new
  // hand remounts them and replays the deal animation.  0 (e.g. reclaim
  // mid-hand) renders static cards with no animation.
  dealSeq: number;
}

const FOLD_ANIM_MS = 800;  // matches the CSS fold-fly-out duration + stagger

export default function PlayerSeat({ player, isCurrent, holeCards, avatarLabel, isMe, positionTag, inHand, dealSeq }: Props) {
  // `=== false` (not `!`) — a missing field must never render everyone
  // folded, which happened when hand_start omitted is_active.
  const folded = player.is_active === false;
  // One-shot fold animation on the active→folded transition.  The card
  // backs fly toward the table centre, then unmount and only the Fold
  // badge remains.  A fresh hand (folded→active) cancels any leftover
  // animation so cards never fly out of a live hand.
  const prevActive = useRef(player.is_active);
  const [justFolded, setJustFolded] = useState(false);
  useEffect(() => {
    const was = prevActive.current;
    prevActive.current = player.is_active;
    if (was === true && player.is_active === false) {
      setJustFolded(true);
      const t = setTimeout(() => setJustFolded(false), FOLD_ANIM_MS);
      return () => clearTimeout(t);
    }
    if (was === false && player.is_active === true) setJustFolded(false);
  }, [player.is_active]);

  // NOTE: no seat-N class here — absolute placement is owned by the outer
  // .seat-wrap (PR #10). player-seat is position:relative (containing block
  // for the .bet capsule); an inner seat-N would re-apply top/left offsets.
  const cls = [
    'player-seat',
    isCurrent ? 'active' : '',
    folded ? 'folded' : '',
    isMe ? 'me' : '',
  ].filter(Boolean).join(' ');

  const showBacks = !isMe && (inHand || justFolded);

  return (
    <div className={cls}>
      <div className="avatar">{avatarLabel}
        {positionTag && <span className={`pos-tag pos-${positionTag.toLowerCase()}`}>{positionTag}</span>}
      </div>
      {showBacks && (
        <div className={`hole-cards${justFolded ? ' folding' : dealSeq > 0 ? ' dealing' : ''}`}>
          {[0, 1].map(i => (
            <span key={`${dealSeq}-${i}`} className="hole-card"
                  style={{ animationDelay: `${i * 70}ms` }} />
          ))}
        </div>
      )}
      <div className="name">{player.name}</div>
      <div className="stack">{player.stack}</div>
      {player.current_bet > 0 && <div className="bet">{player.current_bet}</div>}
      {folded && <span className="folded-tag">Fold</span>}
      {holeCards && (
        // keyed by dealSeq: a new hand remounts the row so the deal
        // animation replays even if hole_cards landed before the trigger
        <div key={dealSeq} className={`cards${dealSeq > 0 ? ' dealing' : ''}`}>
          {holeCards.map((c, i) => <CardView key={i} card={c} big />)}
        </div>
      )}
    </div>
  );
}
