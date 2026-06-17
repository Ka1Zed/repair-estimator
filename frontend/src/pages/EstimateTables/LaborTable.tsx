import { Table } from '../../components/ui/Table';
import styles from './EstimateTables.module.css';

interface LaborItem {
  id: number;
  workName: string;
  specialist: string;
  volume: number;
  price: number;
}

interface LaborTableProps {
  data: LaborItem[];
}

export function LaborTable({ data }: LaborTableProps) {
  return (
    <div className={styles.tableBox}>
      <h3 className={styles.tableTitle}>🛠️ Ремонтные работы</h3>
      <Table>
        <thead>
          <tr>
            <th>Работа</th>
            <th>Специалист</th>
            <th>Объём</th>
            <th>Цена</th>
            <th>Итог</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.id}>
              <td>{item.workName}</td>
              <td>{item.specialist}</td>
              <td>{item.volume}</td>
              <td>{item.price.toLocaleString('ru-RU')} ₽</td>
              <td className={styles.totalCell}>{(item.volume * item.price).toLocaleString('ru-RU')} ₽</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}