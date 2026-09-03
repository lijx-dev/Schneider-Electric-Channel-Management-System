const HOME_URL = '/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green';
const REGISTER_URL = '/pages/register/register';
const LOGIN_API = '/api/auth/login_phone';
const PASSWORD_LOGIN_API = '/api/auth/login_password';
const app = getApp();

Page({
  data: {
    agreed: false,
    loginCode: '',
    showPasswordLogin: false,
    username: '',
    password: ''
  },

  onLoad() {
    this.refreshLoginCode();
  },

  refreshLoginCode() {
    wx.login({
      success: (res) => {
        if (res.code) {
          this.setData({ loginCode: res.code });
          return;
        }

        console.error('获取登录 code 失败', res.errMsg);
      },
      fail: (err) => {
        console.error('微信登录初始化失败', err);
      }
    });
  },

  toggleAgree() {
    this.setData({
      agreed: !this.data.agreed
    });
  },

  togglePasswordLogin() {
    this.setData({
      showPasswordLogin: !this.data.showPasswordLogin
    });
  },

  onUsernameInput(e) {
    this.setData({
      username: e.detail.value
    });
  },

  onPasswordInput(e) {
    this.setData({
      password: e.detail.value
    });
  },

  showPolicy(e) {
    const type = (e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.type) || 'terms';
    const url = type === 'privacy'
      ? '/pages/legal/privacy/index'
      : '/pages/legal/terms/index';

    wx.navigateTo({ url });
  },

  ensureAgreement() {
    if (this.data.agreed) {
      return true;
    }

    wx.showToast({
      title: '请先阅读并同意服务协议与隐私政策',
      icon: 'none',
      duration: 2200
    });
    return false;
  },

  async ensureLoginCode() {
    if (this.data.loginCode) {
      return this.data.loginCode;
    }

    await new Promise((resolve) => {
      wx.login({
        success: (res) => {
          if (res.code) {
            this.setData({ loginCode: res.code });
          }
          resolve();
        },
        fail: () => resolve()
      });
    });

    return this.data.loginCode;
  },

  async getPhoneNumber(e) {
    if (!this.ensureAgreement()) {
      return;
    }

    if (e.detail.errMsg !== 'getPhoneNumber:ok') {
      wx.showToast({
        title: '已取消授权，可选择暂不登录继续体验',
        icon: 'none',
        duration: 2500
      });
      return;
    }

    const loginCode = await this.ensureLoginCode();
    const phoneCode = e.detail.code;

    if (!loginCode || !phoneCode) {
      wx.showToast({
        title: '微信授权信息获取失败，请重试',
        icon: 'none'
      });
      this.refreshLoginCode();
      return;
    }

    this.doLogin(loginCode, phoneCode);
  },

  async doLogin(loginCode, phoneCode) {
    wx.showLoading({ title: '登录中...' });

    try {
      this.refreshLoginCode();

      const res = await app.request({
        url: LOGIN_API,
        method: 'POST',
        data: {
          login_code: loginCode,
          phone_code: phoneCode
        }
      });

      const user = app.normalizeUserInfo(res.user || {});
      const token = res.token || '';

      app.setUserInfo(user);
      app.globalData.userId = user.id || '';
      app.globalData.token = token;
      app.globalData.guestMode = false;

      wx.setStorageSync('userId', user.id || '');
      wx.setStorageSync('token', token);
      wx.removeStorageSync('guestMode');
      app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy', 'redeem']);

      wx.showToast({
        title: '登录成功',
        icon: 'success',
        duration: 1200
      });

      setTimeout(() => {
        if (!(user.disclaimer_agreed === true)) {
          wx.reLaunch({ url: '/pages/disclaimer/disclaimer' });
          return;
        }

        if (!user.profile_verified) {
          wx.reLaunch({
            url: REGISTER_URL
          });
          return;
        }

        wx.switchTab({ url: HOME_URL });
      }, 700);
    } catch (err) {
      console.error('登录失败:', err);
      let msg = err.detail || err.message || '网络或服务器异常，请稍后重试';
      if (msg.includes('code been used')) {
        msg = '登录码已过期，请重新点击登录';
        this.refreshLoginCode();
      }
      wx.showModal({
        title: '登录失败',
        content: msg,
        showCancel: false
      });
    } finally {
      wx.hideLoading();
    }
  },

  async doPasswordLogin() {
    if (!this.ensureAgreement()) {
      return;
    }

    const username = String(this.data.username || '').trim();
    const password = String(this.data.password || '');

    if (!username || !password) {
      wx.showToast({
        title: '请输入账号和密码',
        icon: 'none'
      });
      return;
    }

    wx.showLoading({ title: '登录中...' });

    try {
      const res = await app.request({
        url: PASSWORD_LOGIN_API,
        method: 'POST',
        data: {
          username,
          password
        }
      });

      const user = app.normalizeUserInfo(res.user || {});
      const token = res.token || '';

      app.setUserInfo(user);
      app.globalData.userId = user.id || '';
      app.globalData.token = token;
      app.globalData.guestMode = false;

      wx.setStorageSync('userId', user.id || '');
      wx.setStorageSync('token', token);
      wx.removeStorageSync('guestMode');
      app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy', 'redeem']);

      wx.showToast({
        title: '登录成功',
        icon: 'success',
        duration: 1200
      });

      setTimeout(() => {
        if (!(user.disclaimer_agreed === true)) {
          wx.reLaunch({ url: '/pages/disclaimer/disclaimer' });
          return;
        }

        if (!user.profile_verified) {
          wx.reLaunch({
            url: REGISTER_URL
          });
          return;
        }

        wx.switchTab({ url: HOME_URL });
      }, 700);
    } catch (err) {
      console.error('账号密码登录失败:', err);
      wx.showModal({
        title: '登录失败',
        content: err.detail || err.message || '账号或密码错误，请重试',
        showCancel: false
      });
    } finally {
      wx.hideLoading();
    }
  },

  cancelLogin() {
    wx.setStorageSync('guestMode', true);

    app.clearAuthState();
    app.globalData.guestMode = true;

    wx.switchTab({
      url: HOME_URL,
      fail: () => {
        // 兜底：登录页可能不是从 tab 页进入的，直接重定向到首页保证能退出登录流程
        wx.reLaunch({ url: HOME_URL });
      }
    });
  },

  onShareAppMessage() {
    return {};
  }
});
