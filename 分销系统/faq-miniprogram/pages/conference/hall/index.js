const app = getApp();

const SLOGAN =
  '欢迎开启您的母线能量探索之旅。完成六大主题展区探索并集齐六枚「能量印记」，即可领取专属「能量勋章」，前往手工工坊完成属于您的定制纪念手串。';

Page({
  data: {
    slogan: SLOGAN,
    zones: [],
    medal: { granted: false, medal_code: '' },
    loading: true
  },

  onLoad() {
    this.loadOverview();
  },

  onShow() {
    // 从答题/渠道页返回时刷新印记与勋章状态
    if (!this.data.loading) {
      this.loadOverview();
    }
  },

  async loadOverview() {
    this.setData({ loading: true });
    try {
      const data = await app.request({
        url: '/api/conference/overview',
        retryCount: 1
      });
      this.setData({
        zones: data.zones || [],
        medal: data.medal || { granted: false, medal_code: '' }
      });
    } catch (err) {
      console.warn('load conference overview failed:', err);
      wx.showToast({ title: '加载失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  goToZone(e) {
    const zone = e.currentTarget.dataset.zone;
    if (!zone) return;

    if (zone.task_type === 'channel') {
      wx.navigateTo({ url: '/pages/conference/zone-channel/index' });
    } else {
      wx.navigateTo({
        url: `/pages/conference/zone-quiz/index?code=${zone.code}&name=${encodeURIComponent(zone.name)}`
      });
    }
  },

  goToMedal() {
    wx.navigateTo({ url: '/pages/conference/my-medal/index' });
  }
});
