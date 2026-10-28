import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBlocker, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  CircleDot,
  Eye,
  FlaskConical,
  ListOrdered,
  MapPin,
  MousePointer2,
  PenSquare,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Undo2,
} from 'lucide-react';
import { api, ApiError, mediaUrl } from '../api/client';
import type { DraftObject, EditableDraft, Point, Procedure, Rule, Zone } from '../api/types';
import { useApp, useFlowStep } from '../context/AppContext';
import { ObjectCard } from '../components/ObjectCard';
import { RuleCard } from '../components/RuleCard';
import { VideoPlayer, type Marker, type VideoHandle } from '../components/VideoPlayer';
import { ZoneOverlay } from '../components/ZoneOverlay';
import { Badge, Button, Callout, Card, InfoTip, Modal, PageHeader } from '../components/ui';
import { formatMs, objectColorMap, ZONE_COLORS } from '../lib/format';
import { nextRuleId, objName, refObject, ruleText, validateDraft, zoneName, type DraftIssue } from '../lib/rules';

const ROLE_LABEL: Record<string, string> = { workspace: 'Área de trabajo', target: 'Destino', staging: 'Origen' };

function snapshot(d: EditableDraft): string {
  return JSON.stringify({ objects: d.objects, zones: d.zones, rules: d.rules });
}

export function RuleStudio({ proc, onSaved }: { proc: Procedure; onSaved: (p: Procedure) => void; reload: () => void }) {
  useFlowStep(2);
  const draft = proc.draft!;
  const navigate = useNavigate();
  const { toast } = useApp();
  const player = useRef<VideoHandle>(null);

  const [objects, setObjects] = useState<DraftObject[]>(draft.objects);
  const [zones, setZones] = useState<Zone[]>(draft.zones);
  const [rules, setRules] = useState<Rule[]>(draft.rules);
  const [baseline, setBaseline] = useState(() => snapshot(draft));
  const [editZones, setEditZones] = useState(false);
  const [selZone, setSelZone] = useState<string | null>(null);
  const [hoverZone, setHoverZone] = useState<string | null>(null);
  const [issues, setIssues] = useState<DraftIssue[]>([]);
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const leaving = useRef(false);

  // Si llega una versión nueva desde el servidor, reiniciar el editor.
  useEffect(() => {
    setObjects(draft.objects);
    setZones(draft.zones);
    setRules(draft.rules);
    setBaseline(snapshot(draft));
  }, [proc.version, draft]);

  const current = useMemo(() => snapshot({ objects, zones, rules }), [objects, zones, rules]);
  const dirty = current !== baseline;
  const approved = draft.approved || proc.status === 'approved';

  // Avisos al salir con cambios sin guardar
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname);

  const objColors = useMemo(() => objectColorMap(objects), [objects]);
  const zoneColors = useMemo(
    () => Object.fromEntries(zones.map((z, i) => [z.id, ZONE_COLORS[i % ZONE_COLORS.length] ?? '#0866FF'])),
    [zones],
  );

  const markers: Marker[] = draft.timeline.map((ev, i) => ({
    id: `ev${i}`,
    t_ms: ev.t_ms,
    color: objColors[ev.object] ?? '#0866FF',
    variant: ev.confidence === 'muse_only' ? 'hollow' : 'solid',
    label: `${objName(objects, ev.object)} ${ev.kind === 'place' ? 'colocado en' : 'retirado de'} ${zoneName(zones, ev.zone)}${ev.confidence === 'muse_only' ? ' (solo Muse Spark)' : ''}`,
  }));

  const issueByRule = useMemo(() => {
    const m: Record<string, string> = {};
    for (const i of issues) if (i.ruleId && !m[i.ruleId]) m[i.ruleId] = i.message;
    return m;
  }, [issues]);
  const issueByObj = useMemo(() => {
    const m: Record<string, string> = {};
    for (const i of issues) if (i.objectId && !m[i.objectId]) m[i.objectId] = i.message;
    return m;
  }, [issues]);

  // Re-validar en vivo una vez que el usuario ya intentó guardar
  useEffect(() => {
    if (issues.length) setIssues(validateDraft(objects, zones, rules));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [objects, zones, rules]);

  const updateObject = (o: DraftObject) => {
    const nextObjs = objects.map((x) => (x.id === o.id ? o : x));
    setObjects(nextObjs);
    // Mantener los textos de las reglas coherentes con el nombre nuevo
    const prev = objects.find((x) => x.id === o.id);
    if (prev && prev.description !== o.description) {
      setRules((rs) =>
        rs.map((r) => {
          const uses = r.object === o.id || refObject(r.first) === o.id || refObject(r.second) === o.id;
          return uses ? { ...r, text_es: ruleText(r, nextObjs, zones) } : r;
        }),
      );
    }
  };

  const updateZone = useCallback((id: string, polygon: Point[]) => {
    setZones((zs) => zs.map((z) => (z.id === id ? { ...z, polygon } : z)));
  }, []);

  const updateRule = (r: Rule) => setRules((rs) => rs.map((x) => (x.id === r.id ? r : x)));

  const addRule = (type: 'before' | 'present_in_zone') => {
    const id = nextRuleId(rules);
    const base: Rule =
      type === 'before'
        ? { id, type, enabled: true, origin: 'user', text_es: '', first: `place:${objects[0]?.id ?? 'A'}`, second: `place:${objects[1]?.id ?? objects[0]?.id ?? 'B'}` }
        : { id, type, enabled: true, origin: 'user', text_es: '', object: objects[0]?.id ?? null, zone: zones.find((z) => z.role === 'target')?.id ?? zones[0]?.id ?? null, at: 'end' };
    base.text_es = ruleText(base, objects, zones);
    setRules((rs) => [...rs, base]);
    window.setTimeout(() => document.getElementById(`rule-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
  };

  const discard = () => {
    setObjects(draft.objects);
    setZones(draft.zones);
    setRules(draft.rules);
    setIssues([]);
    setServerError(null);
  };

  const save = async () => {
    setServerError(null);
    const found = validateDraft(objects, zones, rules);
    setIssues(found);
    if (found.length) {
      const first = found[0]!;
      const el = document.getElementById(first.ruleId ? `rule-${first.ruleId}` : first.objectId ? `obj-${first.objectId}` : 'studio-issues');
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setSaving(true);
    let saved = false;
    try {
      if (dirty || !approved) {
        await api.saveRules(proc.procedure_id, { objects, zones, rules });
        saved = true;
      }
      const res = await api.approve(proc.procedure_id);
      leaving.current = true;
      setBaseline(current);
      toast(`Procedimiento aprobado (versión ${res.version}). Ya puedes verificar ejecuciones.`);
      try {
        onSaved(await api.getProcedure(proc.procedure_id));
      } catch {
        /* no crítico */
      }
      navigate(`/procedimientos/${proc.procedure_id}/verificar`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setServerError(saved ? `Se guardaron los cambios, pero no se pudo aprobar: ${msg}` : msg);
      document.getElementById('studio-issues')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } finally {
      setSaving(false);
    }
  };

  const active = rules.filter((r) => r.enabled).length;
  const mainRules = rules.filter((r) => r.origin !== 'hypothesis');
  const hypRules = rules.filter((r) => r.origin === 'hypothesis');

  const renderRule = (r: Rule) => (
    <RuleCard
      key={r.id}
      rule={r}
      objects={objects}
      zones={zones}
      objectColors={objColors}
      issue={issueByRule[r.id]}
      onChange={updateRule}
      onRemove={r.origin === 'user' && !draft.rules.some((d) => d.id === r.id) ? () => setRules((rs) => rs.filter((x) => x.id !== r.id)) : undefined}
      onFocusZone={setHoverZone}
    />
  );

  return (
    <div className="page page--studio">
      <PageHeader
        eyebrow="Paso 2 · Revisar reglas"
        title={proc.name}
        subtitle={
          <>
            <Sparkles size={15} aria-hidden className="inline-icon" /> La IA propone; <strong>tú decides la norma</strong>. Activa lo que deba cumplirse
            siempre y corrige lo que no esté bien.
          </>
        }
        actions={
          <div className="row gap-2">
            <Badge tone={approved ? 'green' : 'neutral'} icon={approved ? <ShieldCheck size={14} aria-hidden /> : <PenSquare size={14} aria-hidden />}>
              {approved ? `Versión ${draft.version} aprobada` : `Borrador · versión ${draft.version}`}
            </Badge>
          </div>
        }
      />

      {approved && dirty && (
        <Callout tone="warning" title={`Guardar creará la versión ${draft.version + 1}`}>
          La versión {draft.version} ya está aprobada. Tus cambios se guardarán como una versión nueva que tendrás que aprobar; los resultados anteriores
          seguirán ligados a la versión {draft.version}.
        </Callout>
      )}

      <div className="studio">
        {/* Columna izquierda: video + objetos */}
        <div className="studio__left">
          <Card className="studio__video">
            <div className="card-head">
              <h2 className="h-sm">Video de referencia</h2>
              <div className="row gap-2">
                <InfoTip label="una zona">
                  Una <strong>zona</strong> es un área de la mesa donde debe estar un objeto. Puedes moverla o cambiar su forma si la IA no la dibujó bien.
                </InfoTip>
                <Button
                  size="sm"
                  variant={editZones ? 'tint' : 'secondary'}
                  icon={<MousePointer2 size={16} />}
                  aria-pressed={editZones}
                  onClick={() => {
                    setEditZones((v) => !v);
                    setSelZone(editZones ? null : (zones.find((z) => z.role === 'target')?.id ?? zones[0]?.id ?? null));
                  }}
                >
                  {editZones ? 'Terminar edición' : 'Editar zonas'}
                </Button>
              </div>
            </div>
            <VideoPlayer
              ref={player}
              src={mediaUrl(proc.video_url)}
              durationMs={proc.duration_ms}
              aspect={proc.width && proc.height ? proc.width / proc.height : null}
              markers={markers}
              label="Video de referencia con zonas y eventos"
              overlayInteractive={editZones}
              overlay={
                <ZoneOverlay
                  zones={zones}
                  colors={zoneColors}
                  editable={editZones}
                  selectedId={selZone}
                  highlightId={hoverZone}
                  onSelect={setSelZone}
                  onChange={updateZone}
                />
              }
            />
            {editZones && (
              <p className="hint-bar" role="status">
                <MousePointer2 size={15} aria-hidden /> Arrastra una zona para moverla y sus puntos blancos para cambiar la forma. Con teclado: tabula hasta un punto y usa las flechas.
              </p>
            )}
            <div className="zone-legend" role="group" aria-label="Zonas">
              {zones.map((z) => (
                <button
                  key={z.id}
                  type="button"
                  className={`zone-chip${selZone === z.id ? ' is-on' : ''}`}
                  style={{ ['--zc' as string]: zoneColors[z.id] }}
                  onClick={() => {
                    setEditZones(true);
                    setSelZone(z.id);
                  }}
                  onMouseEnter={() => setHoverZone(z.id)}
                  onMouseLeave={() => setHoverZone(null)}
                  aria-label={`${z.label} (${ROLE_LABEL[z.role] ?? z.role}). Editar zona`}
                >
                  <span className="zone-chip__sw" aria-hidden />
                  {z.label}
                  <span className="zone-chip__role">{ROLE_LABEL[z.role] ?? z.role}</span>
                </button>
              ))}
            </div>

            <div className="events">
              <div className="events__head">
                <h3 className="h-xs">Lo que ocurrió en el video</h3>
                <span className="events__legend">
                  <span className="lg-dot lg-dot--solid" aria-hidden /> confirmado por SAM 3.1
                  <span className="lg-dot lg-dot--hollow" aria-hidden /> solo Muse Spark
                </span>
              </div>
              {draft.timeline.length === 0 ? (
                <p className="muted small">No se detectaron eventos de colocación.</p>
              ) : (
                <ol className="events__list">
                  {draft.timeline.map((ev, i) => (
                    <li key={i}>
                      <button type="button" className="event-row" onClick={() => player.current?.seek(ev.t_ms)}>
                        <span className="mono event-row__t">{formatMs(ev.t_ms)}</span>
                        <span className={`lg-dot lg-dot--${ev.confidence === 'muse_only' ? 'hollow' : 'solid'}`} style={{ ['--mc' as string]: objColors[ev.object] }} aria-hidden />
                        <span className="event-row__text">
                          <strong>{objName(objects, ev.object)}</strong> {ev.kind === 'place' ? 'se coloca en' : 'se retira de'} {zoneName(zones, ev.zone)}
                        </span>
                        {ev.confidence === 'muse_only' && <span className="sr-only">(solo Muse Spark, no confirmado por SAM)</span>}
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </Card>

        </div>

        {/* Columna derecha: reglas */}
        <div className="studio__right">
          <div id="studio-issues">
            {serverError && (
              <Callout tone="error" title="El servidor no aceptó el procedimiento">
                {serverError}
              </Callout>
            )}
            {issues.length > 0 && (
              <Callout tone="error" title={issues.length === 1 ? 'Hay 1 cosa por corregir' : `Hay ${issues.length} cosas por corregir`}>
                <ul className="issue-list">
                  {issues.map((i, k) => (
                    <li key={k}>
                      {i.ruleId || i.objectId ? (
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => document.getElementById(i.ruleId ? `rule-${i.ruleId}` : `obj-${i.objectId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
                        >
                          {i.message}
                        </button>
                      ) : (
                        i.message
                      )}
                    </li>
                  ))}
                </ul>
              </Callout>
            )}
          </div>

          <Card>
            <div className="card-head">
              <h2 className="h-sm">Objetos</h2>
              <span className="muted small">Confirma que la IA los identificó bien</span>
            </div>
            <div className="stack gap-2">
              {objects.map((o) => (
                <ObjectCard key={o.id} object={o} color={objColors[o.id] ?? '#0866FF'} onChange={updateObject} issue={issueByObj[o.id]} />
              ))}
            </div>
          </Card>

          <Card>
            <div className="card-head">
              <div>
                <h2 className="h-sm">Reglas</h2>
                <p className="muted small">
                  {active} {active === 1 ? 'activa' : 'activas'} de {rules.length}. Solo las activas se comprobarán.
                </p>
              </div>
            </div>
            <div className="stack gap-3">{mainRules.map(renderRule)}</div>
            {mainRules.length === 0 && <p className="muted small">La IA no propuso reglas respaldadas. Revisa las hipótesis o añade una tuya.</p>}

            <div className="add-rule">
              <span className="muted small">Añadir una regla tuya:</span>
              <Button size="sm" icon={<ListOrdered size={16} />} onClick={() => addRule('before')} disabled={objects.length < 2}>
                Orden «A antes de B»
              </Button>
              <Button size="sm" icon={<MapPin size={16} />} onClick={() => addRule('present_in_zone')} disabled={!zones.length}>
                Posición en zona
              </Button>
            </div>
          </Card>

          {hypRules.length > 0 && (
            <Card className="hyp-card">
              <div className="card-head">
                <div>
                  <h2 className="h-sm">
                    <FlaskConical size={18} aria-hidden className="inline-icon" /> Hipótesis para revisar
                  </h2>
                  <p className="muted small">
                    Muse Spark las sugiere, pero SAM 3.1 no las vio en el video. Vienen desactivadas y no se comprobarán salvo que tú las actives.
                  </p>
                </div>
                <InfoTip label="una hipótesis">
                  Una <strong>hipótesis</strong> es una regla que el modelo de lenguaje cree probable, pero que el seguimiento visual no pudo confirmar. Puede ser un error de la IA.
                </InfoTip>
              </div>
              <div className="stack gap-3">{hypRules.map(renderRule)}</div>
            </Card>
          )}

          {draft.uncertainties.length > 0 && (
            <Card>
              <h2 className="h-sm">
                <Eye size={18} aria-hidden className="inline-icon" /> Lo que la IA no pudo confirmar
              </h2>
              <ul className="uncertain">
                {draft.uncertainties.map((u, i) => (
                  <li key={i}>
                    <TriangleAlert size={16} aria-hidden /> {u}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      {/* Barra de acción fija */}
      <div className="actionbar" role="region" aria-label="Guardar procedimiento">
        <div className="actionbar__inner">
          <p className="actionbar__status" aria-live="polite">
            {dirty ? (
              <>
                <CircleDot size={16} className="text-warn" aria-hidden /> Cambios sin guardar
              </>
            ) : approved ? (
              <>
                <ShieldCheck size={16} className="text-ok" aria-hidden /> Versión {draft.version} aprobada
              </>
            ) : (
              <>
                <CircleDot size={16} className="text-muted" aria-hidden /> Sin aprobar · {active} {active === 1 ? 'regla activa' : 'reglas activas'}
              </>
            )}
          </p>
          <div className="actionbar__btns">
            {dirty && (
              <Button variant="ghost" icon={<Undo2 size={18} />} onClick={discard}>
                Descartar
              </Button>
            )}
            {approved && !dirty ? (
              <Button variant="primary" size="lg" iconRight={<ArrowRight size={18} />} onClick={() => navigate(`/procedimientos/${proc.procedure_id}/verificar`)}>
                Continuar a verificar
              </Button>
            ) : (
              <Button variant="primary" size="lg" icon={<ShieldCheck size={20} />} onClick={save} busy={saving}>
                {approved ? `Guardar y aprobar versión ${draft.version + 1}` : 'Guardar y aprobar procedimiento'}
              </Button>
            )}
          </div>
        </div>
      </div>

      <Modal
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        size="sm"
        title="Tienes cambios sin guardar"
        icon={<TriangleAlert size={22} />}
        footer={
          <>
            <Button variant="secondary" onClick={() => blocker.proceed?.()}>
              Salir sin guardar
            </Button>
            <Button variant="primary" onClick={() => blocker.reset?.()} data-autofocus>
              Seguir editando
            </Button>
          </>
        }
      >
        <p>Si sales ahora perderás los cambios en reglas, objetos o zonas.</p>
      </Modal>
    </div>
  );
}

