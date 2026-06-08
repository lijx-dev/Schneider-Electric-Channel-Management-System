const app = getApp();

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hour}:${minute}`;
}

Page({
  data: {
    loading: true,
    items: [],
    searchKeyword: '',
    filteredItems: [],
    expandedMap: {}
  },

  onLoad() {
    if (!app.requireLogin()) return;
    this.loadKnowledgeItems();
  },

  onShow() {
    if (!app.globalData.userId) return;
    this.loadKnowledgeItems();
  },

  async loadKnowledgeItems() {
    this.setData({ loading: true });

    try {
      const res = await app.request({
        url: '/api/knowledge'
      });
      const data = res.data || res;
      const items = (data.items || []).map((item, index) => ({
        ...item,
        indexText: String(index + 1).padStart(2, '0'),
        createdAtText: formatTime(item.created_at),
        expanded: !!this.data.expandedMap[item.id]
      }));

      this.setData({ items, loading: false }, () => this.applyFilter());
    } catch (err) {
      console.error('Knowledge load error:', err);
      this.setData({ loading: false, items: [], filteredItems: [] });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  onSearchInput(e) {
    this.setData({ searchKeyword: e.detail.value || '' }, () => this.applyFilter());
  },

  clearSearch() {
    this.setData({ searchKeyword: '' }, () => this.applyFilter());
  },

  applyFilter() {
    const keyword = String(this.data.searchKeyword || '').trim().toLowerCase();
    const filteredItems = keyword
      ? this.data.items.filter((item) => String(item.explanation || '').toLowerCase().includes(keyword))
      : this.data.items;
    this.setData({ filteredItems });
  },

  toggleKnowledgeItem(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;

    const expandedMap = {
      ...this.data.expandedMap,
      [id]: !this.data.expandedMap[id]
    };
    const items = this.data.items.map((item) => ({
      ...item,
      expanded: !!expandedMap[item.id]
    }));
    this.setData({ expandedMap, items }, () => this.applyFilter());
  },

  deleteKnowledgeItem(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;

    wx.showModal({
      title: '删除知识点',
      content: '确认从知识集中删除这条解析吗？',
      confirmColor: '#00B050',
      success: async (modalRes) => {
        if (!modalRes.confirm) return;
        try {
          await app.request({
            url: `/api/knowledge/${id}`,
            method: 'DELETE'
          });
          this.setData({
            items: this.data.items.filter((item) => item.id !== id)
          }, () => this.applyFilter());
          wx.showToast({ title: '已删除', icon: 'success' });
        } catch (err) {
          console.error('Knowledge delete error:', err);
          wx.showToast({ title: '删除失败', icon: 'none' });
        }
      }
    });
  }
});
