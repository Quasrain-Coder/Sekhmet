interface CardViewProps {
  card?: string;   // e.g. "A♠", "10♥", "K♦", "7♣" — or empty for face-down
  small?: boolean;
}

const RED_SUITS = ['♥', '♦'];

export default function CardView({ card, small }: CardViewProps) {
  if (!card) {
    return <span className={`card card-back ${small ? 'small' : ''}`} />;
  }

  const suit = card.slice(-1);
  const rank = card.slice(0, -1);
  const isRed = RED_SUITS.includes(suit);

  return (
    <span className={`card ${isRed ? 'card-red' : 'card-black'} ${small ? 'small' : ''}`}
          title={card}>
      <span className="rank">{rank}</span>
      <span className="suit">{suit}</span>
    </span>
  );
}
