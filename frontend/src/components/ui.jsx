import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import Icon from './Icon';

export function Spinner({ label = 'Loading' }) {
  return <span className="spinner" role="status" aria-label={label} />;
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading-block">
      <Spinner label={label} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "We couldn't load this" }) {
  return (
    <div className="alert alert-error" role="alert">
      <Icon name="alert" />
      <div style={{ flex: 1 }}>
        <strong>{title}.</strong> {error?.message}
        {onRetry && (
          <div style={{ marginTop: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={onRetry}>
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function Empty({ title, children, icon = 'sparkle' }) {
  return (
    <div className="empty">
      <div className="feature-icon" style={{ margin: '0 auto 10px' }}>
        <Icon name={icon} />
      </div>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Alert({ kind = 'info', children, icon }) {
  const iconName = icon || { info: 'info', warn: 'alert', error: 'alert', success: 'check' }[kind];
  return (
    <div className={`alert alert-${kind}`} role={kind === 'error' ? 'alert' : undefined}>
      <Icon name={iconName} />
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

export function ProgressBar({ value, label }) {
  const pct = Math.max(0, Math.min(100, value || 0));
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Field({ id, label, hint, error, children }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error && (
        <span className="hint" id={`${id}-hint`}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field-error" id={`${id}-error`}>
          {error}
        </span>
      )}
    </div>
  );
}

export function Modal({ open, title, onClose, children, labelledBy = 'modal-title' }) {
  const ref = useRef(null);
  const lastFocus = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    lastFocus.current = document.activeElement;
    const node = ref.current;
    const focusables = () =>
      node.querySelectorAll('a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])');
    (focusables()[0] || node).focus();
    const onKey = (e) => {
      if (e.key === 'Escape') closeRef.current?.();
      if (e.key === 'Tab') {
        const items = Array.from(focusables());
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      lastFocus.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={labelledBy} ref={ref} tabIndex={-1}>
        <div className="modal-header">
          <h2 id={labelledBy}>{title}</h2>
          {onClose && (
            <button className="icon-btn" onClick={onClose} aria-label="Close">
              <Icon name="close" />
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message, kind = 'info') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-wrap" aria-live="polite" role="status">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind === 'error' ? 'error' : ''}`}>
            <Icon name={t.kind === 'error' ? 'alert' : 'check'} />
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

export function ConfirmButton({ children, confirmText = 'Are you sure?', onConfirm, className = 'btn btn-ghost btn-sm' }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!asking) {
    return (
      <button className={className} onClick={() => setAsking(true)}>
        {children}
      </button>
    );
  }
  return (
    <span className="row" style={{ gap: 6 }}>
      <span className="small muted">{confirmText}</span>
      <button
        className="btn btn-danger btn-sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onConfirm();
          } finally {
            setBusy(false);
            setAsking(false);
          }
        }}
      >
        Yes
      </button>
      <button className="btn btn-ghost btn-sm" onClick={() => setAsking(false)}>
        Cancel
      </button>
    </span>
  );
}
