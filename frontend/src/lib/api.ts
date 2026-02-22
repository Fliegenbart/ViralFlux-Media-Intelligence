/**
 * Authenticated API client — handles login + token caching for all API calls.
 *
 * Usage:
 *   import { apiFetch } from '../lib/api';
 *   const data = await apiFetch('/api/v1/marketing/list?limit=100');
 */

let _token: string | null = null;
let _loginPromise: Promise<string> | null = null;

async function ensureToken(): Promise<string> {
  if (_token) return _token;

  // Deduplicate concurrent login requests
  if (_loginPromise) return _loginPromise;

  _loginPromise = (async () => {
    const form = new URLSearchParams();
    form.append('username', 'admin@gelo.de');
    form.append('password', 'gelo2026');

    const res = await fetch('/api/auth/login', {
      method: 'POST',
      body: form,
    });

    if (!res.ok) throw new Error(`Login failed: ${res.status}`);

    const data = await res.json();
    _token = data.access_token;
    return _token!;
  })();

  try {
    return await _loginPromise;
  } finally {
    _loginPromise = null;
  }
}

/**
 * Authenticated fetch wrapper.
 * Automatically logs in on first call and retries once on 401.
 */
export async function apiFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const token = await ensureToken();

  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);

  let res = await fetch(url, { ...init, headers });

  // Token expired → re-login once
  if (res.status === 401) {
    _token = null;
    const freshToken = await ensureToken();
    headers.set('Authorization', `Bearer ${freshToken}`);
    res = await fetch(url, { ...init, headers });
  }

  return res;
}
