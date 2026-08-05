const app = getApp();

const SUBMISSION_TYPES = [
  {
    type: 'nomination',
    name: '微光提名',
    icon: '💡',
    desc: '提名同事的微小正向贡献，随时提名不限次数',
    award: '月度微光之星',
    color: '#fef3c7'
  },
  {
    type: 'order_guardian',
    name: '报备秩序卫士',
    icon: '🛡️',
    desc: '维护报备秩序，规范流程操作',
    award: '季度报备秩序卫士',
    color: '#dbeafe'
  },
  {
    type: 'distributor_pioneer',
    name: '分销商支持先锋',
    icon: '🚀',
    desc: '申报新问题处理、痛点推动案例',
    award: '季度分销商支持先锋',
    color: '#fce7f3'
  },
  {
    type: 'distributor_mentor',
    name: '分销商成长伯乐',
    icon: '🎓',
    desc: '申报合规改善、业绩增长、能力提升案例',
    award: '季度分销商成长伯乐',
    color: '#d1fae5'
  },
  {
    type: 'efficiency_innovator',
    name: '效率提升创新',
    icon: '⚡',
    desc: '申报制度完善、流程优化、工具分享建议',
    award: '季度效率提升创新',
    color: '#ede9fe'
  }
];

Page({
  data: {
    submissionTypes: SUBMISSION_TYPES
  },

  onLoad() {},

  goToSubmitForm(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({
      url: `/pages/recognition/submit-form/submit-form?type=${type}`
    });
  }
});