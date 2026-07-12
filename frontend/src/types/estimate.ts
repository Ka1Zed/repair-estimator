export interface MaterialItem {
  name: string;
  quantity: number;
  base_quantity: number;
  waste_factor: number;
  package_size: number;
  packs: number;
  unit: string;
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
  updated_at?: string;
  source_url?: string | null;
  // Все источники, чьи цены объединены в вилку (#333). Один элемент — цена от
  // одного источника; null — seed-цена. source/source_url указывают на представителя.
  sources?: string[] | null;
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
