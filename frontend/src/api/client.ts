// Cliente tipado del contrato (docs/API_CONTRACT.md).
// Todas las llamadas van a `/api/*` (proxy de Vite → backend sin el prefijo).
// El modo mock (src/mock) solo reemplaza el transporte cuando VITE_MOCK=1.

import type {
  ApproveResponse,
  AuditEntry,
  EditableDraft,
  Procedure,
  ProcedureSummary,
  Run,
  RunSummary,
  Sample,
  SaveRulesResponse,
  Session,
} from './types';

export const API_BASE = '/api';

type Transport = (path: string, init?: RequestInit) => Promise<Response>;
type MediaResolver = (path: string) => string;

let transport: Transport = (path, init) => fetch(API_BASE + path, init);
let mediaResolver: MediaResolver = (path) => {
  if (!path) return path;
  if (/^(https?:|data:|blob:)/.test(path) || path.startsWith(API_BASE + '/')) return path;
  return API_BASE + (path.startsWith('/') ? path : '/' + path);
};

/** Solo para el modo mock. */
export function installTransport(t: Transport, m: MediaResolver): void {
  transport = t;
  mediaResolver = m;
}

/** Convierte `video_url` / `frame_url` del backend en una URL servible (antepone `/api`). */
export function mediaUrl(path: string | null | undefined): string {
  return path ? mediaResolver(path) : '';
}

export class ApiError extends Error {
  readonly status: number;
  readonly retryable: boolean;
  constructor(status: number, message: string, retryable: boolean) {
    super(message);
    this.status = status;
    this.retryable = retryable;
  }
}

function detailToMessage(detail: unknown, status: number): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  // Errores de validación de FastAPI: [{loc, msg, type}]
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean);
    if (msgs.length) return msgs.join(' · ');
  }
  if (status === 0) return 'No hay conexión con el servidor de GhostShift. Comprueba que el backend esté en marcha.';
  if (status >= 500) return 'El servidor tuvo un problema. Inténtalo de nuevo en unos segundos.';
  return `La solicitud no se pudo completar (código ${status}).`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: 'application/json' } };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
  }
  let res: Response;
  try {
    res = await transport(path, init);
  } catch {
    throw new ApiError(0, detailToMessage(null, 0), true);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const obj = (data && typeof data === 'object' ? data : {}) as { detail?: unknown; retryable?: unknown };
    // Un proxy sin backend devuelve 500/502/504 sin JSON.
    const noBackend = data === null && [500, 502, 503, 504].includes(res.status);
    throw new ApiError(
      res.status,
      noBackend ? detailToMessage(null, 0) : detailToMessage(obj.detail, res.status),
      obj.retryable === true || noBackend || res.status >= 500,
    );
  }
  return data as T;
}

const enc = encodeURIComponent;

export const api = {
  createSession: () => request<Session>('POST', '/sessions', { consent: true }),
  deleteSession: (sid: string) => request<void>('DELETE', `/sessions/${enc(sid)}`),
  listProcedures: (sid: string) => request<ProcedureSummary[]>('GET', `/sessions/${enc(sid)}/procedures`),
  audit: (sid: string) => request<AuditEntry[]>('GET', `/audit/${enc(sid)}`),
  samples: () => request<Sample[]>('GET', '/samples'),

  createProcedureFromVideo: (sid: string, name: string, video: File) => {
    const fd = new FormData();
    fd.append('name', name);
    fd.append('video', video);
    return request<{ procedure_id: string }>('POST', `/sessions/${enc(sid)}/procedures/from-video`, fd);
  },
  createProcedureFromSample: (sid: string, name: string, sampleId: string) =>
    request<{ procedure_id: string }>('POST', `/sessions/${enc(sid)}/procedures/from-sample`, {
      name,
      sample_id: sampleId,
    }),
  getProcedure: (pid: string) => request<Procedure>('GET', `/procedures/${enc(pid)}`),
  retryProcedure: (pid: string) => request<unknown>('POST', `/procedures/${enc(pid)}/retry`),
  saveRules: (pid: string, draft: EditableDraft) =>
    request<SaveRulesResponse>('PUT', `/procedures/${enc(pid)}/rules`, { draft }),
  approve: (pid: string) => request<ApproveResponse>('POST', `/procedures/${enc(pid)}/approve`),

  createRunFromVideo: (pid: string, video: File) => {
    const fd = new FormData();
    fd.append('video', video);
    return request<{ run_id: string }>('POST', `/procedures/${enc(pid)}/runs/from-video`, fd);
  },
  createRunFromSample: (pid: string, sampleId: string) =>
    request<{ run_id: string }>('POST', `/procedures/${enc(pid)}/runs/from-sample`, { sample_id: sampleId }),
  getRun: (rid: string) => request<Run>('GET', `/runs/${enc(rid)}`),
  retryRun: (rid: string) => request<unknown>('POST', `/runs/${enc(rid)}/retry`),
  listRuns: (pid: string) => request<RunSummary[]>('GET', `/procedures/${enc(pid)}/runs`),
};
