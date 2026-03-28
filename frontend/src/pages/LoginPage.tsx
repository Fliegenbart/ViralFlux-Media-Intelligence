import React, { useState } from 'react';
import { login } from '../lib/api';

interface LoginPageProps {
  onLogin: () => void;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password, rememberMe);
      onLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-grid-pattern" aria-hidden="true" />
      <div className="login-page__glow login-page__glow--left" aria-hidden="true" />
      <div className="login-page__glow login-page__glow--right" aria-hidden="true" />

      <div className="login-page__inner">
        <section className="login-brand-panel" aria-label="ViralFlux Einordnung">
          <div className="login-brand-panel__brand">
            <span className="login-brand-panel__wordmark">ViralFlux</span>
            <p className="login-brand-panel__subtitle">PEIX x GELO</p>
          </div>

          <div className="login-brand-panel__copy">
            <h1 className="login-brand-panel__headline">
              Klar sehen, <span>was diese Woche zuerst zählt.</span>
            </h1>
            <p className="login-brand-panel__text">
              Nach dem Login siehst du sofort, welches Bundesland Aufmerksamkeit verdient, welche Maßnahme als Nächstes sinnvoll ist und worauf sich diese Einordnung stützt.
            </p>
          </div>

          <div className="login-live-pill">
            <span className="login-live-pill__pulse" aria-hidden="true" />
            <span>Live-Daten aktiv</span>
          </div>
        </section>

        <section className="login-card-shell">
          <div className="login-card">
            <div className="login-card__mobile-brand">ViralFlux</div>

            <header className="login-card__header">
              <h2>Willkommen in der Wochensteuerung</h2>
              <p>Melde dich an, um Wochenplan, Regionen, Kampagnen und Evidenz zu öffnen.</p>
            </header>

            <form className="login-form" onSubmit={handleSubmit}>
              {error && (
                <div role="alert" className="login-error">
                  <span className="material-symbols-outlined" aria-hidden="true">error</span>
                  <span>{error}</span>
                </div>
              )}

              <label className="login-field">
                <span className="login-field__label">E-Mail-Adresse</span>
                <span className="login-input-shell">
                  <span className="material-symbols-outlined login-input-shell__icon" aria-hidden="true">alternate_email</span>
                  <input
                    id="login-email"
                    type="email"
                    required
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@firma.de"
                    className="login-input"
                  />
                </span>
              </label>

              <label className="login-field">
                <span className="login-field__label-row">
                  <span className="login-field__label">Passwort</span>
                  <button
                    type="button"
                    className="login-inline-link login-inline-link--disabled"
                    disabled
                    title="Passwort-Reset ist noch nicht aktiviert."
                  >
                    Passwort vergessen?
                  </button>
                </span>
                <span className="login-input-shell">
                  <span className="material-symbols-outlined login-input-shell__icon" aria-hidden="true">lock</span>
                  <input
                    id="login-password"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="login-input"
                  />
                </span>
              </label>

              <label className="login-checkbox">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>Angemeldet bleiben</span>
              </label>

              <button type="submit" disabled={loading} className="login-submit">
                <span>{loading ? 'Anmelden...' : 'Anmelden'}</span>
                <span className="material-symbols-outlined" aria-hidden="true">login</span>
              </button>

              <div className="login-divider">
                <span>Oder mit Firmenkonto fortfahren</span>
              </div>

              <div className="login-sso-grid" aria-label="Platzhalter für Firmenanmeldung">
                <button
                  type="button"
                  className="login-sso-button"
                  disabled
                  title="Google-Anmeldung ist in diesem Schritt noch nicht aktiv."
                >
                  <span className="login-sso-button__badge">G</span>
                  <span>Google</span>
                </button>
                <button
                  type="button"
                  className="login-sso-button"
                  disabled
                  title="Azure-Anmeldung ist in diesem Schritt noch nicht aktiv."
                >
                  <span className="material-symbols-outlined" aria-hidden="true">corporate_fare</span>
                  <span>Azure AD</span>
                </button>
              </div>
            </form>

            <footer className="login-card__footer">
              <p>
                Noch kein Zugang? <span>Bitte intern freischalten lassen.</span>
              </p>
            </footer>
          </div>
        </section>
      </div>

      <div className="login-footer-links" aria-label="Rechtliche Hinweise">
        <button type="button" disabled>Datenschutz</button>
        <button type="button" disabled>Impressum</button>
        <button type="button" disabled>Systemstatus</button>
      </div>
    </div>
  );
};

export default LoginPage;
