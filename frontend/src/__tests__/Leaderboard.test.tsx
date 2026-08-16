import { render, screen, fireEvent } from '@testing-library/react';
import Leaderboard from '../components/table/Leaderboard';

const seats = [
  { seat_idx: 0, name: 'Hero', is_human: true, bot_level: null, stack: 200, buyin: 185, hands: 2, wins: 1, net_chips: 15, connected: true, is_owner: true },
  { seat_idx: 1, name: 'Bot', is_human: false, bot_level: 3, stack: 200, buyin: 215, hands: 2, wins: 1, net_chips: -15, connected: true, is_owner: false },
];

test('collapsed by default, expands on click, sorted by net desc', () => {
  render(<Leaderboard seats={seats} />);
  expect(screen.queryByText('Hero')).toBeNull();
  fireEvent.click(screen.getByText(/Leaderboard/));
  const rows = screen.getAllByRole('row');
  expect(rows[1].textContent).toContain('Hero');   // +15 first
  expect(rows[2].textContent).toContain('Bot');    // -15 second
  expect(rows[2].textContent).toContain('L3');     // bot level badge
});
