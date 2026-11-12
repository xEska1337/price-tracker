import { useEffect, useState } from 'react';
import * as api from '../api';
import { toast } from './Toast';

interface AdapterWizardProps {
  productId: string;
  domain: string;
  open: boolean;
  onClose: () => void;
  onInstalled: () => void;
}

export function AdapterWizard({ productId, domain, open, onClose, onInstalled }: AdapterWizardProps) {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState('');
  const [installing, setInstalling] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    setError(null);
    setPrompt('');
    setAnswer('');
    api
      .getAdapterPrompt(productId)
      .then((data) => {
        if (alive) setPrompt(data.prompt);
      })
      .catch((err: unknown) => {
        if (alive) setError(api.errMessage(err));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, productId]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !installing) onClose();
    }
    if (open) window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose, installing]);

  if (!open) return null;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      toast('Prompt copied to the clipboard', 'success');
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast('Could not copy — select the text manually', 'error');
    }
  }

  async function handleInstall(event: React.FormEvent) {
    event.preventDefault();
    if (installing || !answer.trim()) return;
    setInstalling(true);
    setError(null);
    try {
      const result = await api.installAdapter(productId, answer.trim());
      toast(`Adapter installed — price found: ${result.price.toFixed(2)}`, 'success');
      onInstalled();
      onClose();
    } catch (err: unknown) {
      setError(api.errMessage(err));
    } finally {
      setInstalling(false);
    }
  }

  return (
    <div
      className="overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !installing) onClose();
      }}
    >
      <div className="modal wizard-modal" role="dialog" aria-modal="true" aria-label="Add store support">
        <button type="button" className="icon-btn modal-close" aria-label="Close" onClick={onClose}>
          ✕
        </button>
        <h2 className="wizard-title">Add support for {domain}</h2>

        <div className="wizard-intro">
          <span className="wizard-step">1</span>
          <div>
            <p>
              Copy this prompt into any AI assistant (ChatGPT, Claude, Gemini, a local model…). It
              contains the page structure and the exact JSON format PriceTrack expects.
            </p>
            <p className="muted small">
              The page HTML is sent to the model you choose — check the store&apos;s terms if that
              matters to you.
            </p>
          </div>
        </div>

        {loading ? <p className="muted">Preparing the prompt…</p> : null}
        {prompt ? (
          <>
            <textarea className="wizard-prompt" readOnly value={prompt} rows={10} spellCheck={false} />
            <div className="wizard-actions">
              <button type="button" className="btn btn-ghost" onClick={handleCopy}>
                {copied ? 'Copied ✓' : 'Copy prompt'}
              </button>
            </div>
          </>
        ) : null}

        <div className="wizard-intro">
          <span className="wizard-step">2</span>
          <div>
            <p>Paste the JSON the assistant replied with. It is tested against the live page before saving.</p>
          </div>
        </div>

        <form className="wizard-form" onSubmit={handleInstall}>
          <textarea
            className="wizard-answer"
            placeholder={'{\n  "domain": "' + domain + '",\n  "selectors": { "price": "…" }\n}'}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            rows={7}
            spellCheck={false}
          />
          {error ? <p className="form-error">{error}</p> : null}
          <div className="wizard-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose} disabled={installing}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={installing || !answer.trim()}>
              {installing ? <span className="spinner" aria-hidden="true" /> : null}
              Test &amp; install
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
