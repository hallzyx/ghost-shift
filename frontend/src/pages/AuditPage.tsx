import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, CircleCheck, CircleX, Plus, RotateCcw, ScanSearch, ScrollText } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { AuditEntry } from '../api/types';
import { useApp } from '../context/AppContext';
import { Badge, Button, Callout, Card, EmptyState, PageHeader, Skeleton } from '../components/ui';
import { formatDate } from '../lib/format';

export function AuditPage() {
  const { sessionId } = useApp();
  const navigate = useNavigate();
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(() => {
    if (!sessionId) return setRows([]);
    setRows(null);
    setError(null);
    api
      .audit(sessionId)
      .then((r) => setRows([...r].sort((a, b) => (a.created_at < b.created_at ? 1 : -1))))
      .catch((e: unknown) => setError(e instanceof ApiError ? e : new ApiError(0, String(e), true)));
  }, [sessionId]);

  useEffect(load, [load]);

  const ok = (s: string) => /^(ok|success|succeeded|done|200)$/i.test(s);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Transparencia"
        title="Registro de llamadas a modelos"
        subtitle="Cada consulta a Muse Spark o SAM 3.1 de tu sesión, con la versión del modelo, el identificador de la petición y su latencia. Sirve para comprobar que la inferencia es real."
        actions={
          sessionId && (
            <Button icon={<RotateCcw size={18} />} onClick={load}>
              Actualizar
            </Button>
          )
        }
      />
      {error && (
        <Callout tone="error" title="No pudimos cargar el registro" action={<Button onClick={load}>Reintentar</Button>}>
          {error.message}
        </Callout>
      )}
      <Card className="audit">
        {rows === null && !error ? (
          <div className="stack gap-2" aria-busy="true">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} h={36} />
            ))}
          </div>
        ) : rows && rows.length === 0 ? (
          <EmptyState
            icon={<ScrollText size={28} />}
            title="Todavía no hay llamadas registradas"
            action={
              <Button variant="primary" icon={<Plus size={18} />} onClick={() => navigate('/ensenar')}>
                Enseñar un procedimiento
              </Button>
            }
          >
            {sessionId
              ? 'Aparecerán aquí en cuanto analices un video.'
              : 'No tienes una sesión activa. Empieza enseñando un procedimiento.'}
          </EmptyState>
        ) : rows ? (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla de llamadas">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Modelo</th>
                  <th scope="col">Versión</th>
                  <th scope="col">ID de petición</th>
                  <th scope="col" className="num">
                    Latencia
                  </th>
                  <th scope="col">Estado</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={String(r.id)}>
                    <td className="nowrap">{formatDate(r.created_at)}</td>
                    <td>
                      {r.kind === 'muse' ? (
                        <Badge tone="violet" icon={<Brain size={13} aria-hidden />}>
                          Muse Spark
                        </Badge>
                      ) : (
                        <Badge tone="blue" icon={<ScanSearch size={13} aria-hidden />}>
                          SAM 3.1
                        </Badge>
                      )}
                    </td>
                    <td className="mono">{r.model_version || '—'}</td>
                    <td className="mono trunc" title={r.request_id ?? ''}>
                      {r.request_id || '—'}
                    </td>
                    <td className="num mono">{r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(2)} s` : '—'}</td>
                    <td>
                      {ok(r.status) ? (
                        <span className="status-ok">
                          <CircleCheck size={15} aria-hidden /> Correcta
                        </span>
                      ) : (
                        <span className="status-err" title={r.error ?? ''}>
                          <CircleX size={15} aria-hidden /> {r.status}
                          {r.error && <span className="block small muted">{r.error}</span>}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
