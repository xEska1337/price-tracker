import { useEffect, useRef, useState } from 'react';
import type { ChartConfiguration } from 'chart.js';
import * as api from '../api';
import {
  firstLetter,
  imageFallback,
  proxiedImage,
  fmtAxisPrice,
  fmtDateTime,
  fmtPct,
  fmtPrice,
  fmtStatNumber,
  fmtTick,
  INTERVALS,
  INTERVAL_LABELS,
  RANGES,
  RANGE_LABELS,
} from '../format';
import type {
  Interval,
  ProductDetail as ProductDetailData,
  ProductSummary,
  RangeParam,
} from '../types';
import { InstalledAdapterPanel } from './InstalledAdapterPanel';
import { NotSupportedHelp } from './NotSupportedHelp';
import { toast } from './Toast';

const ACCENT = '#4f8cff';
const DOWN = '#22c55e';
const MUTED = '#8b93a3';
const GRID = 'rgba(42,46,55,0.7)';

interface ProductDetailProps {
  id: string;
  onClose: () => void;
  onUpdated: (product: ProductSummary) => void;
  onDelete?: (id: string) => Promise<boolean>;
}

export function ProductDetail({ id, onClose, onUpdated, onDelete }: ProductDetailProps) {
  const [range, setRange] = useState<RangeParam>('30d');
  const [detail, setDetail] = useState<ProductDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [scraping, setScraping] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [savingPrice, setSavingPrice] = useState(false);
  const [priceInput, setPriceInput] = useState('');
  const [imgFailed, setImgFailed] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const manualRef = useRef<HTMLDetailsElement>(null);
  const prevIdRef = useRef(id);
  if (prevIdRef.current !== id) {
    prevIdRef.current = id;
    setPriceInput('');
    setImgFailed(false);
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError(null);
    api
      .getProduct(id, range)
      .then((data) => {
        if (!alive) return;
        setDetail(data);
        setLoading(false);
        onUpdated(data);
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setLoading(false);
        setLoadError(api.errMessage(error));
      });
    return () => {
      alive = false;
    };

  }, [id, range, reloadKey]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  useEffect(() => {
    if (!detail) return;

    let cancelled = false;
    let chart: { destroy: () => void } | null = null;

    (async () => {

      const chartModule = await import('chart.js/auto');
      if (cancelled || !canvasRef.current) return;
      const ChartCtor = chartModule.default ?? chartModule.Chart;
      chart = new ChartCtor(canvasRef.current, buildChartConfig(detail, range));
    })().catch((error: unknown) => {
      if (!cancelled) toast(`Could not load the chart: ${api.errMessage(error)}`, 'error');
    });

    return () => {
      cancelled = true;
      chart?.destroy();
      chart = null;
    };
  }, [detail, range]);

  function mergeSummary(summary: ProductSummary) {
    setDetail((prev) => (prev ? { ...prev, ...summary } : prev));
    onUpdated(summary);
  }

  async function handleScrape() {
    if (scraping) return;
    setScraping(true);
    try {
      const summary = await api.scrapeProduct(id);
      mergeSummary(summary);
      setReloadKey((key) => key + 1);
      if (summary.status === 'active' && summary.last_price !== null) {
        toast('Price refreshed', 'success');
      } else if (summary.status === 'unsupported') {
        toast('No price found on that page — see the guidance above', 'error');
      } else {
        toast(summary.last_error || 'Could not refresh the price', 'error');
      }
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setScraping(false);
    }
  }

  async function handleDelete() {
    if (!onDelete || deleting) return;
    const label = detail?.title || detail?.domain || 'this product';
    if (!window.confirm(`Remove “${label}” and its price history?`)) return;
    setDeleting(true);
    const removed = await onDelete(id);
    if (removed) onClose();
    else setDeleting(false);
  }

  async function handleIntervalChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const interval = event.target.value as Interval;
    try {
      const summary = await api.patchProduct(id, { interval });
      mergeSummary(summary);
      toast(`Interval: ${INTERVAL_LABELS[interval]}`, 'info');
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    }
  }

  async function handleSavePrice(event: React.FormEvent) {
    event.preventDefault();
    if (savingPrice) return;
    const raw = priceInput.replace(',', '.').trim();
    const price = Number(raw);
    if (!raw || !Number.isFinite(price) || price < 0) {
      toast('Enter a valid price', 'error');
      return;
    }
    setSavingPrice(true);
    try {
      const summary = await api.addManualPrice(id, price);
      mergeSummary(summary);
      setPriceInput('');
      setReloadKey((key) => key + 1);
      manualRef.current?.removeAttribute('open');
      toast('Manual price saved', 'success');
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setSavingPrice(false);
    }
  }

  const currency = detail?.currency ?? null;
  const stats = detail?.stats;
  const hasPrice = detail?.last_price !== null && detail?.last_price !== undefined;
  const showImage = detail?.image_url && !imgFailed;

  return (
    <div
      className="overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal detail-modal"
        role="dialog"
        aria-modal="true"
        aria-label={detail?.title || 'Product details'}
      >
        <div className="modal-toolbar">
          {onDelete ? (
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-danger"
              onClick={handleDelete}
              disabled={deleting}
              title="Delete this product and its history"
            >
              {deleting ? <span className="spinner" aria-hidden="true" /> : null}
              Delete product
            </button>
          ) : null}
          <button type="button" className="icon-btn modal-close" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        {loadError ? (
          <div className="detail-error">
            <p>{loadError}</p>
            <button type="button" className="btn btn-ghost" onClick={() => setReloadKey((k) => k + 1)}>
              Try again
            </button>
          </div>
        ) : (
          <>
          {detail && !hasPrice && detail.last_error ? (
            <NotSupportedHelp
              status={detail.status === 'unsupported' ? 'unsupported' : 'failed'}
              domain={detail.domain}
              lastError={detail.last_error}
              productId={detail.id}
              onAdapterInstalled={() => setReloadKey((key) => key + 1)}
            />
          ) : null}

          <div className="detail-grid">
            <section className="detail-left">
              <div className="detail-image">
                {showImage ? (
                  <img
                    src={proxiedImage(detail?.image_url)}
                    alt=""
                    onError={(event) => {
                      imageFallback(event, detail?.image_url ?? null);
                      setImgFailed(true);
                    }}
                  />
                ) : (
                  <span className="thumb-letter" aria-hidden="true">
                    {firstLetter(detail?.title)}
                  </span>
                )}
              </div>

              <h2 className="detail-title">{detail?.title || detail?.domain || 'Product'}</h2>
              <p className="muted small">{detail?.domain}</p>
              {detail ? <InstalledAdapterPanel domain={detail.domain} refreshKey={reloadKey} /> : null}
              {detail?.url ? (
                <a className="link" href={detail.url} target="_blank" rel="noopener noreferrer">
                  Open in store ↗
                </a>
              ) : null}

              <div className="detail-price-row">
                <span className="price price-xl">{fmtPrice(detail?.last_price ?? null, currency)}</span>
                {stats?.at_all_time_low ? <span className="chip chip-low">all-time low</span> : null}
              </div>

              <label className="field">
                <span className="field-label">Check frequency</span>
                <select value={detail?.interval ?? '24h'} onChange={handleIntervalChange}>
                  {INTERVALS.map((value) => (
                    <option key={value} value={value}>
                      {INTERVAL_LABELS[value]}
                    </option>
                  ))}
                </select>
              </label>

              <button type="button" className="btn btn-primary" disabled={scraping} onClick={handleScrape}>
                {scraping ? <span className="spinner" aria-hidden="true" /> : null}
                Refresh now
              </button>

              <details className="manual-price" ref={manualRef}>
                <summary>Enter price manually</summary>
                <form className="manual-price-form" onSubmit={handleSavePrice}>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    inputMode="decimal"
                    placeholder={currency ? `Price (${currency})…` : 'Price…'}
                    value={priceInput}
                    onChange={(event) => setPriceInput(event.target.value)}
                  />
                  <button type="submit" className="btn btn-ghost" disabled={savingPrice}>
                    {savingPrice ? <span className="spinner" aria-hidden="true" /> : null}
                    Save
                  </button>
                </form>
              </details>
            </section>

            <section className="detail-right">
              <div className="range-row" role="group" aria-label="Chart range">
                {RANGES.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={`btn btn-sm ${value === range ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setRange(value)}
                  >
                    {RANGE_LABELS[value]}
                  </button>
                ))}
              </div>

              <div className="stats-row">
                <div className="stat">
                  <span className="stat-label">MIN</span>
                  <span className="stat-value" title={fmtPrice(stats?.min ?? null, currency)}>
                    {fmtStatNumber(stats?.min ?? null)}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">MAX</span>
                  <span className="stat-value" title={fmtPrice(stats?.max ?? null, currency)}>
                    {fmtStatNumber(stats?.max ?? null)}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">AVG</span>
                  <span className="stat-value" title={fmtPrice(stats?.avg ?? null, currency)}>
                    {fmtStatNumber(stats?.avg ?? null)}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">Δ 1D</span>
                  <DeltaValue value={stats?.delta_1d_pct ?? null} />
                </div>
                <div className="stat">
                  <span className="stat-label">Δ 7D</span>
                  <DeltaValue value={stats?.delta_7d_pct ?? null} />
                </div>
                <div className="stat">
                  <span className="stat-label">Δ 30D</span>
                  <DeltaValue value={stats?.delta_30d_pct ?? null} />
                </div>
              </div>

              <div className="chart-wrap">
                {loading ? <div className="chart-loading">Loading data…</div> : null}
                {!loading && (detail?.price_points.length ?? 0) < 2 ? (
                  <div className="chart-loading chart-empty">
                    Not enough measurements to draw a chart — the price will appear after the next
                    check.
                  </div>
                ) : (
                  <canvas ref={canvasRef} aria-label="Price chart" role="img" />
                )}
              </div>
              {(detail?.price_points.length ?? 0) >= 2 ? (
                <p className="muted small">
                  Dashed line: moving average. Green dot: all-time low.
                </p>
              ) : null}
            </section>
          </div>
          </>
        )}
      </div>
    </div>
  );
}

function DeltaValue({ value }: { value: number | null }) {
  const cls = value === null || value === 0 ? 'muted' : value < 0 ? 'delta-down' : 'delta-up';
  return <span className={`stat-value ${cls}`}>{fmtPct(value)}</span>;
}

function buildChartConfig(detail: ProductDetailData, range: RangeParam): ChartConfiguration<'line'> {
  const times = [...detail.price_points.map((p) => p.at), ...detail.moving_avg.map((p) => p.at)];
  const isoLabels = Array.from(new Set(times)).sort((a, b) => Date.parse(a) - Date.parse(b));
  const indexOf = new Map(isoLabels.map((iso, index) => [iso, index]));

  const priceData: (number | null)[] = new Array(isoLabels.length).fill(null);
  for (const point of detail.price_points) {
    const index = indexOf.get(point.at);
    if (index !== undefined) priceData[index] = point.price;
  }
  const avgData: (number | null)[] = new Array(isoLabels.length).fill(null);
  for (const point of detail.moving_avg) {
    const index = indexOf.get(point.at);
    if (index !== undefined) avgData[index] = point.price;
  }

  const latestPoint = detail.price_points[detail.price_points.length - 1];
  const atlIndex = detail.stats.at_all_time_low && latestPoint ? indexOf.get(latestPoint.at) ?? -1 : -1;

  const datasets: ChartConfiguration<'line'>['data']['datasets'] = [
    {
      label: 'Price',
      data: priceData,
      borderColor: ACCENT,
      backgroundColor: 'rgba(79,140,255,0.16)',
      borderWidth: 2,
      tension: 0.2,
      fill: true,
      spanGaps: true,
      pointRadius: (ctx) => (ctx.dataIndex === atlIndex ? 6 : 0),
      pointHoverRadius: (ctx) => (ctx.dataIndex === atlIndex ? 7 : 4),
      pointBackgroundColor: DOWN,
      pointBorderColor: '#0f1115',
      pointBorderWidth: 1,
    },
    {
      label: 'Moving average',
      data: avgData,
      borderColor: MUTED,
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderDash: [6, 4],
      tension: 0.2,
      fill: false,
      spanGaps: true,
      pointRadius: 0,
      pointHoverRadius: 3,
    },
  ];

  return {
    type: 'line',
    data: {
      labels: isoLabels.map((iso) => fmtTick(iso, range)),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: detail.moving_avg.length > 0,
          labels: { color: MUTED, boxWidth: 12, boxHeight: 2, usePointStyle: false },
        },
        tooltip: {
          backgroundColor: '#161a22',
          borderColor: '#2a2e37',
          borderWidth: 1,
          titleColor: '#e6e9ef',
          bodyColor: '#e6e9ef',
          displayColors: false,
          callbacks: {
            title: (items) => {
              const index = items[0]?.dataIndex ?? 0;
              return fmtDateTime(isoLabels[index]);
            },
            label: (item) =>
              `${item.dataset.label}: ${fmtPrice(item.parsed.y, detail.currency)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: GRID },
          border: { color: '#2a2e37' },
          ticks: {
            color: MUTED,
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: range === '7d' ? 7 : 6,
          },
        },
        y: {
          grid: { color: GRID },
          border: { color: '#2a2e37' },
          ticks: { color: MUTED, callback: (value) => fmtAxisPrice(Number(value)) },
        },
      },
    },
  };
}
