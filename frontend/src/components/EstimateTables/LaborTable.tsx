import { Table } from "../ui/Table";
import styles from "./EstimateTables.module.css";

// Поля строго по контракту docs/api.md (labor[])
export interface LaborItem {
  service: string;
  specialist: string;
  volume: number;
  unit: string;
  price_avg: number;
  total_avg: number;
  source: string;
}

interface LaborTableProps {
  data: LaborItem[];
}

export function LaborTable({ data }: LaborTableProps) {
  if (!data || data.length === 0) {
    return <p>Нет данных по работам</p>;
  }

  return (
    <div className={styles.tableBox}>
      <h3 className={styles.tableTitle}>Ремонтные работы</h3>
      <Table>
        <thead>
          <tr>
            <th>Работа</th>
            <th>Специалист</th>
            <th>Объём</th>
            <th>Единица</th>
            <th>Цена</th>
            <th>Итог</th>
            <th>Источник</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item, i) => (
            <tr key={i}>
              <td>{item.service}</td>
              <td>{item.specialist}</td>
              <td>{item.volume}</td>
              <td>{item.unit}</td>
              <td>{item.price_avg.toLocaleString("ru-RU")} ₽</td>
              {/* итог берём от backend */}
              <td className={styles.totalCell}>
                {item.total_avg.toLocaleString("ru-RU")} ₽
              </td>
              <td>{item.source}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
