import type {
  DealsRefreshResponse,
  DealsResponse,
  Interval,
  ProductDetail,
  ProductSummary,
  RangeParam,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, message: string, detail: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

type UnauthorizedHandler = () => Promise<boolean>;

let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
}

function detailFrom(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const entry = item as { msg?: unknown; loc?: unknown };
          const msg = typeof entry.msg === 'string' ? entry.msg : '';
          const loc = Array.isArray(entry.loc) ? entry.loc.join('.') : '';
          return loc ? `${loc}: ${msg}` : msg;
        }
        return '';
      })
      .filter(Boolean);
    if (parts.length) return parts.join('; ');
  }
  return null;
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
  }
  const detail = detailFrom(body);
  if (res.status === 401) return new ApiError(401, detail ?? 'Login required', detail);
  if (res.status === 404) return new ApiError(404, detail ?? 'Product not found', detail);
  return new ApiError(res.status, detail ?? `Server error (${res.status})`, detail);
}

async function send(path: string, opts: RequestOptions, retried: boolean): Promise<Response> {
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? 'GET',
    credentials: 'same-origin',
    headers: opts.body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });

  if (res.status === 401 && !retried) {
    const loggedIn = unauthorizedHandler ? await unauthorizedHandler() : false;
    if (loggedIn) return send(path, opts, true);
  }
  if (!res.ok) throw await toApiError(res);
  return res;
}

async function requestJson<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts, false);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof TypeError) return 'Cannot reach the server';
  return e instanceof Error && e.message ? e.message : 'Unknown error';
}

export function listProducts(): Promise<ProductSummary[]> {
  return requestJson<ProductSummary[]>('/products');
}

export interface AddProductResult {
  product: ProductSummary;

  duplicate: boolean;

  status: number;
}

export async function addProduct(url: string, interval: Interval): Promise<AddProductResult> {
  const res = await send('/products', { method: 'POST', body: { url, interval } }, false);
  const product = (await res.json()) as ProductSummary;
  return { product, duplicate: res.status === 200, status: res.status };
}

export function patchProduct(id: string, patch: { interval?: Interval }): Promise<ProductSummary> {
  return requestJson<ProductSummary>(`/products/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: patch,
  });
}

export function scrapeProduct(id: string): Promise<ProductSummary> {
  return requestJson<ProductSummary>(`/products/${encodeURIComponent(id)}/scrape`, { method: 'POST' });
}

export function addManualPrice(id: string, price: number): Promise<ProductSummary> {
  return requestJson<ProductSummary>(`/products/${encodeURIComponent(id)}/price`, {
    method: 'POST',
    body: { price },
  });
}

export async function deleteProduct(id: string): Promise<void> {
  await send(`/products/${encodeURIComponent(id)}`, { method: 'DELETE' }, false);
}

export function getProduct(id: string, range: RangeParam): Promise<ProductDetail> {
  return requestJson<ProductDetail>(`/products/${encodeURIComponent(id)}?range=${range}`);
}

export interface AdapterPromptResponse {
  domain: string;
  url: string;
  prompt: string;
  html_chars: number;
}

export interface AdapterInstallResponse {
  domain: string;
  price: number;
  extractor: string;
  product: ProductSummary;
}

export function getAdapterPrompt(productId: string): Promise<AdapterPromptResponse> {
  return requestJson<AdapterPromptResponse>(
    `/products/${encodeURIComponent(productId)}/adapter-prompt`,
    { method: 'POST' },
  );
}

export interface StoredAdapter {
  domain: string;
  currency: string | null;
  selectors: Record<string, string>;
  file: string;
}

export interface UserAdapterEntry {
  domain: string;
  selectors: Record<string, string>;
  currency: string | null;
  file: string;
}

export function listAdapters(): Promise<{ user: UserAdapterEntry[] }> {
  return requestJson<{ user: UserAdapterEntry[] }>('/adapters');
}

export function deleteAdapter(domain: string): Promise<void> {
  return requestJson<void>(`/adapters/${encodeURIComponent(domain)}`, { method: 'DELETE' });
}

export function installAdapter(productId: string, adapter: string): Promise<AdapterInstallResponse> {
  return requestJson<AdapterInstallResponse>('/adapters', {
    method: 'POST',
    body: { product_id: productId, adapter },
  });
}

export interface StoreInfo {
  domain: string;
  name: string;
  tier?: string;
  verified?: boolean;
  note: string;
}

export interface StoresResponse {
  tiers: Record<string, string>;
  stores: StoreInfo[];
  blocked: StoreInfo[];
}

export function getStores(): Promise<StoresResponse> {
  return requestJson<StoresResponse>('/stores');
}

export function isPriceUnavailable(product: {
  status: string;
  last_price: number | null;
}): boolean {
  return (
    product.status === 'unsupported' ||
    product.status === 'failed' ||
    (product.status === 'active' && product.last_price === null)
  );
}

export function getDeals(): Promise<DealsResponse> {
  return requestJson<DealsResponse>('/deals');
}

export function refreshDeals(): Promise<DealsRefreshResponse> {
  return requestJson<DealsRefreshResponse>('/deals/refresh', { method: 'POST' });
}

export async function login(password: string): Promise<boolean> {
  const res = await fetch('/api/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  return res.ok;
}
