// Geometría de la escena sintética usada por los videos del modo mock
// (generados con ffmpeg: mesa, 3 zonas, 3 cuadrados de color). Solo para el mock.

export type ObjId = 'A' | 'B' | 'C';

export const W = 640;
export const H = 360;
export const SIZE = 52;

export const ZONE_BOXES: Record<string, [number, number, number, number]> = {
  z1: [0.08, 0.18, 0.32, 0.7],
  z2: [0.38, 0.18, 0.62, 0.7],
  z3: [0.68, 0.18, 0.92, 0.7],
};

export const START: Record<ObjId, [number, number]> = { A: [0.14, 0.86], B: [0.47, 0.86], C: [0.8, 0.86] };
export const COLORS: Record<ObjId, string> = { A: '#1877F2', B: '#F5C33B', C: '#E4405F' };

export interface Move {
  obj: ObjId;
  zone: string;
  t0: number; // ms
  t1: number;
}

export interface Scenario {
  moves: Move[];
  /** Mano que tapa una zona: [zona, desde, hasta] */
  hand?: [string, number, number];
  /** Objetos cuyo estado final no es observable */
  occluded: ObjId[];
}

export const SCENARIOS: Record<string, Scenario> = {
  ok: {
    moves: [
      { obj: 'A', zone: 'z1', t0: 1000, t1: 1800 },
      { obj: 'B', zone: 'z2', t0: 3200, t1: 4000 },
      { obj: 'C', zone: 'z3', t0: 5400, t1: 6200 },
    ],
    occluded: [],
  },
  swapped: {
    moves: [
      { obj: 'B', zone: 'z2', t0: 1000, t1: 1800 },
      { obj: 'A', zone: 'z1', t0: 3200, t1: 4000 },
      { obj: 'C', zone: 'z3', t0: 5400, t1: 6200 },
    ],
    occluded: [],
  },
  occluded: {
    moves: [
      { obj: 'A', zone: 'z1', t0: 1000, t1: 1800 },
      { obj: 'B', zone: 'z2', t0: 3200, t1: 4000 },
    ],
    hand: ['z3', 4600, 8000],
    occluded: ['C'],
  },
};

function center(zone: string): [number, number] {
  const b = ZONE_BOXES[zone] ?? [0.4, 0.4, 0.6, 0.6];
  return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
}

export function positionAt(sc: Scenario, obj: ObjId, t: number): [number, number] {
  const m = sc.moves.find((x) => x.obj === obj);
  const s = START[obj];
  if (!m) return s;
  const e = center(m.zone);
  if (t <= m.t0) return s;
  if (t >= m.t1) return e;
  const k = (t - m.t0) / (m.t1 - m.t0);
  return [s[0] + (e[0] - s[0]) * k, s[1] + (e[1] - s[1]) * k];
}

/** Fotograma de evidencia simulado (SVG) con la caja del objeto resaltada. */
export function frameSvg(sc: Scenario, t: number, focus: string | null): string {
  const objs: ObjId[] = ['A', 'B', 'C'];
  let body = `<rect width="${W}" height="${H}" fill="#BFAE92"/><rect x="10" y="10" width="${W - 20}" height="${H - 20}" fill="#D9CBB2"/>`;
  body += `<rect x="0" y="${0.78 * H}" width="${W}" height="${0.22 * H}" fill="#A89678" fill-opacity="0.35"/>`;
  for (const b of Object.values(ZONE_BOXES)) {
    body += `<rect x="${b[0] * W}" y="${b[1] * H}" width="${(b[2] - b[0]) * W}" height="${(b[3] - b[1]) * H}" fill="none" stroke="#fff" stroke-opacity="0.6" stroke-width="3"/>`;
  }
  for (const o of objs) {
    const [x, y] = positionAt(sc, o, t);
    body += `<rect x="${x * W - SIZE / 2}" y="${y * H - SIZE / 2}" width="${SIZE}" height="${SIZE}" fill="${COLORS[o]}"/>`;
  }
  if (sc.hand && t >= sc.hand[1] && t <= sc.hand[2]) {
    const b = ZONE_BOXES[sc.hand[0]]!;
    body += `<rect x="${b[0] * W - 20}" y="${b[1] * H - 10}" width="${(b[2] - b[0]) * W + 40}" height="${(b[3] - b[1]) * H + 30}" fill="#C68E6E"/>`;
  }
  if (focus && objs.includes(focus as ObjId)) {
    const [x, y] = positionAt(sc, focus as ObjId, t);
    const pad = 10;
    const bx = x * W - SIZE / 2 - pad;
    const by = y * H - SIZE / 2 - pad;
    body += `<rect x="${bx}" y="${by}" width="${SIZE + pad * 2}" height="${SIZE + pad * 2}" fill="none" stroke="#00E5FF" stroke-width="4" rx="6"/>`;
    body += `<rect x="${bx}" y="${by - 26}" width="34" height="24" rx="4" fill="#00E5FF"/><text x="${bx + 17}" y="${by - 9}" font-family="Arial" font-size="15" font-weight="700" text-anchor="middle" fill="#000">${focus}</text>`;
  }
  body += `<rect x="${W - 196}" y="${H - 34}" width="186" height="24" rx="12" fill="#000" fill-opacity="0.55"/><text x="${W - 103}" y="${H - 17}" font-family="Arial" font-size="13" text-anchor="middle" fill="#fff">Fotograma simulado (mock)</text>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${body}</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
