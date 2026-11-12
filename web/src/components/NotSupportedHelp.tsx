import { useEffect, useState } from 'react';
import * as api from '../api';
import { AdapterWizard } from './AdapterWizard';

interface StoreInfo {
  domain: string;
  name: string;
  tier?: string;
  verified?: boolean;
  note: string;
}

interface StoresResponse {
  tiers: Record<string, string>;
  stores: StoreInfo[];
  blocked: StoreInfo[];
}

interface NotSupportedHelpProps {
  status: 'unsupported' | 'failed';
  domain: string;
  lastError: string | null;
  productId: string;
  onAdapterInstalled?: () => void;
}

const TIER_ORDER = ['jsonld', 'opengraph', 'adapter', 'browser'];

export function NotSupportedHelp({
  status,
  domain,
  lastError,
  productId,
  onAdapterInstalled,
}: NotSupportedHelpProps) {
  const [stores, setStores] = useState<StoresResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .getStores()
      .then((data) => {
        if (alive) setStores(data);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const blocked = stores?.blocked.find((entry) => domain.endsWith(entry.domain));
  const title =
    status === 'unsupported' ? 'Price not found on this page' : 'The price could not be fetched';

  return (
    <section className="help-panel" aria-label="Why is there no price?">
      <h3 className="help-title">{title}</h3>
      <p className="help-intro">
        {status === 'unsupported'
          ? `${domain} loaded, but PriceTrack could not read a price from it. Here is how to get it working:`
          : `${domain} did not return a readable price (blocked, unreachable, or the request failed). Here is how to get it working:`}
      </p>
      {lastError ? <p className="help-error">{lastError}</p> : null}

      <ol className="help-steps">
        <li>
          Open the product link in your normal browser and check the price is actually visible on the
          page.
        </li>
        <li>
          If the price appears only after the page finishes loading, turn on the{' '}
          <strong>headless browser fallback</strong> in ⚙ Settings (it is on by default) and press
          “Refresh now”.
        </li>
        <li>
          If it still fails, the shop needs a small adapter: copy <code>_example.json</code> from{' '}
          <code>app/scraping/adapters/</code>, set the domain and the price/title/image CSS selectors,
          restart the server, then refresh. Details: README → “Adding a store adapter”.
        </li>
        <li>
          In the meantime you can keep the price history going with “Enter price manually” below.
        </li>
      </ol>

      <div className="help-cta">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setWizardOpen(true)}>
          ✨ Let an LLM write the adapter for me
        </button>
        <span className="muted small">
          Generates a prompt with this page&apos;s structure, then tests the JSON it gives you.
        </span>
      </div>

      {stores ? (
        <div className="help-stores">
          <button
            type="button"
            className="help-stores-toggle"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? '▾' : '▸'} Stores known to work ({stores.stores.length})
          </button>
          {open ? (
            <div className="help-store-list">
              {TIER_ORDER.flatMap((tier) => stores.stores.filter((s) => s.tier === tier)).map((s) => (
                <div className="help-store" key={s.domain}>
                  <span className="help-store-name">{s.name}</span>
                  <span className="help-store-domain">{s.domain}</span>
                  <span className="chip chip-muted">{stores.tiers[s.tier ?? ''] ?? s.tier}</span>
                </div>
              ))}
            </div>
          ) : null}
          {blocked ? (
            <p className="muted small help-blocked">
              Heads-up: {blocked.name} is known to block automated clients.
            </p>
          ) : null}
        </div>
      ) : null}

      <AdapterWizard
        productId={productId}
        domain={domain}
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onInstalled={() => {
          setWizardOpen(false);
          onAdapterInstalled?.();
        }}
      />
    </section>
  );
}
