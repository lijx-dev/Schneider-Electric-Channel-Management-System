const { resolveRuntimeConfig } = require('./config/runtime');
const DIRTY_SCOPE_STORAGE_PREFIX = 'dataDirtyScopes:';

App({
  globalData: {
    userInfo: null,
    userId: '',
    token: '',
    guestMode: false,
    runtimeConfig: null,
    baseUrl: ''
  },

  onLaunch() {
    this.installSafeConsole();
    const runtimeConfig = this.getRuntimeConfig(true);

    if (!wx.cloud) {
      console.error('Please use a supported base library for cloud capability.');
    } else {
      const initOptions = {
        traceUser: true
      };

      if (runtimeConfig.cloudEnvId) {
        initOptions.env = runtimeConfig.cloudEnvId;
      }

      wx.cloud.init(initOptions);
    }

    this.syncAuthWithRuntimeConfig();
    this.getUserProfile();
  },

  installSafeConsole() {
    if (console.__safeLoggerInstalled) {
      return;
    }

    const accountInfo = wx.getAccountInfoSync ? wx.getAccountInfoSync() : {};
    const envVersion = (accountInfo.miniProgram && accountInfo.miniProgram.envVersion) || 'develop';
    const shouldMute = envVersion === 'release';
    const sensitiveKeys = {
      authorization: true,
      avatar: true,
      avatar_file_id: true,
      avatar_url: true,
      data: true,
      detail: true,
      openid: true,
      phone: true,
      receiver_address: true,
      receiver_phone: true,
      token: true,
      userinfo: true
    };

    const maskString = (value) => String(value)
      .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer ***')
      .replace(/(^|[^\d])(1[3-9]\d{9})(?!\d)/g, (match, prefix, phone) => `${prefix}${phone.slice(0, 3)}****${phone.slice(-4)}`);

    const redactValue = (key, value, depth = 0) => {
      const normalizedKey = String(key || '').toLowerCase();
      if (sensitiveKeys[normalizedKey]) {
        return '[redacted]';
      }

      if (typeof value === 'string') {
        return maskString(value);
      }

      if (!value || typeof value !== 'object' || depth >= 3) {
        return value;
      }

      if (Array.isArray(value)) {
        return value.map((item) => redactValue('', item, depth + 1));
      }

      return Object.keys(value).reduce((safeValue, itemKey) => {
        safeValue[itemKey] = redactValue(itemKey, value[itemKey], depth + 1);
        return safeValue;
      }, {});
    };

    ['log', 'info', 'warn', 'error'].forEach((level) => {
      const originalLogger = console[level] && console[level].bind(console);
      if (!originalLogger) {
        return;
      }

      console[level] = (...args) => {
        if (shouldMute) {
          return;
        }
        originalLogger(...args.map((item) => redactValue('', item)));
      };
    });

    console.__safeLoggerInstalled = true;
  },

  getRuntimeConfig(forceRefresh = false) {
    if (!forceRefresh && this.globalData.runtimeConfig) {
      return this.globalData.runtimeConfig;
    }

    const runtimeConfig = resolveRuntimeConfig();
    this.globalData.runtimeConfig = runtimeConfig;
    this.globalData.baseUrl = runtimeConfig.legacyBaseUrl || '';
    return runtimeConfig;
  },

  getCallContainerConfig() {
    const runtimeConfig = this.getRuntimeConfig();
    if (!runtimeConfig.cloudEnvId) {
      return undefined;
    }

    return {
      env: runtimeConfig.cloudEnvId
    };
  },

  buildServiceHeaders(extraHeaders = {}) {
    const runtimeConfig = this.getRuntimeConfig();
    return Object.assign({}, extraHeaders, {
      'X-WX-SERVICE': runtimeConfig.serviceName
    });
  },

  getRuntimeSignature() {
    const runtimeConfig = this.getRuntimeConfig();
    return [
      runtimeConfig.envVersion || '',
      runtimeConfig.cloudEnvId || 'associated-env',
      runtimeConfig.serviceName || ''
    ].join('|');
  },

  buildSafeAvatarName({ userId = '', phone = '', displayName = '' } = {}) {
    const fallbackId = userId ? `user_${String(userId).slice(0, 8)}` : 'guest';
    const phonePart = String(phone || '').replace(/[^\d]/g, '') || fallbackId;
    const namePart = String(displayName || fallbackId).trim() || fallbackId;
    const rawName = `${phonePart}-${namePart}`;
    return rawName
      .replace(/\s+/g, '')
      .replace(/[\\/:*?"<>|#%[\]{}]+/g, '_')
      .replace(/^\.+|\.+$/g, '')
      .slice(0, 100) || fallbackId;
  },

  buildAvatarCloudPath({ userId = '', phone = '', displayName = '', extension = 'png' } = {}) {
    const runtimeConfig = this.getRuntimeConfig();
    const prefix = runtimeConfig.avatarCloudPathPrefix || 'avatars';
    const safeAvatarName = this.buildSafeAvatarName({ userId, phone, displayName });

    return `${prefix}/${safeAvatarName}-头像`;
  },

  buildAvatarAccessUrl(avatarValue) {
    if (!avatarValue || typeof avatarValue !== 'string') {
      return '';
    }

    const trimmed = avatarValue.trim();
    if (!trimmed) {
      return '';
    }

    const baseUrl = this.normalizeRemoteUrlProtocol(this.globalData.baseUrl || '');
    if (!baseUrl) {
      return trimmed;
    }

    if (trimmed.startsWith('/api/upload/avatar/view?key=')) {
      return `${baseUrl}${trimmed}`;
    }

    if (trimmed.startsWith('/static/avatars/')) {
      return `${baseUrl}${trimmed}`;
    }

    const normalizedPath = trimmed.replace(/^\/+/, '');
    if (normalizedPath.startsWith('avatars/')) {
      if (!baseUrl) {
        return '';
      }
      return `${baseUrl}/api/upload/avatar/view?key=${encodeURIComponent(normalizedPath)}`;
    }

    return trimmed;
  },

  normalizeRemoteUrlProtocol(url) {
    if (!url || typeof url !== 'string') {
      return '';
    }

    const trimmed = url.trim();
    if (!trimmed || !/^http:\/\//i.test(trimmed)) {
      return trimmed;
    }

    const isLocalHttpUrl = /^http:\/\/(?:localhost|127(?:\.\d{1,3}){3}|0\.0\.0\.0|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?::\d+)?(?:\/|$)/i;
    if (isLocalHttpUrl.test(trimmed)) {
      return trimmed;
    }

    return trimmed.replace(/^http:\/\//i, 'https://');
  },

  normalizeAvatarUrl(avatarUrl) {
    if (!avatarUrl || typeof avatarUrl !== 'string') {
      return '';
    }

    const trimmed = avatarUrl.trim();
    if (!trimmed) {
      return '';
    }

    const malformedCloudMatch = trimmed.match(/cloud:\/\/.+$/);
    if (malformedCloudMatch) {
      return malformedCloudMatch[0];
    }

    if (trimmed.includes('__usr__') || trimmed.includes('tmp/') || trimmed.includes('wxfile://')) {
      return '';
    }

    if (trimmed.startsWith('cloud://')) {
      return trimmed;
    }

    const normalizedAvatarPath = this.buildAvatarAccessUrl(trimmed);
    if (normalizedAvatarPath !== trimmed) {
      return normalizedAvatarPath;
    }

    const normalizedRemoteUrl = this.normalizeRemoteUrlProtocol(trimmed);

    if (normalizedRemoteUrl.includes('/api/upload/avatar/view?key=')) {
      return normalizedRemoteUrl;
    }

    const cosUrlPattern = /^https?:\/\/[^/]+(?:\.cos\.[^/]+\.myqcloud\.com|\.tcb\.qcloud\.la)\//i;
    if (cosUrlPattern.test(normalizedRemoteUrl)) {
      const pureUrl = normalizedRemoteUrl.split('?')[0];
      const avatarPathIndex = pureUrl.indexOf('/avatars/');
      if (avatarPathIndex >= 0) {
        const rawKey = pureUrl.slice(avatarPathIndex + 1);
        let objectKey = rawKey;
        try {
          objectKey = decodeURIComponent(rawKey);
        } catch (e) {
          objectKey = rawKey;
        }

        const baseUrl = this.normalizeRemoteUrlProtocol(this.globalData.baseUrl || '');
        if (baseUrl) {
          return `${baseUrl}/api/upload/avatar/view?key=${encodeURIComponent(objectKey)}`;
        }
      }
    }

    return normalizedRemoteUrl;
  },

  normalizeUserInfo(userInfo) {
    if (!userInfo || typeof userInfo !== 'object') {
      return userInfo || null;
    }

    const normalizedAvatar = this.normalizeAvatarUrl(
      userInfo.avatar_file_id || userInfo.avatar_url || ''
    );

    return {
      ...userInfo,
      avatar_url: normalizedAvatar,
      avatar_file_id:
        userInfo.avatar_file_id ||
        (typeof normalizedAvatar === 'string' && normalizedAvatar.startsWith('cloud://')
          ? normalizedAvatar
          : '')
    };
  },

  setUserInfo(userInfo) {
    const normalizedUserInfo = this.normalizeUserInfo(userInfo);
    this.globalData.userInfo = normalizedUserInfo || null;

    if (normalizedUserInfo) {
      wx.setStorageSync('userInfo', normalizedUserInfo);
    } else {
      wx.removeStorageSync('userInfo');
    }

    return normalizedUserInfo;
  },

  getDataDirtyStorageKey(userId = this.globalData.userId) {
    return `${DIRTY_SCOPE_STORAGE_PREFIX}${String(userId || 'guest').trim() || 'guest'}`;
  },

  normalizeDirtyScopes(scopes) {
    const list = Array.isArray(scopes) ? scopes : [scopes];
    return Array.from(
      new Set(
        list
          .map((item) => String(item || '').trim())
          .filter(Boolean)
      )
    );
  },

  readDirtyScopeMap(userId = this.globalData.userId) {
    const raw = wx.getStorageSync(this.getDataDirtyStorageKey(userId));
    if (!raw || typeof raw !== 'object') {
      return {};
    }
    return { ...raw };
  },

  writeDirtyScopeMap(scopeMap = {}, userId = this.globalData.userId) {
    const hasValue = Object.keys(scopeMap).length > 0;
    const storageKey = this.getDataDirtyStorageKey(userId);
    if (!hasValue) {
      wx.removeStorageSync(storageKey);
      return;
    }
    wx.setStorageSync(storageKey, scopeMap);
  },

  markDataDirty(scopes, userId = this.globalData.userId) {
    const normalizedScopes = this.normalizeDirtyScopes(scopes);
    if (!normalizedScopes.length) {
      return;
    }

    const scopeMap = this.readDirtyScopeMap(userId);
    normalizedScopes.forEach((scope) => {
      scopeMap[scope] = true;
    });
    this.writeDirtyScopeMap(scopeMap, userId);
  },

  peekDataDirty(scopes, userId = this.globalData.userId) {
    const normalizedScopes = this.normalizeDirtyScopes(scopes);
    if (!normalizedScopes.length) {
      return false;
    }

    const scopeMap = this.readDirtyScopeMap(userId);
    return normalizedScopes.some((scope) => !!scopeMap[scope]);
  },

  consumeDataDirty(scopes, userId = this.globalData.userId) {
    const normalizedScopes = this.normalizeDirtyScopes(scopes);
    if (!normalizedScopes.length) {
      return false;
    }

    const scopeMap = this.readDirtyScopeMap(userId);
    let consumed = false;

    normalizedScopes.forEach((scope) => {
      if (scopeMap[scope]) {
        consumed = true;
        delete scopeMap[scope];
      }
    });

    if (consumed) {
      this.writeDirtyScopeMap(scopeMap, userId);
    }

    return consumed;
  },

  async refreshCurrentUserProfile({ userId = this.globalData.userId } = {}) {
    if (!userId) {
      return null;
    }

    const rawProfile = await this.request({
      url: `/api/user/rank?user_id=${userId}`,
      retryCount: 1,
      timeout: 20000,
      debugTag: 'refresh-current-user-profile'
    });

    const resolvedProfile = await this.resolveAvatarFields(rawProfile, {
      avatarField: 'avatar',
      fileIdField: 'avatar_file_id'
    });

    const mergedUserInfo = {
      ...(this.globalData.userInfo || wx.getStorageSync('userInfo') || {}),
      ...resolvedProfile,
      avatar_url: resolvedProfile.avatar_url || resolvedProfile.avatar || '',
      avatar_file_id: resolvedProfile.avatar_file_id || ''
    };

    return this.setUserInfo(mergedUserInfo);
  },

  startPageAutoRefresh(page, { timerKey = '_autoRefreshTimer', intervalMs = 15000, refresh } = {}) {
    if (!page || typeof refresh !== 'function') {
      return null;
    }

    if (page[timerKey]) {
      return page[timerKey];
    }

    const runner = async () => {
      try {
        await refresh();
      } catch (err) {
        console.warn('page auto refresh failed:', err);
      }
    };

    const timer = setInterval(runner, Math.max(5000, Number(intervalMs) || 15000));
    page[timerKey] = timer;
    return timer;
  },

  stopPageAutoRefresh(page, timerKey = '_autoRefreshTimer') {
    if (!page || !page[timerKey]) {
      return;
    }

    clearInterval(page[timerKey]);
    page[timerKey] = null;
  },

  getTempFileURL(fileId) {
    return new Promise((resolve) => {
      if (!fileId || typeof fileId !== 'string' || !fileId.startsWith('cloud://')) {
        resolve('');
        return;
      }

      wx.cloud.getTempFileURL({
        fileList: [fileId],
        success: (res) => {
          const fileInfo = res && res.fileList && res.fileList[0];
          resolve(
            (fileInfo && (fileInfo.tempFileURL || fileInfo.tempFileUrl || fileInfo.download_url)) || ''
          );
        },
        fail: (err) => {
          console.error('getTempFileURL error:', err);
          resolve('');
        }
      });
    });
  },

  async resolveAvatarData(avatarValue) {
    const normalizedAvatar = this.normalizeAvatarUrl(avatarValue);
    if (!normalizedAvatar) {
      return { raw: '', display: '' };
    }

    if (!normalizedAvatar.startsWith('cloud://')) {
      return {
        raw: normalizedAvatar,
        display: normalizedAvatar
      };
    }

    const tempUrl = await this.getTempFileURL(normalizedAvatar);
    return {
      raw: normalizedAvatar,
      display: tempUrl || ''
    };
  },

  async resolveAvatarFields(target, { avatarField = 'avatar_url', fileIdField = 'avatar_file_id' } = {}) {
    if (!target || typeof target !== 'object') {
      return target || null;
    }

    const avatarSource = target[fileIdField] || target[avatarField] || '';
    const resolved = await this.resolveAvatarData(avatarSource);
    const nextTarget = {
      ...target,
      [avatarField]: resolved.display || '',
      [fileIdField]:
        resolved.raw && resolved.raw.startsWith('cloud://')
          ? resolved.raw
          : target[fileIdField] || ''
    };

    if (!resolved.display && resolved.raw && !resolved.raw.startsWith('cloud://')) {
      nextTarget[avatarField] = resolved.raw;
    }

    return nextTarget;
  },

  async resolveAvatarList(list, options = {}) {
    return Promise.all((list || []).map((item) => this.resolveAvatarFields(item, options)));
  },

  uploadAvatarViaCloud({ filePath = '', userId = '', phone = '', displayName = '', extension = 'png' } = {}) {
    return new Promise((resolve, reject) => {
      wx.cloud.uploadFile({
        cloudPath: this.buildAvatarCloudPath({
          userId,
          phone,
          displayName,
          extension
        }),
        filePath,
        success: async (res) => {
          if (!res || !res.fileID) {
            reject(new Error('Missing uploaded fileID'));
            return;
          }

          const resolvedAvatar = await this.resolveAvatarFields(
            {
              avatar_url: res.fileID,
              avatar_file_id: res.fileID
            },
            {
              avatarField: 'avatar_url',
              fileIdField: 'avatar_file_id'
            }
          );

          resolve({
            avatar_url: resolvedAvatar.avatar_url || '',
            avatar_file_id: resolvedAvatar.avatar_file_id || res.fileID
          });
        },
        fail: (err) => {
          reject(err);
        }
      });
    });
  },

  async uploadAvatar({ filePath = '', userId = '', phone = '', displayName = '', extension = 'png' } = {}) {
    return this.uploadAvatarViaCloud({
      filePath,
      userId,
      phone,
      displayName,
      extension
    });
  },

  legacyUploadAvatar({ filePath = '', cloudPath = '', success, fail, displayName = '' } = {}) {
    const pathForExtension = cloudPath || filePath || '';
    const matched = String(pathForExtension).match(/\.([a-zA-Z0-9]+)(?:$|\?)/);
    const extension = matched ? matched[1].toLowerCase() : 'png';

    this.uploadAvatar({
      filePath,
      userId: this.globalData.userId,
      phone: (this.globalData.userInfo && this.globalData.userInfo.phone) || '',
      extension,
      displayName
    })
      .then((result) => {
        if (typeof success === 'function') {
          success({
            fileID: result.avatar_file_id || result.avatar_url || '',
            avatar_url: result.avatar_url || '',
            avatar_file_id: result.avatar_file_id || ''
          });
        }
      })
      .catch((err) => {
        if (typeof fail === 'function') {
          fail(err);
        }
      });
  },

  syncAuthWithBaseUrl() {
    this.syncAuthWithRuntimeConfig();
  },

  syncAuthWithRuntimeConfig() {
    const currentSignature = this.getRuntimeSignature();
    const storedSignature = wx.getStorageSync('runtimeSignature');

    if (storedSignature && storedSignature !== currentSignature) {
      wx.removeStorageSync('userId');
      wx.removeStorageSync('token');
      wx.removeStorageSync('userInfo');
      wx.removeStorageSync('guestMode');
    }

    wx.setStorageSync('runtimeSignature', currentSignature);
    wx.setStorageSync('apiBaseUrl', this.globalData.baseUrl || '');
  },

  getUserProfile() {
    const userId = wx.getStorageSync('userId');
    const token = wx.getStorageSync('token');
    const userInfo = this.normalizeUserInfo(wx.getStorageSync('userInfo'));
    const guestMode = !!wx.getStorageSync('guestMode');

    this.globalData.guestMode = guestMode;

    if (userId && token) {
      this.globalData.userId = userId;
      this.globalData.token = token;
      this.globalData.userInfo = userInfo || null;
      this.globalData.guestMode = false;
      if (userInfo) {
        wx.setStorageSync('userInfo', userInfo);
      }
      return true;
    }

    this.globalData.userId = '';
    this.globalData.token = '';
    this.globalData.userInfo = null;
    return false;
  },

  getEnergyHistoryStorageKey(userId = '') {
    return `energyMallHistory:${userId}`;
  },

  getEnergySyncSignatureKey(userId = '') {
    return `energyMallHistorySynced:${userId}`;
  },

  readLegacyEnergyHistory(userId = '') {
    if (!userId) {
      return [];
    }

    const history = wx.getStorageSync(this.getEnergyHistoryStorageKey(userId));
    return Array.isArray(history) ? history : [];
  },

  buildEnergyHistorySignature(records = []) {
    return JSON.stringify(
      (records || []).map((item) => ({
        client_record_id: String(item.client_record_id || '').trim(),
        product_id: String(item.product_id || '').trim(),
        cost: Number(item.cost) || 0,
        status: String(item.status || '').trim(),
        created_at: String(item.created_at || '').trim()
      }))
    );
  },

  normalizeLegacyEnergyHistory(records = []) {
    return (records || [])
      .map((item) => ({
        client_record_id: String(item.id || item.client_record_id || '').trim(),
        product_id: String(item.productId || item.product_id || '').trim(),
        product_name: String(item.name || item.product_name || '').trim(),
        cost: Math.max(0, Number(item.cost) || 0),
        status: String(item.status || 'pending').trim() || 'pending',
        created_at: String(item.createdAt || item.created_at || '').trim()
      }))
      .filter((item) =>
        item.client_record_id &&
        item.product_id &&
        item.product_name &&
        item.cost > 0
      );
  },

  async syncEnergyRedemptions(userId = this.globalData.userId, { force = false } = {}) {
    if (!userId || !this.globalData.token) {
      return null;
    }

    const records = this.normalizeLegacyEnergyHistory(this.readLegacyEnergyHistory(userId));
    if (!records.length) {
      return null;
    }

    const signature = this.buildEnergyHistorySignature(records);
    const signatureKey = this.getEnergySyncSignatureKey(userId);
    const lastSyncedSignature = wx.getStorageSync(signatureKey);
    if (!force && lastSyncedSignature && lastSyncedSignature === signature) {
      return null;
    }

    const result = await this.request({
      url: '/api/energy/redemptions/sync',
      method: 'POST',
      data: { records },
      timeout: 20000,
      retryCount: 0,
      dedupe: false,
      debugTag: 'energy-redemption-sync'
    });

    wx.setStorageSync(signatureKey, signature);
    return result;
  },

  checkLogin(autoRedirect = true) {
    if (this.globalData.guestMode) {
      return true;
    }

    if (!this.globalData.userId || !this.globalData.token) {
      if (autoRedirect) {
        wx.navigateTo({
          url: '/pages/login/login'
        });
      }
      return false;
    }

    if (autoRedirect && this.shouldRequireProfileVerification()) {
      this.redirectToRegister();
      return false;
    }

    return true;
  },

  shouldRequireProfileVerification() {
    if (!this.globalData.userId || !this.globalData.token) {
      return false;
    }

    const userInfo = this.globalData.userInfo || this.normalizeUserInfo(wx.getStorageSync('userInfo'));
    return !(userInfo && userInfo.profile_verified);
  },

  redirectToRegister() {
    const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : [];
    const currentRoute = pages.length ? `/${pages[pages.length - 1].route}` : '';

    if (
      currentRoute === '/pages/register/register' ||
      currentRoute === '/pages/login/login'
    ) {
      return;
    }

    wx.reLaunch({
      url: '/pages/register/register'
    });
  },

  clearAuthState() {
    this.globalData.userId = '';
    this.globalData.token = '';
    this.globalData.userInfo = null;
    wx.removeStorageSync('userId');
    wx.removeStorageSync('token');
    wx.removeStorageSync('userInfo');
  },

  handleUnauthorized() {
    this.clearAuthState();
    wx.navigateTo({
      url: '/pages/login/login'
    });
  },

  requireLogin() {
    return this.checkLogin(true);
  },

  getInflightRequestStore() {
    if (!this._inflightRequests) {
      this._inflightRequests = new Map();
    }

    return this._inflightRequests;
  },

  buildRequestDedupKey(method, url, data) {
    let serializedData = '';
    try {
      serializedData = JSON.stringify(data || {});
    } catch (err) {
      serializedData = '';
    }

    return [
      String(method || 'GET').toUpperCase(),
      String(url || ''),
      serializedData,
      this.globalData.userId || '',
      this.globalData.token ? 'authed' : 'guest'
    ].join('::');
  },

  request(options) {
    const method = String(options.method || 'GET').toUpperCase();
    const maxRetries = options.retryCount === undefined ? 2 : options.retryCount;
    const timeout = options.timeout || 20000;
    const debugTag = String(options.debugTag || '').trim();
    const shouldDeduplicate =
      options.dedupe === undefined
        ? method === 'GET'
        : !!options.dedupe;
    const dedupKey = shouldDeduplicate
      ? this.buildRequestDedupKey(method, options.url, options.data)
      : '';
    const inflightRequests = this.getInflightRequestStore();

    if (dedupKey && inflightRequests.has(dedupKey)) {
      return inflightRequests.get(dedupKey);
    }

    const runRequest = (retryLeft) => new Promise((resolve, reject) => {
      let transportMode = 'callContainer';

      const header = {
        'Content-Type': 'application/json'
      };

      if (this.globalData.token) {
        header.Authorization = `Bearer ${this.globalData.token}`;
      }

      const retryOrReject = (error) => {
        if (retryLeft > 0) {
          setTimeout(() => {
            runRequest(retryLeft - 1).then(resolve).catch(reject);
          }, 400);
          return;
        }

        console.error('Network Error:', {
          message: error && error.message,
          errMsg: error && error.errMsg,
          source: error && error.source,
          path: error && error.path
        });
        reject(error);
      };

      const handleResponse = (res) => {
        if (res.statusCode === 401) {
          if (debugTag) {
            console.warn(`[request:${debugTag}] unauthorized via ${transportMode}`, {
              url: options.url,
              method,
              statusCode: res.statusCode
            });
          }
          this.handleUnauthorized();
          reject(res.data || { message: 'Unauthorized' });
          return;
        }

        if (res.statusCode >= 500 && retryLeft > 0) {
          setTimeout(() => {
            runRequest(retryLeft - 1).then(resolve).catch(reject);
          }, 400);
          return;
        }

        if (res.data && res.data.code === 0) {
          if (debugTag) {
            console.info(`[request:${debugTag}] success via ${transportMode}`, {
              url: options.url,
              method,
              statusCode: res.statusCode
            });
          }
          resolve(res.data.data);
          return;
        }

        if (debugTag) {
          console.warn(`[request:${debugTag}] non-zero response via ${transportMode}`, {
            url: options.url,
            method,
            statusCode: res.statusCode,
            code: res.data && res.data.code,
            message: res.data && res.data.message
          });
        }
        console.error('API Error:', {
          statusCode: res.statusCode,
          code: res.data && res.data.code,
          message: res.data && res.data.message
        });
        reject(res.data || { message: `HTTP ${res.statusCode}` });
      };

      const containerConfig = this.getCallContainerConfig();
      if (!containerConfig) {
        retryOrReject(new Error('Missing callContainer config'));
        return;
      }

      wx.cloud.callContainer({
        path: options.url,
        method,
        data: options.data || {},
        header: this.buildServiceHeaders(header),
        timeout,
        config: containerConfig,
        success: handleResponse,
        fail: (err) => {
          const runtimeConfig = this.getRuntimeConfig();
          if (debugTag) {
            console.warn(`[request:${debugTag}] callContainer failed`, {
              url: options.url,
              method,
              errMsg: err && err.errMsg,
              envVersion: runtimeConfig.envVersion || '',
              cloudEnvId: containerConfig.env || '',
              serviceName: runtimeConfig.serviceName || ''
            });
          }

          const enrichedError = Object.assign({}, err, {
            source: 'callContainer',
            path: options.url,
            envVersion: runtimeConfig.envVersion || '',
            cloudEnvId: containerConfig.env || '',
            serviceName: runtimeConfig.serviceName || ''
          });

          console.error('callContainer request failed:', {
            errMsg: enrichedError.errMsg,
            source: enrichedError.source,
            path: enrichedError.path,
            envVersion: enrichedError.envVersion,
            cloudEnvId: enrichedError.cloudEnvId,
            serviceName: enrichedError.serviceName
          });
          retryOrReject(enrichedError);
        }
      });
    });

    const requestPromise = runRequest(maxRetries);

    if (!dedupKey) {
      return requestPromise;
    }

    inflightRequests.set(dedupKey, requestPromise);
    requestPromise.finally(() => {
      if (inflightRequests.get(dedupKey) === requestPromise) {
        inflightRequests.delete(dedupKey);
      }
    });

    return requestPromise;
  }
});
