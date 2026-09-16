import { useEffect, useRef, useState, type ReactNode } from "react";

type Props = {
  title: string;
  body: ReactNode;
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  className?: string;
  ariaLabel?: string;
  children: ReactNode;
};

/** A button that asks for confirmation in a native <dialog> before running a destructive action. */
export default function ConfirmButton({ title, body, confirmLabel = "Delete", onConfirm, className, ariaLabel, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!open && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [open]);

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <>
      <button type="button" className={className} aria-label={ariaLabel}
              onClick={(e) => { e.stopPropagation(); setOpen(true); }}>
        {children}
      </button>
      <dialog ref={ref} className="dialog" onClose={() => setOpen(false)} onClick={(e) => e.stopPropagation()}
              aria-labelledby="confirm-title">
        {open && (
          <form method="dialog" onSubmit={(e) => { e.preventDefault(); confirm(); }}>
            <h3 id="confirm-title">{title}</h3>
            <div className="dialog-body">{body}</div>
            <div className="dialog-actions">
              <button type="button" className="btn ghost sm" onClick={() => setOpen(false)} autoFocus>Cancel</button>
              <button type="submit" className="btn sm danger-solid" disabled={busy} data-testid="confirm-delete">
                {busy ? "Deleting…" : confirmLabel}
              </button>
            </div>
          </form>
        )}
      </dialog>
    </>
  );
}
