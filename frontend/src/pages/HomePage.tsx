import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, CircleCheckBig, ListChecks, Plus, RotateCcw, ScanEye, Upload } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { ProcedureSummary } from '../api/types';
import { useApp } from '../context/AppContext';
import { StatusBadge } from '../components/brand';
import { Button, Callout, Card, PageHeader, Skeleton } from '../components/ui';
import { formatDate } from '../lib/format';

function HowItWorks() {
  const steps = [
    { Icon: Upload, title: 'Enseña', text: 'Sube un video de la tarea bien hecha, con la cámara fija.' },
    { Icon: ListChecks, title: 'Revisa', text: 'La IA propone reglas. Tú decides cuáles forman parte de la norma.' },
    { Icon: ScanEye, title: 'Verifica', text: 'Sube otra ejecución y comprueba si se cumplió cada regla.' },
    { Icon: CircleCheckBig, title: 'Entiende', text: 'PASS, FAIL o REVIEW, con el instante y el fotograma como evidencia.' },
  ];
  return (
    <ol className="how">
      {steps.map(({ Icon, title, text }, i) => (
        <li key={title} className="how__item">
          <span className="how__icon" aria-hidden>
            <Icon size={22} />
          </span>
          <div>
            <p className="how__title">
              <span className="how__n">{i + 1}</span> {title}
            </p>
            <p className="how__text">{text}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function actionFor(p: ProcedureSummary): { label: string; to: string } {
  switch (p.status) {
    case 'analyzing':
      return { label: 'Ver progreso', to: `/procedimientos/${p.procedure_id}` };
    case 'failed':
      return { label: 'Ver qué pasó', to: `/procedimientos/${p.procedure_id}` };
    case 'approved':
      return { label: 'Verificar ejecución', to: `/procedimientos/${p.procedure_id}/verificar` };
    default:
      return { label: 'Revisar reglas', to: `/procedimientos/${p.procedure_id}` };
  }
}

export function HomePage() {
  const { sessionId, forgetSession } = useApp();
  const navigate = useNavigate();
  const [items, setItems] = useState<ProcedureSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!sessionId) {
      setItems([]);
      return;
    }
    let alive = true;
    setItems(null);
    setError(null);
    api
      .listProcedures(sessionId)
      .then((d) => alive && setItems(d))
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          forgetSession(); // la sesión caducó en el servidor
          setItems([]);
        } else setError(e instanceof ApiError ? e : new ApiError(0, String(e), true));
      });
    return () => {
      alive = false;
    };
  }, [sessionId, nonce, forgetSession]);

  const empty = items !== null && items.length === 0 && !error;

  return (
    <div className="page">
      {empty ? (
        <section className="hero">
          <div className="hero__text">
            <p className="eyebrow">Verificador visual de procedimientos</p>
            <h1 className="hero__title">
              Enséñale una tarea una vez.
              <br />
              <span className="grad-text">Comprueba la siguiente ejecución.</span>
            </h1>
            <p className="hero__sub">
              Graba cómo se hace bien una tarea sencilla sobre una mesa. GhostShift propone reglas observables, tú las apruebas y luego
              comprueba cada nueva ejecución con evidencia.
            </p>
            <div className="row gap-3 wrap">
              <Button variant="primary" size="lg" icon={<Plus size={20} />} onClick={() => navigate('/ensenar')}>
                Enseñar nuevo procedimiento
              </Button>
            </div>
            <p className="muted small">¿Sin video a mano? En el siguiente paso puedes usar un video de ejemplo.</p>
          </div>
          <Card className="hero__card">
            <h2 className="h-sm">Cómo funciona</h2>
            <HowItWorks />
            <p className="hero__principle">
              <strong>Los modelos proponen, tú apruebas, el motor decide.</strong> Ninguna regla se vuelve obligatoria sin tu visto bueno.
            </p>
          </Card>
        </section>
      ) : (
        <>
          <PageHeader
            title="Mis procedimientos"
            subtitle="Cada procedimiento es una tarea enseñada con un video de referencia y sus reglas aprobadas."
            actions={
              <Button variant="primary" icon={<Plus size={20} />} onClick={() => navigate('/ensenar')}>
                Enseñar nuevo procedimiento
              </Button>
            }
          />
          {error && (
            <Callout
              tone="error"
              title="No pudimos cargar tus procedimientos"
              action={
                <Button icon={<RotateCcw size={18} />} onClick={() => setNonce((n) => n + 1)}>
                  Reintentar
                </Button>
              }
            >
              {error.message}
            </Callout>
          )}
          {items === null && !error && (
            <div className="proc-grid" aria-busy="true" aria-label="Cargando procedimientos">
              {[0, 1, 2].map((i) => (
                <div key={i} className="card proc">
                  <Skeleton h={14} w={110} />
                  <Skeleton h={22} w="70%" />
                  <Skeleton h={14} w="50%" />
                  <Skeleton h={36} w={150} r={20} />
                </div>
              ))}
            </div>
          )}
          {items && items.length > 0 && (
            <ul className="proc-grid" aria-label="Procedimientos">
              {items.map((p) => {
                const a = actionFor(p);
                return (
                  <li key={p.procedure_id} className="card proc">
                    <div className="proc__top">
                      <StatusBadge status={p.status} />
                      <span className="muted small">v{p.version}</span>
                    </div>
                    <h2 className="proc__name">
                      <Link to={a.to} className="proc__link">
                        {p.name}
                      </Link>
                    </h2>
                    <p className="muted small">
                      {p.status === 'analyzing'
                        ? 'La IA está analizando el video…'
                        : `${p.n_rules} ${p.n_rules === 1 ? 'regla' : 'reglas'}`}{' '}
                      · {formatDate(p.created_at)}
                    </p>
                    <span className={`proc__cta${p.status === 'approved' ? ' is-primary' : ''}`} aria-hidden>
                      {a.label} <ArrowRight size={16} />
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
