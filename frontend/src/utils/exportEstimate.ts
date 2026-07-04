import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import * as XLSX from 'xlsx';

import type { SummaryData } from '../components/EstimateSummary';
import type { MaterialItem, LaborItem } from '../types/estimate';

export interface EstimateExportData {
  summary: SummaryData;
  geometry?: {
    floor_area: number;
    ceiling_area: number;
    wall_area: number;
    perimeter: number;
  };
  materials: MaterialItem[];
  labor: LaborItem[];
}

const formatPricePDF = (price: number) => `${price.toLocaleString('ru-RU')} ₽`;

const applyCurrencyFormat = (ws: XLSX.WorkSheet) => {
  for (const key in ws) {
    if (key[0] === '!') continue;
    if (ws[key].t === 'n') {
      ws[key].z = '#,##0.00" ₽"';
    }
  }
};

const geometryLocales: Record<string, string> = {
  floor_area: 'Площадь пола',
  wall_area: 'Площадь стен',
  ceiling_area: 'Площадь потолка',
  perimeter: 'Периметр',
  openings_area: 'Площадь проемов'
};

export const exportXlsx = (data: EstimateExportData) => {
  const wb = XLSX.utils.book_new();

  const materialsSheet = XLSX.utils.json_to_sheet(
    data.materials.map(m => ({
      'Наименование': m.name,
      'Количество': m.quantity,
      'Ед. изм.': m.unit,
      'Цена за ед.': m.price_avg,
      'Итого': m.total_avg,
    }))
  );
  applyCurrencyFormat(materialsSheet);
  XLSX.utils.book_append_sheet(wb, materialsSheet, 'Материалы');

  const laborSheet = XLSX.utils.json_to_sheet(
    data.labor.map(l => ({
      'Услуга': l.service,
      'Специалист': l.specialist,
      'Объем': l.volume,
      'Ед. изм.': l.unit,
      'Цена за ед.': l.price_avg,
      'Итого': l.total_avg,
    }))
  );
  applyCurrencyFormat(laborSheet);
  XLSX.utils.book_append_sheet(wb, laborSheet, 'Работы');

  const summarySheet = XLSX.utils.json_to_sheet([
    { 'Показатель': 'Материалы (Мин)', 'Сумма': data.summary.materials_min },
    { 'Показатель': 'Материалы (Средняя)', 'Сумма': data.summary.materials_avg },
    { 'Показатель': 'Материалы (Макс)', 'Сумма': data.summary.materials_max },
    { 'Показатель': 'Работы (Мин)', 'Сумма': data.summary.labor_min },
    { 'Показатель': 'Работы (Средняя)', 'Сумма': data.summary.labor_avg },
    { 'Показатель': 'Работы (Макс)', 'Сумма': data.summary.labor_max },
    { 'Показатель': 'ИТОГО (Мин)', 'Сумма': data.summary.total_min },
    { 'Показатель': 'ИТОГО (Средняя)', 'Сумма': data.summary.total_avg },
    { 'Показатель': 'ИТОГО (Макс)', 'Сумма': data.summary.total_max },
  ]);
  applyCurrencyFormat(summarySheet);
  XLSX.utils.book_append_sheet(wb, summarySheet, 'Итого');

  XLSX.writeFile(wb, 'Смета.xlsx');
};

export const exportPdf = async (data: EstimateExportData, city: string, repairType: string) => {
  const doc = new jsPDF();

  try {
    const response = await fetch('/Roboto-Regular.ttf');
    if (!response.ok) throw new Error('Ошибка сети при загрузке шрифта');
    
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
    alert('Не удалось загрузить кириллический шрифт. Выгрузка PDF отменена.');
    return;
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
      .map(([k, v]) => `${geometryLocales[k] || k}: ${v}`)
      .join(' | ');
    doc.text(geomText, 14, currentY + 6);
    currentY += 15;
    doc.setFontSize(12);
  }

  doc.text('Материалы:', 14, currentY);
  autoTable(doc, {
    startY: currentY + 5,
    head: [['Наименование', 'Кол-во', 'Ед.', 'Цена', 'Итого']],
    body: data.materials.map(m => [
      m.name, m.quantity, m.unit, formatPricePDF(m.price_avg), formatPricePDF(m.total_avg)
    ]),
    styles: { font: 'Roboto' },
    headStyles: { halign: 'center', fontStyle: 'normal' },
    columnStyles: {
      0: { halign: 'left', cellWidth: 77 },
      1: { halign: 'right', cellWidth: 20 },
      2: { halign: 'center', cellWidth: 15 },
      3: { halign: 'right', cellWidth: 35 },
      4: { halign: 'right', cellWidth: 35 }
    }
  });

  currentY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 15;
  doc.text('Работы:', 14, currentY);
  autoTable(doc, {
    startY: currentY + 5,
    head: [['Услуга', 'Специалист', 'Объем', 'Ед.', 'Цена', 'Итого']],
    body: data.labor.map(l => [
      l.service, l.specialist, l.volume, l.unit, formatPricePDF(l.price_avg), formatPricePDF(l.total_avg)
    ]),
    styles: { font: 'Roboto' },
    headStyles: { halign: 'center', fontStyle: 'normal' },
    columnStyles: {
      0: { halign: 'left', cellWidth: 52 },
      1: { halign: 'left', cellWidth: 35 },
      2: { halign: 'right', cellWidth: 20 },
      3: { halign: 'center', cellWidth: 15 },
      4: { halign: 'right', cellWidth: 30 },
      5: { halign: 'right', cellWidth: 30 }
    }
  });

  currentY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 15;
  doc.setFontSize(12);
  doc.text(`Итого (Мин): ${formatPricePDF(data.summary.total_min)}`, 14, currentY);
  doc.text(`Итого (Средняя): ${formatPricePDF(data.summary.total_avg)}`, 14, currentY + 7);
  doc.text(`Итого (Макс): ${formatPricePDF(data.summary.total_max)}`, 14, currentY + 14);

  doc.save('Смета.pdf');
};
