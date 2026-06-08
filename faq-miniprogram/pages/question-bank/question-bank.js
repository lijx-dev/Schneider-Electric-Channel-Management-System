const app = getApp();

const CATEGORY_META_MAP = {
  'I-Line B': { icon: 'B', color: 'linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)' },
  'I-Line C': { icon: 'C', color: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)' },
  'I-Line H': { icon: 'H', color: 'linear-gradient(135deg, #fae8ff 0%, #e9d5ff 100%)' },
  'I-Line W': { icon: 'W', color: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)' },
  Track: { icon: 'T', color: 'linear-gradient(135deg, #cffafe 0%, #a5f3fc 100%)' },
  'Canalis KB': { icon: 'K', color: 'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)' },
  '母线基础知识': { icon: '基', color: 'linear-gradient(135deg, #ecfccb 0%, #d9f99d 100%)' },
  '规范&认证&测试': { icon: '规', color: 'linear-gradient(135deg, #fee2e2 0%, #fecaca 100%)' },
  '方案配置&选型': { icon: '配', color: 'linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%)' },
  '其他产品知识': { icon: '其', color: 'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)' },
  'SE公司介绍': { icon: 'S', color: 'linear-gradient(135deg, #fce7f3 0%, #fbcfe8 100%)' },
  'OPEX存量业务': { icon: '存', color: 'linear-gradient(135deg, #fef9c3 0%, #fde68a 100%)' },
  数字化: { icon: '数', color: 'linear-gradient(135deg, #ccfbf1 0%, #99f6e4 100%)' },
  数据中心: { icon: '数', color: 'linear-gradient(135deg, #ddd6fe 0%, #c4b5fd 100%)' },
  友商: { icon: '竞', color: 'linear-gradient(135deg, #fee2e2 0%, #fecdd3 100%)' },
  '未分类': { icon: '题', color: 'linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%)' }
};

const CATEGORY_PALETTE = [
  'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)',
  'linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)',
  'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
  'linear-gradient(135deg, #ccfbf1 0%, #99f6e4 100%)',
  'linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)',
  'linear-gradient(135deg, #fee2e2 0%, #fecaca 100%)'
];

function buildCategoryMeta(category, index) {
  const label = category || '未分类';
  const preset = CATEGORY_META_MAP[label];
  if (preset) {
    return { label, ...preset };
  }

  const compact = String(label).replace(/^I-Line\s*/i, '').trim();
  const icon = compact ? compact.charAt(0).toUpperCase() : '题';

  return {
    label,
    icon,
    color: CATEGORY_PALETTE[index % CATEGORY_PALETTE.length]
  };
}

Page({
  data: {
    totalCount: 0,
    categories: [],
    loading: true
  },

  onLoad() {
    if (!app.requireLogin()) return;
    this.loadBank();
  },

  onShow() {
    if (!app.requireLogin()) return;
    this.loadBank();
  },

  async loadBank() {
    try {
      this.setData({ loading: true });

      const res = await app.request({
        url: '/api/questions/bank'
      });

      const categories = (res.categories || []).map((item, index) => ({
        ...item,
        ...buildCategoryMeta(item.category, index)
      }));

      this.setData({
        totalCount: res.total || 0,
        categories,
        loading: false
      });
    } catch (err) {
      console.error('加载题库失败:', err);
      this.setData({ loading: false });
    }
  },

  goToTypeList(e) {
    if (!app.requireLogin()) return;
    const { category, name } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/question-list/question-list?category=${encodeURIComponent(category)}&name=${encodeURIComponent(name)}`
    });
  }
});
