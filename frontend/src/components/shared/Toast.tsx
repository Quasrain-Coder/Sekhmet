import { useEffect } from 'react';

export interface ToastItem {
  id: number;
  kind: 'error' | 'info';
  text: string;
}

interface Props {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}

export default function Toast({ items, onDismiss }: Props) {
  return (
    <div className="toast-stack">
      {items.map(t => (
        <ToastCard key={t.id} item={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(item.id), 3500);
    return () => clearTimeout(t);
  }, [item.id, onDismiss]);
  return (
    <div className={`toast toast-${item.kind}`} onClick={() => onDismiss(item.id)}>
      {item.text}
    </div>
  );
}
