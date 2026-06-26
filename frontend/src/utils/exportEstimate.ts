import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import * as XLSX from 'xlsx';


export interface EstimateExportData {
  summary: Record<string, number>;
  geometry?: Record<string, string | number>;
  materials: {
    name: string;
    quantity: number;
    unit: string;
    price_avg: number;
    total_avg: number;
  }[];
  labor: {
    service: string;
    specialist: string;
    volume: number;
    unit: string;
    price_avg: number;
    total_avg: number;
  }[];
}


const formatPrice = (price: number) => `${price.toLocaleString('ru-RU')} ₽`;


export const exportXlsx = (data: EstimateExportData) => {
  const wb = XLSX.utils.book_new();


  const materialsSheet = XLSX.utils.json_to_sheet(
    data.materials.map(m => ({
      'Наименование': m.name,
      'Количество': m.quantity,
      'Ед. изм.': m.unit,
      'Цена за ед.': formatPrice(m.price_avg),
      'Итого': formatPrice(m.total_avg),
    }))
  );
  XLSX.utils.book_append_sheet(wb, materialsSheet, 'Материалы');


  const laborSheet = XLSX.utils.json_to_sheet(
    data.labor.map(l => ({
      'Услуга': l.service,
      'Специалист': l.specialist,
      'Объем': l.volume,
      'Ед. изм.': l.unit,
      'Цена за ед.': formatPrice(l.price_avg),
      'Итого': formatPrice(l.total_avg),
    }))
  );
  XLSX.utils.book_append_sheet(wb, laborSheet, 'Работы');


  const summarySheet = XLSX.utils.json_to_sheet([
    { 'Показатель': 'Материалы (Мин)', 'Сумма': formatPrice(data.summary.materials_min) },
    { 'Показатель': 'Материалы (Средняя)', 'Сумма': formatPrice(data.summary.materials_avg) },
    { 'Показатель': 'Материалы (Макс)', 'Сумма': formatPrice(data.summary.materials_max) },
    { 'Показатель': 'Работы (Мин)', 'Сумма': formatPrice(data.summary.labor_min) },
    { 'Показатель': 'Работы (Средняя)', 'Сумма': formatPrice(data.summary.labor_avg) },
    { 'Показатель': 'Работы (Макс)', 'Сумма': formatPrice(data.summary.labor_max) },
    { 'Показатель': 'ИТОГО (Мин)', 'Сумма': formatPrice(data.summary.total_min) },
    { 'Показатель': 'ИТОГО (Средняя)', 'Сумма': formatPrice(data.summary.total_avg) },
    { 'Показатель': 'ИТОГО (Макс)', 'Сумма': formatPrice(data.summary.total_max) },
  ]);
  XLSX.utils.book_append_sheet(wb, summarySheet, 'Итого');

  XLSX.writeFile(wb, 'Смета.xlsx');
};


export const exportPdf = async (data: EstimateExportData, city: string, repairType: string) => {
  const doc = new jsPDF();

  
  try {
    const response = await fetch('/Roboto-Regular.ttf');
    const buffer = await response.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    const fontBase64 = window.btoa(binary);

    doc.addFileToVFS('Roboto-Regular.ttf', fontBase64);
    doc.addFont('Roboto-Regular.ttf', 'Roboto', 'normal');
    doc.setFont('Roboto');
  } catch (err) {
    console.error('Ошибка загрузки шрифта', err);
  }

 
  doc.setFontSize(16);
  doc.text('Проект: Смета на ремонт', 14, 15);
  doc.setFontSize(12);
  doc.text(`Город: ${city}`, 14, 22);
  doc.text(`Тип ремонта: ${repairType}`, 14, 28);
  doc.text(`Дата: ${new Date().toLocaleDateString('ru-RU')}`, 14, 34);

  let currentY = 42;

 
  if (data.geometry && Object.keys(data.geometry).length > 0) {
    doc.text('Геометрия помещений:', 14, currentY);
    doc.setFontSize(10);
    
    const geomText = Object.entries(data.geometry)
      .map(([k, v]) => `${k}: ${v}`)
      .join(' | ');
    doc.text(geomText, 14, currentY + 6);
    currentY += 14;
    doc.setFontSize(12);
  }

  
  doc.text('Материалы:', 14, currentY);
  autoTable(doc, {
    startY: currentY + 4,
    head: [['Наименование', 'Кол-во', 'Ед.', 'Цена', 'Итого']],
    body: data.materials.map(m => [
      m.name, m.quantity, m.unit, formatPrice(m.price_avg), formatPrice(m.total_avg)
    ]),
    styles: { font: 'Roboto' }
  });


  currentY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 10;
  doc.text('Работы:', 14, currentY);
  autoTable(doc, {
    startY: currentY + 4,
    head: [['Услуга', 'Специалист', 'Объем', 'Ед.', 'Цена', 'Итого']],
    body: data.labor.map(l => [
      l.service, l.specialist, l.volume, l.unit, formatPrice(l.price_avg), formatPrice(l.total_avg)
    ]),
    styles: { font: 'Roboto' }
  });

 
  currentY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 10;
  doc.setFontSize(12);
  doc.text(`Итого (Мин): ${formatPrice(data.summary.total_min)}`, 14, currentY);
  doc.text(`Итого (Средняя): ${formatPrice(data.summary.total_avg)}`, 14, currentY + 7);
  doc.text(`Итого (Макс): ${formatPrice(data.summary.total_max)}`, 14, currentY + 14);

  doc.save('Смета.pdf');
};