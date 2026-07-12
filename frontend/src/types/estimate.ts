export interface PriceVariant {
  name: string;
  price: number;
  total: number;
  source: string;
  source_url?: string | null;
}

export interface MaterialItem {
  name: string;
  quantity: number;
  base_quantity: number;
  waste_factor: number;
  package_size: number;
  packs: number;
  unit: string;
  // Цена/итог ИМЕННО для запрошенного tier (backend/app/schemas/estimate.py) —
  // то, что реально нужно показывать как "цену этого уровня". НЕ путать с
  // price_avg/total_avg ниже: это средняя ЦЕНА ВНУТРИ разрешённого для этого
  // запроса товара (корид ор ±источники), она статична и не равна price для
  // min/max-запроса — баг, если использовать её как "цену уровня" (было в #291).
  price: number;
  total: number;
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
  updated_at?: string;
  source_url?: string | null;

  // Все источники, чьи цены объединены в вилку (#333). Один элемент — цена от
  // одного источника; null — seed-цена. source/source_url указывают на представителя.
  sources?: string[] | null;

  // Материал по каждому tier (#291): для 6 finish_key-позиций (ламинат, покраска
  // стен/потолка, плитка, обои, розетка) это разные товары (name/source_url),
  // для остальных — тот же товар с ценой своего tier. Заполняется на фронте
  // из трёх параллельных запросов /calculate с tier=min/avg/max (Workspace.tsx).
  min_item?: PriceVariant | null;
  avg_item?: PriceVariant | null;
  max_item?: PriceVariant | null;
}

export type LaborStage = "rough" | "pre_finish" | "finish";

export interface LaborItem {
  service: string;
  specialist: string;
  volume: number;
  unit: string;
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
  source_url?: string | null;
  stage?: LaborStage;

  // Коридор цены внутри выбранного tier (не межтоварный скачок, как у материалов —
  // у работ tier только сужает границы вилки одной и той же услуги/специалиста).
  price_min?: number;
  price_max?: number;
  total_min?: number;
  total_max?: number;

  // Все компании/прайс-листы, чьи цены объединены в вилку строки (#166/#333).
  // Бэкенд не сообщает, ЧЬЯ именно цена дала price_min/price_max — только
  // список участников и один "представительный" source/source_url.
  sources?: string[] | null;
}

export interface HiddenWorkItem {
  service: string;
  specialist: string;
  reason: string;
  volume: number;
  unit: string;
  price_avg: number;
  total_min: number;
  total_avg: number;
  total_max: number;
  source: string;
}

export interface HiddenWorks {
  note: string;
  total_min: number;
  total_avg: number;
  total_max: number;
  items: HiddenWorkItem[];
}
