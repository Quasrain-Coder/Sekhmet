interface CardViewProps {
  card?: string;   // e.g. "A♠", "10♥", "K♦", "7♣" — or empty for face-down
  small?: boolean;
  big?: boolean;
}

// 四花色四种颜色，小尺寸下一眼区分：
// ♠ 蓝 · ♥ 红 · ♦ 金 · ♣ 绿
const SUIT_CLASS: Record<string, string> = {
  '♠': 'card-suit spades',
  '♥': 'card-suit hearts',
  '♦': 'card-suit diamonds',
  '♣': 'card-suit clubs',
};

const suitClass = (suit: string) => SUIT_CLASS[suit] ?? 'card-suit spades';

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
