interface CardViewProps {
  card?: string;   // e.g. "A♠", "10♥", "K♦", "7♣" — or empty for face-down
  small?: boolean;
  big?: boolean;
}

const RED_SUITS = ['♥', '♦'];

// ♠ 与 ♣ 同为黑色系，小尺寸下容易混淆——草花单独用绿色系渲染。
const suitClass = (suit: string) =>
  suit === '♣' ? 'suit-club' : RED_SUITS.includes(suit) ? 'card-red' : 'card-black';

export default function CardView({ card, small, big }: CardViewProps) {
  const size = big ? 'big' : small ? 'small' : '';
  if (!card) {
    return <span className={`card card-back ${size}`} />;
  }

  const suit = card.slice(-1);
  const rank = card.slice(0, -1);

  return (
    <span className={`card ${suitClass(suit)} ${size}`} title={card}>
      <span className="corner">{rank}<br />{suit}</span>
      <span className="pip">{suit}</span>
    </span>
  );
}
