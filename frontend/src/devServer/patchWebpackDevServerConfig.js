function patchWebpackDevServerConfig(config) {
  if (!config || typeof config !== 'object' || typeof config.setupMiddlewares === 'function') {
    return config;
  }

  const beforeSetup = config.onBeforeSetupMiddleware;
  const afterSetup = config.onAfterSetupMiddleware;

  if (typeof beforeSetup !== 'function' && typeof afterSetup !== 'function') {
    return config;
  }

  const patchedConfig = {
    ...config,
    onBeforeSetupMiddleware: undefined,
    onAfterSetupMiddleware: undefined,
    setupMiddlewares: (middlewares, devServer) => {
      if (typeof beforeSetup === 'function') {
        beforeSetup(devServer);
      }

      if (typeof afterSetup === 'function') {
        afterSetup(devServer);
      }

      return middlewares;
    },
  };

  return patchedConfig;
}

module.exports = {
  patchWebpackDevServerConfig,
};
