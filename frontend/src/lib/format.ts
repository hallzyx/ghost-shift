/** 1800 → "0:01.8" */
export function formatMs(ms: number | null | undefined, precise = true): string {
  if (ms == null || !Number.isFinite(ms)) return '—';
  const total = Math.max(0, ms) / 1000;
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  if (!precise) return `${m}:${String(Math.floor(s)).padStart(2, '0')}`;
  const whole = Math.floor(s);
  const tenth = Math.floor((s - whole) * 10);
  return `${m}:${String(whole).padStart(2, '0')}.${tenth}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

export function formatBytes(n: number): string {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Paleta estable por índice de objeto (también en dark). */
export const OBJECT_COLORS = ['#0866FF', '#8B3DFF', '#00A3A3', '#E8710A', '#D6246E', '#5B6B00'];
export const ZONE_COLORS = ['#0866FF', '#8B3DFF', '#00A3A3', '#E8710A', '#D6246E', '#31A24C'];

export function colorFor(ids: string[], id: string | null | undefined, palette = OBJECT_COLORS): string {
  const i = id ? ids.indexOf(id) : -1;
  return palette[(i >= 0 ? i : 0) % palette.length] ?? '#0866FF';
}

const COLOR_WORDS: [RegExp, string][] = [
  [/\b(red|rojo|roja)\b/i, '#E4405F'],
  [/\b(blue|azul)\b/i, '#1877F2'],
  [/\b(yellow|amarillo|amarilla)\b/i, '#F5C33B'],
  [/\b(green|verde)\b/i, '#31A24C'],
  [/\b(orange|naranja)\b/i, '#F7811E'],
  [/\b(purple|violet|morado|morada|violeta)\b/i, '#8B3DFF'],
  [/\b(pink|rosa|rosado)\b/i, '#E8559D'],
  [/\b(black|negro|negra)\b/i, '#2B2D31'],
  [/\b(white|blanco|blanca)\b/i, '#F5F6F7'],
  [/\b(gr[ae]y|gris)\b/i, '#8A8D91'],
  [/\b(brown|marr[oó]n|caf[eé])\b/i, '#8B5A2B'],
];

/** Color del objeto: el que nombra su descripción (si lo hay) o uno de la paleta. */
export function objectColor(text: string, index: number): string {
  for (const [re, c] of COLOR_WORDS) if (re.test(text)) return c;
  return OBJECT_COLORS[index % OBJECT_COLORS.length] ?? '#0866FF';
}

/** Texto legible (blanco o casi negro) sobre un color de fondo hex. */
export function textOn(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return '#fff';
  const n = parseInt(m[1]!, 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  const L = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return L > 0.4 ? '#1C1E21' : '#FFFFFF';
}

export function objectColorMap(objects: { id: string; description: string; sam_prompt: string }[]): Record<string, string> {
  return Object.fromEntries(objects.map((o, i) => [o.id, objectColor(`${o.sam_prompt} ${o.description}`, i)]));
}
