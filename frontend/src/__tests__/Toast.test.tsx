import { render, screen, fireEvent, act } from '@testing-library/react';
import Toast from '../components/shared/Toast';

test('renders and dismisses on click', () => {
  const onDismiss = vi.fn();
  render(<Toast items={[{ id: 1, kind: 'error', text: 'boom' }]} onDismiss={onDismiss} />);
  fireEvent.click(screen.getByText('boom'));
  expect(onDismiss).toHaveBeenCalledWith(1);
});

test('auto-dismisses after 3.5s', () => {
  vi.useFakeTimers();
  const onDismiss = vi.fn();
  render(<Toast items={[{ id: 1, kind: 'info', text: 'hi' }]} onDismiss={onDismiss} />);
  act(() => { vi.advanceTimersByTime(3600); });
  expect(onDismiss).toHaveBeenCalledWith(1);
  vi.useRealTimers();
});
