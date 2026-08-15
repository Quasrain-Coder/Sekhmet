import { render, screen } from '@testing-library/react';
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

const DETAIL = {
  table_id: 'abc',
  phase: 'WAITING',
  max_seats: 4,
  config: { small_blind: 5, big_blind: 10, default_buyin: 200, max_seats: 4 },
  seats: [],
};

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

test('reload with a reclaim token preselects the disconnected seat', async () => {
  localStorage.setItem('reclaimToken_abc', 'tok123');
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({
      ...DETAIL,
      seats: [{
        seat_idx: 2, name: 'Hero', is_human: true, bot_level: null, stack: 150,
        hands: 1, wins: 0, net_chips: -50, connected: false, is_owner: false,
      }],
    }),
  })));

  render(
    <MemoryRouter initialEntries={['/game/abc']}>
      <Routes>
        <Route path="/game/:tableId" element={<GameTablePage />} />
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByRole('button', { name: 'Sit Down' });
  // our old seat (2) is selected, not the first free seat (0)
  expect(document.querySelector('.picker-seat.seat-2')).toHaveClass('selected');
  expect(document.querySelector('.picker-seat.seat-0')).not.toHaveClass('selected');
});
