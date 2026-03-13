import React, { useState } from 'react';
import { login } from '../lib/api';

interface LoginPageProps {
  onLogin: () => void;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      onLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-primary, #f8fafc)',
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: 380,
          padding: 32,
          borderRadius: 12,
          background: 'var(--bg-secondary, #fff)',
          border: '1px solid var(--border-color, #e2e8f0)',
          boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
        }}
      >
        <h1
          style={{
            fontSize: 20,
            fontWeight: 700,
            marginBottom: 4,
            color: 'var(--text-primary, #1e293b)',
          }}
        >
          ViralFlux
        </h1>
        <p
          style={{
            fontSize: 13,
            color: 'var(--text-muted, #64748b)',
            marginBottom: 24,
          }}
        >
          Media Intelligence Login
        </p>

        {error && (
          <div
            role="alert"
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              background: '#fef2f2',
              color: '#dc2626',
              fontSize: 13,
              marginBottom: 16,
              border: '1px solid #fecaca',
            }}
          >
            {error}
          </div>
        )}

        <label
          htmlFor="login-email"
          style={{
            display: 'block',
            fontSize: 13,
            fontWeight: 500,
            marginBottom: 4,
            color: 'var(--text-secondary, #475569)',
          }}
        >
          E-Mail
        </label>
        <input
          id="login-email"
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid var(--border-color, #e2e8f0)',
            fontSize: 14,
            marginBottom: 16,
            background: 'var(--bg-primary, #f8fafc)',
            color: 'var(--text-primary, #1e293b)',
            boxSizing: 'border-box',
          }}
        />

        <label
          htmlFor="login-password"
          style={{
            display: 'block',
            fontSize: 13,
            fontWeight: 500,
            marginBottom: 4,
            color: 'var(--text-secondary, #475569)',
          }}
        >
          Passwort
        </label>
        <input
          id="login-password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid var(--border-color, #e2e8f0)',
            fontSize: 14,
            marginBottom: 24,
            background: 'var(--bg-primary, #f8fafc)',
            color: 'var(--text-primary, #1e293b)',
            boxSizing: 'border-box',
          }}
        />

        <button
          type="submit"
          disabled={loading}
          style={{
            width: '100%',
            padding: '10px 16px',
            borderRadius: 6,
            border: 'none',
            background: loading ? '#94a3b8' : '#2563eb',
            color: '#fff',
            fontSize: 14,
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? 'Anmelden...' : 'Anmelden'}
        </button>
      </form>
    </div>
  );
};

export default LoginPage;
