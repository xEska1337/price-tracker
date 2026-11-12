import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from './api';
import { DealCard } from './components/DealCard';
import { LoginOverlay } from './components/LoginOverlay';
import { ProductCard } from './components/ProductCard';
import { ProductDetail } from './components/ProductDetail';
import { SettingsModal } from './components/SettingsModal';
import { toast, ToastHost } from './components/Toast';
import { INTERVALS, INTERVAL_LABELS, timeAgo } from './format';
import type { Deal, Interval, ProductSummary } from './types';

type Tab = 'products' | 'deals';

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tab, setTabState] = useState<Tab>(() =>
    window.location.hash === '#promocje' ? 'deals' : 'products',
  );

  const setTab = useCallback((next: Tab) => {
    setTabState(next);
    const hash = next === 'deals' ? '#promocje' : '#produkty';
    if (window.location.hash !== hash) window.history.replaceState(null, '', hash);
  }, []);

  const [loginOpen, setLoginOpen] = useState(false);
  const pendingLogins = useRef<Array<(ok: boolean) => void>>([]);

  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [productsLoading, setProductsLoading] = useState(true);
  const [url, setUrl] = useState('');
  const [addInterval, setAddInterval] = useState<Interval>('24h');
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const [deals, setDeals] = useState<Deal[]>([]);
  const [dealsFetchedAt, setDealsFetchedAt] = useState<string | null>(null);
  const [dealsLoading, setDealsLoading] = useState(false);
  const [dealsLoaded, setDealsLoaded] = useState(false);
  const [dealsBusy, setDealsBusy] = useState(false);
  const [dealQuery, setDealQuery] = useState('');
  const [dealsView, setDealsView] = useState<'grid' | 'list'>(() =>
    window.localStorage.getItem('pricetrack:dealsView') === 'list' ? 'list' : 'grid',
  );
  const [productsView, setProductsView] = useState<'grid' | 'list'>(() =>
    window.localStorage.getItem('pricetrack:productsView') === 'list' ? 'list' : 'grid',
  );

  const upsertProduct = useCallback((summary: ProductSummary) => {
    setProducts((prev) => {
      const index = prev.findIndex((item) => item.id === summary.id);
      if (index === -1) return [summary, ...prev];
      const next = [...prev];
      next[index] = { ...next[index], ...summary };
      return next;
    });
  }, []);

  const loadProducts = useCallback(async () => {
    try {
      setProducts(await api.listProducts());
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setProductsLoading(false);
    }
  }, []);

  const loadDeals = useCallback(async () => {
    setDealsLoading(true);
    try {
      const data = await api.getDeals();
      setDeals(data.deals ?? []);
      setDealsFetchedAt(data.fetched_at ?? null);
      setDealsLoaded(true);
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setDealsLoading(false);
    }
  }, []);

  useEffect(() => {
    api.setUnauthorizedHandler(
      () =>
        new Promise<boolean>((resolve) => {
          pendingLogins.current.push(resolve);
          setLoginOpen(true);
        }),
    );
    return () => api.setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    void loadProducts();
  }, [loadProducts]);

  useEffect(() => {
    if (tab === 'deals' && !dealsLoaded && !dealsLoading) void loadDeals();
  }, [tab, dealsLoaded, dealsLoading, loadDeals]);

  useEffect(() => {
    window.localStorage.setItem('pricetrack:dealsView', dealsView);
  }, [dealsView]);

  useEffect(() => {
    window.localStorage.setItem('pricetrack:productsView', productsView);
  }, [productsView]);

  async function handleSubmitLogin(password: string): Promise<boolean> {
    const ok = await api.login(password);
    if (ok) {
      const pending = pendingLogins.current;
      pendingLogins.current = [];
      for (const resolve of pending) resolve(true);
      setLoginOpen(false);
      toast('Logged in', 'success');
      void loadProducts();
      void loadDeals();
    }
    return ok;
  }

  async function handleAddProduct(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || adding) return;
    setAdding(true);
    try {
      const { product, duplicate } = await api.addProduct(trimmed, addInterval);
      setProducts((prev) => [product, ...prev.filter((item) => item.id !== product.id)]);
      if (duplicate) {
        toast('This URL is already tracked — showing the existing product', 'info');
      } else if (product.status === 'active' && product.last_price !== null) {
        toast('Product added — price is being tracked', 'success');
      } else if (product.status === 'unsupported') {
        toast(
          'Added, but no price could be read from that page — open the product for how to fix it',
          'error',
        );
      } else if (product.status === 'failed') {
        toast('Added, but the store blocked the request — open the product for how to fix it', 'error');
      } else {
        toast(product.last_error || 'Added, but the first price check failed', 'error');
      }
      setUrl('');
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setAdding(false);
    }
  }

  async function handleRefreshProduct(id: string): Promise<void> {
    try {
      const summary = await api.scrapeProduct(id);
      upsertProduct(summary);
      if (summary.status === 'active' && summary.last_price !== null) {
        toast('Price refreshed', 'success');
      } else if (summary.status === 'unsupported') {
        toast('No price found on that page — open the product for how to fix it', 'error');
      } else {
        toast(summary.last_error || 'Could not refresh the price', 'error');
      }
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    }
  }

  async function handleDeleteProduct(id: string): Promise<boolean> {
    try {
      await api.deleteProduct(id);
      setProducts((prev) => prev.filter((item) => item.id !== id));
      setOpenId((current) => (current === id ? null : current));
      toast('Product deleted', 'info');
      return true;
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
      return false;
    }
  }

  async function handleRefreshDeals() {
    if (dealsBusy) return;
    setDealsBusy(true);
    try {
      const result = await api.refreshDeals();
      toast(`Fetched ${result.count} ${countDeals(result.count)}`, 'success');
      await loadDeals();
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setDealsBusy(false);
    }
  }

  const query = dealQuery.trim().toLowerCase();
  const visibleDeals = query
    ? deals.filter((deal) =>
        `${deal.title ?? ''} ${deal.merchant ?? ''}`.toLowerCase().includes(query),
      )
    : deals;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">PriceTrack</span>
          <nav className="tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'products'}
              className={`tab ${tab === 'products' ? 'tab-active' : ''}`}
              onClick={() => setTab('products')}
            >
              Products
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'deals'}
              className={`tab ${tab === 'deals' ? 'tab-active' : ''}`}
              onClick={() => setTab('deals')}
            >
              Deals
            </button>
          </nav>
          <button
            type="button"
            className="btn btn-ghost btn-sm settings-btn"
            onClick={() => setSettingsOpen(true)}
            aria-label="Settings"
            title="Settings"
          >
            ⚙ Settings
          </button>
        </div>
      </header>

      <main className="content">
        {tab === 'products' ? (
          <section className="panel">
            <form className="add-row" onSubmit={handleAddProduct}>
              <input
                className="add-input"
                type="url"
                inputMode="url"
                placeholder="Paste a product link…"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                aria-label="Product URL"
              />
              <select
                className="add-interval"
                value={addInterval}
                onChange={(event) => setAddInterval(event.target.value as Interval)}
                aria-label="Check frequency"
              >
                {INTERVALS.map((value) => (
                  <option key={value} value={value}>
                    {INTERVAL_LABELS[value]}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn btn-primary" disabled={adding || !url.trim()}>
                {adding ? <span className="spinner" aria-hidden="true" /> : null}
                Add
              </button>
              <div className="view-toggle" role="group" aria-label="Products layout">
                <button
                  type="button"
                  className={`view-btn ${productsView === 'grid' ? 'view-btn-active' : ''}`}
                  aria-pressed={productsView === 'grid'}
                  aria-label="Grid view"
                  title="Grid view"
                  onClick={() => setProductsView('grid')}
                >
                  ▦
                </button>
                <button
                  type="button"
                  className={`view-btn ${productsView === 'list' ? 'view-btn-active' : ''}`}
                  aria-pressed={productsView === 'list'}
                  aria-label="List view"
                  title="List view"
                  onClick={() => setProductsView('list')}
                >
                  ☰
                </button>
              </div>
            </form>

            {productsLoading ? (
              <p className="empty">Loading products…</p>
            ) : products.length === 0 ? (
              <div className="empty empty-hint">
                <p className="empty-title">You're not tracking any products yet</p>
                <p className="empty-text">
                  Paste a product link from any store above — PriceTrack will fetch the first price
                  and start checking it at the selected interval.
                </p>
              </div>
            ) : (
              <div className={productsView === 'list' ? 'product-list' : 'grid'}>
                {products.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    view={productsView}
                    onOpen={setOpenId}
                    onRefresh={handleRefreshProduct}
                    onDelete={handleDeleteProduct}
                  />
                ))}
              </div>
            )}
          </section>
        ) : (
          <section className="panel">
            <div className="deals-toolbar">
              <input
                className="search-input"
                type="search"
                placeholder="Search deals…"
                value={dealQuery}
                onChange={(event) => setDealQuery(event.target.value)}
                aria-label="Search deals"
              />
              <span className="muted small">
                {dealsFetchedAt ? `updated ${timeAgo(dealsFetchedAt)}` : 'not fetched yet'}
              </span>
              <div className="view-toggle" role="group" aria-label="Deals layout">
                <button
                  type="button"
                  className={`view-btn ${dealsView === 'grid' ? 'view-btn-active' : ''}`}
                  aria-pressed={dealsView === 'grid'}
                  aria-label="Grid view"
                  title="Grid view"
                  onClick={() => setDealsView('grid')}
                >
                  ▦
                </button>
                <button
                  type="button"
                  className={`view-btn ${dealsView === 'list' ? 'view-btn-active' : ''}`}
                  aria-pressed={dealsView === 'list'}
                  aria-label="List view"
                  title="List view"
                  onClick={() => setDealsView('list')}
                >
                  ☰
                </button>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={dealsBusy}
                onClick={handleRefreshDeals}
              >
                {dealsBusy ? <span className="spinner" aria-hidden="true" /> : null}
                Refresh
              </button>
            </div>

            {dealsLoading ? (
              <p className="empty">Loading deals…</p>
            ) : visibleDeals.length === 0 ? (
              <div className="empty empty-hint">
                <p className="empty-title">
                  {query ? 'No results' : 'No current deals'}
                </p>
                <p className="empty-text">
                  {query
                    ? 'Change your search or clear the field.'
                    : 'Click “Refresh” to fetch the latest deals from pepper.pl.'}
                </p>
              </div>
            ) : (
              <div className={dealsView === 'list' ? 'deal-list' : 'grid grid-deals'}>
                {visibleDeals.map((deal) => (
                  <DealCard key={deal.id} deal={deal} view={dealsView} />
                ))}
              </div>
            )}
          </section>
        )}
      </main>

      {openId ? (
        <ProductDetail
          id={openId}
          onClose={() => setOpenId(null)}
          onUpdated={upsertProduct}
          onDelete={handleDeleteProduct}
        />
      ) : null}

      <LoginOverlay open={loginOpen} onLogin={handleSubmitLogin} />
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <ToastHost />
    </div>
  );
}

function countDeals(count: number): string {
  return count === 1 ? 'deal' : 'deals';
}
