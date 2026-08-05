const app = getApp();

Page({
  data: {
    loading: true,
    // 积分
    totalScore: 0,
    level: { level: '启明星', level_icon: '☆' },
    nextLevel: null,
    pointsToNext: null,
    progressPercent: 0,
    // 获奖记录
    awards: [],
    // 积分明细
    transactions: [],
    // tab
    activeTab: 'awards'
  },

  onLoad() {
    this.loadAll();
  },

  async loadAll() {
    try {
      const [pointsResult, awardsResult, transactionsResult] = await Promise.all([
        app.request({ url: '/api/recognition/points' }),
        app.request({ url: '/api/recognition/awards/results?published=true' }),
        app.request({ url: '/api/recognition/points/transactions' })
      ]);

      const totalScore = (pointsResult && pointsResult.total_score) || 0;
      const level = {
        level: (pointsResult && pointsResult.level) || '启明星',
        level_icon: (pointsResult && pointsResult.level_icon) || '☆',
        progressPercent: this.calcProgress(totalScore, pointsResult)
      };

      this.setData({
        loading: false,
        totalScore,
        level,
        nextLevel: (pointsResult && pointsResult.next_level) || null,
        pointsToNext: (pointsResult && pointsResult.points_to_next) || null,
        progressPercent: level.progressPercent,
        awards: Array.isArray(awardsResult) ? awardsResult : [],
        transactions: Array.isArray(transactionsResult) ? transactionsResult : []
      });
    } catch (err) {
      console.error('Load awards error:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  calcProgress(score, pointsResult) {
    const s = score || 0;
    const level = (pointsResult && pointsResult.level) || '启明星';
    const thresholds = { '启明星': 100, '灿星': 200, '耀星': 300, '极星': 100 };
    const bases = { '启明星': 0, '灿星': 100, '耀星': 300, '极星': 600 };
    const cap = thresholds[level] || 100;
    const base = bases[level] || 0;
    if (cap <= 0) return 100;
    return Math.min((s - base) / cap * 100, 100);
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({ activeTab: tab });
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
  },

  getTransactionReason(reason) {
    const map = {
      monthly_star: '微光之星',
      monthly_mvp: '销圈人气王',
      order_guardian: '报备秩序卫士',
      distributor_pioneer: '分销商支持先锋',
      distributor_mentor: '分销商成长伯乐',
      efficiency_innovator: '效率提升创新',
      annual_star: '年度渠道之星',
      manual_adjust: '手动调整'
    };
    return map[reason] || reason;
  }
});