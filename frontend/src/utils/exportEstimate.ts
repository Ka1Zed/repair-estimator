import jsPDF from 'jspdf';
import autoTable, { type CellHookData } from 'jspdf-autotable';
import * as XLSX from 'xlsx-js-style';

import type { SummaryData } from '../components/EstimateSummary';
import type { MaterialItem, LaborItem, HiddenWorks, HiddenWorkItem } from '../types/estimate';
import type { PriceMode } from '../pages/Workspace/Workspace';

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
  hidden_works?: HiddenWorks;
}

const formatPricePDF = (price: number) => `${price.toLocaleString('ru-RU')} ₽`;

// Палитра Excel
const XLS = {
  accent: 'B07B5E',
  heading: '2A2A2A',
  muted: '6B6363',
  border: 'E5E5E5',
  zebra: 'FAF6F3',
  white: 'FFFFFF',
  link: '0563C1',
};
const MONEY_FMT = '#,##0.00" ₽"';
const thin = { style: 'thin', color: { rgb: XLS.border } };
const allBorders = { top: thin, bottom: thin, left: thin, right: thin };

const titleStyle = { font: { bold: true, sz: 16, color: { rgb: XLS.heading } } };
const metaStyle = { font: { sz: 10, italic: true, color: { rgb: XLS.muted } } };
const sectionStyle = { font: { bold: true, sz: 12, color: { rgb: XLS.heading } } };
const noteStyle = { font: { sz: 9, italic: true, color: { rgb: XLS.muted } } };
const headStyle = {
  font: { bold: true, color: { rgb: XLS.white } },
  fill: { patternType: 'solid', fgColor: { rgb: XLS.accent } },
  alignment: { horizontal: 'center', vertical: 'center' },
  border: allBorders,
};
const bodyStyle = { border: allBorders, alignment: { vertical: 'center' } };
const zebraStyle = { ...bodyStyle, fill: { patternType: 'solid', fgColor: { rgb: XLS.zebra } } };
const totalStyle = {
  font: { bold: true, color: { rgb: XLS.white } },
  fill: { patternType: 'solid', fgColor: { rgb: XLS.accent } },
  border: allBorders,
};

const cellAt = (ws: XLSX.WorkSheet, r: number, c: number) => {
  const ref = XLSX.utils.encode_cell({ r, c });
  if (!ws[ref]) ws[ref] = { t: 's', v: '' };
  return ws[ref];
};

const styleTable = (
  ws: XLSX.WorkSheet,
  cfg: {
    headerRow: number;
    firstData: number;
    lastData: number;
    firstCol: number;
    lastCol: number;
    moneyCols?: number[];
    linkCol?: number;
    isLink?: (dataIdx: number) => boolean;
  },
) => {
  for (let c = cfg.firstCol; c <= cfg.lastCol; c++) {
    cellAt(ws, cfg.headerRow, c).s = headStyle;
  }
  for (let r = cfg.firstData; r <= cfg.lastData; r++) {
    for (let c = cfg.firstCol; c <= cfg.lastCol; c++) {
      const cell = cellAt(ws, r, c);
      let st: Record<string, unknown> = (r - cfg.firstData) % 2 ? { ...zebraStyle } : { ...bodyStyle };
      if (cfg.moneyCols?.includes(c)) {
        st = { ...st, numFmt: MONEY_FMT, alignment: { horizontal: 'right', vertical: 'center' } };
      }
      if (cfg.linkCol === c && cfg.isLink?.(r - cfg.firstData)) {
        st = { ...st, font: { color: { rgb: XLS.link }, underline: true } };
      }
      cell.s = st;
    }
  }
};

const fmtDate = (iso?: string) => (iso ? new Date(iso).toLocaleDateString('ru-RU') : '');

const geometryLocales: Record<string, string> = {
  floor_area: 'Площадь пола',
  wall_area: 'Площадь стен',
  ceiling_area: 'Площадь потолка',
  perimeter: 'Периметр',
  openings_area: 'Площадь проемов'
};

const geometryUnits: Record<string, string> = {
  floor_area: 'м²',
  wall_area: 'м²',
  ceiling_area: 'м²',
  openings_area: 'м²',
  perimeter: 'м'
};

const MODE_LABELS: Record<PriceMode, string> = {
  min: 'Минимальный',
  avg: 'Средний',
  max: 'Максимальный'
};

const scaleFor = (s: SummaryData, priceMode: PriceMode, category: 'materials' | 'labor') => {
  const avg = category === 'materials' ? s.materials_avg : s.labor_avg;
  if (avg === 0) return 1;
  const min = category === 'materials' ? s.materials_min : s.labor_min;
  const max = category === 'materials' ? s.materials_max : s.labor_max;
  if (priceMode === 'min') return min / avg;
  if (priceMode === 'max') return max / avg;
  return 1;
};

// Хелпер для получения РЕАЛЬНЫХ данных материала (с учетом выбранного уровня min/avg/max)
const getActiveMaterialData = (m: MaterialItem, priceMode: PriceMode, scale: number) => {
  let activeName = m.name;
  let activePrice = m.price_avg * scale;
  let activeTotal = m.total_avg * scale;
  let activeSource = m.source;
  let activeUrl = m.source_url;

  if (priceMode === 'min' && m.min_item) {
    activeName = m.min_item.name;
    activePrice = m.min_item.price;
    activeTotal = m.min_item.total;
    activeSource = m.min_item.source || m.source;
    activeUrl = m.min_item.source_url || m.source_url;
  } else if (priceMode === 'avg' && m.avg_item) {
    activeName = m.avg_item.name;
    activePrice = m.avg_item.price;
    activeTotal = m.avg_item.total;
    activeSource = m.avg_item.source || m.source;
    activeUrl = m.avg_item.source_url || m.source_url;
  } else if (priceMode === 'max' && m.max_item) {
    activeName = m.max_item.name;
    activePrice = m.max_item.price;
    activeTotal = m.max_item.total;
    activeSource = m.max_item.source || m.source;
    activeUrl = m.max_item.source_url || m.source_url;
  }

  return { activeName, activePrice, activeTotal, activeSource, activeUrl };
};

export const exportXlsx = (data: EstimateExportData, city: string, priceMode: PriceMode = "avg") => {
  const wb = XLSX.utils.book_new();
  const today = new Date().toLocaleDateString('ru-RU');
  const s = data.summary;

  const scaleMat = scaleFor(s, priceMode, 'materials');
  const scaleLab = scaleFor(s, priceMode, 'labor');
  const pLab = (val: number) => Math.round(val * scaleLab);

  const metaLine = `Город: ${city}    ·    Уровень цен: ${MODE_LABELS[priceMode]}    ·    Дата: ${today}`;

  // ---------- Сводка ----------
  const summaryAoa: (string | number)[][] = [
    ['Смета на ремонт'],
    [metaLine],
    [],
  ];
  const geomEntries = data.geometry ? Object.entries(data.geometry) : [];
  if (geomEntries.length) {
    summaryAoa.push(['Геометрия помещений']);
    for (const [k, v] of geomEntries) {
      summaryAoa.push([geometryLocales[k] ?? k, `${v} ${geometryUnits[k] ?? ''}`.trim()]);
    }
    summaryAoa.push([]);
  }
  summaryAoa.push(['Итоговая стоимость']);
  summaryAoa.push(['', 'Минимум', 'Средняя', 'Максимум']);
  const costFirst = summaryAoa.length;
  summaryAoa.push(['Материалы', s.materials_min, s.materials_avg, s.materials_max]);
  summaryAoa.push(['Работы', s.labor_min, s.labor_avg, s.labor_max]);
  summaryAoa.push(['ИТОГО', s.total_min, s.total_avg, s.total_max]);
  const costLast = summaryAoa.length - 1;
  summaryAoa.push([]);
  summaryAoa.push(['Предварительный расчёт · итоговая стоимость уточняется при замере']);

  const summarySheet = XLSX.utils.aoa_to_sheet(summaryAoa);
  summarySheet['!cols'] = [{ wch: 26 }, { wch: 18 }, { wch: 18 }, { wch: 18 }];
  summarySheet['!merges'] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: 3 } },
    { s: { r: 1, c: 0 }, e: { r: 1, c: 3 } },
  ];
  cellAt(summarySheet, 0, 0).s = titleStyle;
  cellAt(summarySheet, 1, 0).s = metaStyle;
  if (geomEntries.length) cellAt(summarySheet, 3, 0).s = sectionStyle;
  cellAt(summarySheet, costFirst - 2, 0).s = sectionStyle;
  styleTable(summarySheet, {
    headerRow: costFirst - 1,
    firstData: costFirst,
    lastData: costLast,
    firstCol: 0,
    lastCol: 3,
    moneyCols: [1, 2, 3],
  });
  for (let c = 0; c <= 3; c++) cellAt(summarySheet, costLast, c).s = { ...totalStyle, ...(c ? { numFmt: MONEY_FMT, alignment: { horizontal: 'right', vertical: 'center' } } : {}) };
  XLSX.utils.book_append_sheet(wb, summarySheet, 'Сводка');

  // ---------- Материалы ----------
  const matAoa: (string | number)[][] = [
    ['Материалы'],
    [metaLine],
    [],
    ['Наименование', 'Кол-во', 'Ед. изм.', 'Цена за ед.', 'Итого', 'Источник', 'Дата цены'],
    ...data.materials.map(m => {
      const act = getActiveMaterialData(m, priceMode, scaleMat);
      return [
        act.activeName, m.quantity, m.unit, Math.round(act.activePrice), Math.round(act.activeTotal),
        sourceLabel(act.activeSource, m.region), fmtDate(m.updated_at),
      ];
    }),
  ];
  const matSheet = XLSX.utils.aoa_to_sheet(matAoa);
  const matFirst = 4;
  const matLast = matFirst + data.materials.length - 1;
  data.materials.forEach((m, i) => {
    const act = getActiveMaterialData(m, priceMode, scaleMat);
    if (!act.activeUrl) return;
    const ref = XLSX.utils.encode_cell({ r: matFirst + i, c: 5 });
    matSheet[ref].l = { Target: act.activeUrl, Tooltip: 'Открыть источник цены' };
  });
  matSheet['!cols'] = [{ wch: 38 }, { wch: 10 }, { wch: 10 }, { wch: 14 }, { wch: 16 }, { wch: 24 }, { wch: 14 }];
  matSheet['!merges'] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: 6 } },
    { s: { r: 1, c: 0 }, e: { r: 1, c: 6 } },
  ];
  cellAt(matSheet, 0, 0).s = titleStyle;
  cellAt(matSheet, 1, 0).s = metaStyle;
  if (data.materials.length) {
    styleTable(matSheet, {
      headerRow: 3, firstData: matFirst, lastData: matLast, firstCol: 0, lastCol: 6,
      moneyCols: [3, 4], linkCol: 5, isLink: (i) => !!getActiveMaterialData(data.materials[i], priceMode, scaleMat).activeUrl,
    });
    matSheet['!autofilter'] = { ref: `${XLSX.utils.encode_cell({ r: 3, c: 0 })}:${XLSX.utils.encode_cell({ r: matLast, c: 6 })}` };
  }
  XLSX.utils.book_append_sheet(wb, matSheet, 'Материалы');

  // ---------- Работы ----------
  const labAoa: (string | number)[][] = [
    ['Работы'],
    [metaLine],
    [],
    ['Услуга', 'Специалист', 'Объём', 'Ед. изм.', 'Цена за ед.', 'Итого', 'Источник'],
    ...data.labor.map(l => [
      l.service, l.specialist, l.volume, l.unit, pLab(l.price_avg), pLab(l.total_avg),
      sourceLabel(l.source, l.region),
    ]),
  ];
  const labSheet = XLSX.utils.aoa_to_sheet(labAoa);
  const labFirst = 4;
  const labLast = labFirst + data.labor.length - 1;
  data.labor.forEach((l, i) => {
    if (!l.source_url) return;
    const ref = XLSX.utils.encode_cell({ r: labFirst + i, c: 6 });
    labSheet[ref].l = { Target: l.source_url, Tooltip: 'Открыть источник цены' };
  });
  labSheet['!cols'] = [{ wch: 30 }, { wch: 20 }, { wch: 10 }, { wch: 10 }, { wch: 14 }, { wch: 16 }, { wch: 24 }];
  labSheet['!merges'] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: 6 } },
    { s: { r: 1, c: 0 }, e: { r: 1, c: 6 } },
  ];
  cellAt(labSheet, 0, 0).s = titleStyle;
  cellAt(labSheet, 1, 0).s = metaStyle;
  if (data.labor.length) {
    styleTable(labSheet, {
      headerRow: 3, firstData: labFirst, lastData: labLast, firstCol: 0, lastCol: 6,
      moneyCols: [4, 5], linkCol: 6, isLink: (i) => !!data.labor[i].source_url,
    });
    labSheet['!autofilter'] = { ref: `${XLSX.utils.encode_cell({ r: 3, c: 0 })}:${XLSX.utils.encode_cell({ r: labLast, c: 6 })}` };
  }
  XLSX.utils.book_append_sheet(wb, labSheet, 'Работы');

  // ---------- Детализация количества ----------
  const detAoa: (string | number)[][] = [
    ['Детализация количества материалов'],
    ['Количество = базовый расход × запас, округлённое вверх до целых упаковок'],
    [],
    ['Материал', 'Базовый расход', 'Запас', 'Фасовка', 'Упаковок', 'Итого'],
    ...data.materials.map(m => {
      const act = getActiveMaterialData(m, priceMode, scaleMat);
      return [
        act.activeName,
        `${fmtQty(m.base_quantity)} ${m.unit}`,
        wastePct(m.waste_factor),
        `${fmtQty(m.package_size)} ${m.unit}`,
        m.packs,
        `${fmtQty(m.quantity)} ${m.unit}`,
      ];
    }),
  ];
  const detSheet = XLSX.utils.aoa_to_sheet(detAoa);
  detSheet['!cols'] = [{ wch: 38 }, { wch: 18 }, { wch: 10 }, { wch: 16 }, { wch: 12 }, { wch: 16 }];
  detSheet['!merges'] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: 5 } },
    { s: { r: 1, c: 0 }, e: { r: 1, c: 5 } },
  ];
  cellAt(detSheet, 0, 0).s = titleStyle;
  cellAt(detSheet, 1, 0).s = noteStyle;
  if (data.materials.length) {
    const detLast = 3 + data.materials.length;
    styleTable(detSheet, {
      headerRow: 3, firstData: 4, lastData: detLast, firstCol: 0, lastCol: 5,
    });
    detSheet['!autofilter'] = { ref: `${XLSX.utils.encode_cell({ r: 3, c: 0 })}:${XLSX.utils.encode_cell({ r: detLast, c: 5 })}` };
  }
  XLSX.utils.book_append_sheet(wb, detSheet, 'Детализация');

  // ---------- Скрытые работы ----------
  if (data.hidden_works && data.hidden_works.items.length > 0) {
    const hw = data.hidden_works;
    const hwAoa: (string | number)[][] = [
      ['Скрытые работы · возможные доплаты'],
      [hw.note],
      [],
      ['Работа', 'Специалист', 'Причина', 'Объём', 'Ед.', 'Мин.', 'Ср.', 'Макс.'],
      ...hw.items.map(item => [
        item.service, item.specialist, item.reason,
        item.volume, item.unit,
        item.total_min, item.total_avg, item.total_max,
      ]),
      [],
      ['Итого возможных доплат', '', '', '', '', hw.total_min, hw.total_avg, hw.total_max],
    ];
    const hwSheet = XLSX.utils.aoa_to_sheet(hwAoa);
    const hwFirst = 4;
    const hwLast = hwFirst + hw.items.length - 1;
    hwSheet['!cols'] = [{ wch: 28 }, { wch: 18 }, { wch: 40 }, { wch: 10 }, { wch: 8 }, { wch: 16 }, { wch: 16 }, { wch: 16 }];
    hwSheet['!merges'] = [
      { s: { r: 0, c: 0 }, e: { r: 0, c: 7 } },
      { s: { r: 1, c: 0 }, e: { r: 1, c: 7 } },
    ];
    cellAt(hwSheet, 0, 0).s = titleStyle;
    cellAt(hwSheet, 1, 0).s = noteStyle;
    if (hw.items.length) {
      styleTable(hwSheet, {
        headerRow: 3, firstData: hwFirst, lastData: hwLast, firstCol: 0, lastCol: 7,
        moneyCols: [5, 6, 7],
      });
    }
    const totalRow = hwLast + 2;
    for (let c = 0; c <= 7; c++) {
      cellAt(hwSheet, totalRow, c).s = { ...totalStyle, ...(c >= 5 ? { numFmt: MONEY_FMT, alignment: { horizontal: 'right', vertical: 'center' } } : {}) };
    }
    XLSX.utils.book_append_sheet(wb, hwSheet, 'Скрытые работы');
  }

  XLSX.writeFile(wb, 'Смета.xlsx');
};

// Палитра из index.css, чтобы PDF был в одном стиле с сайтом
type RGB = [number, number, number];
const PDF_ACCENT: RGB = [176, 123, 94];
const PDF_HEADING: RGB = [42, 42, 42];
const PDF_MUTED: RGB = [107, 99, 99];
const PDF_BORDER: RGB = [229, 229, 229];
const PDF_ZEBRA: RGB = [250, 246, 243];
const PDF_WHITE: RGB = [255, 255, 255];

const sourceNames: Record<string, string> = { seed: 'База', megastroy: 'Мегастрой', leroy: 'Леруа', lemana: 'Лемана ПРО' };
const sourceLabel = (source: string, region?: string | null) => {
  const src = !source ? '—' : sourceNames[source] ?? source;
  return region ? `${src}, ${region}` : src;
};

const getFinalY = (d: jsPDF) =>
  (d as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;

const fmtQty = (x: number) => x.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
const wastePct = (waste_factor: number) => `+${Math.round((waste_factor - 1) * 100)}%`;

export const exportPdf = async (data: EstimateExportData, city: string, priceMode: PriceMode = "avg") => {
  const doc = new jsPDF();
  const s = data.summary;

  const scaleMat = scaleFor(s, priceMode, 'materials');
  const scaleLab = scaleFor(s, priceMode, 'labor');
  const pLab = (val: number) => Math.round(val * scaleLab);

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

  // Хелпер для ссылок — использует дженерик T для сохранения типобезопасности
  const sourceLinks = <T,>(items: T[], col: number, getUrl: (item: T) => string | null | undefined) => ({
    didParseCell: (h: CellHookData) => {
      if (h.section === 'body' && h.column.index === col && getUrl(items[h.row.index])) {
        h.cell.styles.textColor = PDF_ACCENT;
      }
    },
    didDrawCell: (h: CellHookData) => {
      if (h.section !== 'body' || h.column.index !== col) return;
      const url = getUrl(items[h.row.index]);
      if (url) doc.link(h.cell.x, h.cell.y, h.cell.width, h.cell.height, { url });
    },
  });

  doc.setFontSize(22);
  doc.setTextColor(...PDF_HEADING);
  doc.text('Смета на ремонт', marginX, 22);
  doc.setDrawColor(...PDF_ACCENT);
  doc.setLineWidth(0.8);
  doc.line(marginX, 26, pageW - marginX, 26);
  doc.setFontSize(10);
  doc.setTextColor(...PDF_MUTED);
  
  const meta = `Город: ${city}    ·    Уровень цен: ${MODE_LABELS[priceMode]}    ·    Дата: ${new Date().toLocaleDateString('ru-RU')}`;
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
    ...sourceLinks(data.materials, 5, (m) => getActiveMaterialData(m, priceMode, scaleMat).activeUrl),
    startY: currentY + 4,
    head: [['Наименование', 'Кол-во', 'Ед.', 'Цена', 'Итого', 'Источник']],
    body: data.materials.map(m => {
      const act = getActiveMaterialData(m, priceMode, scaleMat);
      return [
        act.activeName, m.quantity, m.unit, formatPricePDF(Math.round(act.activePrice)), formatPricePDF(Math.round(act.activeTotal)), sourceLabel(act.activeSource, m.region)
      ];
    }),
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
    ...sourceLinks(data.labor, 6, (l) => l.source_url),
    startY: currentY + 4,
    head: [['Услуга', 'Специалист', 'Объём', 'Ед.', 'Цена', 'Итого', 'Источник']],
    body: data.labor.map(l => [
      l.service, l.specialist, l.volume, l.unit, formatPricePDF(pLab(l.price_avg)), formatPricePDF(pLab(l.total_avg)), sourceLabel(l.source, l.region)
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

  currentY = getFinalY(doc) + 14;
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
    body: data.materials.map(m => {
      const act = getActiveMaterialData(m, priceMode, scaleMat);
      return [
        act.activeName,
        `${fmtQty(m.base_quantity)} ${m.unit}`,
        wastePct(m.waste_factor),
        `${fmtQty(m.package_size)} ${m.unit}`,
        m.packs,
        `${fmtQty(m.quantity)} ${m.unit}`,
      ];
    }),
    columnStyles: {
      0: { halign: 'left', cellWidth: 58 },
      1: { halign: 'right', cellWidth: 32 },
      2: { halign: 'center', cellWidth: 18 },
      3: { halign: 'right', cellWidth: 28 },
      4: { halign: 'right', cellWidth: 20 },
      5: { halign: 'right', cellWidth: 26 }
    }
  });

  if (data.hidden_works && data.hidden_works.items.length > 0) {
    const hw = data.hidden_works;
    currentY = getFinalY(doc) + 14;
    if (currentY > pageH - 45) {
      doc.addPage();
      currentY = 20;
    }
    sectionHeading('Скрытые работы · возможные доплаты', currentY);
    doc.setFontSize(8);
    doc.setTextColor(...PDF_MUTED);
    const noteLines = doc.splitTextToSize(hw.note, pageW - marginX * 2);
    doc.text(noteLines, marginX, currentY + 5);
    autoTable(doc, {
      ...tableBase,
      startY: currentY + 5 + noteLines.length * 4,
      head: [['Работа', 'Специалист', 'Причина', 'Объём', 'Мин.', 'Макс.']],
      body: hw.items.map((item: HiddenWorkItem) => [
        item.service,
        item.specialist,
        item.reason,
        `${fmtQty(item.volume)} ${item.unit}`,
        formatPricePDF(item.total_min),
        formatPricePDF(item.total_max),
      ]),
      foot: [['Итого возможных доплат', '', '', '', formatPricePDF(hw.total_min), formatPricePDF(hw.total_max)]],
      footStyles: {
        fillColor: PDF_BORDER,
        textColor: PDF_HEADING,
        fontStyle: 'normal' as const,
        halign: 'right' as const,
      },
      columnStyles: {
        0: { halign: 'left', cellWidth: 32 },
        1: { halign: 'left', cellWidth: 24 },
        2: { halign: 'left', cellWidth: 52 },
        3: { halign: 'right', cellWidth: 18 },
        4: { halign: 'right', cellWidth: 24 },
        5: { halign: 'right', cellWidth: 32 },
      },
    });
  }

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