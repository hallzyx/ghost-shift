import { useRef, type KeyboardEvent, type PointerEvent as RPointerEvent } from 'react';
import { Move } from 'lucide-react';
import type { Point, Zone } from '../api/types';

interface Props {
  zones: Zone[];
  colors: Record<string, string>;
  editable: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onChange: (id: string, polygon: Point[]) => void;
  highlightId?: string | null;
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));
const round = (v: number) => Math.round(v * 1000) / 1000;

function centroid(poly: Point[]): Point {
  const n = poly.length || 1;
  return [poly.reduce((a, p) => a + p[0], 0) / n, poly.reduce((a, p) => a + p[1], 0) / n];
}

/** Desplaza un polígono sin salirse del cuadro. */
function translate(poly: Point[], dx: number, dy: number): Point[] {
  const xs = poly.map((p) => p[0]);
  const ys = poly.map((p) => p[1]);
  const ddx = Math.max(-Math.min(...xs), Math.min(1 - Math.max(...xs), dx));
  const ddy = Math.max(-Math.min(...ys), Math.min(1 - Math.max(...ys), dy));
  return poly.map(([x, y]) => [round(x + ddx), round(y + ddy)] as Point);
}

/**
 * Zonas dibujadas sobre el video (coordenadas normalizadas 0–1).
 * En modo edición: arrastra la zona para moverla y los vértices para cambiar su forma.
 * Con teclado: selecciona un tirador y usa las flechas (Mayús = paso grande).
 */
export function ZoneOverlay({ zones, colors, editable, selectedId, onSelect, onChange, highlightId }: Props) {
  const root = useRef<HTMLDivElement>(null);

  const startDrag = (e: RPointerEvent, zone: Zone, vertex: number | null) => {
    if (!editable) return;
    e.preventDefault();
    e.stopPropagation();
    onSelect(zone.id);
    const rect = root.current?.getBoundingClientRect();
    if (!rect) return;
    const start = { x: e.clientX, y: e.clientY };
    const orig = zone.polygon.map((p) => [...p] as Point);
    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - start.x) / rect.width;
      const dy = (ev.clientY - start.y) / rect.height;
      if (vertex === null) onChange(zone.id, translate(orig, dx, dy));
      else {
        const next = orig.map((p) => [...p] as Point);
        const base = orig[vertex]!;
        next[vertex] = [round(clamp(base[0] + dx)), round(clamp(base[1] + dy))];
        onChange(zone.id, next);
      }
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const keyMove = (e: KeyboardEvent, zone: Zone, vertex: number | null) => {
    const step = e.shiftKey ? 0.05 : 0.01;
    const d: Record<string, Point> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const v = d[e.key];
    if (!v) return;
    e.preventDefault();
    if (vertex === null) onChange(zone.id, translate(zone.polygon, v[0], v[1]));
    else {
      const next = zone.polygon.map((p) => [...p] as Point);
      const p = next[vertex]!;
      next[vertex] = [round(clamp(p[0] + v[0])), round(clamp(p[1] + v[1]))];
      onChange(zone.id, next);
    }
  };

  return (
    <div ref={root} className={`zones${editable ? ' is-editing' : ''}`} onPointerDown={() => editable && onSelect(null)}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="zones__svg" aria-hidden={!editable}>
        {zones.map((z) => {
          const c = colors[z.id] ?? '#0866FF';
          const sel = z.id === selectedId || z.id === highlightId;
          return (
            <polygon
              key={z.id}
              points={z.polygon.map(([x, y]) => `${x * 100},${y * 100}`).join(' ')}
              fill={c}
              fillOpacity={sel ? 0.26 : 0.12}
              stroke={c}
              strokeWidth={sel ? 3 : 2}
              strokeDasharray={z.role === 'staging' ? '6 4' : undefined}
              vectorEffect="non-scaling-stroke"
              className="zones__poly"
              onPointerDown={(e) => startDrag(e, z, null)}
            />
          );
        })}
      </svg>
      {zones.map((z) => {
        const c = colors[z.id] ?? '#0866FF';
        const xs = z.polygon.map((p) => p[0]);
        const ys = z.polygon.map((p) => p[1]);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        const [cx, cy] = centroid(z.polygon);
        const sel = z.id === selectedId;
        return (
          <div key={z.id}>
            <span
              className="zones__label"
              style={{ left: `${minX * 100}%`, top: `${minY * 100}%`, background: c }}
            >
              {z.label}
            </span>
            {editable && sel && (
              <>
                <button
                  type="button"
                  className="zones__move"
                  style={{ left: `${cx * 100}%`, top: `${cy * 100}%`, color: c }}
                  aria-label={`Mover ${z.label} (flechas)`}
                  onPointerDown={(e) => startDrag(e, z, null)}
                  onKeyDown={(e) => keyMove(e, z, null)}
                >
                  <Move size={16} />
                </button>
                {z.polygon.map(([x, y], i) => (
                  <button
                    type="button"
                    key={i}
                    className="zones__handle"
                    style={{ left: `${x * 100}%`, top: `${y * 100}%`, borderColor: c }}
                    aria-label={`Vértice ${i + 1} de ${z.label} (flechas para mover)`}
                    onPointerDown={(e) => startDrag(e, z, i)}
                    onKeyDown={(e) => keyMove(e, z, i)}
                  />
                ))}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
