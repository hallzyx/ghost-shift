import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, CheckCircle2, Info, Loader2, TriangleAlert, X } from 'lucide-react';

/* ---------- Button ---------- */

type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'tint';
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant;
  size?: 'sm' | 'md' | 'lg';
  icon?: ReactNode;
  iconRight?: ReactNode;
  busy?: boolean;
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = 'secondary', size = 'md', icon, iconRight, busy, block, className = '', children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className={`btn btn--${variant} btn--${size}${block ? ' btn--block' : ''} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <Loader2 className="spin" size={18} aria-hidden /> : icon}
      {children && <span>{children}</span>}
      {iconRight}
    </button>
  );
});

/* ---------- Badge ---------- */

export type Tone = 'neutral' | 'blue' | 'violet' | 'amber' | 'green' | 'red';
export function Badge({ tone = 'neutral', icon, children, title }: { tone?: Tone; icon?: ReactNode; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge--${tone}`} title={title}>
      {icon}
      {children}
    </span>
  );
}

/* ---------- Card ---------- */

export function Card({ children, className = '', ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <section className={`card ${className}`} {...rest}>
      {children}
    </section>
  );
}

/* ---------- Callout ---------- */

export function Callout({
  tone = 'info',
  title,
  children,
  action,
  icon,
}: {
  tone?: 'info' | 'warning' | 'error' | 'success' | 'ai';
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  const ic =
    icon ??
    (tone === 'error' ? (
      <AlertCircle size={20} />
    ) : tone === 'warning' ? (
      <TriangleAlert size={20} />
    ) : tone === 'success' ? (
      <CheckCircle2 size={20} />
    ) : (
      <Info size={20} />
    ));
  return (
    <div className={`callout callout--${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      <span className="callout__icon" aria-hidden>
        {ic}
      </span>
      <div className="callout__body">
        {title && <p className="callout__title">{title}</p>}
        {children && <div className="callout__text">{children}</div>}
        {action && <div className="callout__action">{action}</div>}
      </div>
    </div>
  );
}

/* ---------- Skeleton ---------- */

export function Skeleton({ h = 16, w = '100%', r = 8, className = '' }: { h?: number | string; w?: number | string; r?: number; className?: string }) {
  return <span className={`skeleton ${className}`} style={{ height: h, width: w, borderRadius: r }} aria-hidden />;
}

/* ---------- Toggle ---------- */

export function Toggle({
  checked,
  onChange,
  label,
  describedBy,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  describedBy?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      className={`toggle${checked ? ' is-on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span className="toggle__knob" />
    </button>
  );
}

/* ---------- InfoTip (tooltip accesible) ---------- */

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="infotip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className="infotip__btn"
        aria-label={`¿Qué es ${label}?`}
        aria-describedby={id}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
      >
        <Info size={14} aria-hidden />
      </button>
      <span role="tooltip" id={id} className={`infotip__bubble${open ? ' is-open' : ''}`}>
        {children}
      </span>
    </span>
  );
}

/* ---------- EmptyState ---------- */

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <div className="empty__icon" aria-hidden>{icon}</div>}
      <h3>{title}</h3>
      {children && <p className="empty__text">{children}</p>}
      {action && <div className="empty__action">{action}</div>}
    </div>
  );
}

/* ---------- Modal ---------- */

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  icon,
  size = 'md',
  dismissable = true,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  icon?: ReactNode;
  size?: 'sm' | 'md';
  dismissable?: boolean;
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const prevFocus = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    prevFocus.current = document.activeElement;
    const el = panel.current;
    const focusables = () =>
      Array.from(
        el?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? [],
      );
    window.setTimeout(() => {
      const f = focusables();
      (f.find((x) => x.dataset.autofocus !== undefined) ?? f[0] ?? el)?.focus();
    }, 20);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && dismissable) onClose();
      if (e.key === 'Tab') {
        const f = focusables();
        if (!f.length) return;
        const first = f[0]!;
        const last = f[f.length - 1]!;
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
      if (prevFocus.current instanceof HTMLElement) prevFocus.current.focus();
    };
  }, [open, onClose, dismissable]);

  if (!open) return null;
  return createPortal(
    <div className="modal" onMouseDown={(e) => e.target === e.currentTarget && dismissable && onClose()}>
      <div ref={panel} className={`modal__panel modal__panel--${size}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <header className="modal__head">
          {icon && <span className="modal__icon" aria-hidden>{icon}</span>}
          <h2 id={titleId}>{title}</h2>
          {dismissable && (
            <button type="button" className="icon-btn modal__close" aria-label="Cerrar" onClick={onClose}>
              <X size={20} />
            </button>
          )}
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__foot">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

/* ---------- Field ---------- */

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: ReactNode; error?: string | null; children: ReactNode; htmlFor: string }) {
  return (
    <div className={`field${error ? ' has-error' : ''}`}>
      <label className="field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {error ? (
        <p className="field__error" id={`${htmlFor}-err`}>
          <AlertCircle size={14} aria-hidden /> {error}
        </p>
      ) : hint ? (
        <p className="field__hint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/* ---------- Page header ---------- */

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="page-head__text">
        {eyebrow && <div className="page-head__eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="page-head__sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-head__actions">{actions}</div>}
    </header>
  );
}
