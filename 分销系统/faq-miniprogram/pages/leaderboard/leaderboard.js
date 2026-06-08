const app = getApp();

function stripCompanySuffix(name) {
  if (!name) return '';
  return String(name).replace(/\s*[\(（][^\)）]*[\)）]\s*$/, '').trim();
}

function removeCompanyFromName(name, company) {
  const cleanName = stripCompanySuffix(name || '');
  const cleanCompany = String(company || '').trim();

  if (!cleanCompany || !cleanName) {
    return cleanName;
  }

  return cleanName
    .replace(cleanCompany, '')
    .replace(/[-—_｜|]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function formatScore(score) {
  return Number(score || 0).toLocaleString('en-US');
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

function toRankValue(rank) {
  const value = Number(rank);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function formatMonthLabel(monthKey) {
  const [year, month] = String(monthKey || '').split('-');
  if (!year || !month) return '本月月榜';
  return `${year}年${Number(month)}月 月榜`;
}

function getCurrentMonthKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

const MONTH_LEADERBOARD_START = { year: 2026, month: 5 };

function parseMonthKey(monthKey) {
  const [yearText, monthText] = String(monthKey || '').split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return { ...MONTH_LEADERBOARD_START };
  }
  return { year, month };
}

function compareMonth(a, b) {
  if (a.year !== b.year) return a.year - b.year;
  return a.month - b.month;
}

function buildMonthPickerRange(selectedMonth) {
  const current = parseMonthKey(getCurrentMonthKey());
  const selected = parseMonthKey(selectedMonth || getCurrentMonthKey());
  const boundedSelected =
    compareMonth(selected, MONTH_LEADERBOARD_START) < 0
      ? { ...MONTH_LEADERBOARD_START }
      : compareMonth(selected, current) > 0
        ? current
        : selected;

  const years = [];
  for (let year = MONTH_LEADERBOARD_START.year; year <= current.year; year += 1) {
    years.push(`${year}年`);
  }
  const months = [];
  const monthStart =
    boundedSelected.year === MONTH_LEADERBOARD_START.year ? MONTH_LEADERBOARD_START.month : 1;
  const monthEnd = boundedSelected.year === current.year ? current.month : 12;
  for (let month = monthStart; month <= monthEnd; month += 1) {
    months.push(`${month}月`);
  }

  return {
    range: [years, months],
    value: [
      Math.max(0, years.indexOf(`${boundedSelected.year}年`)),
      Math.max(0, months.indexOf(`${boundedSelected.month}月`))
    ]
  };
}

function buildMonthPickerForValue(range, value) {
  const yearText = range[0][value[0]] || `${MONTH_LEADERBOARD_START.year}年`;
  const selectedYear = Number(yearText.replace('年', ''));
  const current = parseMonthKey(getCurrentMonthKey());
  const monthStart = selectedYear === MONTH_LEADERBOARD_START.year ? MONTH_LEADERBOARD_START.month : 1;
  const monthEnd = selectedYear === current.year ? current.month : 12;
  const months = [];
  for (let month = monthStart; month <= monthEnd; month += 1) {
    months.push(`${month}月`);
  }
  return {
    range: [range[0], months],
    value: [value[0], Math.min(value[1], Math.max(0, months.length - 1))]
  };
}

function monthKeyFromPicker(range, value) {
  const yearText = range[0][value[0]] || '';
  const monthText = range[1][value[1]] || '';
  const year = yearText.replace('年', '');
  const month = String(parseInt(monthText, 10) || 1).padStart(2, '0');
  return `${year}-${month}`;
}

function normalizeUser(item, mode = 'quiz') {
  if (!item) return null;

  const nickname =
    removeCompanyFromName(item.real_name || item.nickname, item.company) || '学员';
  const rankValue = toRankValue(item.rank);
  const quizCorrectCount = Number(item.monthly_correct_count ?? item.weekly_correct_count ?? 0);
  const quizTimeSpent = Number(item.monthly_time_spent ?? item.weekly_time_spent ?? 0);
  const quizTotalCount = Number(item.monthly_total_count ?? item.weekly_total_count ?? item.total_count ?? 0);
  const rankingExcluded = !!item.ranking_excluded;

  return {
    ...item,
    nickname,
    company: item.company || '',
    province: item.province || '',
    avatar: item.avatar || '/images/default-avatar.svg',
    total_score: Number(item.total_score || 0),
    weekly_correct_count: quizCorrectCount,
    weekly_time_spent: quizTimeSpent,
    weekly_total_count: quizTotalCount,
    monthly_correct_count: quizCorrectCount,
    monthly_time_spent: quizTimeSpent,
    monthly_total_count: quizTotalCount,
    reward_amount: Number(item.reward_amount || 0),
    scoreText: rankingExcluded ? '' : `答对${formatScore(quizCorrectCount)}题`,
    timeText: rankingExcluded ? '' : `累计用时 ${formatDuration(quizTimeSpent)}`,
    rankValue,
    rankText: rankValue ? String(rankValue).padStart(2, '0') : '--',
    companyRankText: rankValue ? String(rankValue) : '--',
    subtitle: item.province || item.company || '同公司成员',
    isSelf: item.user_id === app.globalData.userId,
    ranking_excluded: rankingExcluded
  };
}

function buildRankEncouragement(myRank, list, scopeLabel) {
  if (myRank && myRank.ranking_excluded) {
    return '内部员工不参与排行榜';
  }

  const rankValue = toRankValue(myRank && myRank.rank);
  const currentCorrect = Number((myRank && myRank.weekly_correct_count) || 0);
  const currentTime = Number((myRank && myRank.weekly_time_spent) || 0);

  if (!rankValue) {
    return `完成每周答题，进入${scopeLabel}`;
  }

  if (rankValue === 1) {
    return `继续保持，你目前位居${scopeLabel}第 1`;
  }

  const sorted = (list || [])
    .filter(item => toRankValue(item.rankValue || item.rank))
    .slice()
    .sort((a, b) => {
      const rankDiff = (a.rankValue || a.rank) - (b.rankValue || b.rank);
      if (rankDiff !== 0) return rankDiff;
      const correctDiff = Number(b.weekly_correct_count || 0) - Number(a.weekly_correct_count || 0);
      if (correctDiff !== 0) return correctDiff;
      return Number(a.weekly_time_spent || 0) - Number(b.weekly_time_spent || 0);
    });

  let previousUser = null;
  for (let i = sorted.length - 1; i >= 0; i -= 1) {
    const item = sorted[i];
    const itemRank = toRankValue(item.rankValue || item.rank);
    if (itemRank && itemRank < rankValue) {
      previousUser = item;
      break;
    }
  }

  if (previousUser) {
    const correctGap = Math.max(0, Number(previousUser.weekly_correct_count || 0) - currentCorrect);
    if (correctGap > 0) {
      return `继续加油，距上一名还差 ${correctGap} 题`;
    }

    const timeGap = Math.max(0, currentTime - Number(previousUser.weekly_time_spent || 0));
    if (timeGap > 0) {
      return `答对数相同，用时再快 ${formatDuration(timeGap)} 可追近上一名`;
    }
  }

  return '继续答题，排名还在持续上升';
}

function buildMonthRankTip(myRank) {
  if (myRank && myRank.ranking_excluded) {
    return '内部员工不参与月榜和奖励结算';
  }

  const rankValue = toRankValue(myRank && myRank.rank);
  if (!rankValue) {
    return '本月开始答题后会显示你的月榜排名';
  }

  const rewardAmount = Number(myRank.reward_amount || 0);
  if (rewardAmount > 0) {
    return `预计奖励：${rewardAmount}格施能量`;
  }
  return '本月暂未进入前50';
}

Page({
  data: {
    currentTab: 'total',
    loading: true,
    leaderboard: [],
    topThree: [],
    rankList: [],
    myRank: null,
    totalEncouragement: '',
    totalHasData: false,
    totalLoaded: false,
    monthLeaderboard: [],
    monthRankList: [],
    monthMyRank: null,
    monthHasData: false,
    monthLoaded: false,
    selectedMonth: getCurrentMonthKey(),
    selectedMonthLabel: formatMonthLabel(getCurrentMonthKey()),
    monthPickerRange: buildMonthPickerRange(getCurrentMonthKey()).range,
    monthPickerValue: buildMonthPickerRange(getCurrentMonthKey()).value,
    monthRewardRuleText: '月末按排名发放施能量：前三30格，4-10名20格，11-20名10格，21-50名5格',
    monthStatusText: '进行中',
    monthRankTip: '',
    companyLeaderboard: [],
    companyMyRank: null,
    companyName: '',
    companyMemberCount: 0,
    companyEncouragement: '',
    companyHasData: false,
    companyLoaded: false
  },

  onLoad() {
    if (!app.requireLogin()) return;
  },

  onShow() {
    if (!app.requireLogin()) return;
    this.loadActiveTab({ force: true });
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',
      intervalMs: 20000,
      refresh: () => this.loadActiveTab({ force: true })
    });
  },

  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onUnload() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onPullDownRefresh() {
    this.loadActiveTab({ force: true }).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (!tab || tab === this.data.currentTab) return;

    this.setData({ currentTab: tab }, () => {
      this.loadActiveTab();
    });
  },

  loadActiveTab({ force = false } = {}) {
    if (this.data.currentTab === 'company') {
      return this.loadCompanyLeaderboard(force);
    }
    if (this.data.currentTab === 'month') {
      return this.loadMonthlyLeaderboard(force);
    }
    return this.loadTotalLeaderboard(force);
  },

  async loadTotalLeaderboard(force = false) {
    if (!force && this.data.totalLoaded) return;

    try {
      this.setData({ loading: true });

      const [leaderboardRes, myRankRes] = await Promise.all([
        app.request({
          url: '/api/leaderboard',
          data: { limit: 50, scope: 'total' }
        }),
        app.request({
          url: '/api/user/rank',
          data: { user_id: app.globalData.userId, scope: 'total' }
        })
      ]);

      const [resolvedLeaderboard, resolvedMyRank] = await Promise.all([
        app.resolveAvatarList(leaderboardRes || [], {
          avatarField: 'avatar',
          fileIdField: 'avatar_file_id'
        }),
        app.resolveAvatarFields(myRankRes, {
          avatarField: 'avatar',
          fileIdField: 'avatar_file_id'
        })
      ]);

      const leaderboard = (resolvedLeaderboard || []).map(item => normalizeUser(item, 'total')).filter(Boolean);
      const myRank = normalizeUser(resolvedMyRank, 'total');
      const rankList = leaderboard.slice(3);

      this.setData({
        leaderboard,
        topThree: leaderboard.slice(0, 3),
        rankList,
        myRank,
        totalEncouragement: buildRankEncouragement(myRank, leaderboard, '总累计榜'),
        totalHasData: !!(leaderboard.length || myRank),
        totalLoaded: true,
        loading: false
      });
    } catch (err) {
      console.error('加载总榜失败', err);
      this.setData({ loading: false });
      wx.showToast({
        title: '加载失败',
        icon: 'none'
      });
    }
  },

  onMonthPickerChange(e) {
    const value = e.detail.value;
    const monthKey = monthKeyFromPicker(this.data.monthPickerRange, value);
    const picker = buildMonthPickerRange(monthKey);
    this.setData({
      selectedMonth: monthKey,
      selectedMonthLabel: formatMonthLabel(monthKey),
      monthPickerValue: picker.value,
      monthLoaded: false
    }, () => this.loadMonthlyLeaderboard(true));
  },

  onMonthPickerColumnChange(e) {
    const value = this.data.monthPickerValue.slice();
    value[e.detail.column] = e.detail.value;
    const picker = buildMonthPickerForValue(this.data.monthPickerRange, value);
    this.setData({
      monthPickerRange: picker.range,
      monthPickerValue: picker.value
    });
  },

  async loadMonthlyLeaderboard(force = false) {
    if (!force && this.data.monthLoaded) return;

    try {
      this.setData({ loading: true });

      const result = await app.request({
        url: '/api/monthly-leaderboard',
        data: { month: this.data.selectedMonth, limit: 50 }
      });

      const [resolvedLeaderboard, resolvedMyRank] = await Promise.all([
        app.resolveAvatarList(result.leaderboard || [], {
          avatarField: 'avatar',
          fileIdField: 'avatar_file_id'
        }),
        app.resolveAvatarFields(result.my_rank, {
          avatarField: 'avatar',
          fileIdField: 'avatar_file_id'
        })
      ]);

      const monthLeaderboard = (resolvedLeaderboard || [])
        .map(item => normalizeUser(item, 'month'))
        .filter(Boolean);
      const monthMyRank = normalizeUser(resolvedMyRank, 'month');

      this.setData({
        monthLeaderboard,
        monthRankList: monthLeaderboard.slice(3),
        monthMyRank,
        monthHasData: !!(monthLeaderboard.length || monthMyRank),
        monthLoaded: true,
        monthRewardRuleText: result.reward_rule_text || this.data.monthRewardRuleText,
        monthStatusText: result.status === 'settled' ? '已结算' : '进行中',
        monthRankTip: buildMonthRankTip(monthMyRank),
        loading: false
      });
    } catch (err) {
      console.error('加载月榜失败', err);
      this.setData({ loading: false });
      wx.showToast({
        title: '加载失败',
        icon: 'none'
      });
    }
  },

  async loadCompanyLeaderboard(force = false) {
    if (!force && this.data.companyLoaded) return;

    try {
      this.setData({ loading: true });

      const [leaderboardRes, myRankRes] = await Promise.all([
        app.request({
          url: '/api/leaderboard',
          data: { limit: 100, scope: 'company' }
        }),
        app.request({
          url: '/api/user/rank',
          data: { user_id: app.globalData.userId, scope: 'company' }
        })
      ]);

      const [resolvedLeaderboard, resolvedMyRank] = await Promise.all([
        app.resolveAvatarList(leaderboardRes || [], {
          avatarField: 'avatar',
          fileIdField: 'avatar_file_id'
        }),
        app.resolveAvatarFields(myRankRes, {
          avatarField: 'avatar',
          fileIdField: 'avatar_file_id'
        })
      ]);

      const companyLeaderboard = (resolvedLeaderboard || []).map(item => normalizeUser(item, 'company')).filter(Boolean);
      const companyMyRank = normalizeUser(resolvedMyRank, 'company');
      const companyName = (companyMyRank && companyMyRank.company) ||
        (companyLeaderboard[0] && companyLeaderboard[0].company) ||
        '';

      this.setData({
        companyLeaderboard,
        companyMyRank,
        companyName,
        companyMemberCount: companyLeaderboard.length,
        companyEncouragement: buildRankEncouragement(companyMyRank, companyLeaderboard, '公司榜'),
        companyHasData: companyLeaderboard.length > 0,
        companyLoaded: true,
        loading: false
      });
    } catch (err) {
      console.error('加载公司榜失败', err);
      this.setData({ loading: false });
      wx.showToast({
        title: '加载失败',
        icon: 'none'
      });
    }
  }
});
