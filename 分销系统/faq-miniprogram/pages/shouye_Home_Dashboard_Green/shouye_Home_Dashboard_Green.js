const app = getApp();
const {
  buildWeeklyQuizSeenKey,
  shouldShowWeeklyQuizBadge
} = require('./weeklyQuizBadge');

function stripCompanySuffix(name) {
  if (!name) {
    return '';
  }

  return String(name)
    .replace(/\s*[（(][^（）()]*[）)]\s*$/, '')
    .trim();
}

function formatDuration(seconds) {
  const safeSeconds = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safeSeconds / 60);
  const restSeconds = safeSeconds % 60;

  if (minutes <= 0) {
    return `${restSeconds}秒`;
  }

  if (minutes < 60) {
    return restSeconds ? `${minutes}分${restSeconds}秒` : `${minutes}分`;
  }

  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return restMinutes ? `${hours}小时${restMinutes}分` : `${hours}小时`;
}

function buildWeeklyMetric(item) {
  const quizCorrectCount = Number(item && item.weekly_correct_count || 0);
  const quizTimeSpent = Number(item && item.weekly_time_spent || 0);

  return {
    weekly_correct_count: quizCorrectCount,
    weekly_time_spent: quizTimeSpent,
    scoreText: `${quizCorrectCount}题`,
    timeText: `累计用时 ${formatDuration(quizTimeSpent)}`
  };
}

Page({
  data: {
    isGuestMode: false,
    userInfo: null,
    rankData: null,
    leaderboard: [],
    quizRes: null,
    todayStudyTime: 0,
    answeredProgress: 0,
    showWeeklyQuizBadge: false,
    lotteryNotice: null
  },

  clampProgress(answeredCount, totalCount) {
    const safeTotal = Number(totalCount) || 0;
    const safeAnswered = Number(answeredCount) || 0;

    if (safeTotal <= 0) {
      return 0;
    }

    return Math.min(100, Math.max(0, Math.floor((safeAnswered / safeTotal) * 100)));
  },

  onLoad() {
    this._isLoadingData = false;
  },

  onShow() {
    this.loadData();
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',
      intervalMs: 15000,
      refresh: () => this.loadData()
    });
  },

  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onUnload() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  setGuestView() {
    this.setData({
      isGuestMode: true,
      userInfo: null,
      rankData: {
        nickname: '分销商',
        company: '登录后查看专属学习数据',
        total_score: 0,
        available_energy: 0,
        weekly_correct_count: 0,
        weekly_time_spent: 0,
        scoreText: '0题',
        timeText: '用时 0秒',
        rank: '-'
      },
      leaderboard: [],
      quizRes: {
        answered_count: 0,
        total_count: 10
      },
      answeredProgress: 0,
      showWeeklyQuizBadge: false,
      lotteryNotice: null
    });
  },

  getWeeklyQuizSeenKey() {
    return buildWeeklyQuizSeenKey(app.globalData.userId);
  },

  getSeenWeeklyQuizDate() {
    try {
      return wx.getStorageSync(this.getWeeklyQuizSeenKey()) || '';
    } catch (err) {
      console.warn('get seen weekly quiz date failed:', err);
      return '';
    }
  },

  markWeeklyQuizSeen(quizDate) {
    const currentQuizDate = String(quizDate || '').trim();
    if (!currentQuizDate) return;

    try {
      wx.setStorageSync(this.getWeeklyQuizSeenKey(), currentQuizDate);
    } catch (err) {
      console.warn('mark weekly quiz seen failed:', err);
    }
  },

  async loadData() {
    if (this._isLoadingData) {
      return;
    }

    if (!app.globalData.userId && !app.getUserProfile()) {
      this.setGuestView();
      return;
    }

    const userId = app.globalData.userId;
    this._isLoadingData = true;

    try {
      try {
        await app.syncEnergyRedemptions(userId);
      } catch (syncErr) {
        console.warn('Home energy sync error:', syncErr);
      }

      const rankProfile = await app.refreshCurrentUserProfile();
      const rankData = await app.resolveAvatarFields(rankProfile, {
        avatarField: 'avatar_url',
        fileIdField: 'avatar_file_id'
      });

      const normalizedRankData = {
        ...rankData,
        avatar: rankData.avatar_url || rankData.avatar || '',
        ...buildWeeklyMetric(rankData),
        nickname: stripCompanySuffix(rankData.nickname) || rankData.nickname,
        real_name: stripCompanySuffix(rankData.real_name) || rankData.real_name
      };

      const userInfo = await app.resolveAvatarFields(rankProfile || app.globalData.userInfo || {}, {
        avatarField: 'avatar_url',
        fileIdField: 'avatar_file_id'
      });

      this.setData({
        isGuestMode: false,
        rankData: normalizedRankData,
        userInfo
      });

      const lbRes = await app.request({
        url: '/api/leaderboard?limit=3'
      });
      const resolvedLeaderboard = await app.resolveAvatarList(lbRes || [], {
        avatarField: 'avatar',
        fileIdField: 'avatar_file_id'
      });

      this.setData({
        leaderboard: resolvedLeaderboard.map((item) => ({
          ...item,
          ...buildWeeklyMetric(item),
          nickname: stripCompanySuffix(item.nickname) || item.nickname
        }))
      });

      const quizRes = await app.request({
        url: `/api/daily/quiz?user_id=${userId}`
      });

      this.setData({
        quizRes,
        answeredProgress: this.clampProgress(quizRes.answered_count, quizRes.total_count),
        showWeeklyQuizBadge: shouldShowWeeklyQuizBadge(quizRes.quiz_date, this.getSeenWeeklyQuizDate())
      });

      this.loadLotteryNotice();
    } catch (err) {
      console.error('Home loadData error:', err);
    } finally {
      this._isLoadingData = false;
    }
  },

  async loadLotteryNotice() {
    try {
      const result = await app.request({
        url: '/api/rewards/latest-notice',
        retryCount: 0
      });
      this.setData({
        lotteryNotice: result && result.has_notice ? result : null
      });
    } catch (err) {
      console.warn('Home lottery notice load failed:', err);
      this.setData({ lotteryNotice: null });
    }
  },

  async goToRewardRecordFromNotice() {
    if (!app.requireLogin()) return;
    const notice = this.data.lotteryNotice;

    if (notice && notice.notice_id) {
      this.setData({ lotteryNotice: null });
      try {
        await app.request({
          url: '/api/rewards/notices/read',
          method: 'POST',
          data: {
            reward_transaction_ids: notice.reward_transaction_ids || [],
            lottery_notice_ids: notice.lottery_notice_ids || []
          },
          retryCount: 0
        });
      } catch (err) {
        console.warn('mark reward notice read failed:', err);
      }
    }

    wx.navigateTo({ url: '/pages/reward-record/index' });
  },

  goToQuestionBank() {
    if (!app.requireLogin()) return;
    wx.navigateTo({ url: '/pages/question-bank/question-bank' });
  },

  goToKnowledge() {
    if (!app.requireLogin()) return;
    wx.navigateTo({ url: '/pages/knowledge/index' });
  },

  goToDaily() {
    if (!app.requireLogin()) return;
    this.markWeeklyQuizSeen(this.data.quizRes && this.data.quizRes.quiz_date);
    this.setData({ showWeeklyQuizBadge: false });
    wx.navigateTo({ url: '/pages/quiz/quiz' });
  },

  goToLeaderboard() {
    if (!app.requireLogin()) return;
    wx.navigateTo({ url: '/pages/leaderboard/leaderboard' });
  },

  goToCertificateQuery() {
    wx.navigateTo({
      url: '/pages/certificate/index'
    });
  },

  onShareAppMessage() {
    return {};
  }
});
