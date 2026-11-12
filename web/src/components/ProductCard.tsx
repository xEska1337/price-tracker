import { useState } from 'react';
import { checkedAgo, firstLetter, fmtPct, fmtPrice, imageFallback, proxiedImage } from '../format';
import type { ProductStatus, ProductSummary } from '../types';
import { Sparkline } from './Sparkline';

const STATUS_LABEL: Partial<Record<ProductStatus, string>> = {
  failed: 'error',
  unsupported: 'not supported',
  paused: 'paused',
};

interface ProductCardProps {
  product: ProductSummary;
  view?: 'grid' | 'list';
  onOpen: (id: string) => void;
  onRefresh: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<boolean>;
}

export function ProductCard({ product, view = 'grid', onOpen, onRefresh, onDelete }: ProductCardProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  const delta = product.delta_7d_pct;
  const trend = delta === null || delta === 0 ? 'flat' : delta < 0 ? 'down' : 'up';

  const failedCheck = product.last_price === null && Boolean(product.last_error);
  const statusLabel =
    STATUS_LABEL[product.status] ?? (failedCheck ? (product.status === 'unsupported' ? 'not supported' : 'error') : null);
  const statusKind = STATUS_LABEL[product.status] ? product.status : 'failed';
  const showImage = product.image_url && !imgFailed;
  const list = view === 'list';

  async function handleRefresh(event: React.MouseEvent) {
    event.stopPropagation();
    if (refreshing) return;
    setRefreshing(true);
    try {
      await onRefresh(product.id);
    } finally {
      setRefreshing(false);
    }
  }

  async function handleDelete(event: React.MouseEvent) {
    event.stopPropagation();
    if (removing) return;
    if (!window.confirm(`Remove “${product.title || product.domain}” from the list?`)) return;
    setRemoving(true);
    const removed = await onDelete(product.id);
    if (!removed) setRemoving(false);
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(product.id);
    }
  }

  return (
    <article
      className={`card product-card ${list ? 'view-list' : ''} status-${product.status}`}
      onClick={() => onOpen(product.id)}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-label={`${product.title || product.domain} — details`}
    >
      <button
        type="button"
        className="icon-btn card-delete"
        title="Delete product"
        aria-label="Delete product"
        disabled={removing}
        onClick={handleDelete}
      >
        {removing ? <span className="spinner" aria-hidden="true" /> : '✕'}
      </button>

      <div className={list ? 'thumb thumb-sm' : 'thumb'}>
        {showImage ? (
          <img
            src={proxiedImage(product.image_url)}
            alt=""
            loading="lazy"
            onError={(event) => {
              imageFallback(event, product.image_url);
              if (!product.image_url || event.currentTarget.dataset.fallback === 'original') {
                setImgFailed(true);
              }
            }}
          />
        ) : (
          <span className="thumb-letter" aria-hidden="true">
            {firstLetter(product.title)}
          </span>
        )}
        {!list && statusLabel ? (
          <span className={`pill pill-${statusKind}`} title={product.last_error ?? undefined}>
            {statusLabel}
          </span>
        ) : null}
      </div>

      <div className="card-body">
        <h3 className={list ? 'clamp-1 card-title' : 'clamp-2 card-title'} title={product.title || product.domain}>
          {product.title || product.domain}
        </h3>
        {list && statusLabel ? (
          <span className={`pill list-pill pill-${statusKind}`} title={product.last_error ?? undefined}>
            {statusLabel}
          </span>
        ) : null}

        <div className="price-row">
          <span className="price">{fmtPrice(product.last_price, product.currency)}</span>
          <span className={`trend trend-${trend}`} title="7-day change">
            {trend === 'down' ? `▼ ${fmtPct(Math.abs(delta as number), false)}` : null}
            {trend === 'up' ? `▲ ${fmtPct(Math.abs(delta as number), false)}` : null}
            {trend === 'flat' ? '—' : null}
          </span>
        </div>

        <Sparkline points={product.sparkline} width={list ? 96 : 120} />

        <div className="card-footer">
          <span className="muted small">
            {product.last_checked_at ? `checked ${checkedAgo(product.last_checked_at)}` : 'not checked yet'}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={refreshing}
            onClick={handleRefresh}
          >
            {refreshing ? <span className="spinner" aria-hidden="true" /> : null}
            Refresh
          </button>
        </div>

        <span className="muted small domain">{product.domain}</span>
      </div>
    </article>
  );
}
