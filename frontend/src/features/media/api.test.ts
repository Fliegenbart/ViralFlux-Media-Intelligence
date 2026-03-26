import '@testing-library/jest-dom';
import { login, logout } from '../../lib/api';
import { mediaApi } from './api';

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

describe('mediaApi authentication', () => {
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

  it('adds the Bearer token to media API requests', async () => {
    const token = createToken();
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
      .mockResolvedValueOnce(mockJsonResponse({ access_token: token }))
      .mockResolvedValueOnce(mockJsonResponse({ cards: [] }));

    await login('test@example.com', 'secret', true);
    await mediaApi.generateRecommendations(payload);

    expect(fetchMock).toHaveBeenCalledTimes(2);

    const [, requestInit] = fetchMock.mock.calls[1];
    const headers = new Headers(requestInit?.headers);

    expect(headers.get('Authorization')).toBe(`Bearer ${token}`);
    expect(headers.get('Content-Type')).toBe('application/json');
  });
});
