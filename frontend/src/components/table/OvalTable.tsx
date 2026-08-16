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
  // Seat → revealed hole cards, populated by hand_result at showdown.
  showdownHoleCards?: Record<number, string[]>;
  // Seats that won (part of) the pot at showdown — highlighted.
  winnerSeats?: number[];
  onAddBot: (seatIdx: number, level: number) => void;
  onKickBot: (seatIdx: number) => void;
  // Viewer mode (join panel): seats become clickable and empty seats render
  // as selectable markers instead of "+ Bot" buttons.  The caller decides
  // which seats are actually selectable (occupied seats are ignored).
  onSeatSelect?: (seatIdx: number) => void;
  selectedSeat?: number | null;
  // In-game: clicking an occupied seat opens its profile.
  onSeatClick?: (seatIdx: number) => void;
}

/** Map a seat index to an on-screen slot.
 *
 * Occupied seats spread evenly around the oval in action order
 * (counterclockwise, hero at the bottom) — sparse tables no longer
 * bunch players on one side, so the action order always traces the
 * same visual direction.  Empty seats keep the natural maxSeats-based
 * slot so the +Bot markers stay put.
 */
function displaySlot(
  seatIdx: number,
  occupied: number[],
  maxSeats: number,
  mySeat: number | null,
): number {
  const total = Math.min(Math.max(maxSeats, 2), 9);
  const idx = occupied.indexOf(seatIdx);
  if (idx === -1) {
    // Empty seat: natural slot by raw position.
    if (mySeat === null) return seatIdx % total;
    const rel = (seatIdx - mySeat + total) % total;
    if (total <= 2) return [0, 4][rel % 2];
    if (total === 9) return [0, 2, 3, 4, 8, 5, 6, 7, 1][rel];
    return [0, 2, 3, 4, 5, 6, 7, 1][rel % 8];
  }
  const n = occupied.length;
  const start = mySeat !== null ? occupied.indexOf(mySeat) : 0;
  const order = [...occupied.slice(start), ...occupied.slice(0, start)];
  const k = order.indexOf(seatIdx);
  if (n === 2) return [0, 4][k];
  if (n === 9) return [0, 2, 3, 4, 8, 5, 6, 7, 1][k];
  return [0, 1, 2, 3, 4, 5, 6, 7][Math.round((k * 8) / n) % 8];
}

export default function OvalTable({
  seats, players, maxSeats, communityCards, pot, currentPlayerIdx,
  dealerIdx, sbSeat, bbSeat,
  mySeat, holeCards, phase, showdownHoleCards, onAddBot, onKickBot,
  onSeatSelect, selectedSeat,
  onSeatClick, winnerSeats,
}: Props) {
  const showCommunity = phase !== 'WAITING' && phase !== 'PREFLOP' && phase !== 'DEALING';
  // Mid-hand seating changes corrupt the engine — only offer bot seats
  // between hands (the server enforces this too; this is the UI half).
  const canAddBot = phase === 'WAITING' || phase === 'SHOWDOWN';
  // Join-panel preview: seats are selectable, bot management is hidden.
  const viewer = !!onSeatSelect;
  const [pendingSeat, setPendingSeat] = useState<number | null>(null);
  // Close a stale level picker when a hand starts — it must not
  // resurrect on its own when bot seats unlock again at SHOWDOWN.
  useEffect(() => {
    if (!canAddBot) setPendingSeat(null);
  }, [canAddBot]);
  const occupied = new Map(seats.map(s => [s.seat_idx, s]));
  // Sorted occupied seats — displaySlot spreads them evenly around the
  // oval in action order.
  const occupiedList = [...occupied.keys()].sort((a, b) => a - b);
  // Card backs persist from the deal through showdown (players are still
  // holding their cards); they clear once the table returns to WAITING.
  const handLive = phase !== 'WAITING';
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
        const slot = displaySlot(seat.seat_idx, occupiedList, maxSeats, mySeat);
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
        // A seat without a player record (joined mid-hand, parked until the
        // next deal) holds no cards — gate the backs per seat.
        const seatInHand = handLive && p !== undefined;
        return (
          <div key={seat.seat_idx} data-seat={seat.seat_idx}
               className={`seat-wrap seat-${slot}${seat.connected === false ? ' offline' : ''}${winnerSeats?.includes(seat.seat_idx) ? ' winner' : ''}${viewer ? ' selectable' : ''}${viewer && selectedSeat === seat.seat_idx ? ' selected' : ''}${!viewer && onSeatClick ? ' clickable' : ''}`}
               onClick={viewer ? () => onSeatSelect!(seat.seat_idx)
                        : onSeatClick ? () => onSeatClick(seat.seat_idx) : undefined}>
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
              inHand={seatInHand}
              dealSeq={dealSeq}
              revealedCards={showdownHoleCards?.[seat.seat_idx]}
            />
            {!seat.is_human && (
              <span className="bot-badge">
                L{seat.bot_level ?? 2}
                {!viewer && (
                  <button className="kick-btn" title="Remove bot"
                          onClick={() => onKickBot(seat.seat_idx)}>×</button>
                )}
              </span>
            )}
            {seat.is_owner && <span className="owner-crown">👑</span>}
            {winnerSeats?.includes(seat.seat_idx) && (
              <span className="winner-badge">WIN</span>
            )}
          </div>
        );
      })}

      {viewer
        ? Array.from({ length: maxSeats }, (_, i) => i)
          .filter(i => !occupied.has(i))
          .map(i => (
            <button key={`empty-${i}`} data-seat={i}
                    className={`empty-seat-btn seat-${displaySlot(i, occupiedList, maxSeats, mySeat)}${selectedSeat === i ? ' selected' : ''}`}
                    onClick={() => onSeatSelect!(i)}>
              {i}
            </button>
          ))
        : canAddBot && Array.from({ length: maxSeats }, (_, i) => i)
          .filter(i => !occupied.has(i))
          .map(i => (
            <div key={`empty-${i}`} className={`empty-seat seat-${displaySlot(i, occupiedList, maxSeats, mySeat)}`}>
              {pendingSeat === i ? (
                <span className="bot-level-picker">
                  {[1, 2, 3, 4].map(lv => (
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
