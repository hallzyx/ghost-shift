import { useId } from 'react';
import { CircleCheck, CircleDashed, Search } from 'lucide-react';
import type { DraftObject } from '../api/types';
import { textOn } from '../lib/format';

export function ObjectCard({
  object,
  color,
  onChange,
  issue,
}: {
  object: DraftObject;
  color: string;
  onChange: (o: DraftObject) => void;
  issue?: string;
}) {
  const id = useId();
  return (
    <div className={`objcard${issue ? ' has-issue' : ''}`} id={`obj-${object.id}`}>
      <div className="objcard__row">
        <span className="objcard__swatch" style={{ background: color, color: textOn(color) }} aria-hidden>
          {object.id}
        </span>
        <div className="objcard__name">
          <label htmlFor={`${id}-d`} className="sr-only">
            Nombre del objeto {object.id}
          </label>
          <input
            id={`${id}-d`}
            className="input input--inline"
            value={object.description}
            maxLength={60}
            placeholder="Nombre, p. ej. Cuadrado azul"
            onChange={(e) => onChange({ ...object, description: e.target.value, confirmed_by_user: true })}
          />
        </div>
        {object.confirmed_by_user ? (
          <span className="objcard__state is-ok" title="Confirmado por ti">
            <CircleCheck size={16} aria-hidden /> <span className="objcard__state-text">Confirmado</span>
          </span>
        ) : (
          <button type="button" className="btn btn--tint btn--sm" onClick={() => onChange({ ...object, confirmed_by_user: true })}>
            <CircleDashed size={15} aria-hidden /> <span>Confirmar</span>
          </button>
        )}
      </div>
      <details className="objcard__adv">
        <summary>
          <Search size={14} aria-hidden /> Cómo lo busca la IA
          <span className="objcard__prompt mono">{object.sam_prompt || 'sin definir'}</span>
        </summary>
        <div className="objcard__adv-body">
          <label htmlFor={`${id}-p`} className="field__label">
            Frase de búsqueda para SAM 3.1
          </label>
          <input
            id={`${id}-p`}
            className="input"
            lang="en"
            value={object.sam_prompt}
            maxLength={40}
            placeholder="blue square"
            aria-describedby={`${id}-ph`}
            onChange={(e) => onChange({ ...object, sam_prompt: e.target.value, confirmed_by_user: true })}
          />
          <p className="field__hint" id={`${id}-ph`}>
            Escríbelo en inglés, 2–3 palabras: color + forma (p. ej. «blue square»). SAM 3.1 solo entiende inglés y usa esta frase para
            encontrar el objeto en cada video.
          </p>
        </div>
      </details>
      {issue && <p className="rule__issue">{issue}</p>}
    </div>
  );
}
