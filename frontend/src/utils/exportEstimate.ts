import jsPDF from 'jspdf';
import autoTable, { type CellHookData } from 'jspdf-autotable';
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

// Палитра из index.css, чтобы PDF был в одном стиле с сайтом
type RGB = [number, number, number];
const PDF_ACCENT: RGB = [176, 123, 94]; // --accent #B07B5E
const PDF_HEADING: RGB = [42, 42, 42]; // --text-h #2A2A2A
const PDF_MUTED: RGB = [107, 99, 99]; // --text #6b6363
const PDF_BORDER: RGB = [229, 229, 229]; // --border #E5E5E5
const PDF_ZEBRA: RGB = [250, 246, 243]; // тёплый оттенок для чётных строк
const PDF_WHITE: RGB = [255, 255, 255];

// Читаемая подпись источника цены: seed → «База», парсеры → человекочитаемо, + регион
const sourceNames: Record<string, string> = { seed: 'База', megastroy: 'Мегастрой', leroy: 'Леруа', lemana: 'Лемана ПРО' };
const sourceLabel = (source: string, region?: string | null) => {
  const src = !source ? '—' : sourceNames[source] ?? source;
  return region ? `${src}, ${region}` : src;
};

const getFinalY = (d: jsPDF) =>
  (d as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;

// Числовое кол-во: без хвостовых нулей, максимум 2 знака
const fmtQty = (x: number) => x.toLocaleString('ru-RU', { maximumFractionDigits: 2 });

// Запас в процентах из множителя waste_factor (1.1 → «+10%»)
const wastePct = (waste_factor: number) => `+${Math.round((waste_factor - 1) * 100)}%`;

export const exportPdf = async (data: EstimateExportData, city: string) => {
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

  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const marginX = 14;

  // Общий стиль таблиц — тёплая шапка вместо синей темы по умолчанию
  const tableBase = {
    theme: 'grid' as const,
    styles: {
      font: 'Roboto',
      fontSize: 9,
      cellPadding: 2.5,
      lineColor: PDF_BORDER,
      lineWidth: 0.1,
      textColor: PDF_HEADING,
    },
    headStyles: {
      fillColor: PDF_ACCENT,
      textColor: PDF_WHITE,
      fontStyle: 'normal' as const,
      halign: 'center' as const,
    },
    alternateRowStyles: { fillColor: PDF_ZEBRA },
    margin: { left: marginX, right: marginX },
  };

  const sectionHeading = (text: string, y: number) => {
    doc.setFontSize(13);
    doc.setTextColor(...PDF_HEADING);
    doc.text(text, marginX, y);
  };

  // Делает ячейки колонки «Источник» кликабельными ссылками на source_url:
  // подсвечивает акцентом и вешает doc.link поверх ячейки.
  const sourceLinks = (items: { source_url?: string | null }[], col: number) => ({
    didParseCell: (h: CellHookData) => {
      if (h.section === 'body' && h.column.index === col && items[h.row.index]?.source_url) {
        h.cell.styles.textColor = PDF_ACCENT;
      }
    },
    didDrawCell: (h: CellHookData) => {
      if (h.section !== 'body' || h.column.index !== col) return;
      const url = items[h.row.index]?.source_url;
      if (url) doc.link(h.cell.x, h.cell.y, h.cell.width, h.cell.height, { url });
    },
  });

  // Обложка: титул + акцентная линейка + мета
  doc.setFontSize(22);
  doc.setTextColor(...PDF_HEADING);
  doc.text('Смета на ремонт', marginX, 22);
  doc.setDrawColor(...PDF_ACCENT);
  doc.setLineWidth(0.8);
  doc.line(marginX, 26, pageW - marginX, 26);
  doc.setFontSize(10);
  doc.setTextColor(...PDF_MUTED);
  const meta = `Город: ${city}    ·    Дата: ${new Date().toLocaleDateString('ru-RU')}`;
  doc.text(meta, marginX, 33);

  let currentY = 44;

  if (data.geometry && Object.keys(data.geometry).length > 0) {
    doc.setFontSize(11);
    doc.setTextColor(...PDF_HEADING);
    doc.text('Геометрия помещений', marginX, currentY);
    doc.setFontSize(9);
    doc.setTextColor(...PDF_MUTED);
    const geomText = Object.entries(data.geometry)
      .map(([k, v]) => `${geometryLocales[k] || k}: ${v}`)
      .join('    ·    ');
    doc.text(geomText, marginX, currentY + 5);
    currentY += 14;
  }

  sectionHeading('Материалы', currentY);
  autoTable(doc, {
    ...tableBase,
    ...sourceLinks(data.materials, 5),
    startY: currentY + 4,
    head: [['Наименование', 'Кол-во', 'Ед.', 'Цена', 'Итого', 'Источник']],
    body: data.materials.map(m => [
      m.name, m.quantity, m.unit, formatPricePDF(m.price_avg), formatPricePDF(m.total_avg), sourceLabel(m.source, m.region)
    ]),
    columnStyles: {
      0: { halign: 'left', cellWidth: 58 },
      1: { halign: 'right', cellWidth: 18 },
      2: { halign: 'center', cellWidth: 12 },
      3: { halign: 'right', cellWidth: 28 },
      4: { halign: 'right', cellWidth: 30 },
      5: { halign: 'left', cellWidth: 36, fontSize: 8, textColor: PDF_MUTED }
    }
  });

  currentY = getFinalY(doc) + 12;
  sectionHeading('Работы', currentY);
  autoTable(doc, {
    ...tableBase,
    ...sourceLinks(data.labor, 6),
    startY: currentY + 4,
    head: [['Услуга', 'Специалист', 'Объём', 'Ед.', 'Цена', 'Итого', 'Источник']],
    body: data.labor.map(l => [
      l.service, l.specialist, l.volume, l.unit, formatPricePDF(l.price_avg), formatPricePDF(l.total_avg), sourceLabel(l.source, l.region)
    ]),
    columnStyles: {
      0: { halign: 'left', cellWidth: 40 },
      1: { halign: 'left', cellWidth: 28 },
      2: { halign: 'right', cellWidth: 16 },
      3: { halign: 'center', cellWidth: 12 },
      4: { halign: 'right', cellWidth: 26 },
      5: { halign: 'right', cellWidth: 28 },
      6: { halign: 'left', cellWidth: 32, fontSize: 8, textColor: PDF_MUTED }
    }
  });

  const s = data.summary;
  currentY = getFinalY(doc) + 14;
  sectionHeading('Итоговая стоимость', currentY);
  autoTable(doc, {
    ...tableBase,
    startY: currentY + 4,
    head: [['', 'Минимум', 'Средняя', 'Максимум']],
    body: [
      ['Материалы', formatPricePDF(s.materials_min), formatPricePDF(s.materials_avg), formatPricePDF(s.materials_max)],
      ['Работы', formatPricePDF(s.labor_min), formatPricePDF(s.labor_avg), formatPricePDF(s.labor_max)],
    ],
    foot: [['Итого', formatPricePDF(s.total_min), formatPricePDF(s.total_avg), formatPricePDF(s.total_max)]],
    footStyles: {
      fillColor: PDF_ACCENT,
      textColor: PDF_WHITE,
      fontStyle: 'normal' as const,
      halign: 'right' as const,
    },
    columnStyles: {
      0: { halign: 'left', cellWidth: 46 },
      1: { halign: 'right', cellWidth: 45 },
      2: { halign: 'right', cellWidth: 45 },
      3: { halign: 'right', cellWidth: 46 }
    }
  });

  // Детализация количества материалов: из чего сложилось «Кол-во» в смете
  currentY = getFinalY(doc) + 14;
  // не оставлять заголовок секции «висеть» внизу страницы — перенести целиком
  if (currentY > pageH - 45) {
    doc.addPage();
    currentY = 20;
  }
  sectionHeading('Детализация количества материалов', currentY);
  doc.setFontSize(8);
  doc.setTextColor(...PDF_MUTED);
  doc.text('Количество = базовый расход × запас, округлённое вверх до целых упаковок', marginX, currentY + 5);
  autoTable(doc, {
    ...tableBase,
    startY: currentY + 9,
    head: [['Материал', 'Базовый расход', 'Запас', 'Фасовка', 'Упаковок', 'Итого']],
    body: data.materials.map(m => [
      m.name,
      `${fmtQty(m.base_quantity)} ${m.unit}`,
      wastePct(m.waste_factor),
      `${fmtQty(m.package_size)} ${m.unit}`,
      m.packs,
      `${fmtQty(m.quantity)} ${m.unit}`,
    ]),
    columnStyles: {
      0: { halign: 'left', cellWidth: 58 },
      1: { halign: 'right', cellWidth: 32 },
      2: { halign: 'center', cellWidth: 18 },
      3: { halign: 'right', cellWidth: 28 },
      4: { halign: 'right', cellWidth: 20 },
      5: { halign: 'right', cellWidth: 26 }
    }
  });

  // Футер: подпись слева, нумерация справа — на каждой странице
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFont('Roboto');
    doc.setFontSize(8);
    doc.setTextColor(...PDF_MUTED);
    doc.text('Предварительный расчёт · итоговая стоимость уточняется при замере', marginX, pageH - 8);
    doc.text(`Стр. ${i} из ${pageCount}`, pageW - marginX, pageH - 8, { align: 'right' });
  }

  doc.save('Смета.pdf');
};
