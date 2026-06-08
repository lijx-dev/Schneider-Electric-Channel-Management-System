const envConfig = require('./env');

function getMiniProgramEnvVersion() {
  try {
    if (typeof wx !== 'undefined' && typeof wx.getAccountInfoSync === 'function') {
      const accountInfo = wx.getAccountInfoSync();
      return (accountInfo.miniProgram && accountInfo.miniProgram.envVersion) || 'develop';
    }
  } catch (err) {
    // ignore and use default
  }

  return 'develop';
}

function trimSlashes(value) {
  return String(value || '').replace(/^\/+|\/+$/g, '');
}

function resolveLocalOverride(envVersion) {
  if (envVersion !== 'develop' || typeof wx === 'undefined' || typeof wx.getStorageSync !== 'function') {
    return {};
  }

  const developProdPreview = (envConfig.localOverrides || {}).developProdPreview || {};
  const storageKey = String(developProdPreview.storageKey || '').trim();
  if (!storageKey) {
    return {};
  }

  try {
    if (!wx.getStorageSync(storageKey)) {
      return {};
    }
  } catch (err) {
    return {};
  }

  return {
    cloudEnvId: developProdPreview.cloudEnvId || '',
    legacyBaseUrl: developProdPreview.legacyBaseUrl || ''
  };
}

function resolveRuntimeConfig() {
  const envVersion = getMiniProgramEnvVersion();
  const scopedConfig = ((envConfig.byEnvVersion || {})[envVersion]) || {};
  const localOverride = resolveLocalOverride(envVersion);

  return {
    envVersion,
    serviceName: scopedConfig.serviceName || envConfig.serviceName || 'faq-backend',
    cloudEnvId:
      localOverride.cloudEnvId ||
      scopedConfig.cloudEnvId ||
      envConfig.cloudEnvId ||
      envConfig.defaultCloudEnvId ||
      '',
    legacyBaseUrl:
      localOverride.legacyBaseUrl ||
      scopedConfig.legacyBaseUrl ||
      envConfig.legacyBaseUrl ||
      '',
    avatarCloudPathPrefix: trimSlashes(
      scopedConfig.avatarCloudPathPrefix || envConfig.avatarCloudPathPrefix || 'avatars'
    )
  };
}

module.exports = {
  resolveRuntimeConfig
};
