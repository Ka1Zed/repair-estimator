import  { useState } from 'react';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { MaterialsTable, type MaterialItem } from '../../components/EstimateTables/MaterialsTable';
import { LaborTable, type LaborItem } from '../../components/EstimateTables/LaborTable';
import { RepairOptionsForm } from '../../components/RepairOptionsForm/RepairOptionsForm';
import { EstimateSummary, type SummaryData } from '../../components/EstimateSummary';
import styles from './EstimateResult.module.css';


import { useProjectStore } from '../../store/projectStore';
import { calculateEstimate } from '../../api/estimates';


// Обновляем интерфейс всего ответа
interface EstimateResponse {
  summary: SummaryData;
  materials: MaterialItem[];
  labor: LaborItem[];
}
export function EstimateResult() {
  const { rooms, repair_type } = useProjectStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [estimateData, setEstimateData] = useState<EstimateResponse | null>(null);
  const handleCalculate = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const payload = {
        city: "Казань", // TODO: взять из стора когда появится поле city
        repair_type: repair_type,
        repair_options: rooms[0]?.repair_options ?? {},
        rooms: rooms.map(room => ({
          name: room.name,
          room_type: room.room_type,
          height: Number(room.height),
          openings: room.openings.map(op => ({
            ...op,
            width: Number(op.width),
            height: Number(op.height)
          })),
          points: room.points.map(p => ({
            x: Number(p.x),
            y: Number(p.y)
          }))
        }))
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
      {/* Шапка с кнопками */}
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

      {/* Показываем ошибки, если сервер упал */}
      {error && <div style={{ color: 'red', marginTop: '20px' }}>{error}</div>}

      {/* Показываем лоадер во время загрузки */}
      {isLoading && <div style={{ marginTop: '20px', fontSize: '18px' }}>Загрузка данных с сервера... ⏳</div>}

      {/* Отрисовываем таблицы ТОЛЬКО если данные успешно пришли */}
      {!isLoading && !error && estimateData && (
        <>
          <EstimateSummary summary={estimateData.summary} />

          <Card title="Детальный расчет" style={{ marginTop: '25px' }}>
            {/* Передаем реальные массивы из estimateData в таблицы */}
            <MaterialsTable data={estimateData.materials} />
            <LaborTable data={estimateData.labor} />
          </Card>
        </>
      )}
    </div>
  );
}
