import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Camera,
  ChevronDown,
  Cpu,
  Eye,
  Hand,
  Lightbulb,
  Plus,
  RotateCcw,
  ScanEye,
  ScrollText,
  SplitSquareHorizontal,
  Sun,
  TriangleAlert,
} from 'lucide-react';
import { api, ApiError, mediaUrl } from '../api/client';
import type { Procedure, Report, Run, RuleResult } from '../api/types';
import { useFlowStep } from '../context/AppContext';
import { usePolling } from '../lib/usePolling';
import { StageProgress } from '../components/StageProgress';
import { VideoPlayer, type Marker, type VideoHandle } from '../components/VideoPlayer';
import { EvidenceFrame } from '../components/EvidenceFrame';
import { VERDICT_META, VerdictBadge } from '../components/brand';
import { Button, Callout, Card, PageHeader } from '../components/ui';
import { formatMs, objectColorMap } from '../lib/format';
import { objName, zoneName } from '../lib/rules';
import { LoadError, PageSkeleton } from './ProcedurePage';

const ISSUE_ES: Record<string, string> = {
  INSUFFICIENT_OBSERVATION: 'Observación insuficiente: algún objeto no se vio con claridad durante el tiempo necesario.',
  NO_OBSERVATION: 'No se detectaron los objetos en el video.',
  CAMERA_MOVED: 'La cámara se movió durante la grabación.',
  CAMERA_MISALIGNED: 'El encuadre es distinto al del video de referencia.',
  OCCLUSION: 'Algo (p. ej. una mano) tapó un objeto en un momento clave.',
  IDENTITY_AMBIGUOUS: 'Dos objetos se parecen demasiado para distinguirlos con seguridad.',
};

const CAMERA_ES: Record<string, string> = {
  ALIGNED: 'Encuadre compatible con la referencia',
  MISALIGNED: 'Encuadre distinto a la referencia',
  MOVED: 'La cámara se movió',
  UNKNOWN: 'No se pudo comprobar el encuadre',
};

const ORDER: Record<string, number> = { FAIL: 0, REVIEW: 1, PASS: 2, SKIPPED: 3 };

function RunProgress({ run, onRetried }: { run: Run; onRetried: () => void }) {
  useFlowStep(3);
  const navigate = useNavigate();
  const [retrying, setRetrying] = useState(false);
  const retry = async () => {
    setRetrying(true);
    try {
      await api.retryRun(run.run_id);
      onRetried();
    } finally {
      setRetrying(false);
    }
  };
  return (
    <div className="page">
      <PageHeader eyebrow="Paso 3 · Verificar" title="Verificando la ejecución" />
      <div className="analysis">
        <Card className="analysis__main">
          <StageProgress
            title={run.status === 'failed' ? 'La verificación no terminó' : 'Comprobando cada regla aprobada'}
            subtitle={run.status === 'running' ? `Usando la versión ${run.procedure_version} del procedimiento. El veredicto lo calcula un motor determinista, no el modelo de lenguaje.` : undefined}
            stages={run.stages}
            running={run.status === 'running'}
            error={run.error ?? (run.status === 'failed' ? { message: 'La verificación falló por un motivo desconocido.', retryable: true } : null)}
            onRetry={retry}
            retrying={retrying}
            fallbackAction={
              <Button icon={<ScanEye size={18} />} onClick={() => navigate(`/procedimientos/${run.procedure_id}/verificar`)}>
                Probar con otro video
              </Button>
            }
          />
        </Card>
        <aside className="analysis__aside">
          <Card>
            <h2 className="h-sm">Ejecución enviada</h2>
            <div className="analysis__video">
              <video src={mediaUrl(run.video_url)} muted playsInline controls preload="metadata" aria-label="Video de la ejecución" />
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function summaryLine(report: Report): string {
  const fail = report.rules.filter((r) => r.verdict === 'FAIL');
  const review = report.rules.filter((r) => r.verdict === 'REVIEW');
  const counted = report.rules.filter((r) => r.verdict !== 'SKIPPED').length;
  if (report.verdict === 'PASS') return `Se cumplieron las ${counted} reglas aprobadas.`;
  if (report.verdict === 'FAIL')
    return fail.length === 1 ? `1 de ${counted} reglas no se cumplió.` : `${fail.length} de ${counted} reglas no se cumplieron.`;
  return review.length === 1
    ? 'No hubo fallos, pero 1 regla no se pudo comprobar con seguridad.'
    : `No hubo fallos, pero ${review.length} reglas no se pudieron comprobar con seguridad.`;
}

const HERO_TITLE: Record<string, string> = {
  PASS: 'La ejecución cumple el procedimiento',
  FAIL: 'La ejecución no cumple el procedimiento',
  REVIEW: 'Observación insuficiente: revisa la grabación',
};

function RuleResultCard({ r, proc, onSeek }: { r: RuleResult; proc: Procedure | null; onSeek: (ms: number) => void }) {
  const objects = proc?.draft?.objects ?? [];
  return (
    <article className={`rres rres--${r.verdict.toLowerCase()}`} id={`res-${r.rule_id}`}>
      <div className="rres__head">
        <VerdictBadge verdict={r.verdict} />
        <span className="rule__id mono">{r.rule_id}</span>
      </div>
      <p className="rres__text">{r.text_es}</p>
      {r.reason_es && <p className="rres__reason">{r.reason_es}</p>}
      {r.missing.length > 0 && (
        <ul className="rres__missing">
          {r.missing.map((m, i) => (
            <li key={i}>
              <TriangleAlert size={14} aria-hidden /> Faltó: {m}
            </li>
          ))}
        </ul>
      )}
      {r.evidence.length > 0 && (r.verdict === 'PASS' || r.verdict === 'SKIPPED') && (
        <details className="rres__more">
          <summary>Ver evidencia ({r.evidence.length})</summary>
          <div className="ev-grid">
            {r.evidence.map((ev, i) => (
              <EvidenceFrame key={i} ev={ev} objLabel={ev.obj ? objName(objects, ev.obj) : 'Escena'} onSeek={onSeek} />
            ))}
          </div>
        </details>
      )}
      {r.evidence.length > 0 && (r.verdict === 'FAIL' || r.verdict === 'REVIEW') && (
        <div className="rres__ev">
          <p className="rres__ev-title">Evidencia · haz clic para verla en el video</p>
          <div className="ev-grid">
            {r.evidence.map((ev, i) => (
              <EvidenceFrame key={i} ev={ev} objLabel={ev.obj ? objName(objects, ev.obj) : 'Escena'} onSeek={onSeek} />
            ))}
          </div>
        </div>
      )}
      {(r.verdict === 'FAIL' || r.verdict === 'REVIEW') && r.evidence.length === 0 && (
        <p className="muted small">No hay fotograma de evidencia para esta regla.</p>
      )}
    </article>
  );
}

function ResultView({ run, proc }: { run: Run; proc: Procedure | null }) {
  useFlowStep(4);
  const navigate = useNavigate();
  const report = run.report!;
  const player = useRef<VideoHandle>(null);
  const playerBox = useRef<HTMLDivElement>(null);
  const [compare, setCompare] = useState(false);
  const meta = VERDICT_META[report.verdict];
  const objects = proc?.draft?.objects ?? [];
  const zones = proc?.draft?.zones ?? [];
  const objColors = useMemo(() => objectColorMap(objects), [objects]);
  const oc = (id: string | undefined) => (id && objColors[id]) || 'var(--c-text-2)';

  const sorted = useMemo(() => [...report.rules].sort((a, b) => (ORDER[a.verdict] ?? 9) - (ORDER[b.verdict] ?? 9)), [report.rules]);
  const counts = {
    PASS: report.rules.filter((r) => r.verdict === 'PASS').length,
    FAIL: report.rules.filter((r) => r.verdict === 'FAIL').length,
    REVIEW: report.rules.filter((r) => r.verdict === 'REVIEW').length,
  };

  const seek = (ms: number) => {
    player.current?.seek(ms);
    const box = playerBox.current;
    if (box) {
      const r = box.getBoundingClientRect();
      if (r.top < 70 || r.bottom > window.innerHeight) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const markers: Marker[] = [
    ...report.events.map((e, i) => ({
      id: `e${i}`,
      t_ms: e.t_hi,
      color: oc(e.obj),
      variant: (e.timing_uncertain ? 'hollow' : 'solid') as Marker['variant'],
      label: `${objName(objects, e.obj)} ${e.kind === 'place' ? 'colocado en' : e.kind === 'remove' ? 'retirado de' : e.kind} ${zoneName(zones, e.zone)}`,
    })),
    ...report.rules
      .filter((r) => r.verdict === 'FAIL' || r.verdict === 'REVIEW')
      .flatMap((r) =>
        r.evidence.map((ev, i) => ({
          id: `v${r.rule_id}${i}`,
          t_ms: ev.t_ms,
          color: r.verdict === 'FAIL' ? 'var(--c-error)' : 'var(--c-warning)',
          variant: 'alert' as const,
          label: `${r.verdict === 'FAIL' ? 'Incumplimiento' : 'Por revisar'} ${r.rule_id}: ${ev.detail ?? r.text_es}`,
        })),
      ),
  ];

  // Línea de tiempo combinada: eventos observados + instantes de incumplimiento
  const timeline = useMemo(() => {
    const rows: { t: number; kind: 'event' | 'FAIL' | 'REVIEW'; text: string; uncertain?: boolean; obj?: string }[] = [];
    report.events.forEach((e) =>
      rows.push({
        t: e.t_hi,
        kind: 'event',
        obj: e.obj,
        uncertain: e.timing_uncertain,
        text: `${objName(objects, e.obj)} ${e.kind === 'place' ? 'se coloca en' : e.kind === 'remove' ? 'se retira de' : e.kind} ${zoneName(zones, e.zone)}`,
      }),
    );
    report.rules
      .filter((r) => r.verdict === 'FAIL' || r.verdict === 'REVIEW')
      .forEach((r) => {
        const ev = r.evidence[0];
        if (ev) rows.push({ t: ev.t_ms, kind: r.verdict as 'FAIL' | 'REVIEW', text: `${r.rule_id} · ${r.text_es}` });
      });
    return rows.sort((a, b) => a.t - b.t);
  }, [report, objects, zones]);

  return (
    <div className="page">
      <section className={`verdict verdict--${report.verdict.toLowerCase()}`} aria-labelledby="verdict-title">
        <div className="verdict__ring" aria-hidden>
          <span className="verdict__icon">
            <meta.Icon size={44} strokeWidth={2.2} />
          </span>
        </div>
        <div className="verdict__text">
          <p className="eyebrow">Paso 4 · Resultado · versión {run.procedure_version} del procedimiento</p>
          <h1 id="verdict-title">
            <span className="verdict__word">{report.verdict}</span>
            <span className="verdict__title">{HERO_TITLE[report.verdict]}</span>
          </h1>
          <p className="verdict__sub">{summaryLine(report)}</p>
          <div className="verdict__counts">
            <VerdictCount v="PASS" n={counts.PASS} />
            <VerdictCount v="FAIL" n={counts.FAIL} />
            <VerdictCount v="REVIEW" n={counts.REVIEW} />
          </div>
        </div>
        <div className="verdict__actions">
          <Button variant="primary" size="lg" icon={<ScanEye size={20} />} onClick={() => navigate(`/procedimientos/${run.procedure_id}/verificar`)}>
            Verificar otra ejecución
          </Button>
          <Button icon={<Plus size={18} />} onClick={() => navigate('/ensenar')}>
            Enseñar otro procedimiento
          </Button>
        </div>
      </section>

      {report.verdict === 'REVIEW' && (
        <Callout tone="warning" title="REVIEW no es un fallo" icon={<Eye size={20} />}>
          <p>
            GhostShift no vio lo suficiente para afirmar que se cumplió o se incumplió alguna regla, así que prefiere no decidir. Graba de nuevo
            teniendo en cuenta:
          </p>
          <ul className="tips">
            <li>
              <Hand size={16} aria-hidden /> Que las manos no tapen las piezas justo al soltarlas.
            </li>
            <li>
              <Camera size={16} aria-hidden /> La cámara fija y con el mismo encuadre que la referencia.
            </li>
            <li>
              <Sun size={16} aria-hidden /> Buena luz, sin reflejos ni sombras fuertes sobre los objetos.
            </li>
          </ul>
        </Callout>
      )}

      <div className="result">
        <div className="result__left">
          <div ref={playerBox} className="sticky-col">
            <Card>
              <div className="card-head">
                <h2 className="h-sm">Video de la ejecución</h2>
                {proc && (
                  <Button size="sm" variant={compare ? 'tint' : 'secondary'} icon={<SplitSquareHorizontal size={16} />} aria-pressed={compare} onClick={() => setCompare((v) => !v)}>
                    {compare ? 'Ocultar referencia' : 'Comparar con referencia'}
                  </Button>
                )}
              </div>
              <div className={compare ? 'compare' : undefined}>
                <VideoPlayer
                  ref={player}
                  src={mediaUrl(run.video_url)}
                  durationMs={run.duration_ms}
                  markers={markers}
                  label="Video de la ejecución con eventos e incumplimientos"
                  caption={compare ? 'Ejecución' : undefined}
                />
                {compare && proc && (
                  <VideoPlayer src={mediaUrl(proc.video_url)} durationMs={proc.duration_ms} label="Video de referencia" caption="Referencia" />
                )}
              </div>
              <p className="legend small">
                <span className="lg-dot lg-dot--solid" aria-hidden /> evento observado
                <span className="lg-dot lg-dot--hollow" aria-hidden /> instante aproximado
                <span className="lg-dot lg-dot--alert" aria-hidden /> incumplimiento o duda
              </p>
            </Card>

            <Card>
              <h2 className="h-sm">Línea de tiempo</h2>
              {timeline.length === 0 ? (
                <p className="muted small">No se observaron eventos de colocación en esta ejecución.</p>
              ) : (
                <ol className="events__list">
                  {timeline.map((row, i) => (
                    <li key={i}>
                      <button type="button" className={`event-row event-row--${row.kind.toLowerCase()}`} onClick={() => seek(row.t)}>
                        <span className="mono event-row__t">{formatMs(row.t)}</span>
                        {row.kind === 'event' ? (
                          <span
                            className={`lg-dot lg-dot--${row.uncertain ? 'hollow' : 'solid'}`}
                            style={{ ['--mc' as string]: oc(row.obj) }}
                            aria-hidden
                          />
                        ) : (
                          <VerdictBadge verdict={row.kind} withLong={false} />
                        )}
                        <span className="event-row__text">
                          {row.text}
                          {row.uncertain && <span className="muted"> (instante aproximado)</span>}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
        </div>

        <div className="result__right">
          <Card>
            <h2 className="h-sm">Reglas comprobadas</h2>
            <div className="stack gap-3">
              {sorted.map((r) => (
                <RuleResultCard key={r.rule_id} r={r} proc={proc} onSeek={seek} />
              ))}
            </div>
          </Card>

          <details className="card how-we">
            <summary>
              <Lightbulb size={18} aria-hidden /> Cómo llegamos a este resultado
              <ChevronDown size={18} className="chev" aria-hidden />
            </summary>
            <div className="how-we__body">
              <ol className="how-we__steps">
                <li>
                  <strong>SAM 3.1</strong> siguió los objetos aprobados en el video y el motor detectó{' '}
                  <strong>
                    {report.events.length} {report.events.length === 1 ? 'evento' : 'eventos'}
                  </strong>{' '}
                  de colocación.
                </li>
                <li>
                  El <strong>motor determinista</strong> de GhostShift evaluó cada regla de la <strong>versión {run.procedure_version}</strong> aprobada. Ningún
                  modelo de lenguaje decide el veredicto.
                </li>
                <li>Regla global: FAIL si alguna regla falla; REVIEW si ninguna falla pero alguna no se pudo comprobar; PASS solo si todas se verificaron.</li>
              </ol>
              <dl className="facts">
                <div>
                  <dt>Encuadre</dt>
                  <dd>{CAMERA_ES[report.camera_status] ?? report.camera_status}</dd>
                </div>
                <div>
                  <dt>Eventos observados</dt>
                  <dd>{report.events.length}</dd>
                </div>
                <div>
                  <dt>Versión del procedimiento</dt>
                  <dd>v{run.procedure_version}</dd>
                </div>
                <div>
                  <dt>Incidencias</dt>
                  <dd>
                    {report.blocking_issues.length === 0
                      ? 'Ninguna'
                      : report.blocking_issues.map((b) => (
                          <span key={b} className="block">
                            {ISSUE_ES[b] ?? b}
                          </span>
                        ))}
                  </dd>
                </div>
              </dl>
              <Link to="/auditoria" className="small row gap-1">
                <ScrollText size={14} aria-hidden /> Ver el registro de llamadas a los modelos
              </Link>
              <p className="muted small row gap-1">
                <Cpu size={14} aria-hidden /> ID de ejecución <code>{run.run_id}</code>
              </p>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}

function VerdictCount({ v, n }: { v: 'PASS' | 'FAIL' | 'REVIEW'; n: number }) {
  const m = VERDICT_META[v];
  return (
    <span className={`vcount vcount--${v.toLowerCase()}${n === 0 ? ' is-zero' : ''}`}>
      <m.Icon size={16} aria-hidden /> <strong>{n}</strong> {v === 'PASS' ? (n === 1 ? 'cumple' : 'cumplen') : v === 'FAIL' ? (n === 1 ? 'no cumple' : 'no cumplen') : 'por revisar'}
    </span>
  );
}

export function RunPage() {
  const { rid } = useParams();
  const poll = usePolling<Run>(rid, () => api.getRun(rid!), (r) => r.status === 'running');
  const [proc, setProc] = useState<Procedure | null>(null);
  const pid = poll.data?.procedure_id;

  useEffect(() => {
    if (!pid) return;
    api
      .getProcedure(pid)
      .then(setProc)
      .catch(() => setProc(null));
  }, [pid]);

  if (poll.error && !poll.data) return <LoadError error={poll.error} onRetry={poll.reload} what="la ejecución" />;
  if (!poll.data) return <PageSkeleton />;
  const run = poll.data;
  if (run.status === 'done' && run.report) return <ResultView run={run} proc={proc} />;
  return (
    <>
      {poll.error && (
        <div className="page page--flush">
          <Callout
            tone="warning"
            title="Se perdió la conexión mientras esperábamos"
            action={
              <Button icon={<RotateCcw size={18} />} onClick={poll.reload}>
                Volver a consultar
              </Button>
            }
          >
            {(poll.error as ApiError).message}
          </Callout>
        </div>
      )}
      <RunProgress run={run} onRetried={poll.reload} />
    </>
  );
}
