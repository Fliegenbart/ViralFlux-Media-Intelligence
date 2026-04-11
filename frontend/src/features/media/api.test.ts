import '@testing-library/jest-dom';
import { login, logout } from '../../lib/api';
import { mediaApi } from './api';

function mockJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as Response;
}

describe('mediaApi authentication', () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn<Promise<Response>, [RequestInfo | URL, RequestInit?]>();
  const originalSetTimeout = window.setTimeout;

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
    document.cookie = 'viralflux_csrf_token=test-csrf-token; path=/';
  });

  afterEach(() => {
    window.setTimeout = originalSetTimeout;
  });

  it('relies on cookie credentials for media API requests', async () => {
    const payload = {
      brand: 'Brand',
      product: 'Produkt',
      campaign_goal: 'Awareness',
      weekly_budget: 1000,
      channel_pool: ['tv'],
      strategy_mode: 'balanced',
      max_cards: 3,
      virus_typ: 'Influenza A',
    };

    fetchMock
      .mockResolvedValueOnce(mockJsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(mockJsonResponse({ cards: [] }));

    await login('test@example.com', 'secret', true);
    await mediaApi.generateRecommendations(payload);

    expect(fetchMock).toHaveBeenCalledTimes(2);

    const [, requestInit] = fetchMock.mock.calls[1];
    const headers = new Headers(requestInit?.headers);

    expect(requestInit?.credentials).toBe('include');
    expect(headers.get('Authorization')).toBeNull();
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('gives the campaigns request the heavy timeout budget', async () => {
    const setTimeoutMock = jest.fn(() => 1 as unknown as number);
    window.setTimeout = setTimeoutMock as unknown as typeof window.setTimeout;

    fetchMock
      .mockResolvedValueOnce(mockJsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(mockJsonResponse({ cards: [] }));

    await login('test@example.com', 'secret', true);
    await mediaApi.getCampaigns('gelo');

    expect(setTimeoutMock).toHaveBeenCalledWith(expect.any(Function), 45000);
  });
});
