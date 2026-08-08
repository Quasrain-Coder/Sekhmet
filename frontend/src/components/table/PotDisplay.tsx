interface Props {
  amount: number;
}

export default function PotDisplay({ amount }: Props) {
  return (
    <div className="pot-display">
      <span className="pot-amount">◈ POT {amount}</span>
    </div>
  );
}
