import type { Interval, RangeParam } from './types';

const numberFmt = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const pctFmt = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const clockFmt = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' });

const dateTimeFmt = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const shortDateFmt = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: '2-digit' });

const longDateFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long' });

function toDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtPrice(value: number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const cur = currency && /^[A-Za-z]{3}$/.test(currency) ? currency.toUpperCase() : '';
  if (cur) {
    try {
      return new Intl.NumberFormat('en-GB', { style: 'currency', currency: cur }).format(value);
    } catch {}
  }
  return `${numberFmt.format(value)}`;
}

export function fmtAxisPrice(value: number): string {
  if (!Number.isFinite(value)) return '';
  if (Math.abs(value) >= 1000) {
    return `${Math.round(value / 1000) * 1000}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  return `${Math.round(value * 10) / 10}`;
}

export function fmtPct(value: number | null | undefined, sign = true): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const abs = pctFmt.format(Math.abs(value));
  if (value === 0) return '0.0%';
  if (!sign) return `${abs}%`;
  return `${value > 0 ? '+' : '-'}${abs}%`;
}

export function timeAgo(iso: string | null | undefined): string {
  const d = toDate(iso);
  if (!d) return '—';
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return 'in a moment';
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min} min ago`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return '1 day ago';
  return `${days} days ago`;
}

export function checkedAgo(iso: string | null | undefined): string {
  const d = toDate(iso);
  if (!d) return 'not checked yet';
  if (isSameDay(d, new Date())) return clockFmt.format(d);
  return timeAgo(iso);
}

export function publishedAgo(iso: string | null | undefined): string {
  const d = toDate(iso);
  if (!d) return '';
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return '';
  if (diffMs < 60_000) return 'just now';
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)} min ago`;
  if (diffMs < 24 * 3_600_000) return `${Math.floor(diffMs / 3_600_000)} h ago`;
  if (isYesterday(d)) return 'yesterday';
  return longDateFmt.format(d);
}

function isYesterday(d: Date): boolean {
  const y = new Date();
  y.setDate(y.getDate() - 1);
  return isSameDay(d, y);
}

export function fmtDateTime(iso: string | null | undefined): string {
  const d = toDate(iso);
  return d ? dateTimeFmt.format(d) : '';
}

export function fmtClock(iso: string | null | undefined): string {
  const d = toDate(iso);
  return d ? clockFmt.format(d) : '';
}

export function fmtTick(iso: string, range: RangeParam): string {
  const d = toDate(iso);
  if (!d) return iso;
  if (range === '7d') return `${shortDateFmt.format(d)} ${clockFmt.format(d)}`;
  return shortDateFmt.format(d);
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  );
}

export const INTERVALS: Interval[] = ['1h', '6h', '12h', '24h', '7d'];

export const INTERVAL_LABELS: Record<Interval, string> = {
  '1h': '1 hour',
  '6h': '6 hours',
  '12h': '12 hours',
  '24h': '24 hours',
  '7d': '7 days',
};

export const RANGES: RangeParam[] = ['7d', '30d', '90d', 'all'];

export const RANGE_LABELS: Record<RangeParam, string> = {
  '7d': '7 days',
  '30d': '30 days',
  '90d': '90 days',
  all: 'All',
};

export function firstLetter(title: string | null | undefined): string {
  const t = (title ?? '').trim();
  return t ? t.charAt(0).toUpperCase() : '?';
}

export function proxiedImage(src: string | null | undefined): string {
  if (!src) return '';
  if (src.startsWith('/') || src.startsWith('data:')) return src;
  return `/api/image?url=${encodeURIComponent(src)}`;
}

export function imageFallback(event: React.SyntheticEvent<HTMLImageElement>, original: string | null): void {
  const img = event.currentTarget;
  if (original && img.dataset.fallback !== 'original') {
    img.dataset.fallback = 'original';
    img.src = original;
  }
}

export function fmtStatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}
