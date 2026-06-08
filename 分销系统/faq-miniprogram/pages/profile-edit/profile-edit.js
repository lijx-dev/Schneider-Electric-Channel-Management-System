const app = getApp();

function normalizeProvinceName(value) {
  if (!value) return '';

  const text = String(value).trim().replace(/\s+/g, '');
  const specialMappings = {
    北京市: '北京',
    上海市: '上海',
    天津市: '天津',
    重庆市: '重庆',
    广西壮族自治区: '广西',
    内蒙古自治区: '内蒙古',
    宁夏回族自治区: '宁夏',
    新疆维吾尔自治区: '新疆',
    西藏自治区: '西藏',
    香港特别行政区: '香港',
    澳门特别行政区: '澳门'
  };

  if (specialMappings[text]) {
    return specialMappings[text];
  }

  if (text.endsWith('省')) {
    return text.slice(0, -1);
  }

  if (text.endsWith('市')) {
    const shortName = text.slice(0, -1);
    if (['北京', '上海', '天津', '重庆'].includes(shortName)) {
      return shortName;
    }
  }

  return text;
}

Page({
  data: {
    userInfo: {
      avatar_url: '',
      avatar_file_id: '',
      nickname: ''
    },
    realName: '',
    selectedProvince: '',
    selectedCompany: '',
    isUploadingAvatar: false,
    isSavingProfile: false
  },

  async onLoad() {
    if (!app.requireLogin()) return;
    await this.loadProfile();
  },

  async loadProfile() {
    const cachedInfo = wx.getStorageSync('userInfo') || {};
    let profile = { ...cachedInfo };

    try {
      const latestProfile = await app.request({
        url: `/api/user/rank?user_id=${app.globalData.userId}`,
        method: 'GET',
        retryCount: 1,
        timeout: 20000,
        debugTag: 'profile-edit-rank'
      });

      if (latestProfile) {
        profile = {
          ...profile,
          nickname: latestProfile.nickname || profile.nickname || '',
          avatar_url: latestProfile.avatar || latestProfile.avatar_url || profile.avatar_url || '',
          avatar_file_id: latestProfile.avatar_file_id || profile.avatar_file_id || '',
          real_name: latestProfile.real_name || profile.real_name || '',
          province: latestProfile.province || profile.province || '',
          company: latestProfile.company || profile.company || '',
          profile_verified: latestProfile.profile_verified ?? profile.profile_verified
        };
      }
    } catch (err) {
      console.warn('加载最新个人信息失败，继续使用本地缓存:', err);
    }

    const resolvedProfile = await app.resolveAvatarFields(profile, {
      avatarField: 'avatar_url',
      fileIdField: 'avatar_file_id'
    });

    this.setData({
      userInfo: {
        avatar_url: resolvedProfile.avatar_url || '',
        avatar_file_id: resolvedProfile.avatar_file_id || '',
        nickname: resolvedProfile.nickname || ''
      },
      realName: resolvedProfile.real_name || '',
      selectedProvince: normalizeProvinceName(resolvedProfile.province || ''),
      selectedCompany: resolvedProfile.company || ''
    });
  },

  buildProfilePayload() {
    const { userInfo, realName, selectedProvince, selectedCompany } = this.data;

    let avatarToSave = userInfo.avatar_file_id || userInfo.avatar_url || '';
    if (
      avatarToSave &&
      (avatarToSave.includes('__usr__') || avatarToSave.includes('tmp/') || avatarToSave.includes('wxfile://'))
    ) {
      avatarToSave = '';
    }

    return {
      user_id: app.globalData.userId,
      nickname: userInfo.nickname || realName || '施耐德用户',
      avatar: avatarToSave,
      real_name: realName,
      province: selectedProvince,
      company: selectedCompany
    };
  },

  async persistProfile({ showSuccessToast = true } = {}) {
    const { userInfo, realName, selectedProvince, selectedCompany } = this.data;

    if (!realName || !selectedProvince || !selectedCompany) {
      wx.showToast({ title: '认证资料缺失，请联系管理员', icon: 'none' });
      return null;
    }

    const updatedProfile = await app.request({
      url: '/api/user/profile',
      method: 'POST',
      data: this.buildProfilePayload(),
      retryCount: 1,
      timeout: 25000
    });

    const nextUserInfo = app.setUserInfo({
      ...(wx.getStorageSync('userInfo') || {}),
      ...updatedProfile,
      nickname: updatedProfile.nickname || userInfo.nickname || realName || '',
      avatar_url: updatedProfile.avatar_url || userInfo.avatar_url || '',
      avatar_file_id: updatedProfile.avatar_file_id || userInfo.avatar_file_id || '',
      real_name: updatedProfile.real_name || realName,
      province: normalizeProvinceName(updatedProfile.province || selectedProvince),
      company: updatedProfile.company || selectedCompany,
      profile_verified: true
    });

    const displayUserInfo = await app.resolveAvatarFields(nextUserInfo, {
      avatarField: 'avatar_url',
      fileIdField: 'avatar_file_id'
    });

    app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy', 'redeem']);

    this.setData({
      userInfo: {
        avatar_url: displayUserInfo.avatar_url || '',
        avatar_file_id: displayUserInfo.avatar_file_id || '',
        nickname: displayUserInfo.nickname || ''
      },
      realName: displayUserInfo.real_name || realName,
      selectedProvince: normalizeProvinceName(displayUserInfo.province || selectedProvince),
      selectedCompany: displayUserInfo.company || selectedCompany
    });

    if (showSuccessToast) {
      wx.showToast({ title: '头像已保存', icon: 'success' });
    }

    return displayUserInfo;
  },

  async onChooseWechatAvatar(event) {
    if (this.data.isUploadingAvatar || this.data.isSavingProfile) {
      return;
    }

    const avatarUrl = String((event && event.detail && event.detail.avatarUrl) || '').trim();
    if (!avatarUrl) {
      return;
    }

    await this.uploadSelectedAvatar(avatarUrl);
  },

  async uploadSelectedAvatar(avatarUrl) {
    const matched = String(avatarUrl).match(/\.([a-zA-Z0-9]+)(?:$|\?)/);
    const extension = matched ? matched[1].toLowerCase() : 'png';
    const safeExtension = ['jpg', 'jpeg', 'png', 'webp'].includes(extension) ? extension : 'png';

    this.setData({ isUploadingAvatar: true });
    wx.showLoading({ title: '上传中...' });

    try {
      const cachedUserInfo = app.globalData.userInfo || wx.getStorageSync('userInfo') || {};
      const result = await app.uploadAvatar({
        filePath: avatarUrl,
        userId: app.globalData.userId,
        phone: cachedUserInfo.phone || '',
        displayName: this.data.realName || this.data.userInfo.nickname || '',
        extension: safeExtension
      });

      this.setData({
        'userInfo.avatar_url': result.avatar_url || '',
        'userInfo.avatar_file_id': result.avatar_file_id || '',
        isSavingProfile: true
      });

      await this.persistProfile({ showSuccessToast: false });

      wx.hideLoading();
      wx.showToast({ title: '头像已更新', icon: 'success' });
    } catch (err) {
      wx.hideLoading();
      console.error('上传头像失败:', err);
      wx.showToast({ title: '网络异常，上传失败', icon: 'none' });
    } finally {
      this.setData({
        isUploadingAvatar: false,
        isSavingProfile: false
      });
    }
  },

  async saveProfile() {
    wx.showLoading({ title: '保存中...' });
    this.setData({ isSavingProfile: true });

    try {
      await this.persistProfile({ showSuccessToast: false });
      wx.hideLoading();
      wx.showToast({ title: '头像已保存', icon: 'success' });

      setTimeout(() => {
        const pages = getCurrentPages();
        if (pages.length > 1) {
          wx.navigateBack();
        } else {
          wx.switchTab({ url: '/pages/wode_User_Profile_Green/wode_User_Profile_Green' });
        }
      }, 1200);
    } catch (err) {
      console.error('保存头像失败:', err);
      wx.hideLoading();
      wx.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      this.setData({ isSavingProfile: false });
    }
  }
});
