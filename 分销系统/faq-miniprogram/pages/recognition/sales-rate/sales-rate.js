const app = getApp();

// 评分维度（key 与后端字段一一对应，顺序为页面展示顺序）
const DIMENSIONS = [
  {
    key: 'efficiency',
    label: '报备处理效率',
    anchors: {
      5: '报备批复快速专业，主动跟进提醒，提前预警潜在问题和冲突',
      3: '按时批复，一般情况下无延误',
      1: '经常延迟批复，需多次催促，影响项目推进'
    }
  },
  {
    key: 'communication',
    label: '沟通顺畅程度',
    anchors: {
      5: '沟通高效，信息准确，态度积极，能换位思考',
      3: '沟通正常，信息基本准确，态度友好',
      1: '沟通不畅，信息有误，态度消极'
    }
  },
  {
    key: 'response',
    label: '分销商诉求响应',
    noDistributorTip: '如名下无对接分销商，可选择【不适用】',
    anchors: {
      5: '主动预判需求，提前解决问题，分销商多次表扬',
      3: '及时响应，按需支持，基本满足诉求',
      1: '响应迟缓，问题搁置，分销商投诉'
    }
  },
  {
    key: 'training',
    label: '分销商赋能培训支持',
    noDistributorTip: '如名下无对接分销商，可选择【不适用】',
    anchors: {
      5: '主动提供有价值的市场/产品/政策信息，积极推动分销商参与赋能，切实有效地提升了分销商能力',
      3: '按照公司要求为分销商提供赋能',
      1: '没有为分销商提供赋能'
    }
  }
];

const SCORE_VALUES = [0, 1, 2, 3, 4, 5];

Page({
  data: {
    loading: true,
    surveyMonth: '',
    submitted: false,
    ratedCount: 0,
    displayList: [],   // 展示列表，每项 { specialist_id, specialist_name, scores, rated, selected }
    dims: DIMENSIONS,
    scoreValues: SCORE_VALUES,
    // 评分数据 { specialist_id: { efficiency, communication, response, training } }
    // 未选择时值为 ''（空），0 表示「不适用」
    scores: {},
    selectedCount: 0,
    submitting: false
  },

  onLoad() {
    this.loadStatus();
  },

  async loadStatus() {
    try {
      const result = await app.request({
        url: '/api/recognition/surveys/status'
      });
      const specialists = result.specialists || [];
      // 展示列表：标记 rated/selected
      const displayList = specialists.map(sp => ({
        ...sp,
        rated: !!sp.scores,
        selected: false
      }));
      const scores = {};
      displayList.forEach(sp => {
        if (!sp.rated) {
          scores[sp.specialist_id] = { efficiency: '', communication: '', response: '', training: '' };
        }
      });
      this.setData({
        loading: false,
        submitted: result.submitted,
        ratedCount: result.rated_count || 0,
        displayList,
        scores,
        surveyMonth: result.survey_month
      });
    } catch (err) {
      console.error('Load survey status error:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  // 选择 / 取消选择要评分的专员（不限人数）
  onToggleSelect(e) {
    const { specialistId } = e.currentTarget.dataset;
    const { displayList, scores } = this.data;
    const target = displayList.find(sp => sp.specialist_id === specialistId);
    if (!target || target.rated) return;

    if (target.selected) {
      // 取消选择：清空该专员的草稿分
      delete scores[specialistId];
    }

    target.selected = !target.selected;
    const selectedCount = displayList.filter(sp => sp.selected).length;
    this.setData({ displayList: [...displayList], scores: { ...scores }, selectedCount });
  },

  // 从已选中列表中移除（取消选择）
  onRemoveSelect(e) {
    this.onToggleSelect(e);
  },

  onScoreTap(e) {
    const { specialistId, dimension, value } = e.currentTarget.dataset;
    this.setData({
      [`scores.${specialistId}.${dimension}`]: value
    });
  },

  async submitSelected() {
    if (this.data.submitting) return;

    const { displayList, scores, surveyMonth } = this.data;
    const selectedList = displayList.filter(sp => sp.selected);

    // 校验：至少选择一位
    if (selectedList.length === 0) {
      wx.showToast({ title: '请先选择要评分的专员', icon: 'none' });
      return;
    }

    // 校验：每位选中专员的每个评分项都必须选择（1~5 或 不适用）
    for (const sp of selectedList) {
      const spScores = scores[sp.specialist_id] || {};
      const missing = DIMENSIONS
        .filter(d => {
          const v = spScores[d.key];
          return v === '' || v === undefined || v === null;
        })
        .map(d => d.label);
      if (missing.length > 0) {
        wx.showToast({
          title: `${sp.specialist_name} 还有评分项未选择：${missing.join('、')}`,
          icon: 'none'
        });
        return;
      }
    }

    this.setData({ submitting: true });

    try {
      for (const sp of selectedList) {
        const spScores = scores[sp.specialist_id] || {};
        await app.request({
          url: '/api/recognition/surveys',
          method: 'POST',
          data: {
            target_id: sp.specialist_id,
            survey_month: surveyMonth,
            score_efficiency: spScores.efficiency || 0,
            score_communication: spScores.communication || 0,
            score_response: spScores.response || 0,
            score_training: spScores.training || 0
          }
        });
      }

      wx.showToast({ title: '评分提交成功', icon: 'success' });
      // 留在页面续评：刷新状态，刚评的卡片变"已评分"
      setTimeout(() => this.loadStatus(), 800);
    } catch (err) {
      console.error('Submit scores error:', err);
      wx.showToast({ title: (err && err.message) || '提交失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  }
});
