import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Brain, Cpu, Plus, RotateCcw, ScanSearch, SearchX } from 'lucide-react';
import { api, ApiError, mediaUrl } from '../api/client';
import type { Procedure } from '../api/types';
import { useApp, useFlowStep } from '../context/AppContext';
import { usePolling } from '../lib/usePolling';
import { StageProgress } from '../components/StageProgress';
import { Button, Callout, Card, EmptyState, PageHeader, Skeleton } from '../components/ui';
import { RuleStudio } from './RuleStudio';

function AnalysisView({ proc, onRetried }: { proc: Procedure; onRetried: () => void }) {
  useFlowStep(1);
  const navigate = useNavigate();
  const [retrying, setRetrying] = useState(false);
  const [retryErr, setRetryErr] = useState<string | null>(null);
  const running = proc.analysis.status === 'running';

  const retry = async () => {
    setRetrying(true);
    setRetryErr(null);
    try {
      await api.retryProcedure(proc.procedure_id);
      onRetried();
    } catch (e) {
      setRetryErr(e instanceof ApiError ? e.message : 'No se pudo reintentar.');
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="page">
      <PageHeader eyebrow="Paso 1 · Enseñar" title={`Analizando «${proc.name}»`} />
      <div className="analysis">
        <Card className="analysis__main">
          <StageProgress
            title={running ? 'La IA está estudiando tu video' : proc.analysis.status === 'failed' ? 'El análisis no terminó' : 'Análisis completado'}
            subtitle={running ? 'Te llevaremos a revisar las reglas en cuanto termine.' : undefined}
            stages={proc.analysis.stages}
            running={running}
            error={proc.analysis.error ?? (proc.analysis.status === 'failed' ? { message: 'El análisis falló por un motivo desconocido.', retryable: true } : null)}
            onRetry={retry}
            retrying={retrying}
            fallbackAction={
              <Button icon={<Plus size={18} />} onClick={() => navigate('/ensenar')}>
                Enseñar con otro video
              </Button>
            }
          />
          {retryErr && <Callout tone="error">{retryErr}</Callout>}
        </Card>
        <aside className="analysis__aside">
          <Card>
            <h2 className="h-sm">Tu video de referencia</h2>
            <div className="analysis__video">
              <video src={mediaUrl(proc.video_url)} muted playsInline controls preload="metadata" aria-label="Video de referencia" />
            </div>
          </Card>
          <Card>
            <h2 className="h-sm">Qué está pasando</h2>
            <ul className="explain">
              <li>
                <Brain size={18} aria-hidden />
                <span>
                  <strong>Muse Spark</strong> describe los objetos, las zonas y el orden en que ocurren las cosas.
                </span>
              </li>
              <li>
                <ScanSearch size={18} aria-hidden />
                <span>
                  <strong>SAM 3.1</strong> localiza y sigue cada objeto para comprobar dónde y cuándo se movió.
                </span>
              </li>
              <li>
                <Cpu size={18} aria-hidden />
                <span>
                  <strong>El motor de GhostShift</strong> contrasta ambos: lo que SAM no respalda se marca como hipótesis.
                </span>
              </li>
            </ul>
          </Card>
        </aside>
      </div>
    </div>
  );
}

export function ProcedurePage() {
  const { pid } = useParams();
  const { toast } = useApp();
  const poll = usePolling<Procedure>(pid, () => api.getProcedure(pid!), (p) => p.analysis.status === 'running');
  const wasRunning = useRef(false);

  useEffect(() => {
    const d = poll.data;
    if (!d) return;
    if (d.analysis.status === 'running') wasRunning.current = true;
    else if (wasRunning.current && d.analysis.status === 'done') {
      wasRunning.current = false;
      toast('Análisis completado. Revisa las reglas propuestas.');
    }
  }, [poll.data, toast]);

  if (poll.error && !poll.data) return <LoadError error={poll.error} onRetry={poll.reload} what="el procedimiento" />;
  if (!poll.data) return <PageSkeleton />;

  const proc = poll.data;
  if (proc.analysis.status === 'done' && proc.draft) {
    return <RuleStudio proc={proc} onSaved={(p) => poll.setData(p)} reload={poll.reload} />;
  }
  if (proc.analysis.status === 'done' && !proc.draft) {
    return (
      <div className="page">
        <Card>
          <EmptyState icon={<SearchX size={28} />} title="No encontramos objetos para proponer reglas">
            El análisis terminó pero no se detectaron objetos suficientes. Graba de nuevo con la cámara fija, buena luz y 2–4 objetos de
            colores distintos.
          </EmptyState>
        </Card>
      </div>
    );
  }
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
            {poll.error.message}
          </Callout>
        </div>
      )}
      <AnalysisView proc={proc} onRetried={poll.reload} />
    </>
  );
}

export function LoadError({ error, onRetry, what }: { error: ApiError; onRetry: () => void; what: string }) {
  const navigate = useNavigate();
  const notFound = error.status === 404;
  return (
    <div className="page">
      <Card>
        <EmptyState
          icon={notFound ? <SearchX size={28} /> : <RotateCcw size={28} />}
          title={notFound ? `No encontramos ${what}` : `No pudimos cargar ${what}`}
          action={
            <div className="row gap-2 wrap center">
              {!notFound && (
                <Button variant="primary" icon={<RotateCcw size={18} />} onClick={onRetry}>
                  Reintentar
                </Button>
              )}
              <Button icon={<ArrowLeft size={18} />} onClick={() => navigate('/')}>
                Ir a Mis procedimientos
              </Button>
            </div>
          }
        >
          {notFound ? 'Puede que se haya borrado o que tu sesión haya caducado.' : error.message}
        </EmptyState>
      </Card>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Cargando">
      <div className="stack gap-3">
        <Skeleton h={14} w={120} />
        <Skeleton h={30} w="45%" />
      </div>
      <div className="split mt-6">
        <div className="card stack gap-3">
          <Skeleton h={280} r={12} />
          <Skeleton h={18} w="60%" />
        </div>
        <div className="card stack gap-3">
          <Skeleton h={80} r={12} />
          <Skeleton h={80} r={12} />
          <Skeleton h={80} r={12} />
        </div>
      </div>
    </div>
  );
}
