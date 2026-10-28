import { CloudUpload, EyeOff, ShieldCheck, Trash2, UserX } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { Button, Callout, Modal } from './ui';

function PrivacyPoints() {
  return (
    <ul className="points">
      <li>
        <CloudUpload size={20} aria-hidden />
        <span>
          <strong>Tus videos salen de tu equipo.</strong> Se envían a un proveedor de inferencia externo para analizarlos con modelos de
          Meta (Muse Spark y SAM 3.1).
        </span>
      </li>
      <li>
        <UserX size={20} aria-hidden />
        <span>
          <strong>No grabes personas identificables</strong> ni información privada sin su permiso. Encuadra solo la mesa y los objetos.
        </span>
      </li>
      <li>
        <Trash2 size={20} aria-hidden />
        <span>
          <strong>Puedes borrarlo todo cuando quieras</strong> desde el menú o el pie de página («Borrar mi sesión y datos»). Las sesiones
          caducan automáticamente.
        </span>
      </li>
      <li>
        <EyeOff size={20} aria-hidden />
        <span>
          <strong>Es un prototipo de investigación.</strong> No sirve para controles críticos, de seguridad ni para evaluar a personas.
        </span>
      </li>
    </ul>
  );
}

export function ConsentModal() {
  const { consentOpen, cancelConsent, acceptConsent, consentBusy, consentError } = useApp();
  return (
    <Modal
      open={consentOpen}
      onClose={cancelConsent}
      title="Antes de subir tu primer video"
      icon={<ShieldCheck size={22} />}
      footer={
        <>
          <Button variant="secondary" onClick={cancelConsent}>
            Ahora no
          </Button>
          <Button variant="primary" busy={consentBusy} onClick={acceptConsent} data-autofocus>
            Entiendo y acepto
          </Button>
        </>
      }
    >
      <p className="lead">GhostShift necesita tu consentimiento para procesar videos. Esto es lo que ocurre con ellos:</p>
      <PrivacyPoints />
      {consentError && (
        <Callout tone="error" title="No se pudo iniciar la sesión">
          {consentError}
        </Callout>
      )}
    </Modal>
  );
}

export function PrivacyModal({ onDelete }: { onDelete: () => void }) {
  const { privacyOpen, setPrivacyOpen, sessionId } = useApp();
  return (
    <Modal
      open={privacyOpen}
      onClose={() => setPrivacyOpen(false)}
      title="Privacidad y datos"
      icon={<ShieldCheck size={22} />}
      footer={
        <>
          <Button
            variant="danger"
            icon={<Trash2 size={18} />}
            onClick={() => {
              setPrivacyOpen(false);
              onDelete();
            }}
          >
            Borrar mi sesión y datos
          </Button>
          <Button variant="primary" onClick={() => setPrivacyOpen(false)} data-autofocus>
            Entendido
          </Button>
        </>
      }
    >
      <PrivacyPoints />
      <p className="muted small">
        {sessionId ? 'Tienes una sesión activa en este navegador.' : 'Todavía no has iniciado una sesión: no hay datos tuyos en el servidor.'}
      </p>
    </Modal>
  );
}
