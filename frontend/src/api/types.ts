// Tipos del contrato docs/API_CONTRACT.md. Mantener 1:1 con el backend.

export type ProcedureStatus = 'analyzing' | 'ready' | 'failed' | 'approved';
export type StageState = 'pending' | 'running' | 'done' | 'failed';
export type JobStatus = 'running' | 'done' | 'failed';
export type Verdict = 'PASS' | 'FAIL' | 'REVIEW';
export type RuleVerdict = Verdict | 'SKIPPED';

export interface Session {
  session_id: string;
  expires_at: string;
}

export interface ProcedureSummary {
  procedure_id: string;
  name: string;
  status: ProcedureStatus;
  version: number;
  created_at: string;
  n_rules: number;
}

export interface AuditEntry {
  id: string | number;
  kind: 'muse' | 'sam';
  model_version: string;
  request_id: string | null;
  latency_ms: number | null;
  status: string;
  error: string | null;
  created_at: string;
}

export interface Sample {
  id: string;
  kind: 'reference' | 'run';
  title_es: string;
  description_es: string;
  video_url: string;
  expected: Verdict | null;
}

export interface Stage {
  id: string;
  label: string;
  state: StageState;
  detail: string | null;
}

export interface JobError {
  message: string;
  retryable: boolean;
}

export interface DraftObject {
  id: string;
  /** Nombre en español para el usuario. */
  description: string;
  /** Frase corta en inglés con la que SAM 3.1 busca el objeto. */
  sam_prompt: string;
  confirmed_by_user: boolean;
}

export type ZoneRole = 'workspace' | 'target' | 'staging';
export type Point = [number, number];

export interface Zone {
  id: string;
  role: ZoneRole;
  label: string;
  polygon: Point[];
}

export type RuleType = 'present_in_zone' | 'in_zone_at' | 'before' | 'stacked_on';
export type RuleOrigin = 'proposed' | 'user' | 'hypothesis';

export interface Rule {
  id: string;
  type: RuleType;
  enabled: boolean;
  origin: RuleOrigin;
  text_es: string;
  object?: string | null;
  zone?: string | null;
  at?: 'end' | 'during' | null;
  first?: string | null;
  second?: string | null;
  /** stacked_on: `object` debe quedar directamente encima de `base` al terminar. */
  base?: string | null;
}

export interface TimelineEvent {
  kind: 'place' | 'remove';
  object: string;
  zone: string;
  t_ms: number;
  confidence: 'sam_confirmed' | 'muse_only';
}

export interface Draft {
  version: number;
  approved: boolean;
  objects: DraftObject[];
  zones: Zone[];
  rules: Rule[];
  timeline: TimelineEvent[];
  uncertainties: string[];
}

export interface Procedure {
  procedure_id: string;
  name: string;
  status: ProcedureStatus;
  version: number;
  video_url: string;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  analysis: {
    status: JobStatus;
    stages: Stage[];
    error: JobError | null;
  };
  draft: Draft | null;
}

export interface EditableDraft {
  objects: DraftObject[];
  zones: Zone[];
  rules: Rule[];
}

export interface SaveRulesResponse {
  procedure_id: string;
  version: number;
  status: 'draft';
}

export interface ApproveResponse {
  procedure_id: string;
  version: number;
  status: 'approved';
  content_hash: string;
}

export interface Evidence {
  kind: 'event' | 'state' | 'absence_probe';
  obj: string | null;
  t_ms: number;
  frame: number | null;
  detail: string | null;
  frame_url: string | null;
}

export interface RuleResult {
  rule_id: string;
  text_es: string;
  verdict: RuleVerdict;
  reason: string;
  reason_es: string;
  evidence: Evidence[];
  missing: string[];
}

export interface ObservedEvent {
  kind: 'place' | 'remove' | string;
  obj: string;
  zone: string;
  t_lo: number;
  t_hi: number;
  timing_uncertain: boolean;
}

export type CameraStatus = 'ALIGNED' | 'RECALIBRATED' | 'UNCHECKED' | 'INCOMPATIBLE';

/** Aviso de cámara: lo observa el registro de OpenCV; el motor decide con él. */
export interface CameraInfo {
  status: CameraStatus | string;
  message_es: string;
  aligned_to_reference: boolean;
  /** Desplazamiento máximo del encuadre dentro del clip (fracción de la diagonal). */
  max_shift: number | null;
  /** Fracción de fotogramas que se pudieron alinear con la mesa. */
  registered_ratio: number | null;
  /** Desplazamiento respecto a la referencia (fracción de la diagonal). */
  reference_shift: number | null;
  warning: boolean;
}

export interface Report {
  verdict: Verdict;
  camera_status: CameraStatus | string;
  camera?: CameraInfo | null;
  blocking_issues: string[];
  rules: RuleResult[];
  events: ObservedEvent[];
}

export interface Run {
  run_id: string;
  procedure_id: string;
  procedure_version: number;
  status: JobStatus;
  stages: Stage[];
  error: JobError | null;
  video_url: string;
  duration_ms: number | null;
  report: Report | null;
}

export interface RunSummary {
  run_id: string;
  status: JobStatus;
  verdict: Verdict | null;
  created_at: string;
}
