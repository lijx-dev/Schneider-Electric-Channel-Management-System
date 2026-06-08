const app = getApp();

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hour = `${date.getHours()}`.padStart(2, '0');
  const minute = `${date.getMinutes()}`.padStart(2, '0');
  return `${year}-${month}-${day} ${hour}:${minute}`;
}

function mapTypeText(type) {
  if (type === 'monthly_rank_reward') return '月榜奖励';
  if (type === 'lottery_reward') return '抽奖奖励';
  return '奖励';
}

Page({
  data: {
    loading: true,
    currentType: 'all',
    tabs: [
      { key: 'all', text: '全部' },
      { key: 'monthly_rank_reward', text: '月榜奖励' },
      { key: 'lottery_reward', text: '抽奖奖励' }
    ],
    records: []
  },

  onLoad() {
    if (!app.requireLogin()) return;
    this.loadData();
  },

  onShow() {
    if (!app.globalData.userId) return;
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  switchType(e) {
    const type = e.currentTarget.dataset.type;
    if (!type || type === this.data.currentType) return;
    this.setData({ currentType: type }, () => this.loadData());
  },

  async loadData() {
    if (!app.globalData.userId) return;

    this.setData({ loading: true });
    try {
      const records = await app.request({
        url: '/api/rewards/records',
        data: {
          reward_type: this.data.currentType,
          limit: 100
        }
      });

      this.setData({
        loading: false,
        records: (records || []).map(item => ({
          ...item,
          typeText: mapTypeText(item.type),
          amountText: `+${Number(item.amount || 0)}格`,
          timeText: formatDateTime(item.created_at)
        }))
      });
    } catch (err) {
      console.error('Reward record load error:', err);
      this.setData({ loading: false, records: [] });
      wx.showToast({
        title: '奖励记录加载失败',
        icon: 'none'
      });
    }
  }
});
