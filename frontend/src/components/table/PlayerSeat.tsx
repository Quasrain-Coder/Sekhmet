import CardView from './CardView';
import type { PlayerInfo } from '../../hooks/useGameState';

interface Props {
  player: PlayerInfo;
  seatIndex: number;
  isCurrent: boolean;
  holeCards?: string[];   // only ever set for the hero
  avatarLabel: string;
  isMe: boolean;
}

export default function PlayerSeat({ player, seatIndex, isCurrent, holeCards, avatarLabel, isMe }: Props) {
  const folded = !player.is_active;
  const cls = [
    'player-seat',
    `seat-${seatIndex}`,
    isCurrent ? 'active' : '',
    folded ? 'folded' : '',
    isMe ? 'me' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={cls}>
      <div className="avatar">{avatarLabel}</div>
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
