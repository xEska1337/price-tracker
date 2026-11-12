

export type Interval = '1h' | '6h' | '12h' | '24h' | '7d';

export type ProductStatus = 'active' | 'failed' | 'unsupported' | 'paused';

export type RangeParam = '7d' | '30d' | '90d' | 'all';

export interface ProductSummary {
  id: string;
  url: string;
  domain: string;
  title: string;
  image_url: string | null;
  currency: string | null;
  last_price: number | null;
  last_price_at: string | null;
  interval: Interval;
  status: ProductStatus;
  last_error: string | null;
  delta_7d_pct: number | null;
  delta_30d_pct: number | null;

  sparkline: number[];
  last_checked_at: string | null;
  next_check_at: string | null;
  created_at: string;
}

export interface PricePoint {
  at: string;
  price: number;
  in_stock: boolean;
}

export interface MovingAvgPoint {
  at: string;
  price: number;
}

export interface ProductStats {
  min: number | null;
  max: number | null;
  avg: number | null;
  current: number | null;
  at_all_time_low: boolean;
  delta_1d_pct: number | null;
  delta_7d_pct: number | null;
  delta_30d_pct: number | null;
}

export interface ProductDetail extends ProductSummary {
  price_points: PricePoint[];
  moving_avg: MovingAvgPoint[];
  stats: ProductStats;
}

export interface Deal {
  id: string;
  title: string;
  link: string;
  image_url: string | null;

  price_raw: string | null;
  merchant: string | null;
  category: string | null;
  snippet: string | null;
  published_at: string;
}

export interface DealsResponse {
  fetched_at: string | null;
  deals: Deal[];
}

export interface DealsRefreshResponse {
  count: number;
  fetched_at: string;
}
