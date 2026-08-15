import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import GameTablePage from '../pages/GameTable';

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(_url: string) { MockWebSocket.instances.push(this); }
  send() {}
  close() {}
}

const CONFIG = { small_blind: 5, big_blind: 10, default_buyin: 200, max_seats: 4 };

const FLOP_DETAIL = {
  table_id: 'abc',
  phase: 'FLOP',
  max_seats: 4,
  config: CONFIG,
  community_cards: ['A♠', 'K♥', '7♦'],
  pot: 60,
  current_bet: 10,
  current_player_idx: 1,
  dealer_idx: 2,
  sb_seat: 0,
  bb_seat: 1,
  seats: [
    { seat_idx: 0, name: 'Alice', is_human: true, bot_level: null, stack: 180,
      hands: 0, wins: 0, net_chips: -20, connected: true, is_owner: true,
      current_bet: 0, is_active: true, is_all_in: false },
    { seat_idx: 1, name: 'Bot L2', is_human: false, bot_level: 2, stack: 170,
      hands: 0, wins: 0, net_chips: -30, connected: true, is_owner: false,
      current_bet: 10, is_active: true, is_all_in: false },
    { seat_idx: 2, name: 'Bob', is_human: true, bot_level: null, stack: 210,
      hands: 0, wins: 0, net_chips: 10, connected: true, is_owner: false,
      current_bet: 0, is_active: false, is_all_in: false },  // folded
  ],
};

function renderPage(detail: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => detail })));
  return render(
    <MemoryRouter initialEntries={['/game/abc']}>
      <Routes>
        <Route path="/game/:tableId" element={<GameTablePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  MockWebSocket.instances = [];
  (globalThis as any).WebSocket = MockWebSocket;
  localStorage.setItem('pokerName', 'Hero');
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as any).WebSocket;
  localStorage.clear();
});

test('join panel previews the live table: community cards, pot, backs, folds', async () => {
  renderPage(FLOP_DETAIL);
  await screen.findByRole('button', { name: 'Sit Down' });

  // the board in the middle
  const cards = document.querySelectorAll('.community-cards .card');
  expect(cards[0].getAttribute('title')).toBe('A♠');
  expect(cards[2].getAttribute('title')).toBe('7♦');
  // the pot
  expect(document.querySelector('.pot-amount')!.textContent).toContain('60');
  // active players hold card backs…
  expect(document.querySelectorAll('.hole-cards .hole-card').length).toBeGreaterThan(0);
  // …the folded player wears the Fold badge
  expect(document.querySelector('.folded-tag')!.textContent).toBe('Fold');
  // dealer / blind tags are visible
  expect(document.querySelector('.pos-tag.pos-d')!.textContent).toBe('D');
  expect(document.querySelector('.pos-tag.pos-sb')!.textContent).toBe('SB');
  expect(document.querySelector('.pos-tag.pos-bb')!.textContent).toBe('BB');
});

test('occupied seats are not pickable; free seats select on click', async () => {
  renderPage({
    ...FLOP_DETAIL,
    phase: 'WAITING',
    community_cards: [],
    pot: 0,
    current_player_idx: null,
    seats: FLOP_DETAIL.seats.slice(0, 2),  // seats 0,1 occupied → 2,3 free
  });
  await screen.findByRole('button', { name: 'Sit Down' });

  // first free seat (2) is preselected
  expect(document.querySelector('[data-seat="2"]')).toHaveClass('selected');

  // clicking an occupied bot seat is ignored
  fireEvent.click(document.querySelector('[data-seat="1"]')!);
  expect(document.querySelector('[data-seat="1"]')).not.toHaveClass('selected');
  expect(document.querySelector('[data-seat="2"]')).toHaveClass('selected');

  // clicking another free seat moves the selection
  fireEvent.click(document.querySelector('[data-seat="3"]')!);
  expect(document.querySelector('[data-seat="3"]')).toHaveClass('selected');
  expect(document.querySelector('[data-seat="2"]')).not.toHaveClass('selected');
});
