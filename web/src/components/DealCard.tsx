import { useState } from 'react';
import { imageFallback, proxiedImage, publishedAgo } from '../format';
import type { Deal } from '../types';

interface DealCardProps {
  deal: Deal;

  view?: 'grid' | 'list';
}

export function DealCard({ deal, view = 'grid' }: DealCardProps) {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = Boolean(deal.image_url) && !imgFailed;
  const list = view === 'list';

  const thumb = (
    <div className={list ? 'deal-thumb deal-thumb-sm' : 'deal-thumb'}>
      {showImage ? (
        <img
          src={proxiedImage(deal.image_url)}
          alt=""
          width={list ? 72 : 150}
          height={list ? 72 : 150}
          loading="lazy"
          onError={(event) => {
            imageFallback(event, deal.image_url ?? null);
            if (!deal.image_url || event.currentTarget.dataset.fallback === 'original') {
              setImgFailed(true);
            }
          }}
        />
      ) : (
        <span className="thumb-letter" aria-hidden="true">
          ?
        </span>
      )}
    </div>
  );

  const chips = (
    <div className="chip-row">
      {deal.merchant || deal.price_raw ? (
        <span className="chip chip-price">
          {[deal.merchant, deal.price_raw].filter(Boolean).join(' · ')}
        </span>
      ) : null}
      {deal.category ? <span className="chip chip-muted">{deal.category}</span> : null}
    </div>
  );

  const link = (
    <a
      className={list ? 'deal-row' : 'card deal-card'}
      href={deal.link}
      target="_blank"
      rel="noopener noreferrer"
      title={deal.title || deal.link}
    >
      {thumb}
      {list ? (
        <div className="deal-row-body">
          <h3 className="clamp-1 deal-title">{deal.title || '(no title)'}</h3>
          {deal.snippet ? <p className="clamp-1 deal-snippet">{deal.snippet}</p> : null}
          <div className="deal-row-meta">
            {chips}
            <span className="muted small">{publishedAgo(deal.published_at)}</span>
          </div>
        </div>
      ) : (
        <div className="card-body">
          <h3 className="clamp-3 deal-title">{deal.title || '(no title)'}</h3>
          {chips}
          {deal.snippet ? <p className="clamp-2 deal-snippet">{deal.snippet}</p> : null}
          <div className="card-footer">
            <span className="muted small">{publishedAgo(deal.published_at)}</span>
            {deal.merchant ? null : <span className="muted small">Open ↗</span>}
          </div>
        </div>
      )}
    </a>
  );

  return link;
}
