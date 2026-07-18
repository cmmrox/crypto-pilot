import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

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
  const needsWord = Boolean(modal.confirmWord);
  const canConfirm = !needsWord || word === modal.confirmWord;

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [onClose]);

  const confirm = async () => {
    if (!canConfirm) return;
    setBusy(true);
    try {
      await modal.onConfirm?.();
      onClose();
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
      <section className={`modal ${modal.tone ?? "warning"}`} role="dialog" aria-modal="true">
        <button className="icon-button modal-close" aria-label="Close dialog" onClick={onClose}>
          <X size={17} />
        </button>
        <span className="modal-icon">
          <AlertTriangle size={22} />
        </span>
        <p className="kicker">{modal.kicker ?? "CONFIRM ACTION"}</p>
        <h1>{modal.title}</h1>
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
            <input aria-label={`Type ${modal.confirmWord} to confirm`} value={word} onChange={(e) => setWord(e.target.value)} autoFocus />
          </label>
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
            {busy ? "Working…" : (modal.confirmLabel ?? "Confirm")}
          </button>
        </div>
      </section>
    </div>
  );
}
