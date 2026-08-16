import { shouldShowRebuy } from '../hooks/useGameState';

describe('shouldShowRebuy', () => {
  test('shows at showdown with a live zero stack', () => {
    expect(shouldShowRebuy('SHOWDOWN', 0, 0)).toBe(true);
  });

  test('shows at WAITING after reconnect when players is empty (seat fallback)', () => {
    expect(shouldShowRebuy('WAITING', undefined, 0)).toBe(true);
  });

  test('hides while the hand runs, even when busted', () => {
    expect(shouldShowRebuy('FLOP', 0, 0)).toBe(false);
    expect(shouldShowRebuy('PREFLOP', 0, undefined)).toBe(false);
  });

  test('hides when the hero still has chips', () => {
    expect(shouldShowRebuy('SHOWDOWN', 5, undefined)).toBe(false);
    expect(shouldShowRebuy('WAITING', 1, 0)).toBe(false);
  });

  test('hides with no stack info at all', () => {
    expect(shouldShowRebuy('WAITING', undefined, undefined)).toBe(false);
  });
});
