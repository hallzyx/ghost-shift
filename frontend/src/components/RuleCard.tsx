import { useId, useState } from 'react';
import { ArrowDownUp, ChevronDown, ListOrdered, MapPin, Pencil, Trash2, TriangleAlert } from 'lucide-react';
import type { DraftObject, Rule, Zone } from '../api/types';
import { objName, refObject, ruleText } from '../lib/rules';
import { textOn } from '../lib/format';
import { OriginBadge } from './brand';
import { Badge, Toggle } from './ui';

const TYPE_META = {
  before: { label: 'Orden', Icon: ListOrdered },
  present_in_zone: { label: 'Posición', Icon: MapPin },
  in_zone_at: { label: 'Posición', Icon: MapPin },
} as const;

interface Props {
  rule: Rule;
  objects: DraftObject[];
  zones: Zone[];
  objectColors: Record<string, string>;
  issue?: string;
  onChange: (r: Rule) => void;
  onRemove?: () => void;
  onFocusZone?: (zoneId: string | null) => void;
  defaultOpen?: boolean;
}

export function RuleCard({ rule, objects, zones, objectColors, issue, onChange, onRemove, onFocusZone, defaultOpen }: Props) {
  const [open, setOpen] = useState(!!defaultOpen);
  const uid = useId();
  const meta = TYPE_META[rule.type] ?? TYPE_META.present_in_zone;
  const hyp = rule.origin === 'hypothesis';

  const edit = (patch: Partial<Rule>) => {
    const next: Rule = { ...rule, ...patch, origin: 'user' };
    next.text_es = ruleText(next, objects, zones);
    onChange(next);
  };

  const first = refObject(rule.first);
  const second = refObject(rule.second);
  const objOptions = objects.map((o) => (
    <option key={o.id} value={o.id}>
      {o.id} · {o.description}
    </option>
  ));

  return (
    <article
      id={`rule-${rule.id}`}
      className={`rule${rule.enabled ? '' : ' is-off'}${hyp ? ' is-hyp' : ''}${issue ? ' has-issue' : ''}`}
      onMouseEnter={() => rule.zone && onFocusZone?.(rule.zone)}
      onMouseLeave={() => onFocusZone?.(null)}
    >
      <div className="rule__main">
        <span className={`rule__type rule__type--${rule.type === 'before' ? 'order' : 'zone'}`} aria-hidden>
          <meta.Icon size={18} />
        </span>
        <div className="rule__body">
          <div className="rule__badges">
            <span className="rule__id mono">{rule.id}</span>
            <Badge tone="neutral">{meta.label}</Badge>
            <OriginBadge origin={rule.origin} />
          </div>
          <p className="rule__text" id={`${uid}-t`}>
            {rule.text_es}
          </p>
          {rule.type === 'before' && (
            <p className="rule__chips" aria-hidden>
              <span className="obj-chip" style={{ background: objectColors[first], color: textOn(objectColors[first] ?? '') }}>{first}</span>
              <span className="muted">antes que</span>
              <span className="obj-chip" style={{ background: objectColors[second], color: textOn(objectColors[second] ?? '') }}>{second}</span>
            </p>
          )}
          {hyp && (
            <p className="rule__note">
              <TriangleAlert size={14} aria-hidden /> SAM 3.1 no la respaldó en el video. Actívala solo si sabes que forma parte de la norma.
            </p>
          )}
          {!rule.enabled && !hyp && <p className="rule__off-note">Desactivada · no se comprobará</p>}
          {issue && (
            <p className="rule__issue" role="alert">
              <TriangleAlert size={14} aria-hidden /> {issue}
            </p>
          )}
        </div>
        <div className="rule__toggle">
          <Toggle
            checked={rule.enabled}
            onChange={(v) => onChange({ ...rule, enabled: v })}
            label={`${rule.enabled ? 'Desactivar' : 'Activar'} regla ${rule.id}`}
            describedBy={`${uid}-t`}
          />
          <span className="rule__toggle-label" aria-hidden>
            {rule.enabled ? 'Activa' : 'Inactiva'}
          </span>
        </div>
      </div>

      <div className="rule__foot">
        <button type="button" className="link-btn rule__edit" aria-expanded={open} aria-controls={`${uid}-ed`} onClick={() => setOpen((v) => !v)}>
          <Pencil size={14} aria-hidden /> {open ? 'Cerrar edición' : 'Editar'}
          <ChevronDown size={14} className={`chev${open ? ' is-open' : ''}`} aria-hidden />
        </button>
        {onRemove && (
          <button type="button" className="link-btn link-btn--danger" onClick={onRemove}>
            <Trash2 size={14} aria-hidden /> Eliminar
          </button>
        )}
      </div>

      {open && (
        <div className="rule__editor" id={`${uid}-ed`}>
          {rule.type === 'before' ? (
            <div className="order-editor">
              <label className="mini-field">
                <span>Primero</span>
                <select className="select" value={first} onChange={(e) => edit({ first: `place:${e.target.value}` })}>
                  {objOptions}
                </select>
              </label>
              <button
                type="button"
                className="icon-btn icon-btn--filled order-editor__swap"
                aria-label="Intercambiar orden"
                title="Intercambiar orden"
                onClick={() => edit({ first: rule.second, second: rule.first })}
              >
                <ArrowDownUp size={18} />
              </button>
              <label className="mini-field">
                <span>Después</span>
                <select className="select" value={second} onChange={(e) => edit({ second: `place:${e.target.value}` })}>
                  {objOptions}
                </select>
              </label>
              <p className="mini-hint">
                «{objName(objects, first)}» se debe colocar antes que «{objName(objects, second)}».
              </p>
            </div>
          ) : (
            <div className="zone-editor">
              <label className="mini-field">
                <span>Objeto</span>
                <select className="select" value={rule.object ?? ''} onChange={(e) => edit({ object: e.target.value })}>
                  {objOptions}
                </select>
              </label>
              <label className="mini-field">
                <span>Zona</span>
                <select className="select" value={rule.zone ?? ''} onChange={(e) => edit({ zone: e.target.value })}>
                  {zones.map((z) => (
                    <option key={z.id} value={z.id}>
                      {z.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="mini-field">
                <span>Cuándo</span>
                <select className="select" value={rule.at ?? 'end'} onChange={(e) => edit({ at: e.target.value as 'end' | 'during' })}>
                  <option value="end">Al finalizar</option>
                  <option value="during">Durante la ejecución</option>
                </select>
              </label>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
