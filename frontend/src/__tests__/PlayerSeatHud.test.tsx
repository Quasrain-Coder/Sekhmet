import { render, screen } from '@testing-library/react';
import PlayerSeat from '../components/table/PlayerSeat';
import type { PlayerInfo } from '../hooks/useGameState';

function mkPlayer(overrides: Partial<PlayerInfo> = {}): PlayerInfo {
  return {
    seat_idx: 1, name: 'Villain', stack: 1000, current_bet: 0,
    is_active: true, is_all_in: false, is_human: true,
    ...overrides,
  };
}

function renderSeat(player: PlayerInfo, isMe = false) {
  return render(
    <PlayerSeat player={player} isCurrent={false} avatarLabel="V"
                isMe={isMe} inHand dealSeq={0} />,
  );
}

test('renders HUD line when the seat has stats', () => {
  renderSeat(mkPlayer({ hud: { hands: 32, vpip_pct: 45, pfr_pct: 20, fold_to_bet_pct: 50 } }));
  const line = screen.getByText(/VPIP 45 · PFR 20/);
  expect(line).toHaveTextContent('32手');
  expect(line.className).not.toContain('hud-thin');   // enough sample
});

test('dims HUD line on a thin sample (<5 hands)', () => {
  renderSeat(mkPlayer({ hud: { hands: 2, vpip_pct: 60, pfr_pct: 40, fold_to_bet_pct: 50 } }));
  expect(screen.getByText(/VPIP 60/).className).toContain('hud-thin');
});

test('no HUD line without stats or on own seat', () => {
  const { container: c1 } = renderSeat(mkPlayer());
  expect(c1.querySelector('.hud-line')).toBeNull();

  const { container: c2 } = renderSeat(
    mkPlayer({ hud: { hands: 30, vpip_pct: 45, pfr_pct: 20, fold_to_bet_pct: 50 } }),
    true,  // isMe — own HUD is noise
  );
  expect(c2.querySelector('.hud-line')).toBeNull();
});
