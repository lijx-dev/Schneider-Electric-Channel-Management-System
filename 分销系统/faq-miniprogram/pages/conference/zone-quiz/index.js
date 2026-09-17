const app = getApp();

const OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

Page({
  data: {
    code: '',
    zoneName: '',
    zone: null,
    questions: [],
    // 答题状态：question_id -> { value: string(单选/填空) | string[](多选), type }
    answers: {},
    submitting: false
  },

  onLoad(options) {
    const code = decodeURIComponent(options.code || '');
    const zoneName = decodeURIComponent(options.name || '');
    this.setData({ code, zoneName });
    wx.setNavigationBarTitle({ title: zoneName || '展区答题' });
    this.loadZone();
  },

  async loadZone() {
    try {
      const data = await app.request({
        url: `/api/conference/zones/${this.data.code}`
      });
      const questions = (data.questions || []).map((q) => ({
        ...q,
        options: (q.options || []).map((text, idx) => ({
          label: OPTION_LETTERS[idx] || String(idx + 1),
          text
        }))
      }));
      this.setData({ zone: data, questions });
    } catch (err) {
      console.warn('load zone quiz failed:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  // ── 单选 / 判断题：点选即记录，不自动提交 ──
  onSelectOption(e) {
    const { qid, label } = e.currentTarget.dataset;
    const answers = { ...this.data.answers };
    answers[qid] = { value: label, type: 'single' };
    this.setData({ answers });
  },

  // ── 多选题：点选切换（支持多选），绝不自动提交 ──
  onToggleMultiOption(e) {
    const { qid, label } = e.currentTarget.dataset;
    const answers = { ...this.data.answers };
    const current = answers[qid] ? answers[qid].value || [] : [];
    const next = current.includes(label)
      ? current.filter((item) => item !== label)
      : [...current, label];
    answers[qid] = { value: next, type: 'multi' };
    this.setData({ answers });
  },

  // ── 填空题：输入 ──
  onFillInput(e) {
    const qid = e.currentTarget.dataset.qid;
    const answers = { ...this.data.answers };
    answers[qid] = { value: e.detail.value, type: 'fill' };
    this.setData({ answers });
  },

  isOptionSelected(qid, label) {
    const entry = this.data.answers[qid];
    if (!entry) return false;
    if (entry.type === 'multi') {
      return (entry.value || []).includes(label);
    }
    return entry.value === label;
  },

  // ── 提交答案（独立按钮，多选也不会点选项即提交） ──
  async onSubmit() {
    if (this.data.submitting) return;

    const questions = this.data.questions;
    const answers = this.data.answers;
    const payload = [];

    for (const q of questions) {
      const entry = answers[q.id];
      let selected = '';
      if (!entry) {
        selected = '';
      } else if (entry.type === 'multi') {
        selected = (entry.value || []).join('');
      } else {
        selected = String(entry.value || '');
      }
      payload.push({ question_id: q.id, selected_answer: selected });
    }

    const unanswered = payload.filter((item) => !item.selected_answer).length;
    if (unanswered > 0) {
      wx.showToast({ title: `还有 ${unanswered} 题未作答`, icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    try {
      const res = await app.request({
        url: `/api/conference/zones/${this.data.code}/submit-quiz`,
        method: 'POST',
        data: { answers: payload },
        timeout: 20000,
        retryCount: 1,
        dedupe: true
      });

      let message = '提交成功';
      if (res.medal_earned) {
        message = `集齐全部印记，获得能量勋章 ${res.medal_code || ''}`;
      } else if (res.mark_earned) {
        message = '恭喜获得本展区能量印记';
      }
      wx.showToast({ title: message, icon: 'none', duration: 2500 });
      setTimeout(() => wx.navigateBack(), 1200);
    } catch (err) {
      console.warn('submit conference quiz failed:', err);
      wx.showToast({ title: '提交失败，请重试', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  }
});
