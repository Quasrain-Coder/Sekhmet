import { useEffect, useRef, type CSSProperties } from 'react';
import CardView from './CardView';

interface Props {
  cards: string[];
}

export default function CommunityCards({ cards }: Props) {
  // Cards that just appeared (index >= previous count) get a flip-in
  // animation; older cards stay static.  Slots are keyed by content so a
  // slot that changes from empty to a real card remounts and animates,
  // while a board reset (new hand) renders plain backs with no animation.
  const prevCount = useRef(0);
  useEffect(() => { prevCount.current = cards.length; }, [cards.length]);
  const display = [...cards];
  while (display.length < 5) display.push('');

  return (
    <div className="community-cards">
      {display.map((c, i) => (
        <span key={`${i}-${c}`}
              className={c !== '' && i >= prevCount.current ? 'dealt' : undefined}
              style={{ '--deal-delay': `${i * 120}ms` } as CSSProperties}>
          <CardView card={c || undefined} />
        </span>
      ))}
    </div>
  );
}
