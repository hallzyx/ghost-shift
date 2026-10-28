import { CircleCheck, CircleHelp, CircleMinus, CircleX, Loader2, PenLine, Sparkles, FlaskConical, ShieldCheck, AlertCircle, FileCheck2 } from 'lucide-react';
import type { ProcedureStatus, RuleOrigin, RuleVerdict } from '../api/types';
import { Badge, type Tone } from './ui';

const GHOST = 'M8 26V13.5a8 8 0 0 1 16 0V26l-2.67-2-2.66 2L16 24l-2.67 2-2.66-2Z';

/** Isotipo propio: un fantasma con su «doble» desplazado (la referencia y la ejecución). */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false" className="logo-mark">
      <defs>
        <linearGradient id="gs-shift" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8B3DFF" />
          <stop offset="1" stopColor="#00C2E0" />
        </linearGradient>
      </defs>
      <path d={GHOST} transform="translate(4.5 -2.5)" fill="none" stroke="url(#gs-shift)" strokeWidth="1.8" strokeLinejoin="round" />
      <path d={GHOST} transform="translate(-1.5 2)" fill="var(--c-primary)" />
      <circle cx="12.6" cy="15" r="1.7" fill="#fff" />
      <circle cx="17.6" cy="15" r="1.7" fill="#fff" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <LogoMark />
      <span className="logo__word">GhostShift</span>
    </span>
  );
}

/* ---------- Veredictos: siempre icono + texto ---------- */

export const VERDICT_META: Record<RuleVerdict, { label: string; long: string; tone: Tone; Icon: typeof CircleCheck }> = {
  PASS: { label: 'PASS', long: 'Cumple', tone: 'green', Icon: CircleCheck },
  FAIL: { label: 'FAIL', long: 'No cumple', tone: 'red', Icon: CircleX },
  REVIEW: { label: 'REVIEW', long: 'Revisar', tone: 'amber', Icon: CircleHelp },
  SKIPPED: { label: 'OMITIDA', long: 'No evaluada', tone: 'neutral', Icon: CircleMinus },
};

export function VerdictBadge({ verdict, withLong = true }: { verdict: RuleVerdict; withLong?: boolean }) {
  const m = VERDICT_META[verdict];
  return (
    <Badge tone={m.tone} icon={<m.Icon size={14} aria-hidden />}>
      <strong>{m.label}</strong>
      {withLong && <span className="badge__long"> · {m.long}</span>}
    </Badge>
  );
}

export const STATUS_META: Record<ProcedureStatus, { label: string; tone: Tone; Icon: typeof CircleCheck }> = {
  analyzing: { label: 'Analizando', tone: 'blue', Icon: Loader2 },
  ready: { label: 'Listo para revisar', tone: 'violet', Icon: FileCheck2 },
  approved: { label: 'Aprobado', tone: 'green', Icon: ShieldCheck },
  failed: { label: 'Análisis fallido', tone: 'red', Icon: AlertCircle },
};

export function StatusBadge({ status }: { status: ProcedureStatus }) {
  const m = STATUS_META[status] ?? STATUS_META.ready;
  return (
    <Badge tone={m.tone} icon={<m.Icon size={14} className={status === 'analyzing' ? 'spin' : undefined} aria-hidden />}>
      {m.label}
    </Badge>
  );
}

export const ORIGIN_META: Record<RuleOrigin, { label: string; tone: Tone; Icon: typeof CircleCheck; help: string }> = {
  proposed: {
    label: 'Propuesta',
    tone: 'blue',
    Icon: Sparkles,
    help: 'La IA la propuso y SAM 3.1 la respaldó observando el video. Tú decides si forma parte de la norma.',
  },
  hypothesis: {
    label: 'Hipótesis',
    tone: 'amber',
    Icon: FlaskConical,
    help: 'Muse Spark la sugiere, pero SAM 3.1 no la pudo respaldar en el video. Viene desactivada: actívala solo si sabes que es correcta.',
  },
  user: {
    label: 'Tuya',
    tone: 'violet',
    Icon: PenLine,
    help: 'La creaste o la modificaste tú.',
  },
};

export function OriginBadge({ origin }: { origin: RuleOrigin }) {
  const m = ORIGIN_META[origin] ?? ORIGIN_META.proposed;
  return (
    <Badge tone={m.tone} icon={<m.Icon size={13} aria-hidden />} title={m.help}>
      {m.label}
      {origin === 'hypothesis' && <span className="badge__long"> (no respaldada por SAM)</span>}
    </Badge>
  );
}
