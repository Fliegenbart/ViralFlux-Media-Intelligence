import '@testing-library/jest-dom';
import {
  AUTH_STORAGE_KEY,
  apiFetch,
  isAuthenticated,
  login,
  logout,
} from './api';

function createToken(expiresInMs = 60_000): string {
  const payload = window.btoa(JSON.stringify({
    exp: Math.floor((Date.now() + expiresInMs) / 1000),
  }));

  return `header.${payload}.signature`;
}

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as Response;
}

describe('auth persistence', () => {
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
  });

  it('stores token in localStorage when remember me is enabled', async () => {
    const token = createToken();
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ access_token: token }));

    await login('test@example.com', 'secret', true);

    expect(JSON.parse(window.localStorage.getItem(AUTH_STORAGE_KEY) || '{}')).toEqual({
      token,
      tokenExpiry: expect.any(Number),
    });
    expect(window.sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(isAuthenticated()).toBe(true);
  });

  it('stores token in sessionStorage when remember me is disabled', async () => {
    const token = createToken();
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ access_token: token }));

    await login('test@example.com', 'secret', false);

    expect(window.localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(JSON.parse(window.sessionStorage.getItem(AUTH_STORAGE_KEY) || '{}')).toEqual({
      token,
      tokenExpiry: expect.any(Number),
    });
    expect(isAuthenticated()).toBe(true);
  });

  it('clears persisted auth on logout and 401 responses', async () => {
    const token = createToken();
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse({ access_token: token }))
      .mockResolvedValueOnce(mockJsonResponse({ detail: 'expired' }, 401));

    await login('test@example.com', 'secret', true);
    expect(window.localStorage.getItem(AUTH_STORAGE_KEY)).not.toBeNull();

    await expect(apiFetch('/api/v1/protected')).rejects.toThrow('Sitzung abgelaufen. Bitte erneut anmelden.');

    expect(window.localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(isAuthenticated()).toBe(false);

    fetchMock.mockResolvedValueOnce(mockJsonResponse({ access_token: token }));
    await login('test@example.com', 'secret', false);

    logout();

    expect(window.localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull();
    expect(isAuthenticated()).toBe(false);
  });
});
