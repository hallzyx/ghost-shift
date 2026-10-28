import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../api/client';

const SESSION_KEY = 'ghostshift.session_id';
const THEME_KEY = 'ghostshift.theme';

export type Theme = 'system' | 'light' | 'dark';
export type FlowStep = 0 | 1 | 2 | 3 | 4; // 0 = fuera del flujo

export interface Toast {
  id: number;
  tone: 'success' | 'error' | 'info';
  text: string;
}

interface AppState {
  sessionId: string | null;
  /** Devuelve la sesión; si no hay, pide consentimiento primero. Rechaza si el usuario cancela. */
  ensureSession: () => Promise<string>;
  /** Olvida una sesión que el servidor ya no reconoce. */
  forgetSession: () => void;
  deleteSession: () => Promise<void>;
  consentOpen: boolean;
  consentBusy: boolean;
  consentError: string | null;
  acceptConsent: () => Promise<void>;
  cancelConsent: () => void;
  privacyOpen: boolean;
  setPrivacyOpen: (v: boolean) => void;
  toasts: Toast[];
  toast: (text: string, tone?: Toast['tone']) => void;
  dismissToast: (id: number) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  step: FlowStep;
  setStep: (s: FlowStep) => void;
}

const Ctx = createContext<AppState | null>(null);

function readLS(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeLS(key: string, val: string | null) {
  try {
    if (val === null) localStorage.removeItem(key);
    else localStorage.setItem(key, val);
  } catch {
    /* almacenamiento no disponible */
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(() => readLS(SESSION_KEY));
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentBusy, setConsentBusy] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const pending = useRef<{ resolve: (s: string) => void; reject: (e: Error) => void } | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [theme, setThemeState] = useState<Theme>(() => (readLS(THEME_KEY) as Theme) || 'system');
  const [step, setStep] = useState<FlowStep>(0);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') delete root.dataset.theme;
    else root.dataset.theme = theme;
  }, [theme]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    writeLS(THEME_KEY, t === 'system' ? null : t);
  }, []);

  const dismissToast = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const toast = useCallback(
    (text: string, tone: Toast['tone'] = 'success') => {
      const id = Date.now() + Math.random();
      setToasts((ts) => [...ts.slice(-2), { id, tone, text }]);
      window.setTimeout(() => dismissToast(id), 4500);
    },
    [dismissToast],
  );

  const ensureSession = useCallback((): Promise<string> => {
    if (sessionId) return Promise.resolve(sessionId);
    return new Promise<string>((resolve, reject) => {
      pending.current = { resolve, reject };
      setConsentError(null);
      setConsentOpen(true);
    });
  }, [sessionId]);

  const acceptConsent = useCallback(async () => {
    setConsentBusy(true);
    setConsentError(null);
    try {
      const s = await api.createSession();
      writeLS(SESSION_KEY, s.session_id);
      setSessionId(s.session_id);
      setConsentOpen(false);
      pending.current?.resolve(s.session_id);
      pending.current = null;
    } catch (e) {
      setConsentError(e instanceof ApiError ? e.message : 'No se pudo crear la sesión.');
    } finally {
      setConsentBusy(false);
    }
  }, []);

  const cancelConsent = useCallback(() => {
    setConsentOpen(false);
    pending.current?.reject(new Error('consent-cancelled'));
    pending.current = null;
  }, []);

  const forgetSession = useCallback(() => {
    writeLS(SESSION_KEY, null);
    setSessionId(null);
  }, []);

  const deleteSession = useCallback(async () => {
    if (sessionId) {
      try {
        await api.deleteSession(sessionId);
      } catch (e) {
        // Si la sesión ya no existe en el servidor, igualmente la olvidamos.
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
    }
    forgetSession();
  }, [sessionId, forgetSession]);

  const value = useMemo<AppState>(
    () => ({
      sessionId,
      ensureSession,
      forgetSession,
      deleteSession,
      consentOpen,
      consentBusy,
      consentError,
      acceptConsent,
      cancelConsent,
      privacyOpen,
      setPrivacyOpen,
      toasts,
      toast,
      dismissToast,
      theme,
      setTheme,
      step,
      setStep,
    }),
    [
      sessionId,
      ensureSession,
      forgetSession,
      deleteSession,
      consentOpen,
      consentBusy,
      consentError,
      acceptConsent,
      cancelConsent,
      privacyOpen,
      toasts,
      toast,
      dismissToast,
      theme,
      setTheme,
      step,
    ],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp fuera de AppProvider');
  return v;
}

/** Marca el paso actual del stepper mientras la pantalla está montada. */
export function useFlowStep(step: FlowStep) {
  const { setStep } = useApp();
  useEffect(() => {
    setStep(step);
    return () => setStep(0);
  }, [step, setStep]);
}
