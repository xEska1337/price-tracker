import { useEffect, useState } from 'react';
import { toast } from './Toast';

export interface AppSettings {
  discord: {
    webhook_url: string;
    configured: boolean;
    min_drop_pct: number;
    highlight_all_time_low: boolean;
  };
  browser: {
    enabled: boolean;
    available: boolean;
    reason: string | null;
  };
}

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onSaved?: (settings: AppSettings) => void;
}

export function SettingsModal({ open, onClose, onSaved }: SettingsModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);

  const [webhook, setWebhook] = useState('');
  const [minDrop, setMinDrop] = useState('0');
  const [highlight, setHighlight] = useState(true);
  const [browserEnabled, setBrowserEnabled] = useState(true);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    setError(null);
    fetch('/api/settings', { credentials: 'same-origin' })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Could not load settings (HTTP ${res.status})`);
        return (await res.json()) as AppSettings;
      })
      .then((data) => {
        if (!alive) return;
        setSettings(data);
        setWebhook(data.discord.webhook_url);
        setMinDrop(String(data.discord.min_drop_pct));
        setHighlight(data.discord.highlight_all_time_low);
        setBrowserEnabled(data.browser.enabled);
      })
      .catch((err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : 'Could not load settings');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    if (saving) return;
    const pct = Number(minDrop.replace(',', '.'));
    if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
      setError('Minimum drop must be a number between 0 and 100');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/settings', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          discord: {
            webhook_url: webhook.trim(),
            min_drop_pct: pct,
            highlight_all_time_low: highlight,
          },
          playwright_enabled: browserEnabled,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Could not save (HTTP ${res.status})`);
      }
      const data = (await res.json()) as AppSettings;
      setSettings(data);
      onSaved?.(data);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not save settings');
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    if (testing) return;
    setTesting(true);
    setError(null);
    try {

      const save = await fetch('/api/settings', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ discord: { webhook_url: webhook.trim() } }),
      });
      if (!save.ok) {
        const body = (await save.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? 'Invalid webhook URL');
      }
      const res = await fetch('/api/notifications/test', {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Test failed (HTTP ${res.status})`);
      }
      toast('Test message sent to Discord', 'success');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTesting(false);
    }
  }

  const browserHint = settings
    ? settings.browser.available
      ? 'Chromium is ready — JS-rendered and bot-protected pages can be scraped.'
      : `Chromium is not available${settings.browser.reason ? `: ${settings.browser.reason}` : ''}. `
    : '';

  return (
    <div
      className="overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form className="modal settings-modal" role="dialog" aria-modal="true" aria-label="Settings" onSubmit={handleSave}>
        <button type="button" className="icon-btn modal-close" aria-label="Close" onClick={onClose}>
          ✕
        </button>
        <h2 className="settings-title">Settings</h2>

        {loading ? <p className="muted">Loading settings…</p> : null}
        {error ? <p className="form-error">{error}</p> : null}

        <section className="settings-section">
          <h3>Discord notifications</h3>
          <p className="muted small">
            Paste a channel webhook URL (Channel settings → Integrations → Webhooks). Price drops are
            posted there automatically; leave empty to disable.
          </p>
          <label className="field">
            <span className="field-label">Webhook URL</span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="https://discord.com/api/webhooks/…"
              value={webhook}
              onChange={(event) => setWebhook(event.target.value)}
            />
          </label>
          <div className="settings-row">
            <label className="field settings-field-sm">
              <span className="field-label">Minimum drop (%)</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={minDrop}
                onChange={(event) => setMinDrop(event.target.value)}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={highlight}
                onChange={(event) => setHighlight(event.target.checked)}
              />
              <span>Mark all-time lows</span>
            </label>
          </div>
          <div className="settings-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleTest}
              disabled={testing || !webhook.trim()}
            >
              {testing ? <span className="spinner" aria-hidden="true" /> : null}
              Send test message
            </button>
          </div>
        </section>

        <section className="settings-section">
          <h3>Headless browser fallback</h3>
          <p className="muted small">
            Renders pages in Chromium when a shop needs JavaScript or blocks plain requests.
            {browserHint ? ` ${browserHint}` : ''}
          </p>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={browserEnabled}
              onChange={(event) => setBrowserEnabled(event.target.checked)}
            />
            <span>Use the browser fallback</span>
          </label>
          {settings && !settings.browser.available ? (
            <p className="muted small">
              Run <code>make browsers</code> (or use the default Docker image, which bundles
              Chromium) and restart the server.
            </p>
          ) : null}
        </section>

        <div className="settings-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || loading}>
            {saving ? <span className="spinner" aria-hidden="true" /> : null}
            Save settings
          </button>
        </div>
      </form>
    </div>
  );
}
