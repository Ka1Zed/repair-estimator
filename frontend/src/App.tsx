import { useEffect } from 'react';
import { Layout } from './components/Layout/Layout';
import { Workspace } from './pages/Workspace/Workspace';
import { apiClient } from './api/client';

function App() {
  useEffect(() => {
    apiClient.checkHealth()
      .then((data) => console.log('Бэкенд доступен:', data))
      .catch((err) => console.log('Бэкенд пока не запущен, используем mock-данные:', err.message));
  }, []);

  return (
    <Layout>
      <Workspace />
    </Layout>
  );
}

export default App;