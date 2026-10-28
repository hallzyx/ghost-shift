import { createBrowserRouter, RouterProvider, useNavigate } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { AppProvider } from './context/AppContext';
import { Layout } from './components/Layout';
import { Button, Card, EmptyState } from './components/ui';
import { HomePage } from './pages/HomePage';
import { TeachPage } from './pages/TeachPage';
import { ProcedurePage } from './pages/ProcedurePage';
import { VerifyPage } from './pages/VerifyPage';
import { RunPage } from './pages/RunPage';
import { AuditPage } from './pages/AuditPage';

function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="page">
      <Card>
        <EmptyState
          icon={<Compass size={28} />}
          title="Esta página no existe"
          action={
            <Button variant="primary" onClick={() => navigate('/')}>
              Ir a Mis procedimientos
            </Button>
          }
        />
      </Card>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <HomePage /> },
      { path: '/ensenar', element: <TeachPage /> },
      { path: '/procedimientos/:pid', element: <ProcedurePage /> },
      { path: '/procedimientos/:pid/verificar', element: <VerifyPage /> },
      { path: '/ejecuciones/:rid', element: <RunPage /> },
      { path: '/auditoria', element: <AuditPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);

export function App() {
  return (
    <AppProvider>
      <RouterProvider router={router} />
    </AppProvider>
  );
}
