const app = getApp();

Page({
  data: {
    loading: true,
    year: 0,
    month: '',
    // 积分排行
    pointsRanking: [],
    // 月度微光之星
    monthlyStars: null,
    // 月度销圈人气王
    monthlyMvp: null,
    // 季度奖项
    quarterlyAwards: null,
    // 年度奖项
    annualAwards: null
  },

  onLoad() {
    const now = new Date();
    this.setData({
      year: now.getFullYear(),
      month: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    });
    this.loadRanking();
  },

  async loadRanking() {
    try {
      const result = await app.request({
        url: `/api/recognition/ranking?year=${this.data.year}&month=${this.data.month}`
      });
      this.setData({
        loading: false,
        pointsRanking: result.points_ranking || [],
        monthlyStars: result.monthly_stars || null,
        monthlyMvp: result.monthly_mvp || null,
        quarterlyAwards: result.quarterly_awards || null,
        annualAwards: result.annual_awards || null
      });
    } catch (err) {
      console.error('Load ranking error:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  getRankBadge(rank) {
    if (rank === 1) return { text: '金', class: 'rank-gold' };
    if (rank === 2) return { text: '银', class: 'rank-silver' };
    if (rank === 3) return { text: '铜', class: 'rank-bronze' };
    return null;
  },

  getAwardTypeName(type) {
    const map = {
      monthly_star: '微光之星',
      monthly_mvp: '销圈人气王',
      order_guardian: '报备秩序卫士',
      distributor_pioneer: '分销商支持先锋',
      distributor_mentor: '分销商成长伯乐',
      efficiency_innovator: '效率提升创新',
      annual_star: '年度渠道之星'
    };
    return map[type] || type;
  }
});