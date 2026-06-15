import React from 'react';
import { Card } from '../../components/ui/Card';
import { Table } from '../../components/ui/Table';
import { Button } from '../../components/ui/Button';
import styles from './EstimateResult.module.css';

// Mock-данные (тестовые данные расчета)
const mockResult = {
  totalCost: 145000,
  floorArea: 45,
  perimeter: 28,
  wallArea: 70,
  materials: [
    { id: 1, name: 'Шпаклевка старт (25кг)', count: '5 шт', price: 650, total: 3250 },
    { id: 2, name: 'Обои флизелиновые', count: '6 рулонов', price: 2800, total: 16800 },
    { id: 3, name: 'Линолеум полукоммерческий', count: '45 кв.м.', price: 950, total: 42750 },
    { id: 4, name: 'Краска для потолка', count: '2 банки', price: 3100, total: 6200 },
  ]
};

export function EstimateResult() {
  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <h2>Результат расчёта сметы</h2>
        <Button variant="secondary" onClick={() => window.print()}>Печать сметы</Button>
      </div>

      {/* Блок общей стоимости и параметров помещения */}
      <div className={styles.statsGrid}>
        <Card title="Общая стоимость ремонта" className={styles.totalCard}>
          <div className={styles.priceValue}>
            {mockResult.totalCost.toLocaleString('ru-RU')} ₽
          </div>
          <p className={styles.subtext}>*Расчёт выполнен на основе базовых цен материалов</p>
        </Card>

        <Card title="Характеристики помещений">
          <div className={styles.paramItem}>
            <span>Площадь пола:</span>
            <strong>{mockResult.floorArea} кв. м.</strong>
          </div>
          <div className={styles.paramItem}>
            <span>Периметр комнат:</span>
            <strong>{mockResult.perimeter} м.</strong>
          </div>
          <div className={styles.paramItem}>
            <span>Площадь стен:</span>
            <strong>{mockResult.wallArea} кв. м.</strong>
          </div>
        </Card>
      </div>

      {/* Таблица с детальным расчетом материалов */}
      <Card title="Детализация необходимых материалов" style={{ marginTop: '25px' }}>
        <Table>
          <thead>
            <tr>
              <th>Материал / Работа</th>
              <th>Количество</th>
              <th>Цена за ед.</th>
              <th>Итого</th>
            </tr>
          </thead>
          <tbody>
            {mockResult.materials.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.count}</td>
                <td>{item.price.toLocaleString('ru-RU')} ₽</td>
                <td>{item.total.toLocaleString('ru-RU')} ₽</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}