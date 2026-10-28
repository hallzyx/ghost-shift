import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Pause, Play, RotateCcw, VideoOff } from 'lucide-react';
import { formatMs } from '../lib/format';

export interface Marker {
  id: string;
  t_ms: number;
  color: string;
  label: string;
  /** solid = confirmado, hollow = solo Muse/incierto, alert = incumplimiento */
  variant?: 'solid' | 'hollow' | 'alert';
}

export interface MarkerRange {
  id: string;
  from: number;
  to: number;
  color: string;
}

export interface VideoHandle {
  seek: (ms: number) => void;
}

interface Props {
  src: string;
  durationMs?: number | null;
  aspect?: number | null; // ancho/alto
  markers?: Marker[];
  ranges?: MarkerRange[];
  overlay?: ReactNode;
  /** Desactiva el clic sobre el video para play/pausa (p. ej. mientras se editan zonas). */
  overlayInteractive?: boolean;
  label: string;
  onTime?: (ms: number) => void;
  caption?: ReactNode;
}

export const VideoPlayer = forwardRef<VideoHandle, Props>(function VideoPlayer(
  { src, durationMs, aspect, markers = [], ranges = [], overlay, overlayInteractive, label, onTime, caption },
  ref,
) {
  const video = useRef<HTMLVideoElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState<number>(durationMs ?? 0);
  const [playing, setPlaying] = useState(false);
  const [ratio, setRatio] = useState<number>(aspect || 16 / 9);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [flash, setFlash] = useState<number | null>(null);

  useEffect(() => {
    setFailed(false);
    setLoaded(false);
  }, [src]);
  useEffect(() => {
    if (aspect) setRatio(aspect);
  }, [aspect]);
  useEffect(() => {
    if (durationMs) setDur(durationMs);
  }, [durationMs]);

  const seek = useCallback(
    (ms: number) => {
      const v = video.current;
      if (!v) return;
      const clamped = Math.max(0, Math.min(ms, dur || ms));
      v.currentTime = clamped / 1000;
      v.pause();
      setT(clamped);
      setFlash(clamped);
      window.setTimeout(() => setFlash(null), 900);
    },
    [dur],
  );

  useImperativeHandle(ref, () => ({ seek }), [seek]);

  const toggle = () => {
    const v = video.current;
    if (!v || failed) return;
    if (v.paused) {
      if (v.ended || (dur && v.currentTime * 1000 >= dur - 50)) v.currentTime = 0;
      void v.play();
    } else v.pause();
  };

  const posFromEvent = (clientX: number) => {
    const r = track.current?.getBoundingClientRect();
    if (!r || !dur) return 0;
    return Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * dur;
  };

  const onTrackKey = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 1000 : 250;
    if (e.key === 'ArrowRight') seek(t + step);
    else if (e.key === 'ArrowLeft') seek(t - step);
    else if (e.key === 'Home') seek(0);
    else if (e.key === 'End') seek(dur);
    else if (e.key === ' ' || e.key === 'k') toggle();
    else return;
    e.preventDefault();
  };

  const pct = (ms: number) => (dur ? `${Math.max(0, Math.min(100, (ms / dur) * 100))}%` : '0%');

  return (
    <figure className="player" aria-label={label}>
      <div className="player__stage" style={{ aspectRatio: String(ratio) }}>
        {!loaded && !failed && <span className="skeleton player__skeleton" aria-hidden />}
        <video
          ref={video}
          src={src}
          playsInline
          muted
          preload="metadata"
          onLoadedMetadata={(e) => {
            const v = e.currentTarget;
            setLoaded(true);
            if (!durationMs && Number.isFinite(v.duration)) setDur(v.duration * 1000);
            if (!aspect && v.videoWidth && v.videoHeight) setRatio(v.videoWidth / v.videoHeight);
          }}
          onTimeUpdate={(e) => {
            const ms = e.currentTarget.currentTime * 1000;
            setT(ms);
            onTime?.(ms);
          }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={() => setFailed(true)}
          onClick={overlayInteractive ? undefined : toggle}
        />
        {overlay && <div className={`player__overlay${overlayInteractive ? ' is-interactive' : ''}`}>{overlay}</div>}
        {failed && (
          <div className="player__error" role="alert">
            <VideoOff size={28} aria-hidden />
            <p>No se pudo cargar el video.</p>
            <p className="small">Comprueba la conexión con el servidor y recarga la página.</p>
          </div>
        )}
        {flash !== null && <span className="player__flash" aria-hidden>{formatMs(flash)}</span>}
      </div>

      <div className="player__controls">
        <button type="button" className="icon-btn icon-btn--filled" onClick={toggle} aria-label={playing ? 'Pausar' : 'Reproducir'} disabled={failed}>
          {playing ? <Pause size={18} /> : dur && t >= dur - 60 ? <RotateCcw size={18} /> : <Play size={18} />}
        </button>
        <div className="player__track-wrap">
          <div
            ref={track}
            className="player__track"
            role="slider"
            tabIndex={0}
            aria-label="Posición en el video"
            aria-valuemin={0}
            aria-valuemax={Math.round(dur)}
            aria-valuenow={Math.round(t)}
            aria-valuetext={`${formatMs(t)} de ${formatMs(dur)}`}
            onKeyDown={onTrackKey}
            onPointerDown={(e) => {
              if ((e.target as HTMLElement).closest('.marker')) return;
              seek(posFromEvent(e.clientX));
            }}
          >
            <span className="player__rail" />
            {ranges.map((r) => (
              <span
                key={r.id}
                className="player__range"
                style={{ left: pct(r.from), width: `calc(${pct(r.to)} - ${pct(r.from)})`, background: r.color }}
              />
            ))}
            <span className="player__fill" style={{ width: pct(t) }} />
            {markers.map((m) => (
              <button
                key={m.id}
                type="button"
                className={`marker marker--${m.variant ?? 'solid'}`}
                style={{ left: pct(m.t_ms), ['--mc' as string]: m.color }}
                onClick={() => seek(m.t_ms)}
                aria-label={`Ir a ${formatMs(m.t_ms)}: ${m.label}`}
                data-tip={`${formatMs(m.t_ms)} · ${m.label}`}
              />
            ))}
            <span className="player__head" style={{ left: pct(t) }} aria-hidden />
          </div>
        </div>
        <span className="player__time mono" aria-hidden>
          {formatMs(t)} / {formatMs(dur)}
        </span>
      </div>
      {caption && <figcaption className="player__caption">{caption}</figcaption>}
    </figure>
  );
});
