// ---------------------------------------------------------------------------
// MODO MOCK — solo se carga con VITE_MOCK=1 (`npm run dev:mock`).
// Simula el backend en el navegador respetando docs/API_CONTRACT.md para poder
// diseñar y probar la interfaz sin servidor. Nada de esto es inferencia real.
// ---------------------------------------------------------------------------
import { installTransport } from '../api/client';
import type {
  AuditEntry,
  Draft,
  Procedure,
  ProcedureStatus,
  Report,
  Rule,
  RuleResult,
  Run,
  Sample,
  Stage,
  Verdict,
} from '../api/types';
import refVideo from './assets/reference.mp4';
import swappedVideo from './assets/run_swapped.mp4';
import occludedVideo from './assets/run_occluded.mp4';
import { frameSvg, SCENARIOS, type ObjId, type Scenario } from './scene';

const LS_KEY = 'ghostshift.mock.v1';
const DURATION = 8000;

const SAMPLES: (Sample & { asset: string; scenario?: string })[] = [
  {
    id: 'ref-kit-abc',
    kind: 'reference',
    title_es: 'Kit de tres piezas A-B-C',
    description_es: 'Se colocan un cuadrado azul, uno amarillo y uno rojo, cada uno en su zona y en ese orden.',
    video_url: '/samples/ref-kit-abc/video',
    expected: null,
    asset: refVideo,
  },
  {
    id: 'run-ok',
    kind: 'run',
    title_es: 'Ejecución correcta',
    description_es: 'Mismas piezas, mismas zonas y el mismo orden.',
    video_url: '/samples/run-ok/video',
    expected: 'PASS',
    asset: refVideo,
    scenario: 'ok',
  },
  {
    id: 'run-swapped',
    kind: 'run',
    title_es: 'Orden invertido',
    description_es: 'El estado final es correcto, pero el amarillo se colocó antes que el azul.',
    video_url: '/samples/run-swapped/video',
    expected: 'FAIL',
    asset: swappedVideo,
    scenario: 'swapped',
  },
  {
    id: 'run-occluded',
    kind: 'run',
    title_es: 'Mano tapando una pieza',
    description_es: 'Una mano oculta la zona derecha al final: no se puede comprobar el cuadrado rojo.',
    video_url: '/samples/run-occluded/video',
    expected: 'REVIEW',
    asset: occludedVideo,
    scenario: 'occluded',
  },
];

interface MockProc {
  id: string;
  session: string;
  name: string;
  created: number;
  started: number;
  failOnce: boolean;
  version: number;
  approved: boolean;
  everApproved: boolean;
  draft: Draft;
  video: string; // asset o blob URL
}
interface MockRun {
  id: string;
  proc: string;
  version: number;
  created: number;
  started: number;
  scenario: string;
  video: string;
  rules: Rule[];
}
interface MockState {
  sessions: string[];
  procs: MockProc[];
  runs: MockRun[];
  audit: (AuditEntry & { session: string })[];
}

function load(): MockState {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const s = JSON.parse(raw) as MockState;
      // Las URL blob no sobreviven a una recarga
      s.procs.forEach((p) => p.video.startsWith('blob:') && (p.video = refVideo));
      s.runs.forEach((r) => r.video.startsWith('blob:') && (r.video = refVideo));
      return s;
    }
  } catch {
    /* ignore */
  }
  return { sessions: [], procs: [], runs: [], audit: [] };
}
const state = load();
const save = () => {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
};

const uid = () => crypto.randomUUID();
const iso = (t: number) => new Date(t).toISOString();

function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
const detail = (status: number, msg: string, retryable = false) => json(status, retryable ? { detail: msg, retryable } : { detail: msg });

function baseDraft(): Draft {
  return {
    version: 1,
    approved: false,
    objects: [
      { id: 'A', description: 'Cuadrado azul', sam_prompt: 'blue square', confirmed_by_user: true },
      { id: 'B', description: 'Cuadrado amarillo', sam_prompt: 'yellow square', confirmed_by_user: true },
      { id: 'C', description: 'Cuadrado rojo', sam_prompt: 'red square', confirmed_by_user: false },
    ],
    zones: [
      { id: 'z1', role: 'target', label: 'Zona izquierda', polygon: [[0.08, 0.18], [0.32, 0.18], [0.32, 0.7], [0.08, 0.7]] },
      { id: 'z2', role: 'target', label: 'Zona central', polygon: [[0.38, 0.18], [0.62, 0.18], [0.62, 0.7], [0.38, 0.7]] },
      { id: 'z3', role: 'target', label: 'Zona derecha', polygon: [[0.68, 0.18], [0.92, 0.18], [0.92, 0.7], [0.68, 0.7]] },
      { id: 'z0', role: 'staging', label: 'Bandeja de origen', polygon: [[0.02, 0.78], [0.98, 0.78], [0.98, 0.98], [0.02, 0.98]] },
    ],
    rules: [
      { id: 'R1', type: 'present_in_zone', enabled: true, origin: 'proposed', text_es: 'El cuadrado azul debe estar en la zona izquierda al finalizar.', object: 'A', zone: 'z1', at: 'end' },
      { id: 'R2', type: 'present_in_zone', enabled: true, origin: 'proposed', text_es: 'El cuadrado amarillo debe estar en la zona central al finalizar.', object: 'B', zone: 'z2', at: 'end' },
      { id: 'R3', type: 'present_in_zone', enabled: true, origin: 'proposed', text_es: 'El cuadrado rojo debe estar en la zona derecha al finalizar.', object: 'C', zone: 'z3', at: 'end' },
      { id: 'R4', type: 'before', enabled: true, origin: 'proposed', text_es: 'El cuadrado azul debe colocarse antes que el amarillo.', first: 'place:A', second: 'place:B' },
      { id: 'R5', type: 'before', enabled: false, origin: 'hypothesis', text_es: 'El cuadrado amarillo debe colocarse antes que el rojo.', first: 'place:B', second: 'place:C' },
    ],
    timeline: [
      { kind: 'place', object: 'A', zone: 'z1', t_ms: 1800, confidence: 'sam_confirmed' },
      { kind: 'place', object: 'B', zone: 'z2', t_ms: 4000, confidence: 'sam_confirmed' },
      { kind: 'place', object: 'C', zone: 'z3', t_ms: 6200, confidence: 'muse_only' },
    ],
    uncertainties: [
      'SAM 3.1 pierde el cuadrado rojo entre 5,4 s y 6,2 s; el instante exacto de su colocación no está confirmado.',
      'No es seguro si el orden entre el cuadrado amarillo y el rojo es obligatorio o casual: por eso esa regla es una hipótesis.',
      '«Cuadrado rojo» aún no está confirmado por ti: revisa que el nombre y la búsqueda sean correctos.',
    ],
  };
}

/* ---------- Etapas que avanzan con el tiempo ---------- */

const ANALYSIS_STAGES: [string, string, number][] = [
  ['validate', 'Validar video', 1200],
  ['interpret', 'Interpretar con Muse Spark', 4000],
  ['segment', 'Seguir objetos con SAM 3.1', 6500],
  ['propose', 'Proponer reglas', 7800],
];
const RUN_STAGES: [string, string, number][] = [
  ['validate', 'Validar video y encuadre', 1000],
  ['segment', 'Seguir objetos con SAM 3.1', 4200],
  ['verify', 'Comprobar reglas', 5200],
];

function stagesAt(defs: [string, string, number][], elapsed: number, failAt?: string): { stages: Stage[]; status: 'running' | 'done' | 'failed' } {
  let prevEnd = 0;
  let failed = false;
  const stages = defs.map(([id, label, end]) => {
    let st: Stage['state'];
    if (failed) st = 'pending';
    else if (failAt === id && elapsed >= prevEnd + 1500) {
      st = 'failed';
      failed = true;
    } else st = elapsed >= end && failAt !== id ? 'done' : elapsed >= prevEnd ? 'running' : 'pending';
    prevEnd = end;
    return { id, label, state: st, detail: st === 'done' ? doneDetail(id) : st === 'failed' ? 'El servicio de inferencia no respondió a tiempo.' : null };
  });
  const status = failed ? 'failed' : stages.every((s) => s.state === 'done') ? 'done' : 'running';
  return { stages, status };
}

function doneDetail(id: string): string | null {
  return (
    {
      validate: 'MP4 · 8 s · 640×360 · cámara estable',
      interpret: '3 objetos, 4 zonas y 3 eventos propuestos',
      segment: '3 objetos seguidos · 1 tramo sin confirmar',
      propose: '4 reglas respaldadas · 1 hipótesis',
      verify: 'Reglas evaluadas por el motor determinista',
    } as Record<string, string>
  )[id] ?? null;
}

function procStatus(p: MockProc): ProcedureStatus {
  const a = stagesAt(ANALYSIS_STAGES, Date.now() - p.started, p.failOnce ? 'interpret' : undefined);
  if (a.status === 'running') return 'analyzing';
  if (a.status === 'failed') return 'failed';
  return p.approved ? 'approved' : 'ready';
}

function procView(p: MockProc): Procedure {
  const a = stagesAt(ANALYSIS_STAGES, Date.now() - p.started, p.failOnce ? 'interpret' : undefined);
  return {
    procedure_id: p.id,
    name: p.name,
    status: procStatus(p),
    version: p.version,
    video_url: `/procedures/${p.id}/video`,
    duration_ms: DURATION,
    width: 640,
    height: 360,
    analysis: {
      status: a.status,
      stages: a.stages,
      error: a.status === 'failed' ? { message: 'Muse Spark no respondió a tiempo (tiempo de espera agotado). Tus datos siguen guardados.', retryable: true } : null,
    },
    draft: a.status === 'done' ? { ...p.draft, version: p.version, approved: p.approved } : null,
  };
}

/* ---------- Evaluación simulada (misma lógica que describe el PRD) ---------- */

function evaluate(run: MockRun): Report {
  const sc: Scenario = SCENARIOS[run.scenario] ?? SCENARIOS.ok!;
  const objs = state.procs.find((x) => x.id === run.proc)?.draft.objects ?? [];
  const nm = (id: string) => `«${objs.find((o) => o.id === id)?.description ?? id}»`;
  const placeOf = (o: string) => sc.moves.find((m) => m.obj === o);
  const fu = (t: number, o: string) => `/runs/${run.id}/frames/${t}.jpg?obj=${o}`;
  const results: RuleResult[] = run.rules.map((r) => {
    if (!r.enabled)
      return { rule_id: r.id, text_es: r.text_es, verdict: 'SKIPPED', reason: 'DISABLED', reason_es: 'Regla desactivada en la versión aprobada.', evidence: [], missing: [] };
    if (r.type === 'before') {
      const a = (r.first ?? '').split(':')[1] ?? '';
      const b = (r.second ?? '').split(':')[1] ?? '';
      const pa = placeOf(a);
      const pb = placeOf(b);
      if (!pa || !pb) {
        const miss = !pa ? a : b;
        return {
          rule_id: r.id,
          text_es: r.text_es,
          verdict: 'REVIEW',
          reason: 'EVENT_NOT_OBSERVED',
          reason_es: `No se observó la colocación del objeto ${nm(miss)}: algo lo tapaba. Sin ese instante no se puede comprobar el orden.`,
          evidence: [{ kind: 'absence_probe', obj: miss, t_ms: 6200, frame: 93, detail: 'Objeto no visible', frame_url: fu(6200, miss) }],
          missing: [`colocación de ${nm(miss)}`],
        };
      }
      const ok = pa.t1 < pb.t0;
      return {
        rule_id: r.id,
        text_es: r.text_es,
        verdict: ok ? 'PASS' : 'FAIL',
        reason: ok ? 'ORDER_OK' : 'ORDER_VIOLATED',
        reason_es: ok
          ? `${nm(a)} se colocó a los ${(pa.t1 / 1000).toFixed(1)} s y ${nm(b)} a los ${(pb.t1 / 1000).toFixed(1)} s.`
          : `${nm(b)} se colocó primero (${(pb.t1 / 1000).toFixed(1)} s) y ${nm(a)} después (${(pa.t1 / 1000).toFixed(1)} s). El estado final es correcto, pero el orden no.`,
        evidence: ok
          ? [{ kind: 'event', obj: a, t_ms: pa.t1, frame: Math.round(pa.t1 / 66), detail: "Colocación", frame_url: fu(pa.t1, a) }]
          : [
              { kind: 'event', obj: b, t_ms: pb.t1, frame: Math.round(pb.t1 / 66), detail: "Se colocó primero", frame_url: fu(pb.t1, b) },
              { kind: 'event', obj: a, t_ms: pa.t1, frame: Math.round(pa.t1 / 66), detail: "Se colocó después", frame_url: fu(pa.t1, a) },
            ],
        missing: [],
      };
    }
    const o = r.object ?? '';
    if (sc.occluded.includes(o as ObjId)) {
      return {
        rule_id: r.id,
        text_es: r.text_es,
        verdict: 'REVIEW',
        reason: 'OCCLUDED',
        reason_es: `Una mano tapa la zona al final del video; no se puede confirmar dónde quedó ${nm(o)}. No se asume que falte.`,
        evidence: [{ kind: 'absence_probe', obj: o, t_ms: 7500, frame: 113, detail: 'Zona tapada por una mano', frame_url: fu(7500, o) }],
        missing: [`estado final de ${nm(o)}`],
      };
    }
    const m = placeOf(o);
    const ok = !!m && m.zone === r.zone;
    return {
      rule_id: r.id,
      text_es: r.text_es,
      verdict: ok ? 'PASS' : 'FAIL',
      reason: ok ? 'IN_ZONE' : 'NOT_IN_ZONE',
      reason_es: ok ? `${nm(o)} está dentro de la zona al final del video.` : `${nm(o)} no está en la zona esperada al final del video.`,
      evidence: [{ kind: 'state', obj: o, t_ms: 7800, frame: 117, detail: ok ? 'Estado final' : 'Fuera de la zona', frame_url: fu(7800, o) }],
      missing: [],
    };
  });
  const verdict: Verdict = results.some((r) => r.verdict === 'FAIL') ? 'FAIL' : results.some((r) => r.verdict === 'REVIEW') ? 'REVIEW' : 'PASS';
  return {
    verdict,
    camera_status: 'ALIGNED',
    blocking_issues: sc.occluded.length ? ['INSUFFICIENT_OBSERVATION'] : [],
    rules: results,
    events: sc.moves.map((m) => ({ kind: 'place', obj: m.obj, zone: m.zone, t_lo: m.t0, t_hi: m.t1, timing_uncertain: false })),
  };
}

function runView(r: MockRun): Run {
  const s = stagesAt(RUN_STAGES, Date.now() - r.started);
  return {
    run_id: r.id,
    procedure_id: r.proc,
    procedure_version: r.version,
    status: s.status,
    stages: s.stages,
    error: null,
    video_url: `/runs/${r.id}/video`,
    duration_ms: DURATION,
    report: s.status === 'done' ? evaluate(r) : null,
  };
}

function addAudit(session: string, kinds: ('muse' | 'sam')[]) {
  const now = Date.now();
  kinds.forEach((k, i) =>
    state.audit.push({
      session,
      id: uid(),
      kind: k,
      model_version: k === 'muse' ? 'muse-spark-1.3 (simulado)' : 'sam-3.1 (simulado)',
      request_id: `mock-${uid().slice(0, 8)}`,
      latency_ms: k === 'muse' ? 2800 + i * 120 : 2400 + i * 90,
      status: 'ok',
      error: null,
      created_at: iso(now + i * 1000),
    }),
  );
}

function hasCycle(rules: Rule[]): boolean {
  const edges = rules.filter((r) => r.enabled && r.type === 'before').map((r) => [(r.first ?? '').split(':')[1], (r.second ?? '').split(':')[1]] as const);
  const nodes = new Set(edges.flat());
  const visit = (n: string | undefined, seen: Set<string>): boolean => {
    if (!n) return false;
    if (seen.has(n)) return true;
    seen.add(n);
    const r = edges.filter((e) => e[0] === n).some((e) => visit(e[1], new Set(seen)));
    return r;
  };
  return [...nodes].some((n) => visit(n, new Set()));
}

/* ---------- Router ---------- */

async function handle(path: string, init: RequestInit = {}): Promise<Response> {
  await new Promise((r) => setTimeout(r, 250));
  const method = (init.method ?? 'GET').toUpperCase();
  const url = new URL(path, 'http://mock');
  const p = url.pathname.split('/').filter(Boolean);
  const body = () => (typeof init.body === 'string' ? JSON.parse(init.body) : {});

  // /sessions
  if (method === 'POST' && path === '/sessions') {
    const id = uid();
    state.sessions.push(id);
    save();
    return json(201, { session_id: id, expires_at: iso(Date.now() + 86400000) });
  }
  if (p[0] === 'sessions' && p[1]) {
    const sid = p[1];
    if (!state.sessions.includes(sid)) return detail(404, 'Sesión no encontrada o caducada.');
    if (method === 'DELETE' && p.length === 2) {
      state.sessions = state.sessions.filter((s) => s !== sid);
      const pids = state.procs.filter((x) => x.session === sid).map((x) => x.id);
      state.procs = state.procs.filter((x) => x.session !== sid);
      state.runs = state.runs.filter((r) => !pids.includes(r.proc));
      state.audit = state.audit.filter((a) => a.session !== sid);
      save();
      return json(204);
    }
    if (method === 'GET' && p[2] === 'procedures') {
      return json(
        200,
        state.procs
          .filter((x) => x.session === sid)
          .sort((a, b) => b.created - a.created)
          .map((x) => ({ procedure_id: x.id, name: x.name, status: procStatus(x), version: x.version, created_at: iso(x.created), n_rules: x.draft.rules.filter((r) => r.enabled).length })),
      );
    }
    if (method === 'POST' && p[2] === 'procedures') {
      let name = '';
      let video = refVideo;
      let failOnce = false;
      if (p[3] === 'from-video') {
        const fd = init.body as FormData;
        name = String(fd.get('name') ?? '');
        const f = fd.get('video') as File | null;
        if (f) {
          video = URL.createObjectURL(f);
          failOnce = /error|fallo/i.test(f.name);
        }
      } else {
        const b = body();
        name = b.name;
        if (!SAMPLES.some((s) => s.id === b.sample_id && s.kind === 'reference')) return detail(404, 'Ejemplo no encontrado.');
      }
      if (!name.trim()) return detail(422, 'El procedimiento necesita un nombre.');
      const id = uid();
      state.procs.push({ id, session: sid, name, created: Date.now(), started: Date.now(), failOnce, version: 1, approved: false, everApproved: false, draft: baseDraft(), video });
      if (!failOnce) addAudit(sid, ['muse', 'sam', 'sam', 'sam']);
      save();
      return json(202, { procedure_id: id });
    }
  }
  if (method === 'GET' && p[0] === 'audit' && p[1]) {
    if (!state.sessions.includes(p[1])) return detail(404, 'Sesión no encontrada.');
    return json(200, state.audit.filter((a) => a.session === p[1]).map(({ session: _s, ...a }) => a));
  }
  if (method === 'GET' && path === '/samples') return json(200, SAMPLES.map(({ asset: _a, scenario: _s, ...s }) => s));

  // /procedures/{pid}
  if (p[0] === 'procedures' && p[1]) {
    const proc = state.procs.find((x) => x.id === p[1]);
    if (!proc) return detail(404, 'Procedimiento no encontrado.');
    if (method === 'GET' && p.length === 2) return json(200, procView(proc));
    if (method === 'POST' && p[2] === 'retry') {
      proc.failOnce = false;
      proc.started = Date.now();
      addAudit(proc.session, ['muse', 'sam', 'sam', 'sam']);
      save();
      return json(202, {});
    }
    if (method === 'PUT' && p[2] === 'rules') {
      const d = body().draft as Pick<Draft, 'objects' | 'zones' | 'rules'>;
      if (hasCycle(d.rules)) return detail(422, 'Las reglas de orden forman un ciclo (p. ej. A antes de B y B antes de A). Desactiva o invierte una de ellas.');
      if (proc.approved) {
        proc.version += 1;
        proc.approved = false;
      }
      proc.draft = { ...proc.draft, objects: d.objects, zones: d.zones, rules: d.rules };
      save();
      return json(200, { procedure_id: proc.id, version: proc.version, status: 'draft' });
    }
    if (method === 'POST' && p[2] === 'approve') {
      if (!proc.draft.rules.some((r) => r.enabled)) return detail(422, 'No hay ninguna regla activa.');
      proc.approved = true;
      proc.everApproved = true;
      save();
      return json(200, { procedure_id: proc.id, version: proc.version, status: 'approved', content_hash: 'mock-' + proc.version });
    }
    if (method === 'GET' && p[2] === 'runs') {
      return json(
        200,
        state.runs
          .filter((r) => r.proc === proc.id)
          .sort((a, b) => b.created - a.created)
          .map((r) => {
            const v = runView(r);
            return { run_id: r.id, status: v.status, verdict: v.report?.verdict ?? null, created_at: iso(r.created) };
          }),
      );
    }
    if (method === 'POST' && p[2] === 'runs') {
      if (!proc.approved) return detail(409, 'No hay una versión aprobada de este procedimiento.');
      let scenario = 'ok';
      let video = refVideo;
      if (p[3] === 'from-video') {
        const f = (init.body as FormData).get('video') as File | null;
        if (f) video = URL.createObjectURL(f);
      } else {
        const s = SAMPLES.find((x) => x.id === body().sample_id && x.kind === 'run');
        if (!s) return detail(404, 'Ejemplo no encontrado.');
        scenario = s.scenario ?? 'ok';
        video = s.asset;
      }
      const id = uid();
      state.runs.push({ id, proc: proc.id, version: proc.version, created: Date.now(), started: Date.now(), scenario, video, rules: proc.draft.rules });
      addAudit(proc.session, ['sam', 'sam', 'sam']);
      save();
      return json(202, { run_id: id });
    }
  }
  if (p[0] === 'runs' && p[1]) {
    const run = state.runs.find((r) => r.id === p[1]);
    if (!run) return detail(404, 'Ejecución no encontrada.');
    if (method === 'GET' && p.length === 2) return json(200, runView(run));
    if (method === 'POST' && p[2] === 'retry') {
      run.started = Date.now();
      save();
      return json(202, {});
    }
  }
  return detail(404, `Ruta simulada no encontrada: ${method} ${path}`);
}

function resolveMedia(path: string): string {
  if (/^(https?:|data:|blob:)/.test(path)) return path;
  const url = new URL(path, 'http://mock');
  const p = url.pathname.split('/').filter(Boolean);
  if (p[0] === 'samples') return SAMPLES.find((s) => s.id === p[1])?.asset ?? refVideo;
  if (p[0] === 'procedures') return state.procs.find((x) => x.id === p[1])?.video ?? refVideo;
  if (p[0] === 'runs') {
    const run = state.runs.find((r) => r.id === p[1]);
    if (p[2] === 'video') return run?.video ?? refVideo;
    if (p[2] === 'frames') {
      const t = parseInt(p[3] ?? '0', 10);
      return frameSvg(SCENARIOS[run?.scenario ?? 'ok'] ?? SCENARIOS.ok!, t, url.searchParams.get('obj'));
    }
  }
  return refVideo;
}

export function installMock(): void {
  installTransport(handle, resolveMedia);
  console.info('[GhostShift] Modo mock activo: respuestas simuladas, sin backend ni inferencia real.');
}
