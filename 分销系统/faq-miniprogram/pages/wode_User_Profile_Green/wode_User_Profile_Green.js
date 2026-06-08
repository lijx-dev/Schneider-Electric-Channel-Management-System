const app = getApp();

Page({
  data: {
    isGuestMode: false,
    userData: null,
    profileName: '',
    profileCompany: '',
    level: 1,
    redeemCount: 0
  },

  onLoad() {
    this._isLoadingUserData = false;
  },

  onShow() {
    this.loadUserData();
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',
      intervalMs: 20000,
      refresh: () => this.loadUserData()
    });
  },

  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onUnload() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  setGuestView() {
    this.setData({
      isGuestMode: true,
      userData: {
        total_score: 0,
        available_energy: 0,
        rank: '-',
        total_count: 0
      },
      profileName: '游客',
      profileCompany: '登录后完善个人资料',
      level: 1,
      redeemCount: 0
    });
  },

  async loadUserData() {
    if (this._isLoadingUserData) {
      return;
    }

    if (!app.globalData.userId && !app.getUserProfile()) {
      this.setGuestView();
      return;
    }

    this._isLoadingUserData = true;

    try {
      try {
        await app.syncEnergyRedemptions(app.globalData.userId);
      } catch (syncErr) {
        console.warn('Profile energy sync error:', syncErr);
      }

      const refreshedProfile = await app.refreshCurrentUserProfile();
      const res = await app.resolveAvatarFields(refreshedProfile, {
        avatarField: 'avatar_url',
        fileIdField: 'avatar_file_id'
      });

      const profileName =
        res.real_name ||
        (res.nickname || '').replace(/\s*\([^)]*\)\s*$/, '') ||
        '分销商学堂';

      const normalizedUserData = {
        ...res,
        avatar: res.avatar_url || res.avatar || ''
      };

      this.setData({
        isGuestMode: false,
        userData: normalizedUserData,
        profileName,
        profileCompany: res.company || '',
        level: Math.floor((normalizedUserData.total_score || 0) / 1000) + 1,
        redeemCount: Number(normalizedUserData.redemption_count) || 0
      });
    } catch (err) {
      console.error('Profile load error:', err);
    } finally {
      this._isLoadingUserData = false;
    }
  },

  goToProfileEdit() {
    if (this.data.isGuestMode) {
      wx.navigateTo({ url: '/pages/login/login' });
      return;
    }

    wx.navigateTo({ url: '/pages/profile-edit/profile-edit' });
  },

  goToStudyRecord() {
    if (this.data.isGuestMode) {
      wx.navigateTo({ url: '/pages/login/login' });
      return;
    }

    wx.navigateTo({ url: '/pages/studyRecord/index' });
  },

  goToRedeemRecord() {
    if (this.data.isGuestMode) {
      wx.navigateTo({ url: '/pages/login/login' });
      return;
    }

    wx.navigateTo({ url: '/pages/redeem-record/index' });
  },

  goToRewardRecord() {
    if (this.data.isGuestMode) {
      wx.navigateTo({ url: '/pages/login/login' });
      return;
    }

    wx.navigateTo({ url: '/pages/reward-record/index' });
  },

  goToHelpCenter() {
    wx.navigateTo({ url: '/pages/help-center/index' });
  },

  goToAboutAcademy() {
    wx.navigateTo({ url: '/pages/about-academy/index' });
  },

  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (!res.confirm) return;

        wx.removeStorageSync('token');
        wx.removeStorageSync('userId');
        wx.removeStorageSync('userInfo');
        wx.removeStorageSync('guestMode');

        app.globalData.token = '';
        app.globalData.userId = '';
        app.globalData.userInfo = null;
        app.globalData.guestMode = false;

        wx.showToast({
          title: '已退出登录',
          icon: 'success'
        });

        setTimeout(() => {
          wx.navigateTo({ url: '/pages/login/login' });
        }, 300);
      }
    });
  },

  onShareAppMessage() {
    return {};
  }
});
