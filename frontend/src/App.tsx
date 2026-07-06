import { useEffect } from 'react';
import { Layout } from './components/Layout/Layout';
import { Workspace } from './pages/Workspace/Workspace';
import { BackendBanner } from './components/BackendBanner/BackendBanner';
import { apiClient } from './api/client';
import { useBackendStatus } from './store/backendStatus';

function App() {
  const setBackendDown = useBackendStatus((s) => s.setBackendDown);

  useEffect(() => {
    apiClient.checkHealth()
      .then(() => setBackendDown(false))
      .catch(() => setBackendDown(true));
  }, [setBackendDown]);

  return (
    <Layout>
      <BackendBanner />
      <Workspace />
    </Layout>
  );
}

export default App;
