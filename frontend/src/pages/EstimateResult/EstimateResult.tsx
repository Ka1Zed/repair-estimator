import  { useState } from 'react';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { MaterialsTable, type MaterialItem } from '../../components/EstimateTables/MaterialsTable';
import { LaborTable, type LaborItem } from '../../components/EstimateTables/LaborTable';
import { RepairOptionsForm } from '../../components/RepairOptionsForm/RepairOptionsForm';
import { EstimateSummary, type SummaryData } from '../../components/EstimateSummary';
import styles from './EstimateResult.module.css';
import { exportPdf, exportXlsx, type EstimateExportData } from '../../utils/exportEstimate';

import { useProjectStore } from '../../store/projectStore';
import { calculateEstimate } from '../../api/estimates';


interface GeometryData {
  floor_area: number;
  ceiling_area: number;
  wall_area: number;
  perimeter: number;
}

// Обновляем интерфейс всего ответа
interface EstimateResponse {
  summary: SummaryData;
  geometry: GeometryData;
  materials: MaterialItem[];
  labor: LaborItem[];
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
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <Button variant="primary" onClick={handleCalculate} disabled={isLoading}>
            {isLoading ? 'Считаем...' : 'Рассчитать'}
          </Button>
          
          {/* Кнопки появляются только когда данные загружены и нет ошибок */}
          {!isLoading && !error && estimateData && (
            <>
              <Button 
                variant="secondary" 
                onClick={() => exportPdf(estimateData as unknown as EstimateExportData, "Казань", repair_type)}
              >
                Скачать PDF
              </Button>
              <Button 
                variant="secondary" 
                onClick={() => exportXlsx(estimateData as unknown as EstimateExportData)}
              >
                Скачать Excel
              </Button>
            </>
          )}

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
