const app = getApp();

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hour = `${date.getHours()}`.padStart(2, '0');
  const minute = `${date.getMinutes()}`.padStart(2, '0');
  return `${month}-${day} ${hour}:${minute}`;
}

function mapSourceText(source) {
  if (source === 'daily') return '每周答题';
  if (source === 'practice' || source === 'bank') return '题库练习';
  return '学习记录';
}

function mapQuestionType(type) {
  if (type === 'single_choice') return '单选题';
  if (type === 'multiple_choice') return '多选题';
  if (type === 'true_false') return '判断题';
  if (type === 'short_answer') return '简答题';
  if (type === 'fill_blank') return '填空题';
  return '题目';
}

function formatDuration(seconds) {
  const totalSeconds = Number(seconds) || 0;
  if (totalSeconds <= 0) return '0秒';

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainSeconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}小时${minutes}分钟`;
  }

  if (minutes > 0) {
    return remainSeconds > 0 ? `${minutes}分钟${remainSeconds}秒` : `${minutes}分钟`;
  }

  return `${remainSeconds}秒`;
}

Page({
  data: {
    loading: true,
    displayName: '学习记录',
    summary: {
      total_answers: 0,
      total_correct: 0,
      accuracy: 0,
      total_score: 0,
      daily_answers: 0,
      practice_answers: 0,
      active_days: 0,
      today_answers: 0
    },
    coreCards: [],
    portraitCards: [],
    recentRecords: []
  },

  onLoad() {
    if (!app.requireLogin()) {
      return;
    }
    this.loadData();
  },

  onShow() {
    if (!app.globalData.userId) {
      return;
    }
    this.loadData();
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',
      intervalMs: 20000,
      refresh: () => this.loadData()
    });
  },

  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onUnload() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onPullDownRefresh() {
    this.loadData().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadData() {
    if (!app.globalData.userId) {
      return;
    }

    this.setData({ loading: true });

    try {
      const res = await app.request({
        url: `/api/study/records?user_id=${app.globalData.userId}`
      });

      const summary = res.summary || {};
      const displayName = summary.real_name || summary.nickname || '学习记录';
      const recentRecords = (res.recent_records || []).map((item) => ({
        ...item,
        createdAtText: formatDateTime(item.created_at),
        sourceText: mapSourceText(item.source),
        questionTypeText: mapQuestionType(item.question_type),
        resultText: item.is_correct ? '回答正确' : '继续加油',
        resultClass: item.is_correct ? 'is-correct' : 'is-wrong',
        scoreText: `${item.score > 0 ? '+' : ''}${item.score || 0}`,
        questionText: item.question_content || item.question_preview || '题目内容同步中'
      }));

      this.setData({
        loading: false,
        displayName,
        summary,
        coreCards: [
          { label: '累计答题', value: summary.total_answers || 0, suffix: '题' },
          { label: '正确率', value: summary.accuracy || 0, suffix: '%' },
          { label: '累计能量值', value: summary.total_score || 0, suffix: '' }
        ],
        portraitCards: [
          { label: '今日学习', value: summary.today_answers || 0, desc: '今天完成的题目数量' },
          { label: '活跃天数', value: summary.active_days || 0, desc: '保持学习节奏的天数' },
          { label: '每周答题', value: summary.daily_answers || 0, desc: '周答题累计作答数' },
          { label: '题库练习', value: formatDuration(summary.practice_duration_seconds), desc: '累计练习时长' },
          { label: '答对题数', value: summary.total_correct || 0, desc: '累计答对的题目数量' }
        ],
        recentRecords
      });
    } catch (err) {
      console.error('Study record load error:', err);
      this.setData({ loading: false });
      wx.showToast({
        title: '学习记录加载失败',
        icon: 'none'
      });
    }
  },

  showRecordDetail(e) {
    const index = Number(e.currentTarget.dataset.index);
    const record = this.data.recentRecords[index];
    if (!record) return;

    wx.showModal({
      title: '完整题目',
      content: record.questionText || '题目内容同步中',
      showCancel: false,
      confirmText: '知道了',
      confirmColor: '#00B050'
    });
  }
});
