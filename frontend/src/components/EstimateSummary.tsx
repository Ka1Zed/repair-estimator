import React from 'react';

// 1. Описываем тип данных, которые придут с бэкенда (из контракта С1)
export interface SummaryData {
  materials_min: number;
  materials_avg: number;
  materials_max: number;
  labor_min: number;
  labor_avg: number;
  labor_max: number;
  total_min: number;
  total_avg: number;
  total_max: number;
}

interface EstimateSummaryProps {
  summary: SummaryData;
}

// 2. Функция для правильного отображения денег
const formatPrice = (price: number) => {
  return `${price.toLocaleString('ru-RU')} ₽`;
};

// 3. Сам компонент
export const EstimateSummary: React.FC<EstimateSummaryProps> = ({ summary }) => {
  return (
    <div style={{ display: 'flex', gap: '20px', marginTop: '20px', marginBottom: '20px' }}>
      
      {/* Карточка 1: Материалы */}
      <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', flex: 1 }}>
        <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '18px' }}>Материалы</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '14px' }}>
          <span>Минимум: {formatPrice(summary.materials_min)}</span>
          <span>Средняя: {formatPrice(summary.materials_avg)}</span>
          <span>Максимум: {formatPrice(summary.materials_max)}</span>
        </div>
      </div>

      {/* Карточка 2: Работы */}
      <div style={{ border: '1px solid #ccc', padding: '16px', borderRadius: '8px', flex: 1 }}>
        <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '18px' }}>Работы</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '14px' }}>
          <span>Минимум: {formatPrice(summary.labor_min)}</span>
          <span>Средняя: {formatPrice(summary.labor_avg)}</span>
          <span>Максимум: {formatPrice(summary.labor_max)}</span>
        </div>
      </div>

      {/* Карточка 3: Итог (Выделена цветом и жирным шрифтом) */}
      <div style={{ border: '2px solid #007bff', padding: '16px', borderRadius: '8px', flex: 1, backgroundColor: '#f8f9fa' }}>
        <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '18px', color: '#007bff' }}>Итоговая цена</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '15px' }}>
          <span>Минимум: <strong>{formatPrice(summary.total_min)}</strong></span>
          <span>Средняя: <strong>{formatPrice(summary.total_avg)}</strong></span>
          <span>Максимум: <strong>{formatPrice(summary.total_max)}</strong></span>
        </div>
      </div>

    </div>
  );
};