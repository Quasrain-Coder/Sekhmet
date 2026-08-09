interface CardViewProps {
  card?: string;   // e.g. "A♠", "10♥", "K♦", "7♣" — or empty for face-down
  small?: boolean;
  big?: boolean;
}

const RED_SUITS = ['♥', '♦'];

export default function CardView({ card, small, big }: CardViewProps) {
  const size = big ? 'big' : small ? 'small' : '';
  if (!card) {
    return <span className={`card card-back ${size}`} />;
  }

  const suit = card.slice(-1);
  const rank = card.slice(0, -1);
  const isRed = RED_SUITS.includes(suit);

  return (
    <span className={`card ${isRed ? 'card-red' : 'card-black'} ${size}`} title={card}>
      <span className="corner">{rank}<br />{suit}</span>
      <span className="pip">{suit}</span>
    </span>
  );
}
