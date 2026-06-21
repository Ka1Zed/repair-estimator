import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { MaterialsTable } from '../../components/EstimateTables/MaterialsTable';
import { LaborTable } from '../../components/EstimateTables/LaborTable';
import { RepairOptionsForm } from '../../components/RepairOptionsForm/RepairOptionsForm';
import styles from './EstimateResult.module.css';

// Mock-данные в формате контракта docs/api.md (materials[] / labor[]).
// Временно, пока не подключён реальный API (F2-6 / C4).
const mockMaterials = [
  { name: 'Грунтовка', quantity: 2, unit: 'л', price_avg: 450, total_avg: 900, source: 'seed', updated_at: '2026-06-17' },
  { name: 'Шпаклевка', quantity: 12, unit: 'кг', price_avg: 550, total_avg: 6600, source: 'seed', updated_at: '2026-06-17' },
  { name: 'Краска для стен', quantity: 3, unit: 'л', price_avg: 3200, total_avg: 9600, source: 'Мегастрой', updated_at: '2026-06-17' },
];

const mockLabors = [
  { service: 'Выравнивание стен', specialist: 'Штукатур', volume: 70, unit: 'м²', price_avg: 450, total_avg: 31500, source: 'seed' },
  { service: 'Грунтовка поверхностей', specialist: 'Отделочник', volume: 70, unit: 'м²', price_avg: 80, total_avg: 5600, source: 'seed' },
  { service: 'Покраска стен', specialist: 'Маляр', volume: 70, unit: 'м²', price_avg: 200, total_avg: 14000, source: 'seed' },
];

export function EstimateResult() {
  // Итог суммируем по готовым total_avg от backend (НЕ пересчитываем quantity*price)
  const matTotal = mockMaterials.reduce((acc, item) => acc + item.total_avg, 0);
  const laborTotal = mockLabors.reduce((acc, item) => acc + item.total_avg, 0);
  const totalCost = matTotal + laborTotal;

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <h2>Результат расчёта сметы</h2>
        <Button variant="secondary" onClick={() => window.print()}>Печать сметы</Button>
      </div>

      <RepairOptionsForm />

      <div className={styles.statsGrid}>
        <Card title="Общая стоимость ремонта" className={styles.totalCard}>
          <div className={styles.priceValue}>
            {totalCost.toLocaleString('ru-RU')} ₽
          </div>
          <p className={styles.subtext}>
            Материалы: {matTotal.toLocaleString('ru-RU')} ₽ | Работы: {laborTotal.toLocaleString('ru-RU')} ₽
          </p>
        </Card>

        <Card title="Характеристики помещений">
          <div className={styles.paramItem}>
            <span>Площадь пола:</span>
            <strong>45 кв. м.</strong>
          </div>
          <div className={styles.paramItem}>
            <span>Периметр комнат:</span>
            <strong>28 м.</strong>
          </div>
          <div className={styles.paramItem}>
            <span>Площадь стен:</span>
            <strong>70 кв. м.</strong>
          </div>
        </Card>
      </div>

      <Card title="Детальный расчет" style={{ marginTop: '25px' }}>
        <MaterialsTable data={mockMaterials} />
        <LaborTable data={mockLabors} />
      </Card>
    </div>
  );
}
