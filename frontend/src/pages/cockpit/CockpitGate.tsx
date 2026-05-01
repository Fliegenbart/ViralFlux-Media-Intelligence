import React, { useState } from 'react';

/**
 * Simple password gate for the public cockpit URL.
 *
 * POSTs to /api/v1/media/cockpit/unlock; on 200 the backend sets a signed
 * HttpOnly cookie and we reload the page so the cockpit SWR hooks see the
 * new cookie on their next fetch. On 401 we render an inline error.
 *
 * The password itself is not in the frontend bundle — it is held by the
 * backend in COCKPIT_ACCESS_PASSWORD. The only thing this component knows
 * is whether the server said yes or no.
 */
export const CockpitGate: React.FC<{ onUnlocked?: () => void }> = ({ onUnlocked }) => {
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/media/cockpit/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ password: password.trim() }),
      });
      if (res.status === 401) {
        setError('Falsches Passwort.');
        setSubmitting(false);
        return;
      }
      if (!res.ok) {
        setError(`Dienst nicht erreichbar (HTTP ${res.status}).`);
        setSubmitting(false);
        return;
      }
      // Cookie is set server-side. Tell the parent (so SWR can revalidate)
      // or simply reload — reload is the simplest path.
      if (onUnlocked) {
        onUnlocked();
      } else {
        window.location.reload();
      }
    } catch {
      setError('Netzwerkfehler. Bitte erneut versuchen.');
      setSubmitting(false);
    }
  };

  return (
    <div className="peix-gate">
      <div className="peix-gate__frame">
        <div className="peix-gate__mark">◆</div>
        <div className="peix-gate__kicker">peix · labpulse</div>
        <h1 className="peix-gate__headline">
          FluxEngine
          <em> — für Eingeladene.</em>
        </h1>
        <p className="peix-gate__dek">
          Regionaler Wellen-Forecast + Media-Shift-Prüfung für Pharma.
          16 Bundesländer, mehrtägiger Horizont, transparent bei Datenlücken.
          Passwort eingeben, um das Pilot-Cockpit zu öffnen.
        </p>
        <form onSubmit={handleSubmit} className="peix-gate__form" autoComplete="off">
          <label className="peix-gate__label" htmlFor="peix-gate-pw">
            Passwort
          </label>
          <input
            id="peix-gate-pw"
            type="password"
            className="peix-gate__input"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              if (error) setError(null);
            }}
            autoFocus
            autoComplete="current-password"
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={error ? 'peix-gate-error' : undefined}
            disabled={submitting}
          />
          <button type="submit" className="peix-gate__submit" disabled={submitting || !password.trim()}>
            {submitting ? 'Wird geprüft…' : 'Cockpit öffnen'}
          </button>
          {error && (
            <div id="peix-gate-error" className="peix-gate__error" role="alert">
              {error}
            </div>
          )}
        </form>
        <div className="peix-gate__footer">
          Bei Fragen: <span className="peix-gate__mono">mail@davidwegener.de</span>
        </div>
      </div>
    </div>
  );
};

export default CockpitGate;
