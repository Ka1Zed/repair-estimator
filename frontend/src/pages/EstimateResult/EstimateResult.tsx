import { useState } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { calculateEstimate } from '../../api/estimates';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { EstimateLedger, type LedgerRow } from '../../components/EstimateLedger/EstimateLedger';
import { RepairOptionsForm } from '../../components/RepairOptionsForm/RepairOptionsForm';
import { EstimateSummary, type SummaryData } from '../../components/EstimateSummary';
import type { MaterialItem, LaborItem } from '../../types/estimate';
import styles from './EstimateResult.module.css';

const fmt = (n: number) => n.toLocaleString('ru-RU');

interface GeometryData {
  floor_area: number;
  ceiling_area: number;
  wall_area: number;
  perimeter: number;
}

interface EstimateResponse {
  summary: SummaryData;
  geometry: GeometryData;
  materials: MaterialItem[];
  labor: LaborItem[];
}

function materialToLedgerRow(item: MaterialItem): LedgerRow {
  const details: LedgerRow['details'] = [
    { label: 'Базовое кол-во', value: `${item.base_quantity} ${item.unit}` },
    { label: 'Запас', value: `×${item.waste_factor} (+${Math.round((item.waste_factor - 1) * 100)}%)` },
    { label: 'Упаковок', value: `${item.packs} × ${item.package_size} ${item.unit}` },
    { label: 'Итого кол-во', value: `${item.quantity} ${item.unit}` },
    { label: 'Цена за единицу', value: `${fmt(item.price_avg)} ₽/${item.unit}` },
    { label: 'Итого', value: `${fmt(item.total_avg)} ₽` },
    { label: 'Источник', value: item.source },
  ];
  if (item.updated_at) details.push({ label: 'Обновлено', value: new Date(item.updated_at).toLocaleDateString('ru-RU') });
  return {
    name: item.name,
    subtitle: item.source,
    volume: `${item.quantity} ${item.unit}`,
    price: `${fmt(item.total_avg)} ₽`,
    details,
  };
}

function laborToLedgerRow(item: LaborItem): LedgerRow {
  return {
    name: item.service,
    subtitle: item.specialist,
    volume: `${item.volume} ${item.unit}`,
    price: `${fmt(item.total_avg)} ₽`,
    details: [
      { label: 'Специалист', value: item.specialist },
      { label: 'Ставка', value: `${fmt(item.price_avg)} ₽/${item.unit}` },
      { label: 'Объём', value: `${item.volume} ${item.unit}` },
      { label: 'Итого', value: `${fmt(item.total_avg)} ₽` },
      { label: 'Источник', value: item.source },
    ],
  };
}

export function EstimateResult() {
  const { rooms, repair_type, repair_options } = useProjectStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [estimateData, setEstimateData] = useState<EstimateResponse | null>(null);

  const handleCalculate = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const payload = {
        city: "Казань", // TODO: взять из стора когда появится поле city
        repair_type,
        repair_options,
        rooms: rooms.map(room => ({
          name: room.name,
          room_type: room.room_type,
          height: Number(room.height),
          openings: room.openings.map(op => ({
            ...op,
            width: Number(op.width),
            height: Number(op.height),
          })),
          points: room.points.map(p => ({ x: Number(p.x), y: Number(p.y) })),
        })),
      };
      const data = await calculateEstimate(payload);
      setEstimateData(data as EstimateResponse);
    } catch (err) {
      console.error(err);
      setError("Не удалось рассчитать смету. Проверьте подключение к серверу.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <h2>Результат расчёта сметы</h2>
        <div style={{ display: 'flex', gap: '10px' }}>
          <Button variant="primary" onClick={handleCalculate} disabled={isLoading}>
            {isLoading ? 'Считаем...' : 'Рассчитать'}
          </Button>
          <Button variant="secondary" onClick={() => window.print()}>
            Печать сметы
          </Button>
        </div>
      </div>

      <RepairOptionsForm />

      {error && <div style={{ color: 'red', marginTop: '20px' }}>{error}</div>}
      {isLoading && <div style={{ marginTop: '20px', fontSize: '18px' }}>Загрузка данных с сервера... ⏳</div>}

      {!isLoading && !error && estimateData && (
        <>
          {estimateData.geometry && (
            <Card title="Параметры помещения" style={{ marginTop: '25px' }}>
              <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', fontSize: '14px' }}>
                <span>Площадь пола: <strong>{estimateData.geometry.floor_area} м²</strong></span>
                <span>Площадь потолка: <strong>{estimateData.geometry.ceiling_area} м²</strong></span>
                <span>Площадь стен: <strong>{estimateData.geometry.wall_area} м²</strong></span>
                <span>Периметр: <strong>{estimateData.geometry.perimeter} м</strong></span>
              </div>
            </Card>
          )}

          <EstimateSummary summary={estimateData.summary} />

          <Card title="Ведомость материалов" style={{ marginTop: '25px' }}>
            <EstimateLedger rows={estimateData.materials.map(materialToLedgerRow)} />
          </Card>
          <Card title="Ремонтные работы" style={{ marginTop: '16px' }}>
            <EstimateLedger rows={estimateData.labor.map(laborToLedgerRow)} />
          </Card>
        </>
      )}
    </div>
  );
}
