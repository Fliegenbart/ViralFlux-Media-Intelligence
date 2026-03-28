'use strict';

const { patchWebpackDevServerConfig } = require('../src/devServer/patchWebpackDevServerConfig');

const configPath = require.resolve('react-scripts/config/webpackDevServer.config');
const originalModule = require(configPath);

require.cache[configPath].exports = function patchedWebpackDevServerConfig(proxy, allowedHost) {
  const config = originalModule(proxy, allowedHost);
  return patchWebpackDevServerConfig(config);
};

require('react-scripts/scripts/start');
