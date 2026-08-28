import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import History from '../pages/History';

const HAND = {
  id: 42,
  table_id: 'AB12CD',
  players: [
    { seat_idx: 0, name: 'QQ', is_human: true, stack_before: 1000, stack_after: 960 },
    { seat_idx: 3, name: 'Bot L3', is_human: false, stack_before: 500, stack_after: 560 },
  ],
  board: ['A♣', '6♣', '3♥', 'A♦', '9♣'],
  actions: [
    { seat: 0, action: 'CALL', amount: 10 },
    { seat: 3, action: 'BET', amount: 25 },
    { seat: 0, action: 'FOLD', amount: 0 },
  ],
  awards: [{ seat_idx: 3, amount: 60, hand: 'Two Pair, Aces and Nines' }],
  created_at: '2026-08-28T12:34:56.789012',
};

const PLAYERS = [
  { name: 'Bot L3', hands: 10, wins: 6, net_chips: 320, updated_at: '2026-08-28T12:40:00' },
  { name: 'QQ', hands: 10, wins: 4, net_chips: -120, updated_at: '2026-08-28T12:40:00' },
];

function stubFetch(hands: unknown[] = [HAND], players: unknown[] = PLAYERS) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    json: async () => url.includes('/players') ? { players } : { hands },
  })));
}

const renderPage = () => render(<MemoryRouter><History /></MemoryRouter>);

afterEach(() => vi.unstubAllGlobals());

test('renders ranked player stats with signed net chips', async () => {
  stubFetch();
  renderPage();
  await waitFor(() => expect(screen.getByText('Bot L3')).toBeInTheDocument());
  const rows = screen.getAllByRole('row');
  // header + 2 players; server orders by net_chips desc
  expect(rows).toHaveLength(3);
  expect(rows[1]).toHaveTextContent('Bot L3');
  expect(rows[1].querySelector('.net-pos')).toHaveTextContent('+320');
  expect(rows[2].querySelector('.net-neg')).toHaveTextContent('-120');
  expect(rows[1]).toHaveTextContent('60%'); // win rate 6/10
});

test('renders hand card: board cards, winner trophy, colored nets', async () => {
  stubFetch();
  const { container } = renderPage();
  await waitFor(() => expect(screen.getByText('#42')).toBeInTheDocument());
  expect(container.querySelectorAll('.hand-card-board .card')).toHaveLength(5);
  expect(screen.getByText(/AB12CD · 2026-08-28 12:34/)).toBeInTheDocument();
  const players = container.querySelectorAll('.hand-player');
  expect(players[0]).toHaveTextContent('QQ');
  expect(players[0].querySelector('.net-neg')).toHaveTextContent('-40');
  expect(players[1]).toHaveTextContent('🏆 Bot L3');
  expect(players[1].querySelector('.net-pos')).toHaveTextContent('+60');
});

test('click expands the action list with seat names', async () => {
  stubFetch();
  const { container } = renderPage();
  await waitFor(() => screen.getByText('#42'));
  expect(container.querySelector('.hand-actions')).toBeNull();
  fireEvent.click(screen.getByText('#42'));
  const items = container.querySelectorAll('.hand-actions li');
  expect(items).toHaveLength(3);
  expect(items[1]).toHaveTextContent('Bot L3 BET 25');
  fireEvent.click(screen.getByText('#42')); // collapse again
  expect(container.querySelector('.hand-actions')).toBeNull();
});

test('shows empty states when nothing is recorded', async () => {
  stubFetch([], []);
  const { container } = renderPage();
  await waitFor(() => expect(screen.getByText('暂无对局记录')).toBeInTheDocument());
  expect(screen.getByText(/暂无战绩/)).toBeInTheDocument();
  expect(container.querySelectorAll('.card')).toHaveLength(0);
});

test('preflop fold-out shows placeholder instead of cards', async () => {
  stubFetch([{ ...HAND, id: 7, board: [] }], []);
  renderPage();
  await waitFor(() => expect(screen.getByText('翻前结束')).toBeInTheDocument());
});
