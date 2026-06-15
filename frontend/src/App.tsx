import React, { useEffect, useState } from 'react';
import { Layout } from './components/Layout/Layout';
import { EstimateResult } from './pages/EstimateResult/EstimateResult';
import { apiClient } from './api/client';
import ProjectCreatePage from './pages/ProjectCreatePage';

function App() {
  const [page, setPage] = useState<'editor' | 'estimate'>('editor');

  useEffect(() => {
    apiClient.checkHealth()
      .then((data) => console.log('Бэкенд доступен:', data))
      .catch((err) => console.log('Бэкенд пока не запущен, используем mock-данные:', err.message));
  }, []);

  return (
    <Layout>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        <button onClick={() => setPage('editor')}>Редактор помещения</button>
        <button onClick={() => setPage('estimate')}>Смета</button>
      </div>
      
      {page === 'editor' ? (
        <div style={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
          <ProjectCreatePage />
        </div>
      ) : (
        <EstimateResult />
      )}
    </Layout>
  );
}

export default App;