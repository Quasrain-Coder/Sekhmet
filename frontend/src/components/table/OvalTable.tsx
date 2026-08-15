import { useEffect, useRef, useState } from 'react';
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
  dealerIdx: number | null;
  sbSeat: number | null;
  bbSeat: number | null;
  mySeat: number | null;
  holeCards: string[];
  phase: string;
  onAddBot: (seatIdx: number, level: number) => void;
  onKickBot: (seatIdx: number) => void;
}

/** Map a seat index to an oval display slot, rotating so *mySeat* is at
 *  position 0 (bottom center). */
function displaySlot(seatIdx: number, total: number, mySeat: number | null): number {
  if (mySeat === null) return seatIdx % total;
  const rel = (seatIdx - mySeat + total) % total;
  if (total <= 2) return [0, 4][rel % 2];
  // 9-handed needs the 9th visual slot (.seat-8, between top-left and
  // top-center) — folding it into slot 0 would stack it on my seat.
  if (total === 9) return [0, 2, 3, 4, 8, 5, 6, 7, 1][rel];
  const SLOTS = [0, 2, 3, 4, 5, 6, 7, 1];
  return SLOTS[rel % SLOTS.length];
}

export default function OvalTable({
  seats, players, maxSeats, communityCards, pot, currentPlayerIdx,
  dealerIdx, sbSeat, bbSeat,
  mySeat, holeCards, phase, onAddBot, onKickBot,
}: Props) {
  const showCommunity = phase !== 'WAITING' && phase !== 'PREFLOP' && phase !== 'DEALING';
  // Mid-hand seating changes corrupt the engine — only offer bot seats
  // between hands (the server enforces this too; this is the UI half).
  const canAddBot = phase === 'WAITING' || phase === 'SHOWDOWN';
  const [pendingSeat, setPendingSeat] = useState<number | null>(null);
  // Close a stale level picker when a hand starts — it must not
  // resurrect on its own when bot seats unlock again at SHOWDOWN.
  useEffect(() => {
    if (!canAddBot) setPendingSeat(null);
  }, [canAddBot]);
  const total = Math.min(Math.max(maxSeats, 2), 9);
  const occupied = new Map(seats.map(s => [s.seat_idx, s]));
  // Card backs exist from deal through showdown; they clear in WAITING.
  const handLive = phase !== 'WAITING' && phase !== 'SHOWDOWN';
  // Deal-animation trigger: fires on the WAITING/SHOWDOWN → DEALING/PREFLOP
  // transition (a new hand).  Reclaims mid-hand never fire it — prevPhase
  // initialises to the current phase, so only a real transition counts.
  const prevPhase = useRef(phase);
  const [dealSeq, setDealSeq] = useState(0);
  useEffect(() => {
    const started = (phase === 'DEALING' || phase === 'PREFLOP')
      && (prevPhase.current === 'WAITING' || prevPhase.current === 'SHOWDOWN');
    prevPhase.current = phase;
    if (started) setDealSeq(s => s + 1);
  }, [phase]);

  return (
    <div className="table-felt">
      <div className="felt-rail" />
      <div className="felt-cloth" />
      <div className="bet-line" />
      <div className="felt-watermark">♠ SEKHMET</div>
      {showCommunity && <CommunityCards cards={communityCards} />}
      <PotDisplay amount={pot} />

      {seats.map((seat) => {
        const p = players.find(pl => pl.seat_idx === seat.seat_idx);
        const isMe = mySeat === seat.seat_idx;
        const tag = seat.seat_idx === dealerIdx ? 'D'
          : seat.seat_idx === sbSeat ? 'SB'
          : seat.seat_idx === bbSeat ? 'BB'
          : undefined;
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
          <div key={seat.seat_idx}
               className={`seat-wrap seat-${slot}${seat.connected === false ? ' offline' : ''}`}>
            <PlayerSeat
              player={merged}
              isCurrent={currentPlayerIdx === seat.seat_idx}
              holeCards={isMe ? holeCards : undefined}
              avatarLabel={
                seat.is_human
                  ? (isMe ? '你' : seat.name.charAt(0))
                  : `L${seat.bot_level ?? 2}`
              }
              isMe={isMe}
              positionTag={tag}
              inHand={handLive}
              dealSeq={dealSeq}
            />
            {!seat.is_human && (
              <span className="bot-badge">
                L{seat.bot_level ?? 2}
                <button className="kick-btn" title="Remove bot"
                        onClick={() => onKickBot(seat.seat_idx)}>×</button>
              </span>
            )}
            {seat.is_owner && <span className="owner-crown">👑</span>}
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
