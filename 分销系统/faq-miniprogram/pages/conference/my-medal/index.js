const app = getApp();

const SLOGAN =
  '欢迎开启您的母线能量探索之旅。完成六大主题展区探索并集齐六枚「能量印记」，即可领取专属「能量勋章」，前往手工工坊完成属于您的定制纪念手串。';

const REDEEM_GUIDE = '请前往大会兑换处出示本勋章兑换实物勋章，并前往 DIY 区制作专属纪念手串';

Page({
  data: {
    slogan: SLOGAN,
    redeemGuide: REDEEM_GUIDE,
    medal: null,
    loading: true
  },

  onLoad() {
    this.loadMedal();
  },

  async loadMedal() {
    this.setData({ loading: true });
    try {
      const data = await app.request({
        url: '/api/conference/medal',
        retryCount: 1
      });
      this.setData({ medal: data });
    } catch (err) {
      console.warn('load medal failed:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  }
});
