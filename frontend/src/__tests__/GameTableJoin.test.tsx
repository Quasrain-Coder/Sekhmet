import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import GameTablePage from '../pages/GameTable';

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = 0;
  url: string;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) { this.sent.push(data); }
  close() { this.readyState = 3; }

  // test helpers
  open() { this.readyState = 1; this.onopen?.(); }
  receive(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }); }
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
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({ ...DETAIL, seats: [] }),
  })));
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as any).WebSocket;
});

test('rival grabbing the seat first must not strand us in the table view', async () => {
  render(
    <MemoryRouter initialEntries={['/game/abc']}>
      <Routes>
        <Route path="/game/:tableId" element={<GameTablePage />} />
      </Routes>
    </MemoryRouter>,
  );

  // wait for the join panel (detail fetch resolves) and open the socket
  const sitButton = await screen.findByRole('button', { name: 'Sit Down' });
  act(() => { MockWebSocket.instances[0].open(); });
  fireEvent.click(sitButton);

  // our sit_down went out
  expect(JSON.parse(MockWebSocket.instances[0].sent[0]).type).toBe('sit_down');

  // the rival won the race: THEIR table_state broadcast arrives before our
  // rejection error — the old table_state handler cleared pendingSeat here
  // and the error below was swallowed, leaving mySeat optimistically set.
  act(() => {
    MockWebSocket.instances[0].receive({
      type: 'table_state',
      table_id: 'abc',
      phase: 'WAITING',
      max_seats: 4,
      config: DETAIL.config,
      seats: [{ seat_idx: 0, name: 'Rival', is_human: true, bot_level: null,
                stack: 200, hands: 0, wins: 0, net_chips: 0, connected: true,
                is_owner: true }],
    });
    MockWebSocket.instances[0].receive({ type: 'error', message: 'Seat 0 is already occupied' });
  });

  // back at the join panel, not stuck in the table view
  expect(await screen.findByRole('button', { name: 'Sit Down' })).toBeTruthy();
  expect(screen.getByText('Seat 0 is already occupied')).toBeTruthy();  // toast
});
