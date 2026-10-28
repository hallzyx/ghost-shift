import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/components.css';
import './styles/pages.css';
import { App } from './App';

async function boot() {
  // El modo mock solo existe con VITE_MOCK=1 (npm run dev:mock). En cualquier otro
  // build esta rama se elimina y el código de src/mock no se incluye.
  if (import.meta.env.VITE_MOCK === '1') {
    const { installMock } = await import('./mock');
    installMock();
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void boot();
