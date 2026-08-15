import { render, act } from '@testing-library/react';
import ActionBar from '../components/table/ActionBar';

const baseProps = {
  currentBet: 10,
  myStack: 200,
  myCurrentBet: 0,
  bigBlind: 10,
  onAction: vi.fn(),
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test('counts down from 30s while it is my turn', () => {
  const { container } = render(<ActionBar {...baseProps} isMyTurn />);
  expect(container.querySelector('.action-timer')!.textContent).toContain('30s');
  act(() => { vi.advanceTimersByTime(5_000); });
  expect(container.querySelector('.action-timer')!.textContent).toContain('25s');
});

test('warns during the final 10 seconds', () => {
  const { container } = render(<ActionBar {...baseProps} isMyTurn />);
  act(() => { vi.advanceTimersByTime(21_000); });
  const timer = container.querySelector('.action-timer')!;
  expect(timer.textContent).toContain('9s');
  expect(timer.className).toContain('warn');
});

test('turn end stops the countdown; a new turn restarts at 30s', () => {
  const { container, rerender } = render(<ActionBar {...baseProps} isMyTurn />);
  act(() => { vi.advanceTimersByTime(10_000); });
  rerender(<ActionBar {...baseProps} isMyTurn={false} />);
  expect(container.textContent).toContain('Waiting for others');
  rerender(<ActionBar {...baseProps} isMyTurn />);
  expect(container.querySelector('.action-timer')!.textContent).toContain('30s');
});

test('turnEpoch bump (server re-armed after reclaim) restarts the clock', () => {
  const { container, rerender } = render(<ActionBar {...baseProps} isMyTurn turnEpoch={0} />);
  act(() => { vi.advanceTimersByTime(18_000); });
  expect(container.querySelector('.action-timer')!.textContent).toContain('12s');
  rerender(<ActionBar {...baseProps} isMyTurn turnEpoch={1} />);
  expect(container.querySelector('.action-timer')!.textContent).toContain('30s');
});
