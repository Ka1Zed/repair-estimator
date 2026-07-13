import { useCallback, useEffect, useState } from 'react';
import { Layout } from './components/Layout/Layout';
import { Workspace } from './pages/Workspace/Workspace';
import { ProjectsPage } from './pages/ProjectsPage/ProjectsPage';
import { SharedProjectPage } from './pages/SharedProjectPage/SharedProjectPage';
import { BackendBanner } from './components/BackendBanner/BackendBanner';
import { apiClient } from './api/client';
import { useBackendStatus } from './store/backendStatus';

export type Page =
  | { type: 'workspace'; projectId?: number; shareToken?: string }
  | { type: 'projects' }
  | { type: 'share'; token: string };

export type Navigate = (page: Page) => void;

function getInitialPage(): Page {
  const path = window.location.pathname;
  const shareMatch = path.match(/^\/share\/(.+)$/);
  if (shareMatch) return { type: 'share', token: shareMatch[1] };
  if (path === '/projects') return { type: 'projects' };
  return { type: 'workspace' };
}

function pageToPath(page: Page): string {
  if (page.type === 'projects') return '/projects';
  if (page.type === 'share') return `/share/${page.token}`;
  return '/';
}

function App() {
  const [page, setPage] = useState<Page>(getInitialPage);
  const setBackendDown = useBackendStatus((s) => s.setBackendDown);

  const navigate = useCallback<Navigate>((p) => {
    history.pushState(null, '', pageToPath(p));
    setPage(p);
  }, []);

  useEffect(() => {
    apiClient.checkHealth()
      .then(() => setBackendDown(false))
      .catch(() => setBackendDown(true));
  }, [setBackendDown]);

  useEffect(() => {
    const onPop = () => setPage(getInitialPage());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  return (
    <Layout>
      <BackendBanner />
      {page.type === 'workspace' && (
        <Workspace onNavigate={navigate} projectId={page.projectId} shareToken={page.shareToken} />
      )}
      {page.type === 'projects' && <ProjectsPage onNavigate={navigate} />}
      {page.type === 'share' && <SharedProjectPage token={page.token} onNavigate={navigate} />}
    </Layout>
  );
}

export default App;
