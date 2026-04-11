import '@testing-library/jest-dom';
import {
  apiFetch,
  isAuthenticated,
  login,
  rehydrateAuth,
  logout,
} from './api';

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as Response;
}

describe('auth session handling', () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn<Promise<Response>, [RequestInfo | URL, RequestInit?]>();

  beforeAll(() => {
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  beforeEach(() => {
    fetchMock.mockReset();
    logout();
    window.localStorage.clear();
    window.sessionStorage.clear();
    document.cookie = 'viralflux_csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  it('logs in with credentials include and stores no token in browser storage', async () => {
    document.cookie = 'viralflux_csrf_token=test-csrf-token; path=/';
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ authenticated: true }));

    await login('test@example.com', 'secret', true);

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/login?remember_me=true', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({
        'x-csrf-token': 'test-csrf-token',
      }),
    }));
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(isAuthenticated()).toBe(true);
  });

  it('rehydrates auth state from the server-side session endpoint', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ authenticated: true, subject: 'test@example.com', role: 'admin' }));

    await expect(rehydrateAuth(true)).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/session', expect.objectContaining({
      credentials: 'include',
    }));
    expect(isAuthenticated()).toBe(true);
  });

  it('clears auth state on logout and 401 responses', async () => {
    document.cookie = 'viralflux_csrf_token=test-csrf-token; path=/';
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(mockJsonResponse({ detail: 'expired' }, 401));

    await login('test@example.com', 'secret', true);

    await expect(apiFetch('/api/v1/protected')).rejects.toThrow('Sitzung abgelaufen. Bitte erneut anmelden.');

    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(isAuthenticated()).toBe(false);

    fetchMock
      .mockResolvedValueOnce(mockJsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(mockJsonResponse({ authenticated: false }));

    await login('test@example.com', 'secret', false);

    logout();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(fetchMock).toHaveBeenLastCalledWith('/api/auth/logout', expect.objectContaining({
      credentials: 'include',
      method: 'POST',
      headers: expect.objectContaining({
        'x-csrf-token': 'test-csrf-token',
      }),
    }));
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(isAuthenticated()).toBe(false);
  });

  it('adds the csrf header to authenticated state-changing api requests', async () => {
    document.cookie = 'viralflux_csrf_token=test-csrf-token; path=/';
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(mockJsonResponse({ ok: true }));

    await login('test@example.com', 'secret', true);
    await apiFetch('/api/v1/protected', { method: 'PATCH' });

    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/protected', expect.objectContaining({
      method: 'PATCH',
      credentials: 'include',
      headers: expect.objectContaining({
        'x-csrf-token': 'test-csrf-token',
      }),
    }));
  });
});
