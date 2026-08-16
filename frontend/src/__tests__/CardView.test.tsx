import { render } from '@testing-library/react';
import CardView from '../components/table/CardView';

test('each suit gets its own distinct color class', () => {
  const cases: [string, string][] = [
    ['A♠', 'spades'],
    ['K♥', 'hearts'],
    ['Q♦', 'diamonds'],
    ['J♣', 'clubs'],
  ];
  for (const [card, cls] of cases) {
    const { container, unmount } = render(<CardView card={card} />);
    const el = container.querySelector('.card')!;
    expect(el.className).toContain(`card-suit ${cls}`);
    expect(el.getAttribute('title')).toBe(card);
    unmount();
  }
});

test('all four suit classes are mutually distinct', () => {
  const { container } = render(
    <>
      <CardView card="A♠" />
      <CardView card="K♥" />
      <CardView card="Q♦" />
      <CardView card="J♣" />
    </>,
  );
  const cards = [...container.querySelectorAll('.card')];
  const classes = cards.map(c => c.className);
  expect(new Set(classes).size).toBe(4);
});

test('empty card renders a face-down back', () => {
  const { container } = render(<CardView card={undefined} />);
  expect(container.querySelector('.card')!.className).toContain('card-back');
});
