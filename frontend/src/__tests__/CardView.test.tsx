import { render } from '@testing-library/react';
import CardView from '../components/table/CardView';

test('renders corner rank and suit', () => {
  const { container } = render(<CardView card="A♥" />);
  expect(container.querySelector('.corner')!.textContent).toBe('A♥');
  expect(container.querySelector('.pip')!.textContent).toBe('♥');
  expect(container.querySelector('.card')!.className).toContain('card-red');
});

test('black suit gets card-black, face-down gets card-back', () => {
  const { container } = render(<CardView card="K♠" />);
  expect(container.querySelector('.card')!.className).toContain('card-black');
  const back = render(<CardView />);
  expect(back.container.querySelector('.card-back')).toBeTruthy();
});

test('ten renders two-char rank', () => {
  const { container } = render(<CardView card="10♦" />);
  expect(container.querySelector('.corner')!.textContent).toBe('10♦');
});
