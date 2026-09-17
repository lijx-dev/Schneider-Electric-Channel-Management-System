const app = getApp();

Page({
  data: {
    zone: null,
    progress: null,
    loading: true
  },

  onLoad() {
    this.loadZone();
  },

  onShow() {
    // 从各步骤返回时刷新进度
    if (!this.data.loading) {
      this.loadZone();
    }
  },

  async loadZone() {
    this.setData({ loading: true });
    try {
      const data = await app.request({
        url: '/api/conference/zones/channel',
        retryCount: 1
      });
      this.setData({ zone: data, progress: data.progress || null });
    } catch (err) {
      console.warn('load channel zone failed:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // ── 各步骤「去完成」按钮 ──
  goToWeeklyQuiz() {
    wx.navigateTo({ url: '/pages/quiz/quiz' });
  },

  goToAiChat() {
    wx.navigateTo({
      url: '/pages/zhinengwenda_AI_Assistant_Green/zhinengwenda_AI_Assistant_Green'
    });
  },

  goToEnergyMall() {
    wx.switchTab({ url: '/pages/energy-mall/index' });
  }
});
