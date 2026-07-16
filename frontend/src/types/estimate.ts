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
  // запроса товара (коридор ±источники), она статична и не равна price для
  // min/max-запроса — баг, если использовать её как "цену уровня" (было в #291).
  price: number;
  total: number;
  // Запрошенный уровень комплектации строки — эхо request.tier.
  tier: "min" | "avg" | "max";
  // Коридор цены внутри выбранного SKU (прижат к −15%/+20% от средней на бэке,
  // PRICE_CORRIDOR) — не межтоварный разброс уровней, тот в min_item/max_item.
  price_min: number;
  price_avg: number;
  price_max: number;
  total_min: number;
  total_avg: number;
  total_max: number;
  source: string;
  region?: string | null;
  updated_at?: string;
  source_url?: string | null;

  // Все источники, чьи цены объединены в вилку (#333). Один элемент — цена от
  // одного источника; null — seed-цена. source/source_url указывают на представителя.
  sources?: string[] | null;

  // Источник, чья цена реально стала границей вилки price_min/price_max при
  // объединении нескольких источников (#348) — null, если источник один или
  // граница совпадает с представителем (source/source_url).
  min_source?: string | null;
  min_source_url?: string | null;
  max_source?: string | null;
  max_source_url?: string | null;

  // Материал по каждому tier — бэкенд отдаёт готовыми в /calculate (#349), присылает
  // все три всегда. Для 6 finish_key-позиций (ламинат, покраска стен/потолка, плитка,
  // обои, розетка, #331) это разные товары (name/source_url), для остальных — тот же
  // товар с ценой своего tier.
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
  // Цена/итог для запрошенного tier (см. MaterialItem.price) и сам tier.
  price: number;
  total: number;
  tier: "min" | "avg" | "max";
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
  updated_at?: string;
  source_url?: string | null;
  // Стадия ремонта строки: бэкенд отдаёт всегда (rough/pre_finish/finish).
  stage: LaborStage;

  // Коридор цены внутри выбранного tier (не межтоварный скачок, как у материалов —
  // у работ tier только сужает границы вилки одной и той же услуги/специалиста).
  price_min: number;
  price_max: number;
  total_min: number;
  total_max: number;

  // Все компании/прайс-листы, чьи цены объединены в вилку строки (#166/#333).
  sources?: string[] | null;

  // Компания, чья цена реально стала границей вилки price_min/price_max (#348) —
  // null, если источник один или граница совпадает с представителем (source/source_url).
  min_source?: string | null;
  min_source_url?: string | null;
  max_source?: string | null;
  max_source_url?: string | null;
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
