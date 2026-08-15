import { render, fireEvent } from '@testing-library/react';
import ActionBar from '../components/table/ActionBar';

// Facing a 30 bet having put in 10: toCall=20, minRaiseTo=50, maxRaise=510.
const baseProps = {
  isMyTurn: true,
  currentBet: 30,
  myStack: 500,
  myCurrentBet: 10,
  bigBlind: 10,
  minRaise: 50,
  pot: 100,
  onAction: vi.fn(),
};

// ---------------------------------------------------------------------------
// Pot-fraction presets
// ---------------------------------------------------------------------------

describe('pot-fraction presets', () => {
  test('1/2 pot raises to call + half of the pot after the call', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    fireEvent.click(container.querySelector('.raise-presets .btn:nth-child(2)')!);
    // 20 + (100 + 20) / 2 = 80
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 80');
    expect((container.querySelector('.raise-input') as HTMLInputElement).value).toBe('80');
  });

  test('full pot raises to call + pot after the call', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    fireEvent.click(container.querySelector('.raise-presets .btn:nth-child(4)')!);
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 140');
  });

  test('unopened betting sizes against the pot directly', () => {
    const { container } = render(
      <ActionBar {...baseProps} currentBet={0} myCurrentBet={0} />,
    );
    fireEvent.click(container.querySelector('.raise-presets .btn:nth-child(2)')!);
    // 0 + 100 / 2 = 50
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Bet 50');
  });

  test('presets clamp up to the legal minimum raise-to', () => {
    // tiny pot: 1/3 pot would undercut the min raise-to of 50
    const { container } = render(
      <ActionBar {...baseProps} pot={6} currentBet={0} myCurrentBet={0} />,
    );
    fireEvent.click(container.querySelector('.raise-presets .btn:nth-child(1)')!);
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Bet 50');
  });

  test('presets clamp down to an all-in when the pot is huge', () => {
    const { container } = render(<ActionBar {...baseProps} pot={2000} />);
    fireEvent.click(container.querySelector('.raise-presets .btn:nth-child(4)')!);
    // 20 + (2000 + 20) = 2040 → capped at stack + current bet = 510
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 510');
  });

  test('presets disabled when the raise does not reopen (short all-in)', () => {
    const { container } = render(
      <ActionBar {...baseProps} minRaise={80} myStack={30} myCurrentBet={10} />,
    );
    // maxRaise = 40 < minRaiseTo = 110
    expect((container.querySelector('.btn.raise') as HTMLButtonElement).disabled).toBe(true);
    expect((container.querySelector('.raise-presets .btn') as HTMLButtonElement).disabled).toBe(true);
    expect((container.querySelector('.raise-input') as HTMLInputElement).disabled).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Direct raise input
// ---------------------------------------------------------------------------

describe('direct raise input', () => {
  test('typing a value commits it on blur', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    const input = container.querySelector('.raise-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '150' } });
    fireEvent.blur(input);
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 150');
    expect((container.querySelector('.raise-slider') as HTMLInputElement).value).toBe('150');
  });

  test('an un-blurred draft still applies on raise click', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    const input = container.querySelector('.raise-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '200' } });
    fireEvent.click(container.querySelector('.btn.raise')!);
    expect(baseProps.onAction).toHaveBeenCalledWith('RAISE', 200);
  });

  test('out-of-range input clamps to the legal bounds', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    const input = container.querySelector('.raise-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '99999' } });
    fireEvent.blur(input);
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 510');
  });

  test('garbage input reverts to the committed value', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    const input = container.querySelector('.raise-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 50');
  });

  test('slider and input stay in sync', () => {
    const { container } = render(<ActionBar {...baseProps} />);
    const slider = container.querySelector('.raise-slider') as HTMLInputElement;
    fireEvent.change(slider, { target: { value: '120' } });
    expect((container.querySelector('.raise-input') as HTMLInputElement).value).toBe('120');
  });

  test('a new turn resets the draft to the street minimum', () => {
    const { container, rerender } = render(<ActionBar {...baseProps} />);
    const input = container.querySelector('.raise-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '200' } });
    fireEvent.blur(input);
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 200');

    rerender(<ActionBar {...baseProps} isMyTurn={false} />);
    rerender(<ActionBar {...baseProps} isMyTurn minRaise={90} />);
    // minRaise is already a raise-TO value → minRaiseTo = 90; the draft
    // resets to it instead of keeping the stale 200
    expect(container.querySelector('.btn.raise')!.textContent).toBe('Raise to 90');
  });
});
