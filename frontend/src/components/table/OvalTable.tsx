import type { PlayerInfo } from '../../hooks/useGameState';
import PlayerSeat from './PlayerSeat';
import CommunityCards from './CommunityCards';
import PotDisplay from './PotDisplay';

interface Props {
  players: PlayerInfo[];
  communityCards: string[];
  pot: number;
  currentPlayerIdx: number | null;
  mySeat: number | null;
  holeCards: string[];
  phase: string;
}

/** Map a player's seat index to a display position slot (0-7). */
function displaySlot(seatIdx: number, totalSeats: number): number {
  // Spread seats evenly around the oval
  if (totalSeats <= 2) return seatIdx === 0 ? 0 : 4;
  return seatIdx % 8;
}

export default function OvalTable({ players, communityCards, pot, currentPlayerIdx, mySeat, holeCards, phase }: Props) {
  const showCommunity = phase !== 'WAITING' && phase !== 'PREFLOP' && phase !== 'DEALING';

  return (
    <div className="table-felt">
      {showCommunity && <CommunityCards cards={communityCards} />}
      <PotDisplay amount={pot} />

      {players.map((p) => {
        const slot = displaySlot(p.seat_idx, players.length);
        const isMe = mySeat === p.seat_idx;
        return (
          <PlayerSeat
            key={p.seat_idx}
            player={p}
            seatIndex={slot}
            isCurrent={currentPlayerIdx === p.seat_idx}
            holeCards={isMe ? holeCards : undefined}
            showCards={phase === 'SHOWDOWN' || isMe}
          />
        );
      })}
    </div>
  );
}
