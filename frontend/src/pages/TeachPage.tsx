import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Boxes, Camera, CheckCircle2, Clock, Film, Hand, LayoutPanelTop, PlayCircle, RefreshCw, Sparkles } from 'lucide-react';
import { api, ApiError, mediaUrl } from '../api/client';
import type { Sample } from '../api/types';
import { useApp, useFlowStep } from '../context/AppContext';
import { DropZone, MAX_DURATION_S, MIN_DURATION_S, readVideoMeta, validateVideoFile, WARN_DURATION_S } from '../components/DropZone';
import { Button, Callout, Card, Field, PageHeader, Skeleton } from '../components/ui';
import { formatBytes, formatMs } from '../lib/format';

type Source =
  | { kind: 'file'; file: File; url: string; duration: number; width: number; height: number }
  | { kind: 'sample'; sample: Sample };

const REQUIREMENTS = [
  { Icon: Camera, title: 'Cámara fija', text: 'Apoya el móvil o la cámara; que no se mueva durante la grabación.' },
  { Icon: LayoutPanelTop, title: 'Toda la mesa a la vista', text: 'Encuadra la superficie completa y las zonas donde se colocan las piezas.' },
  { Icon: Boxes, title: '2–4 objetos distinguibles', text: 'Por color o forma (p. ej. «cuadrado azul», «taza roja»).' },
  { Icon: Hand, title: 'Sin tapar las piezas', text: 'Evita que las manos oculten un objeto justo al soltarlo.' },
  { Icon: Clock, title: 'Duración razonable', text: `Entre ${MIN_DURATION_S} s y ${WARN_DURATION_S} s es lo ideal. MP4, MOV o WebM.` },
];

function nameFromFile(f: string) {
  const base = f.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
  return base ? base.charAt(0).toUpperCase() + base.slice(1) : 'Mi procedimiento';
}

export function TeachPage() {
  useFlowStep(1);
  const navigate = useNavigate();
  const { ensureSession, forgetSession } = useApp();
  const [source, setSource] = useState<Source | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [name, setName] = useState('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [samplesError, setSamplesError] = useState(false);

  useEffect(() => {
    api
      .samples()
      .then((s) => setSamples(s.filter((x) => x.kind === 'reference')))
      .catch(() => setSamplesError(true));
  }, []);

  useEffect(
    () => () => {
      if (source?.kind === 'file') URL.revokeObjectURL(source.url);
    },
    [source],
  );

  const pickFile = async (f: File) => {
    setSubmitError(null);
    const err = validateVideoFile(f);
    if (err) {
      setFileError(err);
      return;
    }
    setFileError(null);
    setReading(true);
    const url = URL.createObjectURL(f);
    try {
      const meta = await readVideoMeta(url);
      if (meta.duration > MAX_DURATION_S) {
        URL.revokeObjectURL(url);
        setFileError(
          `El video dura ${Math.round(meta.duration)} s y el máximo es ${MAX_DURATION_S} s. Recórtalo para que muestre solo la tarea.`,
        );
        return;
      }
      if (meta.duration < MIN_DURATION_S) {
        URL.revokeObjectURL(url);
        setFileError(`El video es demasiado corto (${meta.duration.toFixed(1)} s). Graba la tarea completa de principio a fin.`);
        return;
      }
      setSource({ kind: 'file', file: f, url, ...meta });
      if (!name.trim()) setName(nameFromFile(f.name));
    } catch {
      URL.revokeObjectURL(url);
      setFileError('Tu navegador no puede leer este video (¿códec poco común?). Expórtalo como MP4 (H.264) e inténtalo de nuevo.');
    } finally {
      setReading(false);
    }
  };

  const pickSample = (s: Sample) => {
    setFileError(null);
    setSubmitError(null);
    setSource({ kind: 'sample', sample: s });
    setName(s.title_es);
  };

  const submit = async () => {
    if (!source) return;
    if (!name.trim()) {
      setNameError('Ponle un nombre para reconocerlo después (p. ej. «Kit A-B-C»).');
      return;
    }
    setNameError(null);
    setSubmitError(null);
    let sid: string;
    try {
      sid = await ensureSession();
    } catch {
      return; // canceló el consentimiento
    }
    setSubmitting(true);
    try {
      const res =
        source.kind === 'file'
          ? await api.createProcedureFromVideo(sid, name.trim(), source.file)
          : await api.createProcedureFromSample(sid, name.trim(), source.sample.id);
      navigate(`/procedimientos/${res.procedure_id}`);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, String(e), true);
      if (err.status === 404) {
        forgetSession();
        setSubmitError(new ApiError(404, 'Tu sesión caducó. Pulsa de nuevo «Analizar video» para iniciar una nueva.', true));
      } else setSubmitError(err);
      setSubmitting(false);
    }
  };

  const warnings = useMemo(() => {
    if (source?.kind !== 'file') return [];
    const w: string[] = [];
    if (source.duration > WARN_DURATION_S) w.push(`El video dura ${Math.round(source.duration)} s. Si puedes, recórtalo a la tarea: el análisis será más rápido y preciso.`);
    if (source.height > source.width) w.push('El video está en vertical. Funciona mejor en horizontal, con toda la mesa a la vista.');
    return w;
  }, [source]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Paso 1 · Enseñar"
        title="Enseña un procedimiento nuevo"
        subtitle="Sube un video de la tarea hecha correctamente. La IA propondrá objetos, zonas y reglas que revisarás en el siguiente paso."
      />
      <div className="teach">
        <Card className="teach__main">
          {!source ? (
            <>
              {reading ? (
                <div className="dropzone is-reading" aria-busy="true">
                  <Skeleton h={28} w={28} r={14} />
                  <p className="dropzone__title">Leyendo el video…</p>
                </div>
              ) : (
                <DropZone onFile={pickFile} describedBy="teach-reqs" />
              )}
              {samples && samples[0] && !reading && (
                <div className="or-sample">
                  <span className="muted small">¿No tienes un video a mano?</span>
                  <Button size="sm" variant="tint" icon={<PlayCircle size={16} />} onClick={() => pickSample(samples[0]!)}>
                    Usar video de ejemplo
                  </Button>
                </div>
              )}
              {fileError && (
                <Callout tone="error" title="No podemos usar este archivo">
                  {fileError}
                </Callout>
              )}
            </>
          ) : (
            <div className="preview">
              <div className="preview__video">
                <video
                  src={source.kind === 'file' ? source.url : mediaUrl(source.sample.video_url)}
                  controls
                  muted
                  playsInline
                  preload="metadata"
                  aria-label="Vista previa del video de referencia"
                />
              </div>
              <div className="preview__meta">
                <span className="chip">
                  <Film size={14} aria-hidden />
                  {source.kind === 'file' ? source.file.name : `Ejemplo: ${source.sample.title_es}`}
                </span>
                {source.kind === 'file' && (
                  <>
                    <span className="chip">{formatMs(source.duration * 1000, false)} min</span>
                    <span className="chip">{formatBytes(source.file.size)}</span>
                    {source.width > 0 && (
                      <span className="chip">
                        {source.width}×{source.height}
                      </span>
                    )}
                  </>
                )}
                <button type="button" className="link-btn preview__change" onClick={() => setSource(null)}>
                  <RefreshCw size={14} aria-hidden /> Cambiar video
                </button>
              </div>
              {source.kind === 'sample' && <p className="muted small">{source.sample.description_es}</p>}
              {warnings.map((w) => (
                <Callout key={w} tone="warning">
                  {w}
                </Callout>
              ))}
            </div>
          )}

          <Field label="Nombre del procedimiento" htmlFor="proc-name" error={nameError} hint="Para reconocerlo en tu lista, p. ej. «Kit de montaje A-B-C».">
            <input
              id="proc-name"
              className="input"
              value={name}
              maxLength={80}
              placeholder="Kit de montaje A-B-C"
              aria-invalid={!!nameError}
              aria-describedby={nameError ? 'proc-name-err' : 'proc-name-hint'}
              onChange={(e) => {
                setName(e.target.value);
                if (nameError) setNameError(null);
              }}
              onKeyDown={(e) => e.key === 'Enter' && source && void submit()}
            />
          </Field>

          {submitError && (
            <Callout tone="error" title="No pudimos empezar el análisis">
              {submitError.message}
            </Callout>
          )}

          <div className="teach__actions">
            <Button variant="primary" size="lg" icon={<Sparkles size={20} />} onClick={submit} busy={submitting} disabled={!source}>
              Analizar video
            </Button>
            {!source && <span className="muted small">Primero elige un video o un ejemplo.</span>}
          </div>
        </Card>

        <aside className="teach__aside">
          <Card>
            <h2 className="h-sm" id="teach-reqs">
              Para que funcione bien
            </h2>
            <ul className="reqs">
              {REQUIREMENTS.map(({ Icon, title, text }) => (
                <li key={title}>
                  <span className="reqs__icon" aria-hidden>
                    <Icon size={18} />
                  </span>
                  <div>
                    <p className="reqs__title">{title}</p>
                    <p className="reqs__text">{text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <h2 className="h-sm">¿No tienes un video? Usa un ejemplo</h2>
            {samplesError && <p className="muted small">No pudimos cargar los ejemplos ahora mismo.</p>}
            {samples === null && !samplesError && (
              <div className="stack gap-2">
                <Skeleton h={56} />
                <Skeleton h={56} />
              </div>
            )}
            {samples && samples.length === 0 && <p className="muted small">No hay ejemplos disponibles en este servidor.</p>}
            {samples && samples.length > 0 && (
              <ul className="samples">
                {samples.map((s) => {
                  const on = source?.kind === 'sample' && source.sample.id === s.id;
                  return (
                    <li key={s.id}>
                      <button type="button" className={`sample${on ? ' is-on' : ''}`} aria-pressed={on} onClick={() => pickSample(s)}>
                        <span className="sample__icon" aria-hidden>
                          {on ? <CheckCircle2 size={20} /> : <PlayCircle size={20} />}
                        </span>
                        <span className="sample__text">
                          <strong>{s.title_es}</strong>
                          <span className="muted small">{s.description_es}</span>
                          <span className="sample__cta">{on ? 'Seleccionado' : 'Usar video de ejemplo'}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </aside>
      </div>
    </div>
  );
}
