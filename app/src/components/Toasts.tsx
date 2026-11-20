import { useT } from "../lib/i18n";
import { Icon } from "./Icons";

export type ToastKind = "info" | "ok" | "error";

export type ToastItem = {
  id: number;
  message: string;
  kind: ToastKind;
};

export function Toasts({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  const t = useT();
  if (items.length === 0) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast ${item.kind}`}>
          <span className="toast-icon">
            <Icon
              name={item.kind === "error" ? "alert" : item.kind === "ok" ? "check" : "info"}
              size={16}
            />
          </span>
          <span>{item.message}</span>
          <button onClick={() => onDismiss(item.id)} aria-label={t("Dispensar aviso")}>
            <Icon name="x" size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
