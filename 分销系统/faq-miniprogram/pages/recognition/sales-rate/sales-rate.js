const app = getApp();

const DIMENSIONS = [
  { key: 'efficiency', label: '响应效率', desc: '处理报备和问题的响应速度' },
  { key: 'response', label: '问题解决', desc: '解决问题能力和专业程度' },
  { key: 'training', label: '培训指导', desc: '提供产品知识培训质量' },
  { key: 'communication', label: '沟通协作', desc: '沟通顺畅度和协作配合' }
];

Page({
  data: {
    loading: true,
    surveyMonth: '',
    submitted: false,
    ratedCount: 0,
    maxSpecialists: 4,
    displayList: [],   // 展示列表，每项 { specialist_id, specialist_name, scores, rated, selected }
    // 评分数据 { specialist_id: { efficiency, response, training, communication } }
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
      // 展示列表：标记 rated/selected；scores 只为未评专员预初始化，避免 WXML 中 || {} 兜底导致 }} 解析错误
      const displayList = specialists.map(sp => ({
        ...sp,
        rated: !!sp.scores,
        selected: false
      }));
      const scores = {};
      displayList.forEach(sp => {
        if (!sp.rated) {
          scores[sp.specialist_id] = { efficiency: 0, response: 0, training: 0, communication: 0 };
        }
      });
      this.setData({
        loading: false,
        submitted: result.submitted,
        ratedCount: result.rated_count || 0,
        maxSpecialists: result.max_specialists || 4,
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

  // 选择 / 取消选择要评分的专员
  onToggleSelect(e) {
    const { specialistId } = e.currentTarget.dataset;
    const { displayList, maxSpecialists, ratedCount, scores } = this.data;
    const target = displayList.find(sp => sp.specialist_id === specialistId);
    if (!target || target.rated) return;

    if (!target.selected) {
      const selectedCount = displayList.filter(sp => sp.selected).length;
      if (selectedCount >= maxSpecialists - ratedCount) {
        wx.showToast({
          title: `本月最多可为 ${maxSpecialists} 位专员评分`,
          icon: 'none'
        });
        return;
      }
    } else {
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

  onScoreChange(e) {
    const { specialistId, dimension } = e.currentTarget.dataset;
    const value = parseInt(e.detail.value) || 0;
    this.setData({
      [`scores.${specialistId}.${dimension}`]: value
    });
  },

  onScoreTap(e) {
    const { specialistId, dimension, value } = e.currentTarget.dataset;
    this.setData({
      [`scores.${specialistId}.${dimension}`]: value
    });
  },

  getScoreLabel(specialistId, dimension, currentValue) {
    const value = currentValue || 0;
    if (value === 0) return 'N/A';
    return value + '分';
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

    // 校验：每位专员至少一个维度 > 0
    for (const sp of selectedList) {
      const spScores = scores[sp.specialist_id] || {};
      const dims = ['efficiency', 'response', 'training', 'communication'];
      const hasScore = dims.some(d => (spScores[d] || 0) > 0);
      if (!hasScore) {
        wx.showToast({
          title: `请为 ${sp.specialist_name} 至少评分一个维度`,
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
            score_response: spScores.response || 0,
            score_training: spScores.training || 0,
            score_communication: spScores.communication || 0
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