import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { MaterialsTable } from '../../components/EstimateTables/MaterialsTable';
import { LaborTable } from '../../components/EstimateTables/LaborTable';
import styles from './EstimateResult.module.css';

// Расширенные mock-данные по требованиям задачи #12
const mockMaterials = [
  { id: 1, name: 'Грунтовка глубокого проникновения', count: 2, unit: 'канистра', price: 450 },
  { id: 2, name: 'Штукатурка гипcapitalовая (30 кг)', count: 12, unit: 'мешок', price: 550 },
  { id: 3, name: 'Краска интерьерная матовая', count: 3, unit: 'галон', price: 3200 },
];

const mockLabors = [
  { id: 1, workName: 'Выравнивание стен по маякам', specialist: 'Штукатур-маляр', volume: 70, price: 450 },
  { id: 2, workName: 'Грунтовка поверхностей в 2 слоя', specialist: 'Мастер-отделочник', volume: 70, price: 80 },
  { id: 3, workName: 'Покраска стен безвоздушная', specialist: 'Маляр', volume: 70, price: 200 },
];

export function EstimateResult() {
  // Быстрый расчет общей суммы для верхней карточки
  const matTotal = mockMaterials.reduce((acc, item) => acc + item.count * item.price, 0);
  const laborTotal = mockLabors.reduce((acc, item) => acc + item.volume * item.price, 0);
  const totalCost = matTotal + laborTotal;

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <h2>Результат расчёта сметы</h2>
        <Button variant="secondary" onClick={() => window.print()}>Печать сметы</Button>
      </div>

      <div className={styles.statsGrid}>
        <Card title="Общая стоимость ремонта" className={styles.totalCard}>
          <div className={styles.priceValue}>
            {totalCost.toLocaleString('ru-RU')} ₽
          </div>
          <p className={styles.subtext}>Материалы: {matTotal.toLocaleString('ru-RU')} ₽ | Работы: {laborTotal.toLocaleString('ru-RU')} ₽</p>
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

      {/* Выводим новые таблицы */}
      <Card title="Детальный расчет" style={{ marginTop: '25px' }}>
        <MaterialsTable data={mockMaterials} />
        <LaborTable data={mockLabors} />
      </Card>
    </div>
  );
}