const app = getApp();

const DIM_KEY_MAP = [
  { key: 'efficiency', label: '报备处理效率' },
  { key: 'communication', label: '沟通顺畅程度' },
  { key: 'response', label: '分销商诉求响应' },
  { key: 'training', label: '分销商赋能培训支持' }
];

Page({
  data: {
    loading: true,
    month: '',
    records: [],
    total: 0,
    isManager: false
  },

  onLoad() {
    // 默认查询上月
    const now = new Date();
    const last = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastMonth = `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}`;
    const recognitionRole = (app.globalData.userInfo && app.globalData.userInfo.recognition_role) || '';
    this.setData({ month: lastMonth, isManager: recognitionRole === 'manager' });
    this.loadDetails();
  },

  onMonthChange(e) {
    this.setData({ month: e.detail.value });
    this.loadDetails();
  },

  loadPrevMonth() {
    const [y, m] = this.data.month.split('-').map(Number);
    if (!y || !m) return;
    const prev = new Date(y, m - 2, 1);
    this.setData({
      month: `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}`
    });
    this.loadDetails();
  },

  loadNextMonth() {
    const [y, m] = this.data.month.split('-').map(Number);
    if (!y || !m) return;
    const next = new Date(y, m, 1);
    const now = new Date();
    const maxMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const nextMonth = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`;
    if (nextMonth > maxMonth) {
      wx.showToast({ title: '不能查看未来月份', icon: 'none' });
      return;
    }
    this.setData({ month: nextMonth });
    this.loadDetails();
  },

  async loadDetails() {
    this.setData({ loading: true });
    try {
      const result = await app.request({
        url: `/api/recognition/surveys/details?month=${this.data.month}`,
        retryCount: 0
      });
      const list = Array.isArray(result) ? result : [];
      const records = list.map((item, idx) => ({
        id: `${item.rater_id}-${item.target_id}-${idx}`,
        raterName: item.rater_name || item.rater_id,
        targetName: item.target_name || item.target_id,
        submittedAt: (item.submitted_at || '').replace('T', ' '),
        dims: DIM_KEY_MAP.map(d => ({
          label: d.label,
          value: this._fmtScore(item.scores && item.scores[d.key])
        }))
      }));
      this.setData({ records, total: records.length, loading: false });
    } catch (err) {
      console.error('Load survey details error:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  _fmtScore(v) {
    if (v === null || v === undefined || v === '') return 'N/A';
    return String(v);
  }
});