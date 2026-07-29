import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { Spinner } from "./AsyncState";

export interface ModalSpec {
  tone?: "warning" | "danger";
  kicker?: string;
  title: string;
  body: string;
  details?: string[];
  confirmLabel?: string;
  confirmWord?: string; // require typing this word (e.g. FLATTEN)
  onConfirm?: () => void | Promise<void>;
}

/** Guarded confirmation modal for irreversible/money-touching actions (UIUX rules). */
export function ConfirmModal({ modal, onClose }: { modal: ModalSpec; onClose: () => void }) {
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const needsWord = Boolean(modal.confirmWord);
  const canConfirm = !needsWord || word === modal.confirmWord;

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const focusable = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
    focusable()[0]?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  const confirm = async () => {
    if (!canConfirm) return;
    setBusy(true);
    setError(null);
    try {
      await modal.onConfirm?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The requested action was not completed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className={`modal ${modal.tone ?? "warning"}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <button className="icon-button modal-close" aria-label="Close dialog" onClick={onClose}>
          <X size={17} />
        </button>
        <span className="modal-icon">
          <AlertTriangle size={22} />
        </span>
        <p className="kicker">{modal.kicker ?? "CONFIRM ACTION"}</p>
        <h1 id={titleId}>{modal.title}</h1>
        <p>{modal.body}</p>
        {modal.details && (
          <ul className="modal-details">
            {modal.details.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        )}
        {needsWord && (
          <label className="confirm-field">
            Type <strong>{modal.confirmWord}</strong> to confirm
            <input
              aria-label={`Type ${modal.confirmWord} to confirm`}
              value={word}
              onChange={(e) => setWord(e.target.value)}
              autoFocus
            />
          </label>
        )}
        {error && (
          <div className="inline-msg err" role="alert">
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className={`button ${modal.tone === "danger" ? "danger" : "primary"}`}
            disabled={!canConfirm || busy}
            onClick={() => void confirm()}
          >
            {busy ? <><Spinner /> Confirming…</> : (modal.confirmLabel ?? "Confirm")}
          </button>
        </div>
      </section>
    </div>
  );
}
