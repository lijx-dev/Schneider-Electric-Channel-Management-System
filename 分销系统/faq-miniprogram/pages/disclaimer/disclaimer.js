const app = getApp();
const DISCLAIMER_VERSION = 'v1';
const HOME_URL = '/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green';

Page({
  data: {
    agreed: false,
    confirming: false
  },

  onLoad() {
    // 未登录（非游客）用户不应进入本页，引导回登录
    if (!app.globalData.userId || !app.globalData.token) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }

    // 已登录且已同意过：不再重复展示，直接回首页
    const userInfo =
      app.globalData.userInfo || app.normalizeUserInfo(wx.getStorageSync('userInfo'));
    if (userInfo && userInfo.disclaimer_agreed) {
      wx.reLaunch({ url: HOME_URL });
    }
  },

  toggleAgree() {
    this.setData({ agreed: !this.data.agreed });
  },

  onDecline() {
    wx.showModal({
      title: '无法继续使用',
      content: '本系统内容仅限于授权合作伙伴开展业务活动使用，您需要同意本声明后才能使用平台功能。',
      showCancel: false
    });
  },

  async onAgree() {
    if (!this.data.agreed) {
      wx.showToast({
        title: '请先勾选同意声明',
        icon: 'none'
      });
      return;
    }

    if (this.data.confirming) {
      return;
    }

    this.setData({ confirming: true });
    wx.showLoading({ title: '提交中...' });

    try {
      const res = await app.request({
        url: '/api/auth/consent',
        method: 'POST',
        data: { version: DISCLAIMER_VERSION }
      });

      const user = app.normalizeUserInfo(res.user || {});
      app.setUserInfo(user);

      if (app.globalData.userInfo) {
        app.globalData.userInfo.disclaimer_agreed = !!(user.disclaimer_agreed);
      }

      app.markDataDirty(['profile', 'home']);

      wx.hideLoading();
      wx.showToast({
        title: '已同意',
        icon: 'success',
        duration: 800
      });

      setTimeout(() => {
        wx.reLaunch({ url: HOME_URL });
      }, 700);
    } catch (err) {
      wx.hideLoading();
      wx.showModal({
        title: '提交失败',
        content: (err && err.detail) || '同意操作失败，请稍后重试',
        showCancel: false
      });
    } finally {
      this.setData({ confirming: false });
    }
  }
});