import { useEffect, useState } from 'react';
import { Layout } from './components/Layout/Layout';
import { Workspace } from './pages/Workspace/Workspace';
import { apiClient } from './api/client';

function App() {
  const [isBackendDown, setIsBackendDown] = useState(false);

  useEffect(() => {
    apiClient.checkHealth()
      .then(() => setIsBackendDown(false))
      .catch(() => setIsBackendDown(true));
  }, []);

  return (
    <Layout>
      {isBackendDown && (
        <div style={{
          backgroundColor: '#fee2e2',
          color: '#991b1b',
          padding: '8px 16px',
          textAlign: 'center',
          fontSize: '13px',
          borderBottom: '1px solid #f87171'
        }}>
          Внимание: бэкенд недоступен. Расчет сметы временно не работает.
        </div>
      )}
      <Workspace />
    </Layout>
  );
}

export default App;