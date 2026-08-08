import { useState } from 'react';
import type { PlayerInfo, SeatInfo } from '../../hooks/useGameState';
import PlayerSeat from './PlayerSeat';
import CommunityCards from './CommunityCards';
import PotDisplay from './PotDisplay';

interface Props {
  seats: SeatInfo[];
  players: PlayerInfo[];
  maxSeats: number;
  communityCards: string[];
  pot: number;
  currentPlayerIdx: number | null;
  mySeat: number | null;
  holeCards: string[];
  phase: string;
  onAddBot: (seatIdx: number, level: number) => void;
  onKickBot: (seatIdx: number) => void;
}

/** Map a seat index to an oval display slot, rotating so *mySeat* is at
 *  position 0 (bottom center). */
function displaySlot(seatIdx: number, total: number, mySeat: number | null): number {
  if (mySeat === null) return seatIdx % 8;
  const rel = (seatIdx - mySeat + total) % total;
  const SLOTS = total <= 2 ? [0, 4] : [0, 2, 3, 4, 5, 6, 7, 1];
  if (total <= 8) return SLOTS[rel % SLOTS.length];
  return rel % 8;
}

export default function OvalTable({
  seats, players, maxSeats, communityCards, pot, currentPlayerIdx,
  mySeat, holeCards, phase, onAddBot, onKickBot,
}: Props) {
  const showCommunity = phase !== 'WAITING' && phase !== 'PREFLOP' && phase !== 'DEALING';
  // Mid-hand seating changes corrupt the engine — only offer bot seats
  // between hands (the server enforces this too; this is the UI half).
  const canAddBot = phase === 'WAITING' || phase === 'SHOWDOWN';
  const [pendingSeat, setPendingSeat] = useState<number | null>(null);
  const total = Math.min(Math.max(maxSeats, 2), 8);
  const occupied = new Map(seats.map(s => [s.seat_idx, s]));

  return (
    <div className="table-felt">
      {showCommunity && <CommunityCards cards={communityCards} />}
      <PotDisplay amount={pot} />

      {seats.map((seat) => {
        const p = players.find(pl => pl.seat_idx === seat.seat_idx);
        const isMe = mySeat === seat.seat_idx;
        const slot = displaySlot(seat.seat_idx, total, mySeat);
        // Merge lobby-level seat info with in-hand player info
        const merged: PlayerInfo = p ?? {
          seat_idx: seat.seat_idx,
          name: seat.name,
          stack: seat.stack,
          current_bet: 0,
          is_active: true,
          is_all_in: false,
          is_human: seat.is_human,
        };
        return (
          <div key={seat.seat_idx} className="seat-wrap">
            <PlayerSeat
              player={merged}
              seatIndex={slot}
              isCurrent={currentPlayerIdx === seat.seat_idx}
              holeCards={isMe ? holeCards : undefined}
              showCards={phase === 'SHOWDOWN' || isMe}
            />
            {!seat.is_human && (
              <span className="bot-badge">
                L{seat.bot_level ?? 2}
                <button className="kick-btn" title="Remove bot"
                        onClick={() => onKickBot(seat.seat_idx)}>×</button>
              </span>
            )}
          </div>
        );
      })}

      {canAddBot && Array.from({ length: maxSeats }, (_, i) => i)
        .filter(i => !occupied.has(i))
        .map(i => (
          <div key={`empty-${i}`} className={`empty-seat seat-${displaySlot(i, total, mySeat)}`}>
            {pendingSeat === i ? (
              <span className="bot-level-picker">
                {[1, 2, 3].map(lv => (
                  <button key={lv} className="btn btn-sm"
                          onClick={() => { onAddBot(i, lv); setPendingSeat(null); }}>
                    L{lv}
                  </button>
                ))}
              </span>
            ) : (
              <button className="add-bot-btn" onClick={() => setPendingSeat(i)}>+ Bot</button>
            )}
          </div>
        ))}
    </div>
  );
}
