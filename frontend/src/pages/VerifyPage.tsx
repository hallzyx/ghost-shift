import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Film, Lightbulb, ListChecks, Lock, PlayCircle, RefreshCw, ScanEye } from 'lucide-react';
import { api, ApiError, mediaUrl } from '../api/client';
import type { Procedure, RunSummary, Sample } from '../api/types';
import { useFlowStep } from '../context/AppContext';
import { VerdictBadge } from '../components/brand';
import { DropZone, MAX_DURATION_S, readVideoMeta, validateVideoFile } from '../components/DropZone';
import { Button, Callout, Card, EmptyState, PageHeader, Skeleton } from '../components/ui';
import { formatBytes, formatDate } from '../lib/format';
import { LoadError, PageSkeleton } from './ProcedurePage';

type Source = { kind: 'file'; file: File; url: string } | { kind: 'sample'; sample: Sample };

const EXPECTED_HINT: Record<string, string> = {
  PASS: 'Este ejemplo debería dar PASS',
  FAIL: 'Este ejemplo debería dar FAIL',
  REVIEW: 'Este ejemplo debería dar REVIEW',
};

export function VerifyPage() {
  useFlowStep(3);
  const { pid } = useParams();
  const navigate = useNavigate();
  const [proc, setProc] = useState<Procedure | null>(null);
  const [loadErr, setLoadErr] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [submitErr, setSubmitErr] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!pid) return;
    setLoadErr(null);
    api
      .getProcedure(pid)
      .then(setProc)
      .catch((e: unknown) => setLoadErr(e instanceof ApiError ? e : new ApiError(0, String(e), true)));
    api
      .listRuns(pid)
      .then(setRuns)
      .catch(() => setRuns([]));
  }, [pid, nonce]);

  useEffect(() => {
    api
      .samples()
      .then((s) => setSamples(s.filter((x) => x.kind === 'run')))
      .catch(() => setSamples([]));
  }, []);

  useEffect(
    () => () => {
      if (source?.kind === 'file') URL.revokeObjectURL(source.url);
    },
    [source],
  );

  if (loadErr) return <LoadError error={loadErr} onRetry={() => setNonce((n) => n + 1)} what="el procedimiento" />;
  if (!proc) return <PageSkeleton />;

  const approved = proc.status === 'approved' || !!proc.draft?.approved;
  const activeRules = proc.draft?.rules.filter((r) => r.enabled) ?? [];

  if (!approved) {
    return (
      <div className="page">
        <PageHeader eyebrow="Paso 3 · Verificar" title={`Verificar «${proc.name}»`} />
        <Card>
          <EmptyState
            icon={<Lock size={28} />}
            title="Primero aprueba las reglas"
            action={
              <Button variant="primary" iconRight={<ArrowRight size={18} />} onClick={() => navigate(`/procedimientos/${proc.procedure_id}`)}>
                {proc.status === 'analyzing' ? 'Ver el análisis' : 'Ir a revisar reglas'}
              </Button>
            }
          >
            Solo se puede verificar contra una versión aprobada por ti: así ninguna sugerencia de la IA se convierte en obligación sin tu visto
            bueno.
          </EmptyState>
        </Card>
      </div>
    );
  }

  const pickFile = async (f: File) => {
    setSubmitErr(null);
    const err = validateVideoFile(f);
    if (err) return setFileError(err);
    const url = URL.createObjectURL(f);
    try {
      const meta = await readVideoMeta(url);
      if (meta.duration > MAX_DURATION_S) {
        URL.revokeObjectURL(url);
        return setFileError(`El video dura ${Math.round(meta.duration)} s y el máximo es ${MAX_DURATION_S} s. Recórtalo a la tarea.`);
      }
    } catch {
      URL.revokeObjectURL(url);
      return setFileError('Tu navegador no puede leer este video. Expórtalo como MP4 (H.264) e inténtalo de nuevo.');
    }
    setFileError(null);
    setSource({ kind: 'file', file: f, url });
  };

  const submit = async () => {
    if (!source) return;
    setBusy(true);
    setSubmitErr(null);
    try {
      const r =
        source.kind === 'file'
          ? await api.createRunFromVideo(proc.procedure_id, source.file)
          : await api.createRunFromSample(proc.procedure_id, source.sample.id);
      navigate(`/ejecuciones/${r.run_id}`);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, String(e), true);
      setSubmitErr(err.status === 409 ? new ApiError(409, 'Este procedimiento no tiene una versión aprobada. Vuelve a Revisar reglas y apruébalo.', false) : err);
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Paso 3 · Verificar"
        title={`Verifica una ejecución de «${proc.name}»`}
        subtitle={
          <>
            Sube un video nuevo de la misma tarea, grabado con el mismo encuadre. Se comprobará con la <strong>versión {proc.version} aprobada</strong>.
          </>
        }
      />
      <div className="teach">
        <Card className="teach__main">
          {!source ? (
            <>
              <DropZone onFile={pickFile} title="Arrastra aquí el video de la ejecución" />
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
                  aria-label="Vista previa de la ejecución"
                />
              </div>
              <div className="preview__meta">
                <span className="chip">
                  <Film size={14} aria-hidden />
                  {source.kind === 'file' ? source.file.name : `Ejemplo: ${source.sample.title_es}`}
                </span>
                {source.kind === 'file' && <span className="chip">{formatBytes(source.file.size)}</span>}
                {source.kind === 'sample' && source.sample.expected && (
                  <span className="chip chip--hint">
                    <Lightbulb size={14} aria-hidden /> {EXPECTED_HINT[source.sample.expected]}
                  </span>
                )}
                <button type="button" className="link-btn preview__change" onClick={() => setSource(null)}>
                  <RefreshCw size={14} aria-hidden /> Cambiar video
                </button>
              </div>
            </div>
          )}

          {submitErr && (
            <Callout tone="error" title="No pudimos empezar la verificación">
              {submitErr.message}
            </Callout>
          )}

          <div className="teach__actions">
            <Button variant="primary" size="lg" icon={<ScanEye size={20} />} onClick={submit} busy={busy} disabled={!source}>
              Verificar ejecución
            </Button>
            {!source && <span className="muted small">Primero elige un video o un ejemplo.</span>}
          </div>
        </Card>

        <aside className="teach__aside">
          <Card>
            <h2 className="h-sm">
              <ListChecks size={18} aria-hidden className="inline-icon" /> Se comprobarán {activeRules.length} reglas
            </h2>
            <ul className="mini-rules">
              {activeRules.map((r) => (
                <li key={r.id}>
                  <CheckCircle2 size={16} aria-hidden /> <span>{r.text_es}</span>
                </li>
              ))}
            </ul>
            <Link to={`/procedimientos/${proc.procedure_id}`} className="small">
              Ver o editar reglas
            </Link>
          </Card>

          <Card>
            <h2 className="h-sm">¿Sin video? Prueba un ejemplo</h2>
            {samples === null ? (
              <div className="stack gap-2">
                <Skeleton h={56} />
                <Skeleton h={56} />
              </div>
            ) : samples.length === 0 ? (
              <p className="muted small">No hay ejecuciones de ejemplo en este servidor.</p>
            ) : (
              <ul className="samples">
                {samples.map((s) => {
                  const on = source?.kind === 'sample' && source.sample.id === s.id;
                  return (
                    <li key={s.id}>
                      <button
                        type="button"
                        className={`sample${on ? ' is-on' : ''}`}
                        aria-pressed={on}
                        onClick={() => {
                          setFileError(null);
                          setSubmitErr(null);
                          setSource({ kind: 'sample', sample: s });
                        }}
                      >
                        <span className="sample__icon" aria-hidden>
                          {on ? <CheckCircle2 size={20} /> : <PlayCircle size={20} />}
                        </span>
                        <span className="sample__text">
                          <strong>{s.title_es}</strong>
                          <span className="muted small">{s.description_es}</span>
                          {s.expected && (
                            <span className="sample__hint">
                              <Lightbulb size={13} aria-hidden /> {EXPECTED_HINT[s.expected]}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {runs && runs.length > 0 && (
            <Card>
              <h2 className="h-sm">Ejecuciones anteriores</h2>
              <ul className="runs">
                {runs.map((r) => (
                  <li key={r.run_id}>
                    <Link to={`/ejecuciones/${r.run_id}`} className="runs__row">
                      {r.verdict ? <VerdictBadge verdict={r.verdict} withLong={false} /> : <span className="muted small">{r.status === 'running' ? 'En curso…' : 'Sin resultado'}</span>}
                      <span className="muted small">{formatDate(r.created_at)}</span>
                      <ArrowRight size={16} aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}
