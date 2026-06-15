import React from 'react';
import { Table } from '../ui/Table';
import styles from './EstimateTables.module.css';

interface MaterialItem {
  id: number;
  name: string;
  count: number;
  unit: string;
  price: number;
}

interface MaterialsTableProps {
  data: MaterialItem[];
}

export function MaterialsTable({ data }: MaterialsTableProps) {
  return (
    <div className={styles.tableBox}>
      <h3 className={styles.tableTitle}>📋 Ведомость материалов</h3>
      <Table>
        <thead>
          <tr>
            <th>Название</th>
            <th>Количество</th>
            <th>Единица</th>
            <th>Цена</th>
            <th>Итог</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.id}>
              <td>{item.name}</td>
              <td>{item.count}</td>
              <td>{item.unit}</td>
              <td>{item.price.toLocaleString('ru-RU')} ₽</td>
              <td className={styles.totalCell}>{(item.count * item.price).toLocaleString('ru-RU')} ₽</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}