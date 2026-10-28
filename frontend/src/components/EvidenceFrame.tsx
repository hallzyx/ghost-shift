import { useState } from 'react';
import { ImageOff, Play } from 'lucide-react';
import type { Evidence } from '../api/types';
import { mediaUrl } from '../api/client';
import { formatMs } from '../lib/format';

const KIND_LABEL: Record<string, string> = {
  event: 'Evento',
  state: 'Estado',
  absence_probe: 'Comprobación de ausencia',
};

/** «place:B» → «Colocación»; deja intacto el texto ya legible. */
function humanDetail(d: string | null): string | null {
  if (!d) return null;
  const m = /^(place|remove|present|absent)(?::\w+)?$/i.exec(d.trim());
  if (!m) return d;
  return ({ place: 'Colocación', remove: 'Retirada', present: 'Presente', absent: 'No visible' } as Record<string, string>)[m[1]!.toLowerCase()] ?? d;
}

export function EvidenceFrame({ ev, objLabel, onSeek }: { ev: Evidence; objLabel: string; onSeek: (ms: number) => void }) {
  const [state, setState] = useState<'loading' | 'ok' | 'error'>(ev.frame_url ? 'loading' : 'error');
  return (
    <button
      type="button"
      className="evidence"
      onClick={() => onSeek(ev.t_ms)}
      aria-label={`Ver en el video en ${formatMs(ev.t_ms)}: ${objLabel}. ${humanDetail(ev.detail) ?? ''}`}
    >
      <span className="evidence__img">
        {state === 'loading' && <span className="skeleton" aria-hidden />}
        {ev.frame_url && state !== 'error' && (
          <img
            src={mediaUrl(ev.frame_url)}
            alt=""
            loading="lazy"
            onLoad={() => setState('ok')}
            onError={() => setState('error')}
            style={{ opacity: state === 'ok' ? 1 : 0 }}
          />
        )}
        {state === 'error' && (
          <span className="evidence__missing">
            <ImageOff size={20} aria-hidden />
            Sin fotograma
          </span>
        )}
        <span className="evidence__time mono">
          <Play size={11} aria-hidden fill="currentColor" /> {formatMs(ev.t_ms)}
        </span>
      </span>
      <span className="evidence__meta">
        <strong>{objLabel}</strong>
        <span className="muted">{humanDetail(ev.detail) || KIND_LABEL[ev.kind] || ev.kind}</span>
      </span>
    </button>
  );
}
