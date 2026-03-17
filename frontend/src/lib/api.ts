/**
 * Authenticated API client — handles token management for all API calls.
 *
 * Credentials are provided by the user via the login form,
 * NOT hardcoded in the source code.
 *
 * Usage:
 *   import { apiFetch, login, logout, isAuthenticated } from '../lib/api';
 *   await login(email, password);
 *   const data = await apiFetch('/api/v1/marketing/list?limit=100');
 */

let _token: string | null = null;
let _tokenExpiry: number | null = null;

/** Check whether a valid (non-expired) token exists. */
export function isAuthenticated(): boolean {
  if (!_token) return false;
  if (_tokenExpiry && Date.now() >= _tokenExpiry) {
    _token = null;
    _tokenExpiry = null;
    return false;
  }
  return true;
}

/** Log in with email + password. Stores token in memory only. */
export async function login(email: string, password: string): Promise<void> {
  const form = new URLSearchParams();
  form.append('username', email);
  form.append('password', password);

  const res = await fetch('/api/auth/login', {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(detail || `Login fehlgeschlagen (${res.status})`);
  }

  const data = await res.json();
  _token = data.access_token;
  // JWT tokens contain exp claim (seconds since epoch)
  try {
    const payload = JSON.parse(atob(data.access_token.split('.')[1]));
    _tokenExpiry = payload.exp ? payload.exp * 1000 : null;
  } catch {
    // If we can't parse expiry, token will be refreshed on 401
    _tokenExpiry = null;
  }
}

/** Clear token (log out). */
export function logout(): void {
  _token = null;
  _tokenExpiry = null;
}

/**
 * Authenticated fetch wrapper.
 * Throws if not logged in. Retries once on 401 (token expired).
 */
export async function apiFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  if (!_token) {
    throw new Error('Nicht eingeloggt. Bitte zuerst anmelden.');
  }

  // Check expiry proactively
  if (_tokenExpiry && Date.now() >= _tokenExpiry) {
    _token = null;
    _tokenExpiry = null;
    throw new Error('Sitzung abgelaufen. Bitte erneut anmelden.');
  }

  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${_token}`);

  let res = await fetch(url, { ...init, headers });

  // Token expired server-side → signal re-login needed
  if (res.status === 401) {
    _token = null;
    _tokenExpiry = null;
    throw new Error('Sitzung abgelaufen. Bitte erneut anmelden.');
  }

  return res;
}
