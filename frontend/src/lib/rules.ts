import type { DraftObject, Rule, Zone } from '../api/types';

/** `place:A` → `A` */
export function refObject(ref: string | null | undefined): string {
  if (!ref) return '';
  const i = ref.indexOf(':');
  return i >= 0 ? ref.slice(i + 1) : ref;
}

export function objName(objects: DraftObject[], id: string | null | undefined): string {
  if (!id) return '—';
  const o = objects.find((x) => x.id === id);
  return o?.description?.trim() || `Objeto ${id}`;
}

export function zoneName(zones: Zone[], id: string | null | undefined): string {
  if (!id) return '—';
  return zones.find((z) => z.id === id)?.label || id;
}

/** Texto en español para una regla editada por el usuario (el backend puede regenerarlo).
 *  Se usan comillas en lugar de artículos para no equivocar el género del nombre. */
export function ruleText(rule: Rule, objects: DraftObject[], zones: Zone[]): string {
  const o = (id: string | null | undefined) => `«${objName(objects, id)}»`;
  const z = (id: string | null | undefined) => `«${zoneName(zones, id)}»`;
  switch (rule.type) {
    case 'before':
      return `${o(refObject(rule.first))} debe colocarse antes que ${o(refObject(rule.second))}.`;
    case 'present_in_zone':
      return rule.at === 'during'
        ? `${o(rule.object)} debe aparecer en ${z(rule.zone)} durante la ejecución.`
        : `${o(rule.object)} debe estar en ${z(rule.zone)} al finalizar.`;
    case 'in_zone_at':
      return rule.at === 'during'
        ? `${o(rule.object)} debe entrar en ${z(rule.zone)} durante la ejecución.`
        : `${o(rule.object)} debe quedar en ${z(rule.zone)} al finalizar.`;
    default:
      return rule.text_es;
  }
}

export interface DraftIssue {
  ruleId?: string;
  objectId?: string;
  message: string;
}

/** Validaciones simples en cliente (el backend vuelve a validar y responde 422). */
export function validateDraft(objects: DraftObject[], zones: Zone[], rules: Rule[]): DraftIssue[] {
  const issues: DraftIssue[] = [];
  const objIds = new Set(objects.map((x) => x.id));
  const zoneIds = new Set(zones.map((x) => x.id));

  for (const ob of objects) {
    if (!ob.description.trim()) issues.push({ objectId: ob.id, message: `El objeto ${ob.id} necesita un nombre.` });
    if (!ob.sam_prompt.trim())
      issues.push({ objectId: ob.id, message: `Falta cómo buscar el objeto ${ob.id} (descripción en inglés para SAM).` });
  }
  for (const zn of zones) {
    if (zn.polygon.length < 3) issues.push({ message: `La zona «${zn.label}» necesita al menos 3 vértices.` });
  }

  const enabled = rules.filter((r) => r.enabled);
  if (enabled.length === 0) issues.push({ message: 'Activa al menos una regla para poder aprobar el procedimiento.' });

  for (const r of enabled) {
    if (r.type === 'before') {
      const a = refObject(r.first);
      const b = refObject(r.second);
      if (!objIds.has(a) || !objIds.has(b))
        issues.push({ ruleId: r.id, message: `La regla ${r.id} usa un objeto que no existe.` });
      else if (a === b)
        issues.push({ ruleId: r.id, message: `En la regla ${r.id} el primer y el segundo objeto son el mismo. Elige dos distintos.` });
    } else {
      if (!r.object || !objIds.has(r.object))
        issues.push({ ruleId: r.id, message: `Elige un objeto para la regla ${r.id}.` });
      if (!r.zone || !zoneIds.has(r.zone)) issues.push({ ruleId: r.id, message: `Elige una zona para la regla ${r.id}.` });
    }
  }

  const cycle = findOrderCycle(enabled);
  if (cycle) {
    issues.push({
      ruleId: cycle.ruleId,
      message: `Las reglas de orden forman un círculo (${cycle.path.map((id) => objName(objects, id)).join(' → ')}). Desactiva o invierte una de ellas.`,
    });
  }
  return issues;
}

function findOrderCycle(rules: Rule[]): { path: string[]; ruleId: string } | null {
  const edges = new Map<string, { to: string; rule: string }[]>();
  for (const r of rules) {
    if (r.type !== 'before') continue;
    const a = refObject(r.first);
    const b = refObject(r.second);
    if (!a || !b || a === b) continue;
    const list = edges.get(a) ?? [];
    list.push({ to: b, rule: r.id });
    edges.set(a, list);
  }
  const state = new Map<string, 1 | 2>();
  const stack: string[] = [];
  let found: { path: string[]; ruleId: string } | null = null;
  const visit = (n: string): boolean => {
    state.set(n, 1);
    stack.push(n);
    for (const e of edges.get(n) ?? []) {
      const s = state.get(e.to);
      if (s === 1) {
        const start = stack.indexOf(e.to);
        found = { path: [...stack.slice(start), e.to], ruleId: e.rule };
        return true;
      }
      if (!s && visit(e.to)) return true;
    }
    stack.pop();
    state.set(n, 2);
    return false;
  };
  for (const n of edges.keys()) {
    if (!state.get(n) && visit(n)) break;
  }
  return found;
}

export function nextRuleId(rules: Rule[]): string {
  let n = rules.length + 1;
  const ids = new Set(rules.map((r) => r.id));
  while (ids.has(`R${n}`)) n++;
  return `R${n}`;
}
