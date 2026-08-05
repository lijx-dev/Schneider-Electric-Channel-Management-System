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
    submitted: false,
    specialistList: [],
    surveyMonth: '',
    // 评分数据 { specialist_id: { efficiency, response, training, communication } }
    scores: {},
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
      const specialistList = result.specialists || [];
      // 预初始化 scores，避免 WXML 中需要用 || {} 兜底导致 }} 解析错误
      const scores = {};
      specialistList.forEach(sp => {
        scores[sp.specialist_id] = { efficiency: 0, response: 0, training: 0, communication: 0 };
      });
      this.setData({
        loading: false,
        submitted: result.submitted,
        specialistList,
        scores,
        surveyMonth: result.survey_month
      });
    } catch (err) {
      console.error('Load survey status error:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
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

  async submitAllScores() {
    if (this.data.submitting) return;

    const { specialistList, scores } = this.data;

    // 校验
    const targets = specialistList.filter(s => !s.scores);
    if (targets.length === 0) {
      wx.showToast({ title: '所有专员已评分', icon: 'none' });
      return;
    }

    // 校验每个专员4个维度都有评分
    for (const sp of targets) {
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
      for (const sp of targets) {
        const spScores = scores[sp.specialist_id] || {};
        await app.request({
          url: '/api/recognition/surveys',
          method: 'POST',
          data: {
            target_id: sp.specialist_id,
            survey_month: this.data.surveyMonth,
            score_efficiency: spScores.efficiency || 0,
            score_response: spScores.response || 0,
            score_training: spScores.training || 0,
            score_communication: spScores.communication || 0
          }
        });
      }

      wx.showToast({ title: '评分提交成功', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 1200);
    } catch (err) {
      console.error('Submit scores error:', err);
      wx.showToast({ title: (err && err.message) || '提交失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  }
});