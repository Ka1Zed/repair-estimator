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
