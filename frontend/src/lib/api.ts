const AUTH_CHANGE_EVENT = 'viralflux-auth-change';

interface SessionState {
  authenticated: boolean;
  subject?: string | null;
  role?: string | null;
}

let _authenticated = false;
let _hydrated = false;
let _rehydratePromise: Promise<boolean> | null = null;

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

  const data = await response.json() as SessionState;
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

export function isAuthenticated(): boolean {
  return _authenticated;
}

export async function login(email: string, password: string, rememberMe = true): Promise<void> {
  const form = new URLSearchParams();
  form.append('username', email);
  form.append('password', password);

  const res = await fetch(`/api/auth/login?remember_me=${rememberMe ? 'true' : 'false'}`, {
    method: 'POST',
    body: form,
    credentials: 'include',
  });

  if (!res.ok) {
    throw new Error(await readErrorMessage(res, `Login fehlgeschlagen (${res.status})`));
  }

  _authenticated = true;
  _hydrated = true;
  notifyAuthChange(true);
}

export function logout(): void {
  const shouldNotify = _authenticated;
  clearAuthState(true);
  if (typeof window === 'undefined' || !shouldNotify) {
    return;
  }

  void Promise.resolve(fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include',
  })).catch((error) => {
    console.error('Logout request failed', error);
  });
}

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

  const res = await fetch(url, {
    ...init,
    credentials: 'include',
  });

  if (res.status === 401) {
    clearAuthState(true);
    throw new Error('Sitzung abgelaufen. Bitte erneut anmelden.');
  }

  return res;
}
