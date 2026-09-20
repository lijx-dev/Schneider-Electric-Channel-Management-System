const app = getApp();

const SLOGAN = '欢迎开启您的母线能量探索之旅。完成六大主题展区探索并集齐六枚「能量印记」，即可领取专属「能量勋章」，前往手工工坊完成属于您的定制纪念手串。';
const REDEEM_TEXT = '请前往大会兑换处出示本勋章兑换实物勋章，并前往 DIY 区制作专属纪念手串';

Page({
  data: {
    slogan: SLOGAN,
    redeemText: REDEEM_TEXT,
    phone: '',
    zones: [],
    claimedCount: 0,
    totalZones: 0,
    medal: { granted: false, medal_code: '' },
    canGoBack: false,
    loading: true
  },

  onLoad() {
    const phone = wx.getStorageSync('conferencePhone') || '';
    const pages = getCurrentPages();
    this.setData({ canGoBack: pages.length > 1 });
    if (!phone) {
      wx.showToast({ title: '请先扫码签到', icon: 'none' });
      this.setData({ loading: false });
      return;
    }
    this.setData({ phone });
    this.loadOverview();
  },

  async loadOverview() {
    this.setData({ loading: true });
    try {
      const data = await app.request({
        url: '/api/conference/overview',
        data: { phone: this.data.phone },
        retryCount: 1
      });
      const zones = data.zones || [];
      const claimedCount = zones.filter((z) => z.claimed).length;
      this.setData({
        zones,
        claimedCount,
        totalZones: zones.length,
        medal: data.medal || { granted: false, medal_code: '' }
      });
    } catch (err) {
      console.warn('load conference overview failed:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  goBackToZone() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    }
  }
});
