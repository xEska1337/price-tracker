import { useEffect, useRef, useState } from 'react';

interface LoginOverlayProps {
  open: boolean;
  onLogin: (password: string) => Promise<boolean>;
}

export function LoginOverlay({ open, onLogin }: LoginOverlayProps) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const ok = await onLogin(password);
    setBusy(false);
    if (!ok) {
      setError('Wrong password');
      inputRef.current?.select();
    } else {
      setPassword('');
    }
  }

  return (
    <div className="overlay overlay-login" role="dialog" aria-modal="true" aria-label="Login">
      <form className="login-box" onSubmit={handleSubmit}>
        <h2>PriceTrack</h2>
        <p className="muted login-hint">This server requires login — enter the password.</p>
        <label className="field">
          <span className="field-label">Password</span>
          <input
            ref={inputRef}
            type="password"
            value={password}
            autoComplete="current-password"
            placeholder="Password…"
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" className="btn btn-primary" disabled={busy || password.length === 0}>
          {busy ? <span className="spinner" aria-hidden="true" /> : null}
          Log in
        </button>
      </form>
    </div>
  );
}
