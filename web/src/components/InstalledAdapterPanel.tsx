import { useEffect, useState } from 'react';
import * as api from '../api';
import { toast } from './Toast';

interface InstalledAdapterPanelProps {
  domain: string;

  refreshKey?: number;
}

export function InstalledAdapterPanel({ domain, refreshKey = 0 }: InstalledAdapterPanelProps) {
  const [adapter, setAdapter] = useState<api.UserAdapterEntry | null>(null);
  const [open, setOpen] = useState(false);
  const [removing, setRemoving] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .listAdapters()
      .then((data) => {
        if (!alive) return;
        const match = data.user.find(
          (entry) => domain === entry.domain || domain.endsWith('.' + entry.domain),
        );
        setAdapter(match ?? null);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [domain, refreshKey]);

  if (!adapter) return null;

  async function handleRemove() {
    if (!adapter || removing) return;
    if (!window.confirm(`Remove the installed adapter for ${adapter.domain}?`)) return;
    setRemoving(true);
    try {
      await api.deleteAdapter(adapter.domain);
      toast('Adapter removed', 'info');
      setAdapter(null);
    } catch (error: unknown) {
      toast(api.errMessage(error), 'error');
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="adapter-panel">
      <button
        type="button"
        className="help-stores-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? '▾' : '▸'} Custom adapter ({adapter.domain})
      </button>
      {open ? (
        <>
          <pre className="help-json">
            {JSON.stringify(
              { domain: adapter.domain, currency: adapter.currency, selectors: adapter.selectors },
              null,
              2,
            )}
          </pre>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-danger"
            onClick={handleRemove}
            disabled={removing}
          >
            {removing ? <span className="spinner" aria-hidden="true" /> : null}
            Remove adapter
          </button>
        </>
      ) : null}
    </div>
  );
}
