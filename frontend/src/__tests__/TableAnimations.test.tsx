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
    rerender(
      <PlayerSeat player={player({ is_active: false })} isCurrent={false}
                  avatarLabel="L2" isMe={false} inHand={false} dealSeq={0} />,
    );
    expect(container.querySelector('.hole-cards')!.className).toContain('folding');
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
    const { container } = render(
      <PlayerSeat player={player({ is_active: false })} isCurrent={false}
                  avatarLabel="L2" isMe={false} inHand={false} dealSeq={0} />,
    );
    expect(container.querySelector('.hole-cards')).toBeNull();
    expect(container.querySelector('.folded-tag')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Deal trigger (OvalTable)
// ---------------------------------------------------------------------------

const seat = (idx: number, name: string, isHuman: boolean): SeatInfo => ({
  seat_idx: idx, name, is_human: isHuman, bot_level: isHuman ? null : 2,
  stack: 1000, hands: 0, wins: 0, net_chips: 0, connected: true, is_owner: false,
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
