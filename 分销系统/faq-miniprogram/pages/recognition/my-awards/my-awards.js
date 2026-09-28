const app = getApp();

// 经理端「评选结果」分组顺序
const AWARD_TYPE_ORDER = [
  'monthly_star',
  'monthly_mvp',
  'order_guardian',
  'distributor_pioneer',
  'distributor_mentor',
  'efficiency_innovator',
  'annual_star'
];

Page({
  data: {
    loading: true,
    // 经理端：展示全量已发布评选结果，不展示个人等级卡片与积分明细
    isManager: false,
    awardGroups: [],
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
    const recognitionRole = (app.globalData.userInfo && app.globalData.userInfo.recognition_role) || '';
    const isManager = recognitionRole === 'manager';
    this.setData({ isManager });

    try {
      if (isManager) {
        // 经理端：全量已发布评选结果，按奖项类型分组
        const awardsResult = await app.request({
          url: '/api/recognition/awards/results?published=true'
        });
        const awards = Array.isArray(awardsResult) ? awardsResult : [];
        this.setData({
          loading: false,
          awards,
          awardGroups: this.buildAwardGroups(awards)
        });
        return;
      }

      const [pointsResult, awardsResult, transactionsResult] = await Promise.all([
        app.request({ url: '/api/recognition/points' }),
        app.request({ url: '/api/recognition/awards/results?published=true&mine=true' }),
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

  // 经理端：把评奖结果按奖项类型分组，未知类型排在已知类型之后
  buildAwardGroups(awards) {
    const grouped = {};
    (awards || []).forEach((item) => {
      const type = (item && item.award_type) || 'other';
      if (!grouped[type]) grouped[type] = [];
      grouped[type].push(item);
    });

    const orderedTypes = AWARD_TYPE_ORDER.filter((type) => grouped[type] && grouped[type].length)
      .concat(Object.keys(grouped).filter((type) => AWARD_TYPE_ORDER.indexOf(type) < 0));

    return orderedTypes.map((type) => ({
      type,
      typeName: this.getAwardTypeName(type),
      items: grouped[type]
    }));
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
      efficiency_innovator: '效能提升创新者',
      annual_star: '年度渠道之星',
      other: '其他奖项'
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