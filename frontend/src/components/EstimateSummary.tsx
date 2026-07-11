import React from 'react';
import styles from './EstimateSummary.module.css';

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

const formatPrice = (price: number) => {
  return `${price.toLocaleString('ru-RU')} ₽`;
};

export const EstimateSummary: React.FC<EstimateSummaryProps> = ({ summary }) => {
  return (
    <div className={styles.cards}>

      {/* Карточка 1: Материалы */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Материалы</h3>
        <div className={styles.cardBody}>
          <span>Минимум: {formatPrice(summary.materials_min)}</span>
          <span>Средняя: {formatPrice(summary.materials_avg)}</span>
          <span>Максимум: {formatPrice(summary.materials_max)}</span>
        </div>
      </div>

      {/* Карточка 2: Работы */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Работы</h3>
        <div className={styles.cardBody}>
          <span>Минимум: {formatPrice(summary.labor_min)}</span>
          <span>Средняя: {formatPrice(summary.labor_avg)}</span>
          <span>Максимум: {formatPrice(summary.labor_max)}</span>
        </div>
      </div>

      {/* Карточка 3: Итог */}
      <div className={styles.cardTotal}>
        <h3 className={styles.cardTotalTitle}>Итоговая цена</h3>
        <div className={styles.cardTotalBody}>
          <span>Минимум: <strong>{formatPrice(summary.total_min)}</strong></span>
          <span>Средняя: <strong>{formatPrice(summary.total_avg)}</strong></span>
          <span>Максимум: <strong>{formatPrice(summary.total_max)}</strong></span>
        </div>
      </div>

    </div>
  );
};
