export interface MaterialItem {
  name: string;
  quantity: number;
  unit: string;
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
  updated_at?: string;
}

export interface LaborItem {
  service: string;
  specialist: string;
  volume: number;
  unit: string;
  price_avg: number;
  total_avg: number;
  source: string;
  region?: string | null;
}
