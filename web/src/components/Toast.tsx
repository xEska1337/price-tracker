import { useEffect, useState } from 'react';

export type ToastKind = 'info' | 'error' | 'success';

interface ToastItem {
  id: number;
  text: string;
  kind: ToastKind;
}

let nextId = 1;
let items: ToastItem[] = [];
const listeners = new Set<(items: ToastItem[]) => void>();

function emit(): void {
  for (const listener of listeners) listener(items);
}

export function dismissToast(id: number): void {
  const next = items.filter((item) => item.id !== id);
  if (next.length !== items.length) {
    items = next;
    emit();
  }
}

export function toast(text: string, kind: ToastKind = 'info'): void {
  const item: ToastItem = { id: nextId++, text, kind };
  items = [...items, item].slice(-4);
  emit();
  window.setTimeout(() => dismissToast(item.id), 4000);
}

const KIND_LABEL: Record<ToastKind, string> = {
  info: 'Info',
  error: 'Error',
  success: 'OK',
};

export function ToastHost() {
  const [list, setList] = useState<ToastItem[]>(items);

  useEffect(() => {
    listeners.add(setList);
    setList(items);
    return () => {
      listeners.delete(setList);
    };
  }, []);

  if (list.length === 0) return null;

  return (
    <div className="toast-host" role="status" aria-live="polite">
      {list.map((item) => (
        <div key={item.id} className={`toast toast-${item.kind}`}>
          <span className="toast-text">{item.text}</span>
          <button
            type="button"
            className="toast-close"
            aria-label={KIND_LABEL[item.kind]}
            onClick={() => dismissToast(item.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
