import React from 'react';
import { Layout } from './components/Layout/Layout';
import { Card } from './components/ui/Card';
import { Button } from './components/ui/Button';
import { Input } from './components/ui/Input';
import { Table } from './components/ui/Table';

function App() {
  return (
    <Layout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
        
        {/* Секция с карточками и кнопками */}
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px' }}>
          <Card title="Управление проектом">
            <p>Добро пожаловать в Repair Estimator. Здесь вы можете рассчитать стоимость ремонта.</p>
            <div style={{ display: 'flex', gap: '10px', marginTop: '15px' }}>
              <Button variant="primary">Создать смету</Button>
              <Button variant="secondary">Инструкция</Button>
            </div>
          </Card>

          <Card title="Новая комната">
            <Input label="Название помещения" placeholder="например, Гостиная" />
            <Input label="Площадь (кв. м.)" type="number" placeholder="20" />
            <Button variant="primary" style={{ width: '100%' }}>Добавить в расчет</Button>
          </Card>
        </section>

        {/* Секция с демонстрационной таблицей сметы */}
        <section>
          <Card title="Пример расчета стоимости материалов">
            <Table>
              <thead>
                <tr>
                  <th>Наименование материала</th>
                  <th>Количество</th>
                  <th>Цена за ед.</th>
                  <th>Итого</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Ламинат (33 класс)</td>
                  <td>25 кв. м.</td>
                  <td>1 200 ₽</td>
                  <td>30 000 ₽</td>
                </tr>
                <tr>
                  <td>Краска для стен (моющаяся)</td>
                  <td>2 банки</td>
                  <td>4 500 ₽</td>
                  <td>9 000 ₽</td>
                </tr>
              </tbody>
            </Table>
          </Card>
        </section>

      </div>
    </Layout>
  );
}

export default App;