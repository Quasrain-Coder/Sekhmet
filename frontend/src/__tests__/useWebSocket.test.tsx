import { act, renderHook } from '@testing-library/react';
import { useWebSocket } from '../hooks/useWebSocket';

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = 0; // CONNECTING
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
  close() {
    this.readyState = 3; // CLOSED
    this.onclose?.();
  }

  // test helpers
  open() { this.readyState = 1; this.onopen?.(); }
  drop() { this.readyState = 3; this.onclose?.(); }
  receive(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }); }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.useFakeTimers();
  (globalThis as any).WebSocket = MockWebSocket;
});

afterEach(() => {
  vi.useRealTimers();
  delete (globalThis as any).WebSocket;
});

test('connects, sends only when open, and delivers messages to the handler', () => {
  const handler = vi.fn();
  const { result } = renderHook(() => useWebSocket('abc'));
  const { onMessage, send } = result.current;
  act(() => { onMessage(handler); });

  expect(MockWebSocket.instances).toHaveLength(1);
  expect(result.current.connected).toBe(false);

  // send before open is a no-op
  send({ type: 'player_action', action: 'FOLD' });
  expect(MockWebSocket.instances[0].sent).toHaveLength(0);

  act(() => { MockWebSocket.instances[0].open(); });
  expect(result.current.connected).toBe(true);

  send({ type: 'player_action', action: 'FOLD' });
  expect(MockWebSocket.instances[0].sent).toEqual(
    [JSON.stringify({ type: 'player_action', action: 'FOLD' })]);

  act(() => { MockWebSocket.instances[0].receive({ type: 'hand_start' }); });
  expect(handler).toHaveBeenCalledWith({ type: 'hand_start' });
});

test('reconnects with exponential backoff after a drop, and stops on unmount', () => {
  const { result, unmount } = renderHook(() => useWebSocket('abc'));
  act(() => { MockWebSocket.instances[0].open(); });
  expect(result.current.connected).toBe(true);

  // drop the connection — a retry is scheduled at 1s
  act(() => { MockWebSocket.instances[0].drop(); });
  expect(result.current.connected).toBe(false);
  expect(result.current.reconnectIn).toBe(1000);

  act(() => { vi.advanceTimersByTime(1000); });
  expect(MockWebSocket.instances).toHaveLength(2);
  expect(result.current.reconnectIn).toBe(0); // attempt in flight

  // that attempt also fails — the next retry waits 2s (backoff doubled)
  act(() => { MockWebSocket.instances[1].drop(); });
  expect(result.current.reconnectIn).toBe(2000);

  act(() => { vi.advanceTimersByTime(2000); });
  expect(MockWebSocket.instances).toHaveLength(3);

  // a successful reconnect resets the backoff
  act(() => { MockWebSocket.instances[2].open(); });
  expect(result.current.connected).toBe(true);
  expect(result.current.reconnectIn).toBe(0);
  act(() => { MockWebSocket.instances[2].drop(); });
  expect(result.current.reconnectIn).toBe(1000);

  unmount();
  const countAfterUnmount = MockWebSocket.instances.length;
  act(() => { vi.advanceTimersByTime(60_000); });
  expect(MockWebSocket.instances).toHaveLength(countAfterUnmount); // no retries after unmount
});

test('backoff caps at 10s', () => {
  const { result } = renderHook(() => useWebSocket('abc'));
  const waits = [1000, 2000, 4000, 8000, 10_000, 10_000];
  for (let i = 0; i < waits.length; i++) {
    act(() => { MockWebSocket.instances[i].drop(); });
    act(() => { vi.advanceTimersByTime(waits[i]); });
    expect(MockWebSocket.instances).toHaveLength(i + 2);
    // the two final waits are the 10s cap, not 16s/32s
    expect(result.current.reconnectIn).toBeLessThanOrEqual(10_000);
  }
  const last = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  expect(last.url).toContain('/ws/abc');
});
