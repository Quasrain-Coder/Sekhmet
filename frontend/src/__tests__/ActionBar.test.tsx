import { render } from '@testing-library/react';
import ActionBar from '../components/table/ActionBar';

const baseProps = {
  isMyTurn: true,
  currentBet: 30,
  myStack: 500,
  myCurrentBet: 10,
  bigBlind: 10,
  minRaise: 50,
  onAction: vi.fn(),
};

test('slider floor follows the server min_raise (grows with last raise)', () => {
  // BB=10, someone raised to 30 → engine min_raise is 20 → legal raise-to is 50.
  // The blind-based approximation (30+10=40) would offer illegal sizes.
  const { container } = render(<ActionBar {...baseProps} minRaise={50} />);
  expect(container.querySelector('.raise-slider')!.getAttribute('min')).toBe('50');
  expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 50');
});

test('falls back to the blind approximation until the first broadcast arrives', () => {
  const { container } = render(<ActionBar {...baseProps} minRaise={0} />);
  expect(container.querySelector('.raise-slider')!.getAttribute('min')).toBe('40');
});

test('shows waiting UI when it is not my turn', () => {
  const { container } = render(<ActionBar {...baseProps} isMyTurn={false} />);
  expect(container.textContent).toContain('Waiting for others');
});
