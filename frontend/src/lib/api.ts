/**
 * Authenticated API client — handles token management for all API calls.
 *
 * Credentials are provided by the user via the login form.
 * The browser stores the session in an httpOnly cookie set by the backend,
 * so no readable JWT is persisted in localStorage or sessionStorage.
 *
 * Usage:
 *   import { apiFetch, login, logout, isAuthenticated } from '../lib/api';
 *   await login(email, password, true);
 *   const data = await apiFetch('/api/v1/marketing/list?limit=100');
 */

const AUTH_CHANGE_EVENT = 'viralflux-auth-change';
const CSRF_COOKIE_NAME = 'viralflux_csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';
const CSRF_PROTECTED_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

interface SessionState {
  authenticated: boolean;
  subject?: string | null;
  role?: string | null;
}

let _authenticated = false;
let _hydrated = false;
let _rehydratePromise: Promise<boolean> | null = null;

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const prefix = `${name}=`;
  const cookie = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));

  if (!cookie) {
    return null;
  }

  return decodeURIComponent(cookie.slice(prefix.length));
}

function buildHeaders(
  headers?: HeadersInit,
  extraHeaders?: Record<string, string>,
): Record<string, string> | undefined {
  const merged = new Headers(headers);
  if (extraHeaders) {
    Object.entries(extraHeaders).forEach(([key, value]) => {
      merged.set(key, value);
    });
  }
  const normalized = Object.fromEntries(merged.entries());
  return Object.keys(normalized).length > 0 ? normalized : undefined;
}

async function ensureCsrfToken(): Promise<string> {
  const existingToken = readCookie(CSRF_COOKIE_NAME);
  if (existingToken) {
    return existingToken;
  }

  const response = await fetch('/api/auth/csrf', {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `CSRF-Token konnte nicht geladen werden (${response.status})`));
  }

  const cookieToken = readCookie(CSRF_COOKIE_NAME);
  if (cookieToken) {
    return cookieToken;
  }

  const data = await response.json().catch(() => null) as { csrf_token?: string } | null;
  if (data && typeof data.csrf_token === 'string' && data.csrf_token.trim()) {
    return data.csrf_token;
  }

  throw new Error('CSRF-Token konnte nicht geladen werden.');
}

async function withCsrfProtection(init: RequestInit = {}): Promise<RequestInit> {
  const method = String(init.method || 'GET').toUpperCase();
  if (!CSRF_PROTECTED_METHODS.has(method)) {
    return init;
  }

  const csrfToken = await ensureCsrfToken();
  return {
    ...init,
    headers: buildHeaders(init.headers, {
      [CSRF_HEADER_NAME]: csrfToken,
    }),
  };
}

function notifyAuthChange(authenticated: boolean): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent<boolean>(AUTH_CHANGE_EVENT, { detail: authenticated }));
}

function clearAuthState(notify = false): void {
  const hadAuth = _authenticated;
  _authenticated = false;
  _hydrated = true;
  _rehydratePromise = null;

  if (notify && hadAuth) {
    notifyAuthChange(false);
  }
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const data = await response.json().catch(() => null) as { detail?: string } | null;
  if (data && typeof data.detail === 'string' && data.detail.trim()) {
    return data.detail;
  }

  const text = await response.text().catch(() => '');
  return text || fallback;
}

async function fetchSessionState(): Promise<boolean> {
  const response = await fetch('/api/auth/session', {
    credentials: 'include',
  });

  if (response.status === 401) {
    return false;
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `Sitzung konnte nicht geprüft werden (${response.status})`));
  }

  const data = await response.json().catch(() => ({ authenticated: false })) as SessionState;
  return Boolean(data.authenticated);
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

/** Restore auth state from the backend session after a page reload. */
export async function rehydrateAuth(force = false): Promise<boolean> {
  if (_hydrated && !force) {
    return _authenticated;
  }

  if (_rehydratePromise && !force) {
    return _rehydratePromise;
  }

  _rehydratePromise = (async () => {
    try {
      _authenticated = await fetchSessionState();
      return _authenticated;
    } finally {
      _hydrated = true;
      _rehydratePromise = null;
    }
  })();

  return _rehydratePromise;
}

/** Check whether a valid authenticated session exists in memory. */
export function isAuthenticated(): boolean {
  return _authenticated;
}

/** Log in with email + password. The backend stores the JWT in an httpOnly cookie. */
export async function login(email: string, password: string, rememberMe = true): Promise<void> {
  const form = new URLSearchParams();
  form.append('username', email);
  form.append('password', password);

  const requestInit = await withCsrfProtection({
    method: 'POST',
    body: form,
    credentials: 'include',
  });
  const res = await fetch(`/api/auth/login?remember_me=${rememberMe ? 'true' : 'false'}`, requestInit);

  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Login fehlgeschlagen (${res.status})`));
  }

  _authenticated = true;
  _hydrated = true;
  notifyAuthChange(true);
}

/** Clear session state and ask the backend to expire the auth cookie. */
export function logout(): void {
  const shouldNotify = _authenticated;
  clearAuthState(true);
  if (typeof window === 'undefined' || !shouldNotify) {
    return;
  }

  void Promise.resolve(withCsrfProtection({
    method: 'POST',
    credentials: 'include',
  }))
    .then((requestInit) => fetch('/api/auth/logout', requestInit))
    .catch(() => undefined);
}

/**
 * Authenticated fetch wrapper.
 * Throws if not logged in and clears auth state on 401.
 */
export async function apiFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  if (!_hydrated) {
    await rehydrateAuth();
  }

  if (!_authenticated) {
    throw new Error('Nicht eingeloggt. Bitte zuerst anmelden.');
  }

  const requestInit = await withCsrfProtection({
    ...init,
    credentials: 'include',
  });
  const res = await fetch(url, requestInit);

  if (res.status === 401) {
    clearAuthState(true);
    throw new Error('Sitzung abgelaufen. Bitte erneut anmelden.');
  }

  return res;
}
