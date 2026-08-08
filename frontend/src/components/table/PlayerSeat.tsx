import CardView from './CardView';
import type { PlayerInfo } from '../../hooks/useGameState';

interface Props {
  player: PlayerInfo;
  seatIndex: number;
  isCurrent: boolean;
  holeCards?: string[];
  showCards?: boolean;
}

export default function PlayerSeat({ player, seatIndex, isCurrent, holeCards, showCards }: Props) {
  const folded = !player.is_active;
  const cls = [
    'player-seat',
    `seat-${seatIndex}`,
    isCurrent ? 'active' : '',
    folded ? 'folded' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={cls}>
      <div className="name">
        {isCurrent && '▸ '}{player.name}
      </div>
      <div className="cards">
        {holeCards ? (
          holeCards.map((c, i) => <CardView key={i} card={showCards ? c : undefined} small />)
        ) : (
          <>
            <CardView small />
            <CardView small />
          </>
        )}
      </div>
      <div className="stack">{player.stack}</div>
      {player.current_bet > 0 && (
        <div className="bet">Bet: {player.current_bet}</div>
      )}
    </div>
  );
}
