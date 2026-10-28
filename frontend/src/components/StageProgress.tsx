import { useEffect, useState, type ReactNode } from 'react';
import { Check, Circle, Loader2, RotateCcw, X } from 'lucide-react';
import type { JobError, Stage } from '../api/types';
import { Button, Callout } from './ui';
import { LogoMark } from './brand';
import { IS_MOCK } from '../lib/env';

/** Mensajes honestos por etapa (se muestran junto a la etiqueta del backend). */
const STAGE_HINT: Record<string, string> = {
  validate: 'Comprobando formato, duración y encuadre del video…',
  interpret: 'Muse Spark está interpretando el video: qué objetos hay y qué ocurre…',
  segment: 'SAM 3.1 está siguiendo cada objeto fotograma a fotograma…',
  propose: 'Contrastando ambos modelos y redactando reglas propuestas…',
  verify: 'El motor determinista está comprobando cada regla aprobada…',
};

const STAGE_FALLBACK_LABEL: Record<string, string> = {
  validate: 'Validar video',
  interpret: 'Interpretar con Muse Spark',
  segment: 'Seguir objetos con SAM 3.1',
  propose: 'Proponer reglas',
  verify: 'Comprobar reglas',
};

function useElapsed(active: boolean) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [active]);
  const s = Math.floor((now - start) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function StageProgress({
  title,
  subtitle,
  stages,
  running,
  error,
  onRetry,
  retrying,
  fallbackAction,
}: {
  title: string;
  subtitle?: ReactNode;
  stages: Stage[];
  running: boolean;
  error: JobError | null;
  onRetry?: () => void;
  retrying?: boolean;
  fallbackAction?: ReactNode;
}) {
  const elapsed = useElapsed(running);
  const current = stages.find((s) => s.state === 'running');
  const doneCount = stages.filter((s) => s.state === 'done').length;
  const pct = stages.length ? Math.round(((doneCount + (current ? 0.5 : 0)) / stages.length) * 100) : 0;
  const live = error
    ? `Error: ${error.message}`
    : current
      ? `${current.label || STAGE_FALLBACK_LABEL[current.id] || current.id}: en curso`
      : running
        ? 'Preparando…'
        : 'Completado';

  return (
    <div className="stages">
      <div className="stages__head">
        <span className={`ai-ring${running && !error ? ' is-active' : ''}${error ? ' is-error' : ''}`} aria-hidden>
          <span className="ai-ring__inner">
            <LogoMark size={30} />
          </span>
        </span>
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
      </div>

      <div className="progress" role="progressbar" aria-label="Progreso" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <span className={`progress__bar${running && !error ? ' is-live' : ''}${error ? ' is-error' : ''}`} style={{ width: `${Math.max(pct, 4)}%` }} />
      </div>

      <ol className="stages__list">
        {stages.map((s) => {
          const label = s.label || STAGE_FALLBACK_LABEL[s.id] || s.id;
          return (
            <li key={s.id} className={`stage is-${s.state}`}>
              <span className="stage__icon" aria-hidden>
                {s.state === 'done' ? (
                  <Check size={16} strokeWidth={3} />
                ) : s.state === 'running' ? (
                  <Loader2 size={18} className="spin" />
                ) : s.state === 'failed' ? (
                  <X size={16} strokeWidth={3} />
                ) : (
                  <Circle size={10} />
                )}
              </span>
              <div className="stage__text">
                <p className="stage__label">
                  {label}
                  <span className="sr-only">
                    {' '}
                    — {s.state === 'done' ? 'hecho' : s.state === 'running' ? 'en curso' : s.state === 'failed' ? 'falló' : 'pendiente'}
                  </span>
                </p>
                {(s.state === 'running' || s.detail) && (
                  <p className="stage__detail">{s.detail || (s.state === 'running' ? STAGE_HINT[s.id] : null)}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <p className="sr-only" aria-live="polite">
        {live}
      </p>

      {error ? (
        <Callout
          tone="error"
          title="No pudimos terminar"
          action={
            <div className="row gap-2 wrap">
              {error.retryable && onRetry && (
                <Button variant="primary" icon={<RotateCcw size={18} />} onClick={onRetry} busy={retrying}>
                  Reintentar
                </Button>
              )}
              {fallbackAction}
            </div>
          }
        >
          {error.message}
          {!error.retryable && ' Prueba con otro video que cumpla los requisitos.'}
        </Callout>
      ) : (
        running && (
          <p className="stages__foot muted small">
            Tiempo transcurrido {elapsed}.{' '}
            {IS_MOCK
              ? 'Modo demo simulado: estas etapas no llaman a ningún modelo.'
              : 'Puede tardar uno o dos minutos: los modelos se ejecutan de verdad, no hay resultados precalculados.'}
          </p>
        )
      )}
    </div>
  );
}
