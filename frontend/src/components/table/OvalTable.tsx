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

/** Map a player's seat index to an oval display slot, rotating so
 *  *mySeat* is always at position 0 (bottom center). */
function displaySlot(seatIdx: number, total: number, mySeat: number | null): number {
  if (mySeat === null) return seatIdx % 8;
  const rel = (seatIdx - mySeat + total) % total;
  // Spread evenly: position 0 = bottom center, rest clockwise
  const SLOTS = total <= 2 ? [0, 4] : [0, 2, 3, 4, 5, 6, 7, 1];
  if (total <= 8) return SLOTS[rel % SLOTS.length];
  return rel % 8;
}

export default function OvalTable({ players, communityCards, pot, currentPlayerIdx, mySeat, holeCards, phase }: Props) {
  const showCommunity = phase !== 'WAITING' && phase !== 'PREFLOP' && phase !== 'DEALING';
  const n = players.length;

  return (
    <div className="table-felt">
      {showCommunity && <CommunityCards cards={communityCards} />}
      <PotDisplay amount={pot} />

      {players.map((p) => {
        const slot = displaySlot(p.seat_idx, n, mySeat);
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
