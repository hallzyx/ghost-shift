import { useId, useRef, useState, type DragEvent } from 'react';
import { FileVideo, UploadCloud } from 'lucide-react';

export const ACCEPTED_EXT = ['mp4', 'mov', 'webm', 'm4v'];
export const ACCEPTED_MIME = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-m4v'];
/** Límites del lado cliente (orientativos; el backend valida los definitivos). */
export const MAX_BYTES = 200 * 1024 * 1024;
export const MAX_DURATION_S = 120;
export const WARN_DURATION_S = 60;
export const MIN_DURATION_S = 2;

export function validateVideoFile(f: File): string | null {
  const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ACCEPTED_MIME.includes(f.type) && !ACCEPTED_EXT.includes(ext)) {
    return `«${f.name}» no es un video compatible. Usa MP4, MOV o WebM.`;
  }
  if (f.size === 0) return 'El archivo está vacío. Vuelve a exportar el video e inténtalo de nuevo.';
  if (f.size > MAX_BYTES) {
    return `El video pesa ${(f.size / 1024 / 1024).toFixed(0)} MB y el máximo es ${MAX_BYTES / 1024 / 1024} MB. Recórtalo o expórtalo a menor resolución (720p basta).`;
  }
  return null;
}

/** Lee la duración del archivo en el navegador. Rechaza si no se puede decodificar. */
export function readVideoMeta(url: string): Promise<{ duration: number; width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const v = document.createElement('video');
    v.preload = 'metadata';
    v.muted = true;
    const done = () => {
      v.removeAttribute('src');
      v.load();
    };
    v.onloadedmetadata = () => {
      const r = { duration: v.duration, width: v.videoWidth, height: v.videoHeight };
      done();
      resolve(r);
    };
    v.onerror = () => {
      done();
      reject(new Error('unreadable'));
    };
    v.src = url;
  });
}

export function DropZone({
  onFile,
  title = 'Arrastra tu video aquí',
  compact = false,
  describedBy,
}: {
  onFile: (f: File) => void;
  title?: string;
  compact?: boolean;
  describedBy?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const id = useId();

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };

  return (
    <div
      className={`dropzone${drag ? ' is-drag' : ''}${compact ? ' dropzone--compact' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
    >
      <span className="dropzone__icon" aria-hidden>
        {drag ? <FileVideo size={28} /> : <UploadCloud size={28} />}
      </span>
      <p className="dropzone__title">{drag ? 'Suelta el video para usarlo' : title}</p>
      <p className="dropzone__sub">
        o{' '}
        <button type="button" className="link-btn" onClick={() => input.current?.click()} aria-describedby={describedBy}>
          elígelo de tu equipo
        </button>{' '}
        · MP4, MOV o WebM
      </p>
      <input
        ref={input}
        id={id}
        type="file"
        accept={[...ACCEPTED_MIME, ...ACCEPTED_EXT.map((e) => '.' + e)].join(',')}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = '';
        }}
      />
    </div>
  );
}
