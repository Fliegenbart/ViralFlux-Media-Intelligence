/**
 * Authenticated API client — handles token management for all API calls.
 *
 * Credentials are provided by the user via the login form,
 * NOT hardcoded in the source code.
 *
 * Usage:
 *   import { apiFetch, login, logout, isAuthenticated } from '../lib/api';
 *   await login(email, password, true);
 *   const data = await apiFetch('/api/v1/marketing/list?limit=100');
 */

export const AUTH_STORAGE_KEY = 'viralflux-auth';

const AUTH_CHANGE_EVENT = 'viralflux-auth-change';

interface PersistedAuthState {
  token: string;
  tokenExpiry: number | null;
}

let _token: string | null = null;
let _tokenExpiry: number | null = null;
let _hydrated = false;

function parseTokenExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function clearPersistedAuth(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  window.sessionStorage.removeItem(AUTH_STORAGE_KEY);
}

function persistAuthState(rememberMe: boolean): void {
  if (typeof window === 'undefined' || !_token) return;

  const serialized = JSON.stringify({
    token: _token,
    tokenExpiry: _tokenExpiry,
  } satisfies PersistedAuthState);

  const targetStorage = rememberMe ? window.localStorage : window.sessionStorage;
  const otherStorage = rememberMe ? window.sessionStorage : window.localStorage;

  targetStorage.setItem(AUTH_STORAGE_KEY, serialized);
  otherStorage.removeItem(AUTH_STORAGE_KEY);
}

function readPersistedAuth(): PersistedAuthState | null {
  if (typeof window === 'undefined') return null;

  for (const storage of [window.localStorage, window.sessionStorage]) {
    const raw = storage.getItem(AUTH_STORAGE_KEY);
    if (!raw) continue;

    try {
      const parsed = JSON.parse(raw) as Partial<PersistedAuthState>;
      if (typeof parsed.token !== 'string' || parsed.token.length === 0) {
        storage.removeItem(AUTH_STORAGE_KEY);
        continue;
      }

      const tokenExpiry = typeof parsed.tokenExpiry === 'number' ? parsed.tokenExpiry : null;
      if (tokenExpiry && Date.now() >= tokenExpiry) {
        storage.removeItem(AUTH_STORAGE_KEY);
        continue;
      }

      return {
        token: parsed.token,
        tokenExpiry,
      };
    } catch {
      storage.removeItem(AUTH_STORAGE_KEY);
    }
  }

  return null;
}

function notifyAuthChange(authenticated: boolean): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent<boolean>(AUTH_CHANGE_EVENT, { detail: authenticated }));
}

function ensureHydrated(): void {
  if (!_hydrated) {
    rehydrateAuth();
  }
}

function clearAuthState(notify = false): void {
  const hadToken = Boolean(_token);
  _token = null;
  _tokenExpiry = null;
  _hydrated = true;
  clearPersistedAuth();

  if (notify && hadToken) {
    notifyAuthChange(false);
  }
}

function getTokenOrThrow(): string {
  ensureHydrated();

  if (!_token) {
    throw new Error('Nicht eingeloggt. Bitte zuerst anmelden.');
  }

  if (_tokenExpiry && Date.now() >= _tokenExpiry) {
    clearAuthState(true);
    throw new Error('Sitzung abgelaufen. Bitte erneut anmelden.');
  }

  return _token;
}

export function addAuthChangeListener(listener: (authenticated: boolean) => void): () => void {
  if (typeof window === 'undefined') {
    return () => {};
  }

  const handleChange = (event: Event) => {
    listener((event as CustomEvent<boolean>).detail);
  };

  window.addEventListener(AUTH_CHANGE_EVENT, handleChange as EventListener);
  return () => window.removeEventListener(AUTH_CHANGE_EVENT, handleChange as EventListener);
}

/** Restore auth state from browser storage after a page reload. */
export function rehydrateAuth(): boolean {
  const persisted = readPersistedAuth();

  _hydrated = true;

  if (!persisted) {
    _token = null;
    _tokenExpiry = null;
    return false;
  }

  _token = persisted.token;
  _tokenExpiry = persisted.tokenExpiry;
  return true;
}

/** Check whether a valid (non-expired) token exists. */
export function isAuthenticated(): boolean {
  ensureHydrated();

  if (!_token) return false;
  if (_tokenExpiry && Date.now() >= _tokenExpiry) {
    clearAuthState(true);
    return false;
  }
  return true;
}

/** Log in with email + password and store only token + expiry. */
export async function login(email: string, password: string, rememberMe = true): Promise<void> {
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
  if (typeof data.access_token !== 'string' || data.access_token.length === 0) {
    throw new Error('Login-Antwort enthält kein Zugriffstoken.');
  }

  _token = data.access_token;
  _tokenExpiry = parseTokenExpiry(data.access_token);
  _hydrated = true;
  persistAuthState(rememberMe);
  notifyAuthChange(true);
}

/** Clear token (log out). */
export function logout(): void {
  clearAuthState(true);
}

/**
 * Authenticated fetch wrapper.
 * Throws if not logged in and clears auth state on 401 / expired token.
 */
export async function apiFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const token = getTokenOrThrow();

  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);

  let res = await fetch(url, { ...init, headers });

  if (res.status === 401) {
    clearAuthState(true);
    throw new Error('Sitzung abgelaufen. Bitte erneut anmelden.');
  }

  return res;
}
