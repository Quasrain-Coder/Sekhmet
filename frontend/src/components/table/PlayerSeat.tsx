import CardView from './CardView';
import type { PlayerInfo } from '../../hooks/useGameState';

interface Props {
  player: PlayerInfo;
  isCurrent: boolean;
  holeCards?: string[];   // only ever set for the hero
  avatarLabel: string;
  isMe: boolean;
  positionTag?: 'D' | 'SB' | 'BB';
}

export default function PlayerSeat({ player, isCurrent, holeCards, avatarLabel, isMe, positionTag }: Props) {
  const folded = !player.is_active;
  // NOTE: no seat-N class here — absolute placement is owned by the outer
  // .seat-wrap (PR #10). player-seat is position:relative (containing block
  // for the .bet capsule); an inner seat-N would re-apply top/left offsets.
  const cls = [
    'player-seat',
    isCurrent ? 'active' : '',
    folded ? 'folded' : '',
    isMe ? 'me' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={cls}>
      <div className="avatar">{avatarLabel}
        {positionTag && <span className={`pos-tag pos-${positionTag.toLowerCase()}`}>{positionTag}</span>}
      </div>
      <div className="name">{player.name}</div>
      <div className="stack">{player.stack}</div>
      {player.current_bet > 0 && <div className="bet">{player.current_bet}</div>}
      {holeCards && (
        <div className="cards">
          {holeCards.map((c, i) => <CardView key={i} card={c} big />)}
        </div>
      )}
    </div>
  );
}
