import { useEffect, useRef, useState } from 'react';
import { Link, Outlet, useNavigate } from 'react-router-dom';
import {
  Check,
  CheckCircle2,
  AlertCircle,
  Info,
  LayoutList,
  Lock,
  Menu as MenuIcon,
  Monitor,
  Moon,
  ScrollText,
  Sun,
  Trash2,
  X,
} from 'lucide-react';
import { useApp, type FlowStep } from '../context/AppContext';
import { Logo } from './brand';
import { Button, Callout, Modal } from './ui';
import { ConsentModal, PrivacyModal } from './Consent';
import { IS_MOCK } from '../lib/env';

export const STEPS = ['Enseñar', 'Revisar reglas', 'Verificar', 'Resultado'] as const;

export function Stepper({ step }: { step: FlowStep }) {
  if (!step) return null;
  return (
    <nav className="stepper" aria-label="Progreso del procedimiento">
      <ol>
        {STEPS.map((label, i) => {
          const n = i + 1;
          const state = n < step ? 'done' : n === step ? 'current' : 'todo';
          return (
            <li key={label} className={`stepper__item is-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="stepper__dot" aria-hidden>
                {state === 'done' ? <Check size={14} strokeWidth={3} /> : n}
              </span>
              <span className="stepper__label">
                <span className="sr-only">Paso {n} de 4{state === 'done' ? ' (completado)' : ''}: </span>
                {label}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="stepper__compact" aria-hidden>
        Paso {step} de 4 · <strong>{STEPS[step - 1]}</strong>
      </p>
    </nav>
  );
}

function AppMenu({ onDelete }: { onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  const { theme, setTheme, setPrivacyOpen } = useApp();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const close = () => setOpen(false);
  return (
    <div className="menu" ref={ref}>
      <button
        type="button"
        className="icon-btn icon-btn--filled"
        aria-label="Menú y ajustes"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <X size={20} /> : <MenuIcon size={20} />}
      </button>
      {open && (
        <div className="menu__panel" role="menu">
          <Link role="menuitem" className="menu__item" to="/" onClick={close}>
            <LayoutList size={18} aria-hidden /> Mis procedimientos
          </Link>
          <Link role="menuitem" className="menu__item" to="/auditoria" onClick={close}>
            <ScrollText size={18} aria-hidden /> Registro de llamadas a modelos
          </Link>
          <button
            role="menuitem"
            type="button"
            className="menu__item"
            onClick={() => {
              close();
              setPrivacyOpen(true);
            }}
          >
            <Lock size={18} aria-hidden /> Privacidad y datos
          </button>
          <div className="menu__sep" />
          <div className="menu__group" role="group" aria-label="Tema">
            <span className="menu__group-label">Tema</span>
            <div className="seg">
              {(
                [
                  ['system', 'Sistema', Monitor],
                  ['light', 'Claro', Sun],
                  ['dark', 'Oscuro', Moon],
                ] as const
              ).map(([val, label, Ic]) => (
                <button
                  key={val}
                  type="button"
                  className={`seg__btn${theme === val ? ' is-on' : ''}`}
                  aria-pressed={theme === val}
                  onClick={() => setTheme(val)}
                >
                  <Ic size={15} aria-hidden /> {label}
                </button>
              ))}
            </div>
          </div>
          <div className="menu__sep" />
          <button
            role="menuitem"
            type="button"
            className="menu__item menu__item--danger"
            onClick={() => {
              close();
              onDelete();
            }}
          >
            <Trash2 size={18} aria-hidden /> Borrar mi sesión y datos
          </button>
        </div>
      )}
    </div>
  );
}

export function DeleteSessionDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { deleteSession, sessionId, toast } = useApp();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    if (open) setErr(null);
  }, [open]);
  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      await deleteSession();
      onClose();
      navigate('/');
      toast('Se borraron tu sesión, tus videos y tus procedimientos.');
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'No se pudo borrar la sesión.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title="¿Borrar tu sesión y datos?"
      icon={<Trash2 size={22} />}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button variant="danger" busy={busy} onClick={run} disabled={!sessionId}>
            Borrar todo
          </Button>
        </>
      }
    >
      {sessionId ? (
        <p>
          Se eliminarán del servidor de GhostShift tus videos, procedimientos, resultados y el registro de llamadas. Esta acción no se
          puede deshacer.
        </p>
      ) : (
        <p>No tienes una sesión activa: no hay datos tuyos guardados en el servidor.</p>
      )}
      {err && (
        <div className="mt-3">
          <Callout tone="error" title="No se pudo borrar">
            {err}
          </Callout>
        </div>
      )}
    </Modal>
  );
}

function Toasts() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="toasts" aria-live="polite" aria-atomic="false">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.tone}`} role={t.tone === 'error' ? 'alert' : 'status'}>
          {t.tone === 'success' ? <CheckCircle2 size={18} aria-hidden /> : t.tone === 'error' ? <AlertCircle size={18} aria-hidden /> : <Info size={18} aria-hidden />}
          <span>{t.text}</span>
          <button type="button" className="icon-btn icon-btn--sm" aria-label="Cerrar aviso" onClick={() => dismissToast(t.id)}>
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Layout() {
  const { step, setPrivacyOpen } = useApp();
  const [delOpen, setDelOpen] = useState(false);
  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Saltar al contenido
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Link to="/" className="topbar__brand" aria-label="GhostShift, ir a Mis procedimientos">
            <Logo />
          </Link>
          <div className="topbar__center">
            <Stepper step={step} />
          </div>
          <div className="topbar__actions">
            {IS_MOCK && (
              <span className="mock-pill" title="Respuestas simuladas en el navegador; no hay inferencia real.">
                Modo demo simulado
              </span>
            )}
            <AppMenu onDelete={() => setDelOpen(true)} />
          </div>
        </div>
      </header>
      <main id="main" className="main" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="footer">
        <div className="footer__inner">
          <p className="footer__warn">
            <AlertCircle size={16} aria-hidden /> Prototipo de investigación — no apto para controles críticos o de seguridad.
          </p>
          <p className="footer__meta">
            Con modelos Muse Spark y SAM 3.1 de la API de Meta ·{' '}
            <Link to="/auditoria">Registro de llamadas</Link> ·{' '}
            <button type="button" className="link-btn" onClick={() => setPrivacyOpen(true)}>
              Privacidad
            </button>{' '}
            ·{' '}
            <button type="button" className="link-btn" onClick={() => setDelOpen(true)}>
              Borrar mi sesión y datos
            </button>
          </p>
        </div>
      </footer>
      <Toasts />
      <ConsentModal />
      <PrivacyModal onDelete={() => setDelOpen(true)} />
      <DeleteSessionDialog open={delOpen} onClose={() => setDelOpen(false)} />
    </div>
  );
}
