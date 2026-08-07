import CardView from './CardView';

interface Props {
  cards: string[];
}

export default function CommunityCards({ cards }: Props) {
  const display = [...cards];
  while (display.length < 5) display.push('');

  return (
    <div className="community-cards">
      {display.map((c, i) => (
        <CardView key={i} card={c || undefined} />
      ))}
    </div>
  );
}
