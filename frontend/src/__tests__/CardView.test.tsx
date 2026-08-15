import { render } from '@testing-library/react';
import CardView from '../components/table/CardView';

test('spades use the standard black-suit style', () => {
  const { container } = render(<CardView card="A♠" />);
  const el = container.querySelector('.card')!;
  expect(el.className).toContain('card-black');
  expect(el.className).not.toContain('suit-club');
  expect(el.getAttribute('title')).toBe('A♠');
});

test('clubs get the distinct green-suit style so ♠/♣ are not confused', () => {
  const { container } = render(<CardView card="K♣" />);
  const el = container.querySelector('.card')!;
  expect(el.className).toContain('suit-club');
  expect(el.className).not.toContain('card-black');
});

test('red suits stay red', () => {
  const { container } = render(<CardView card="Q♥" />);
  expect(container.querySelector('.card')!.className).toContain('card-red');
});

test('empty card renders a face-down back', () => {
  const { container } = render(<CardView card={undefined} />);
  expect(container.querySelector('.card')!.className).toContain('card-back');
});
