import { render, act } from '@testing-library/react';
import PlayerSeat from '../components/table/PlayerSeat';
import OvalTable from '../components/table/OvalTable';
import CommunityCards from '../components/table/CommunityCards';
import type { PlayerInfo, SeatInfo } from '../hooks/useGameState';

const player = (over: Partial<PlayerInfo> = {}): PlayerInfo => ({
  seat_idx: 1,
  name: 'Bot L2',
  stack: 1000,
  current_bet: 0,
  is_active: true,
  is_all_in: false,
  is_human: false,
  ...over,
});

// ---------------------------------------------------------------------------
// In-hand card backs
// ---------------------------------------------------------------------------

describe('in-hand card backs', () => {
  test('active opponent shows two face-down cards during a hand', () => {
    const { container } = render(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand dealSeq={0} />,
    );
    expect(container.querySelectorAll('.hole-cards .hole-card')).toHaveLength(2);
  });

  test('no backs between hands', () => {
    const { container } = render(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand={false} dealSeq={0} />,
    );
    expect(container.querySelector('.hole-cards')).toBeNull();
  });

  test('hero never gets backs — their real cards render instead', () => {
    const { container } = render(
      <PlayerSeat player={player({ seat_idx: 0, is_human: true })}
                  holeCards={['A♠', 'K♥']} isCurrent={false} avatarLabel="你"
                  isMe inHand dealSeq={0} />,
    );
    expect(container.querySelector('.hole-cards')).toBeNull();
    expect(container.querySelectorAll('.cards .card')).toHaveLength(2);
  });

  test('reclaim mid-hand renders static backs without the deal animation', () => {
    const { container } = render(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand dealSeq={0} />,
    );
    expect(container.querySelector('.hole-cards')!.className).not.toContain('dealing');
  });
});

// ---------------------------------------------------------------------------
// Fold animation
// ---------------------------------------------------------------------------

describe('fold animation', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test('folding plays the fly-out, then only the Fold badge remains', () => {
    const { container, rerender } = render(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand dealSeq={0} />,
    );
    // inHand stays true for the whole hand in the real app (OvalTable
    // passes a phase-based flag) — a folded player must lose the backs
    // anyway, and they must NOT remount with the deal fly-in.
    rerender(
      <PlayerSeat player={player({ is_active: false })} isCurrent={false}
                  avatarLabel="L2" isMe={false} inHand dealSeq={1} />,
    );
    expect(container.querySelector('.hole-cards')!.className).toContain('folding');
    expect(container.querySelector('.hole-cards')!.className).not.toContain('dealing');
    expect(container.querySelector('.folded-tag')!.textContent).toBe('Fold');

    act(() => { vi.advanceTimersByTime(900); });
    expect(container.querySelector('.hole-cards')).toBeNull();
    expect(container.querySelector('.folded-tag')).not.toBeNull();
  });

  test('a new hand cancels a leftover fold animation', () => {
    const { container, rerender } = render(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand dealSeq={0} />,
    );
    rerender(
      <PlayerSeat player={player({ is_active: false })} isCurrent={false}
                  avatarLabel="L2" isMe={false} inHand={false} dealSeq={0} />,
    );
    expect(container.querySelector('.hole-cards')!.className).toContain('folding');

    // next hand deals the player back in before the animation finished
    rerender(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand dealSeq={1} />,
    );
    expect(container.querySelector('.hole-cards')!.className).toContain('dealing');
    expect(container.querySelector('.folded-tag')).toBeNull();
  });

  test('mounting with an already-folded player skips the animation', () => {
    // inHand is true mid-hand even for a folded seat (phase-based flag)
    const { container } = render(
      <PlayerSeat player={player({ is_active: false })} isCurrent={false}
                  avatarLabel="L2" isMe={false} inHand dealSeq={1} />,
    );
    expect(container.querySelector('.hole-cards')).toBeNull();
    expect(container.querySelector('.folded-tag')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Showdown reveal
// ---------------------------------------------------------------------------

describe('showdown reveal', () => {
  test('revealedCards render face-up cards instead of backs', () => {
    const { container } = render(
      <PlayerSeat player={player()} isCurrent={false} avatarLabel="L2"
                  isMe={false} inHand dealSeq={1}
                  revealedCards={['A♠', 'K♥']} />,
    );
    expect(container.querySelector('.hole-cards')).toBeNull();
    const faces = container.querySelectorAll('.revealed-cards .card');
    expect(faces).toHaveLength(2);
    expect(faces[0].getAttribute('title')).toBe('A♠');
    expect(faces[1].getAttribute('title')).toBe('K♥');
  });

  test('hero never gets the reveal row — their own cards are already face-up', () => {
    const { container } = render(
      <PlayerSeat player={player({ seat_idx: 0, is_human: true })}
                  holeCards={['A♠', 'K♥']} isCurrent={false} avatarLabel="你"
                  isMe inHand dealSeq={1} revealedCards={['A♠', 'K♥']} />,
    );
    expect(container.querySelector('.revealed-cards')).toBeNull();
    expect(container.querySelectorAll('.cards .card')).toHaveLength(2);
  });

  test('a folded player never gets revealed cards', () => {
    const { container } = render(
      <PlayerSeat player={player({ is_active: false })} isCurrent={false}
                  avatarLabel="L2" isMe={false} inHand dealSeq={1}
                  revealedCards={['A♠', 'K♥']} />,
    );
    // the fold badge stays; the seat shows no cards (reveal or backs)
    expect(container.querySelector('.folded-tag')).not.toBeNull();
    expect(container.querySelectorAll('.revealed-cards .card, .hole-cards .hole-card')).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Deal trigger (OvalTable)
// ---------------------------------------------------------------------------

const seat = (idx: number, name: string, isHuman: boolean): SeatInfo => ({
  seat_idx: idx, name, is_human: isHuman, bot_level: isHuman ? null : 2,
  stack: 1000, buyin: 1000, buyin_count: 1, hands: 0, wins: 0, net_chips: 0, connected: true, is_owner: false,
});

describe('deal trigger', () => {
  test('WAITING → PREFLOP starts the deal animation for in-hand players', () => {
    const props = {
      seats: [seat(0, '你', true), seat(1, 'Bot L2', false)],
      players: [player({ seat_idx: 0, is_human: true }), player()],
      maxSeats: 2, communityCards: [], pot: 0,
      currentPlayerIdx: null, dealerIdx: null, sbSeat: null, bbSeat: null,
      mySeat: 0, holeCards: [], onAddBot: vi.fn(), onKickBot: vi.fn(),
    };
    const { container, rerender } = render(<OvalTable {...props} phase="WAITING" />);
    expect(container.querySelector('.hole-cards')).toBeNull();

    rerender(<OvalTable {...props} phase="PREFLOP" />);
    const row = container.querySelector('.hole-cards')!;
    expect(row).not.toBeNull();
    expect(row.className).toContain('dealing');
  });

  test('backs persist through showdown and clear in WAITING', () => {
    const props = {
      seats: [seat(0, '你', true), seat(1, 'Bot L2', false)],
      players: [player({ seat_idx: 0, is_human: true }), player()],
      maxSeats: 2, communityCards: [], pot: 0,
      currentPlayerIdx: null, dealerIdx: null, sbSeat: null, bbSeat: null,
      mySeat: 0, holeCards: [], onAddBot: vi.fn(), onKickBot: vi.fn(),
    };
    const { container, rerender } = render(<OvalTable {...props} phase="SHOWDOWN" />);
    // players still hold their cards at showdown
    expect(container.querySelector('.hole-cards')).not.toBeNull();
    rerender(<OvalTable {...props} phase="WAITING" />);
    expect(container.querySelector('.hole-cards')).toBeNull();
  });

  test('a seat parked outside the running hand holds no cards', () => {
    const props = {
      seats: [seat(0, '你', true), seat(1, 'Bot L2', false), seat(2, 'Late', true)],
      // seat 2 sat mid-hand — no player record in the running hand
      players: [player({ seat_idx: 0, is_human: true }), player()],
      maxSeats: 3, communityCards: ['A♠'], pot: 0,
      currentPlayerIdx: null, dealerIdx: null, sbSeat: null, bbSeat: null,
      mySeat: 0, holeCards: [], onAddBot: vi.fn(), onKickBot: vi.fn(),
    };
    const { container } = render(<OvalTable {...props} phase="FLOP" />);
    expect(container.querySelector('[data-seat="2"] .hole-cards')).toBeNull();
    expect(container.querySelector('[data-seat="1"] .hole-cards')).not.toBeNull();
  });

  test('reclaim mid-hand (mount in FLOP) does not fire the deal animation', () => {
    const props = {
      seats: [seat(0, '你', true), seat(1, 'Bot L2', false)],
      players: [player({ seat_idx: 0, is_human: true }), player()],
      maxSeats: 2, communityCards: ['A♠'], pot: 0,
      currentPlayerIdx: null, dealerIdx: null, sbSeat: null, bbSeat: null,
      mySeat: 0, holeCards: [], onAddBot: vi.fn(), onKickBot: vi.fn(),
    };
    const { container } = render(<OvalTable {...props} phase="FLOP" />);
    expect(container.querySelector('.hole-cards')!.className).not.toContain('dealing');
  });
});

// ---------------------------------------------------------------------------
// Community card flip-in
// ---------------------------------------------------------------------------

describe('community card flip-in', () => {
  test('newly dealt cards animate; old cards and empty slots stay static', () => {
    const { container, rerender } = render(<CommunityCards cards={[]} />);
    rerender(<CommunityCards cards={['A♠', 'K♥', '7♦']} />);
    const flopSlots = container.querySelectorAll('.community-cards > span');
    expect(flopSlots).toHaveLength(5);
    expect(flopSlots[0].className).toContain('dealt');
    expect(flopSlots[1].className).toContain('dealt');
    expect(flopSlots[2].className).toContain('dealt');
    // still-empty slots render plain backs, no animation
    expect(flopSlots[3].className).not.toContain('dealt');

    rerender(<CommunityCards cards={['A♠', 'K♥', '7♦', '2♣']} />);
    const turnSlots = container.querySelectorAll('.community-cards > span');
    // only the turn card animates — the flop stays static
    expect(turnSlots[0].className).not.toContain('dealt');
    expect(turnSlots[3].className).toContain('dealt');
  });

  test('a board reset renders plain backs with no animation', () => {
    const { container, rerender } = render(<CommunityCards cards={['A♠', 'K♥', '7♦']} />);
    rerender(<CommunityCards cards={[]} />);
    const slots = container.querySelectorAll('.community-cards > span');
    slots.forEach(s => expect(s.className).not.toContain('dealt'));
  });
});

// ---------------------------------------------------------------------------
// Seat spreading — occupied seats spread evenly around the oval
// ---------------------------------------------------------------------------

describe('seat spreading', () => {
  const base = {
    players: [] as PlayerInfo[],
    maxSeats: 9, communityCards: [], pot: 0,
    currentPlayerIdx: null, dealerIdx: null, sbSeat: null, bbSeat: null,
    mySeat: 0, holeCards: [], onAddBot: vi.fn(), onKickBot: vi.fn(),
  };

  test('HU on a 9-max table puts the opponent at the top (seat-4)', () => {
    const { container } = render(
      <OvalTable {...base} phase="WAITING"
                 seats={[seat(0, '你', true), seat(1, 'Bot L2', false)]} />,
    );
    const me = container.querySelector('[data-seat="0"]')!;
    const opp = container.querySelector('[data-seat="1"]')!;
    expect(me.className).toContain('seat-0');
    expect(opp.className).toContain('seat-4');  // 正对面，不再挤在右侧
  });

  test('3 players spread out: hero bottom, next ccw top-right, next top-left', () => {
    const { container } = render(
      <OvalTable {...base} phase="WAITING"
                 seats={[seat(0, '你', true), seat(1, 'B1', false), seat(2, 'B2', false)]} />,
    );
    const s0 = container.querySelector('[data-seat="0"]')!.className;
    const s1 = container.querySelector('[data-seat="1"]')!.className;
    const s2 = container.querySelector('[data-seat="2"]')!.className;
    expect(s0).toContain('seat-0');
    expect(s1).toContain('seat-3');  // top-right (counterclockwise)
    expect(s2).toContain('seat-5');  // top-left
  });

  test('action order stays counterclockwise around the oval', () => {
    // 6 players: hero bottom → slot1 → slot2 → slot3 → slot4 → slot5…
    const seats = [0, 1, 2, 3, 4, 5].map(i =>
      seat(i, i === 0 ? '你' : `B${i}`, i === 0));
    const { container } = render(
      <OvalTable {...base} phase="WAITING" seats={seats} maxSeats={6} />,
    );
    const slots = [0, 1, 2, 3, 4, 5].map(i =>
      Number(container.querySelector(`[data-seat="${i}"]`)!.className
        .match(/seat-(\d)/)![1]));
    // In action order the slot numbers must keep increasing (the oval
    // is numbered counterclockwise) — no reversal.
    for (let i = 1; i < slots.length; i++) {
      expect(slots[i]).toBeGreaterThan(slots[i - 1]);
    }
  });
});

describe('seat spreading rotation', () => {
  const base = {
    players: [] as PlayerInfo[],
    maxSeats: 6, communityCards: [], pot: 0,
    currentPlayerIdx: null, dealerIdx: null, sbSeat: null, bbSeat: null,
    holeCards: [], onAddBot: vi.fn(), onKickBot: vi.fn(),
  };

  test('hero at a non-zero seat: own seat at bottom, order still ccw', () => {
    const seats = [0, 1, 2, 3, 4, 5].map(i =>
      seat(i, i === 3 ? '你' : `B${i}`, i === 3));
    const { container } = render(
      <OvalTable {...base} seats={seats} mySeat={3} phase="WAITING" />,
    );
    const hero = container.querySelector('[data-seat="3"]')!.className;
    expect(hero).toContain('seat-0');  // rotated to bottom

    // Action order from the hero: 4,5,0,1,2 — slots must strictly
    // increase (counterclockwise) and wrap without reversal.
    const slots = [3, 4, 5, 0, 1, 2].map(i =>
      Number(container.querySelector(`[data-seat="${i}"]`)!.className
        .match(/seat-(\d)/)![1]));
    for (let i = 1; i < slots.length; i++) {
      expect(slots[i]).toBeGreaterThan(slots[i - 1]);
    }
  });

  test('viewer mode (join panel) spreads occupied seats evenly', () => {
    const { container } = render(
      <OvalTable {...base} seats={[seat(2, 'A', true), seat(5, 'B', true)]}
                 mySeat={null} onSeatSelect={vi.fn()} phase="WAITING" />,
    );
    expect(container.querySelector('[data-seat="2"]')!.className).toContain('seat-0');
    expect(container.querySelector('[data-seat="5"]')!.className).toContain('seat-4');
  });
});
