import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { statusMeta } from "./api";

export function StatusBadge({ status }) {
  const [label, tone] = statusMeta[status] || [status, "gray"];
  return (
    <span className={`badge ${tone}`}>
      <span className="dot" />
      {label}
    </span>
  );
}

export function Notice({ children, error = false }) {
  return children ? (
    <div
      className={`notice ${error ? "error" : ""}`}
      role={error ? "alert" : "status"}
    >
      {children}
    </div>
  ) : null;
}

export function Modal({ title, subtitle, onClose, children, busy = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    dialog.focus();
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = before;
      previous?.focus();
    };
  }, []);
  function keys(event) {
    if (event.key === "Escape" && !busy) onClose();
    if (event.key !== "Tab") return;
    const items = [
      ...ref.current.querySelectorAll(
        "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])",
      ),
    ];
    if (!items.length) {
      event.preventDefault();
      return;
    }
    const first = items[0],
      last = items[items.length - 1];
    if (
      event.shiftKey &&
      (document.activeElement === first ||
        document.activeElement === ref.current)
    ) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  return (
    <div
      className="overlay"
      onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}
    >
      <aside
        className="drawer"
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={keys}
      >
        <div className="drawer-head">
          <div>
            <span className="drawer-kicker">NOVA REVIEW</span>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button
            className="icon-btn close"
            aria-label="Close review"
            disabled={busy}
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}
