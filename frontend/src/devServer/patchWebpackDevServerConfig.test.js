import { patchWebpackDevServerConfig } from './patchWebpackDevServerConfig';

describe('patchWebpackDevServerConfig', () => {
  it('moves deprecated dev-server hooks into setupMiddlewares', () => {
    const calls = [];
    const config = {
      client: { overlay: true },
      onBeforeSetupMiddleware: (devServer) => {
        calls.push(`before:${devServer.name}`);
      },
      onAfterSetupMiddleware: (devServer) => {
        calls.push(`after:${devServer.name}`);
      },
    };

    const patched = patchWebpackDevServerConfig(config);
    const middlewares = [{ name: 'existing' }];
    const devServer = { name: 'viralflux-dev-server' };

    expect(patched).not.toBe(config);
    expect(patched.onBeforeSetupMiddleware).toBeUndefined();
    expect(patched.onAfterSetupMiddleware).toBeUndefined();
    expect(typeof patched.setupMiddlewares).toBe('function');
    expect(patched.setupMiddlewares(middlewares, devServer)).toBe(middlewares);
    expect(calls).toEqual(['before:viralflux-dev-server', 'after:viralflux-dev-server']);
  });

  it('keeps configs that already use setupMiddlewares unchanged', () => {
    const setupMiddlewares = jest.fn((middlewares) => middlewares);
    const config = {
      setupMiddlewares,
      client: { overlay: true },
    };

    expect(patchWebpackDevServerConfig(config)).toBe(config);
  });
});
