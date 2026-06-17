import { Table } from '../../components/ui/Table';
import styles from './EstimateTables.module.css';

// Поля строго по контракту docs/api.md (materials[])
interface MaterialItem {
  name: string;
  quantity: number;
  unit: string;
  price_avg: number;
  total_avg: number;
  source: string;
  updated_at?: string;
}

interface MaterialsTableProps {
  data: MaterialItem[];
}

export function MaterialsTable({ data }: MaterialsTableProps) {
  if (!data || data.length === 0) {
    return <p>Нет данных по материалам</p>;
  }

  return (
    <div className={styles.tableBox}>
      <h3 className={styles.tableTitle}>Ведомость материалов</h3>
      <Table>
        <thead>
          <tr>
            <th>Название</th>
            <th>Количество</th>
            <th>Единица</th>
            <th>Цена</th>
            <th>Итог</th>
            <th>Источник</th>
            <th>Обновлено</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item, i) => (
            <tr key={i}>
              <td>{item.name}</td>
              <td>{item.quantity}</td>
              <td>{item.unit}</td>
              <td>{item.price_avg.toLocaleString('ru-RU')} ₽</td>
              {/* итог берём от backend, не пересчитываем */}
              <td className={styles.totalCell}>{item.total_avg.toLocaleString('ru-RU')} ₽</td>
              <td>{item.source}</td>
              <td>{item.updated_at ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
