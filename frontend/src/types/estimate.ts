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
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
  updated_at?: string;
  source_url?: string | null;

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
