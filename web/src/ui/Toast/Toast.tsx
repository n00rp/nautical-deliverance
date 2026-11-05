import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import styles from "./Toast.module.css";

export type ToastTone = "info" | "ok" | "warn" | "crit";
type Item = { id: number; message: string; tone: ToastTone };
type Ctx = {
  items: Item[];
  push: (m: string, t?: ToastTone) => void;
  dismiss: (id: number) => void;
};

const ToastContext = createContext<Ctx | null>(null);
const LIFETIME_MS = 6000;
let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const dismiss = useCallback((id: number) => {
    setItems((all) => all.filter((i) => i.id !== id));
  }, []);
  const push = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = nextId++;
      setItems((all) => [...all, { id, message, tone }]);
      setTimeout(() => {
        dismiss(id);
      }, LIFETIME_MS);
    },
    [dismiss],
  );
  return <ToastContext value={{ items, push, dismiss }}>{children}</ToastContext>;
}

function useToastContext(): Ctx {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("Toast hooks need a <ToastProvider>");
  return ctx;
}

export function useToast(): (message: string, tone?: ToastTone) => void {
  return useToastContext().push;
}

export function ToastHost() {
  const { items, dismiss } = useToastContext();
  return (
    <div className={styles.host} role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`${styles.toast} ${styles[t.tone]}`}>
          <span>{t.message}</span>
          <button
            type="button"
            className={styles.close}
            aria-label="Dismiss"
            onClick={() => {
              dismiss(t.id);
            }}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
