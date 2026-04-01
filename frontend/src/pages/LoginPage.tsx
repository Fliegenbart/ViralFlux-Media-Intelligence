import React, { useState } from 'react';
import { AlertCircle, AtSign, Lock, LogIn } from 'lucide-react';
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
            <h1 className="login-brand-panel__headline">Die Wochensteuerung für PEIX x GELO</h1>
            <p className="login-brand-panel__text">
              Der Einstieg führt direkt in den Wochenplan: mit Fokus auf Bundesländer,
              empfohlene Richtung und der Evidenz, auf die sich PEIX x GELO diese Woche
              stützen kann.
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
              <h2>In den Wochenplan</h2>
              <p>Melde dich an, um Wochenfokus, Bundesländer und Evidenz für PEIX x GELO zu öffnen.</p>
            </header>

            <form className="login-form" onSubmit={handleSubmit}>
              {error && (
                <div role="alert" className="login-error">
                  <AlertCircle size={18} aria-hidden="true" />
                  <span>{error}</span>
                </div>
              )}

              <label className="login-field">
                <span className="login-field__label">E-Mail-Adresse</span>
                <span className="login-input-shell">
                  <AtSign size={18} className="login-input-shell__icon" aria-hidden="true" />
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
                <span className="login-field__label">Passwort</span>
                <span className="login-input-shell">
                  <Lock size={18} className="login-input-shell__icon" aria-hidden="true" />
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
                <span>{loading ? 'Wird geöffnet...' : 'Wochenplan öffnen'}</span>
                <LogIn size={18} aria-hidden="true" />
              </button>
            </form>

            <footer className="login-card__footer">
              <p>
                Noch kein Zugang? <span>Bitte intern freischalten lassen.</span>
              </p>
            </footer>
          </div>
        </section>
      </div>

    </div>
  );
};

export default LoginPage;
