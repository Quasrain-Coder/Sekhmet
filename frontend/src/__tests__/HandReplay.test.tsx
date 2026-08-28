import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import HandReplay, { type ReplayData } from '../pages/HandReplay';

const PLAYERS = [
  { seat_idx: 0, name: 'Hero', is_human: true, stack: 195, current_bet: 5,
    is_active: true, is_all_in: false, hole_cards: ['A♠', 'K♠'] },
  { seat_idx: 1, name: 'Bot', is_human: false, stack: 190, current_bet: 10,
    is_active: true, is_all_in: false, hole_cards: ['10♥', '10♦'] },
];

const REPLAY: ReplayData = {
  id: 42, table_id: 'AB12CD', created_at: '2026-08-28T12:34:56',
  small_blind: 5, big_blind: 10,
  awards: [{ seat_idx: 1, amount: 60, hand: 'Three of a Kind' }],
  frames: [
    { phase: 'PREFLOP', board: [], pot: 15, to_act: 0,
      players: PLAYERS, last_action: null },
    { phase: 'PREFLOP', board: [], pot: 15, to_act: 1,
      players: PLAYERS.map(p => p.seat_idx === 0
        ? { ...p, stack: 165, current_bet: 30 } : p),
      last_action: { seat: 0, action: 'RAISE', amount: 30 } },
    { phase: 'FLOP', board: ['10♣', '7♠', '2♥'], pot: 60, to_act: 1,
      players: PLAYERS.map(p => ({ ...p, current_bet: 0 })),
      last_action: { seat: 1, action: 'CALL', amount: 0 } },
    { phase: 'SHOWDOWN', board: ['10♣', '7♠', '2♥', '4♦', '9♠'], pot: 60,
      to_act: null,
      players: PLAYERS.map(p => p.seat_idx === 0
        ? { ...p, current_bet: 0, is_active: false } : { ...p, current_bet: 0 }),
      last_action: { seat: 0, action: 'FOLD', amount: 0 } },
  ],
};

function stubFetch(data: ReplayData | null = REPLAY, ok = true) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok,
    json: async () => data,
  })));
}

const renderPage = () => render(
  <MemoryRouter initialEntries={['/history/42']}>
    <Routes><Route path="/history/:handId" element={<HandReplay />} /></Routes>
  </MemoryRouter>,
);

afterEach(() => vi.unstubAllGlobals());

test('renders frame 0: blinds posted, hole cards face-up, no board', async () => {
  stubFetch();
  const { container } = renderPage();
  await waitFor(() => expect(screen.getByText('发牌')).toBeInTheDocument());
  expect(screen.getByText('底池 15')).toBeInTheDocument();
  expect(container.querySelector('.phase-pill')).toHaveTextContent('翻前');
  // hole cards of both seats visible (4 small cards), no community cards
  expect(container.querySelectorAll('.replay-seat-cards .card')).toHaveLength(4);
  expect(container.querySelectorAll('.replay-community .card')).toHaveLength(0);
});

test('step forward/back through frames, ticker follows last action', async () => {
  stubFetch();
  const { container } = renderPage();
  await waitFor(() => screen.getByText('发牌'));
  fireEvent.click(screen.getByText('▶|'));
  expect(screen.getByText('Hero RAISE 30')).toBeInTheDocument();
  expect(screen.getByText('2/4')).toBeInTheDocument();
  fireEvent.click(screen.getByText('▶|'));
  expect(screen.getByText('Bot CALL')).toBeInTheDocument();
  expect(container.querySelector('.phase-pill')).toHaveTextContent('翻牌');
  fireEvent.click(screen.getByText('◀'));
  expect(screen.getByText('Hero RAISE 30')).toBeInTheDocument();
});

test('jump to final frame shows awards and dims the folded seat', async () => {
  stubFetch();
  const { container } = renderPage();
  await waitFor(() => screen.getByText('发牌'));
  fireEvent.click(screen.getByText('⏭'));
  expect(screen.getByText('4/4')).toBeInTheDocument();
  expect(screen.getByText(/Bot 赢得 60（Three of a Kind）/)).toBeInTheDocument();
  const seats = container.querySelectorAll('.replay-seat');
  expect(seats[0].className).toContain('folded');
  expect(seats[1].className).toContain('winner');
  // at final frame the play button becomes restart
  expect(screen.getByText('↺')).toBeInTheDocument();
});

test('slider scrubs to a frame', async () => {
  stubFetch();
  renderPage();
  await waitFor(() => screen.getByText('发牌'));
  fireEvent.change(document.querySelector('.replay-slider')!, { target: { value: '2' } });
  expect(screen.getByText('Bot CALL')).toBeInTheDocument();
});

test('shows a friendly message when the hand is missing', async () => {
  stubFetch(null, false);
  renderPage();
  await waitFor(() => expect(screen.getByText(/未找到这手牌/)).toBeInTheDocument());
});
