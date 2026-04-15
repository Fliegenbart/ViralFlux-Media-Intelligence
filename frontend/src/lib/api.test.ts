import '@testing-library/jest-dom';
import {
  apiFetch,
  isAuthenticated,
  login,
  rehydrateAuth,
  logout,
} from './api';

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

function mockJsonResponse(body: JsonValue, status = 200): Response {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

describe('auth session handling', () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn<Promise<Response>, [RequestInfo | URL, RequestInit?]>() as jest.MockedFunction<typeof fetch>;

  beforeAll(() => {
    global.fetch = fetchMock;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  beforeEach(() => {
    fetchMock.mockReset();
    logout();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('logs in with credentials include and stores no token in browser storage', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ authenticated: true }));

    await login('test@example.com', 'secret', true);

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/login?remember_me=true', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
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

  it('fails loudly when the session payload cannot be parsed', async () => {
    const brokenJsonResponse = new Response('', { status: 200 });
    Object.defineProperty(brokenJsonResponse, 'json', {
      value: async () => {
        throw new Error('kaputtes JSON');
      },
    });
    fetchMock.mockResolvedValueOnce(brokenJsonResponse);

    await expect(rehydrateAuth(true)).rejects.toThrow('kaputtes JSON');
    expect(isAuthenticated()).toBe(false);
  });

  it('clears auth state on logout and 401 responses', async () => {
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

    expect(fetchMock).toHaveBeenLastCalledWith('/api/auth/logout', expect.objectContaining({
      credentials: 'include',
      method: 'POST',
    }));
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(isAuthenticated()).toBe(false);
  });
});
