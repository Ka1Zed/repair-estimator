import React, { useEffect } from 'react';
import { Layout } from './components/Layout/Layout';
import { EstimateResult } from './pages/EstimateResult/EstimateResult';
import { apiClient } from './api/client';

function App() {
  useEffect(() => {
    // Проверяем статус бэкенда в фоновом режиме при загрузке страницы
    apiClient.checkHealth()
      .then(data => console.log('Бэкенд доступен:', data))
      .catch(err => console.log('Бэкенд пока не запущен, используем mock-данные. Ошибка:', err.message));
  }, []);

  return (
    <Layout>
      <EstimateResult />
    </Layout>
  );
}

export default App;