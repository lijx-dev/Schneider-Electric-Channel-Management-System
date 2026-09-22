const app = getApp();

const OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
const SLOGAN = '欢迎开启您的母线能量探索之旅。完成六大主题展区探索并集齐六枚「能量印记」，即可领取专属「能量勋章」，前往手工工坊完成属于您的定制纪念手串。';

Page({
  data: {
    code: '',
    zoneName: '',
    zone: null,
    questions: [],
    answers: {},
    submitting: false,
    loading: false,
    signedIn: false,
    submitted: false,
    allCorrect: false,
    phone: '',
    name: ''
  },

  onLoad(options) {
    // 小程序码（getwxacodeunlimit）扫码落点页时，展区 code 通过 scene 传入
    // （scene=conference_<code>），而手动进入/开发者工具编译模式用 code 参数。
    // 两者都解析，缺 code 时回退到 scene。
    let code = decodeURIComponent(options.code || '');
    if (!code && options.scene) {
      let scene = '';
      try {
        scene = decodeURIComponent(options.scene);
      } catch (e) {
        scene = String(options.scene || '');
      }
      const raw = String(scene || '').trim();
      if (raw.startsWith('conference_')) {
        code = raw.slice('conference_'.length).trim();
      }
    }
    const zoneName = decodeURIComponent(options.name || '');
    this.setData({ code, zoneName });
    wx.setNavigationBarTitle({ title: zoneName || '大会打卡' });

    // 读取本地签到缓存（同一手机号 4 个打卡点复用）
    const phone = wx.getStorageSync('conferencePhone') || '';
    const name = wx.getStorageSync('conferenceName') || '';
    if (phone) {
      this.setData({ signedIn: true, phone, name });
      this.loadZone();
    }
  },

  onInputName(e) {
    this.setData({ name: e.detail.value });
  },

  onInputPhone(e) {
    this.setData({ phone: e.detail.value });
  },

  // ── 姓名＋手机号自助签到 ──
  async onSignIn() {
    const name = String(this.data.name || '').trim();
    const phone = String(this.data.phone || '').trim();
    if (!name) {
      wx.showToast({ title: '请填写姓名', icon: 'none' });
      return;
    }
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      wx.showToast({ title: '请填写正确的手机号', icon: 'none' });
      return;
    }
    try {
      const res = await app.request({
        url: '/api/conference/join',
        method: 'POST',
        data: { name, phone },
        retryCount: 1,
        dedupe: true
      });
      wx.setStorageSync('conferencePhone', res.phone);
      wx.setStorageSync('conferenceName', res.name);
      this.setData({ signedIn: true, phone: res.phone, name: res.name });
      this.loadZone();
    } catch (err) {
      console.warn('conference join failed:', err);
      wx.showToast({ title: '签到失败，请重试', icon: 'none' });
    }
  },

  async loadZone() {
    this.setData({ loading: true });
    try {
      const data = await app.request({
        url: `/api/conference/zones/${this.data.code}`,
        data: { phone: this.data.phone },
        retryCount: 1
      });
      const questions = (data.questions || []).map((q) => ({
        ...q,
        options: (q.options || []).map((text, idx) => ({
          label: OPTION_LETTERS[idx] || String(idx + 1),
          text,
          selected: false
        }))
      }));
      this.setData({ zone: data, questions });
    } catch (err) {
      console.warn('load zone quiz failed:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 根据 answers 重算每道题每个选项的 selected 标记（避免在 WXML 中做方法调用）
  syncSelectedFlags(questions, answers) {
    return (questions || []).map((q) => {
      const entry = answers[q.id];
      return {
        ...q,
        options: (q.options || []).map((opt) => {
          let selected = false;
          if (entry) {
            if (entry.type === 'multi') {
              selected = (entry.value || []).indexOf(opt.label) > -1;
            } else {
              selected = entry.value === opt.label;
            }
          }
          return { ...opt, selected };
        })
      };
    });
  },

  // ── 选项点击：按题型分流（多选切换/单选记录），绝不自动提交 ──
  onSelectOption(e) {
    const { qid, label, qtype } = e.currentTarget.dataset;
    const answers = { ...this.data.answers };
    if (qtype === 'multiple_choice') {
      const current = answers[qid] ? answers[qid].value || [] : [];
      const next = current.indexOf(label) > -1
        ? current.filter((item) => item !== label)
        : [...current, label];
      answers[qid] = { value: next, type: 'multi' };
    } else {
      answers[qid] = { value: label, type: 'single' };
    }
    this.setData({
      answers,
      questions: this.syncSelectedFlags(this.data.questions, answers)
    });
  },

  // ── 填空题：输入 ──
  onFillInput(e) {
    const qid = e.currentTarget.dataset.qid;
    const answers = { ...this.data.answers };
    answers[qid] = { value: e.detail.value, type: 'fill' };
    this.setData({ answers });
  },

  // ── 提交答案（独立按钮，多选也不会点选项即提交） ──
  async onSubmit() {
    if (this.data.submitting) return;
    if (this.data.allCorrect) {
      wx.showToast({ title: '本展区已全部答对，无需重复提交', icon: 'none' });
      return;
    }

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
        data: {
          phone: this.data.phone,
          name: this.data.name,
          answers: payload
        },
        timeout: 20000,
        retryCount: 1,
        dedupe: true
      });

      if (res.medal_earned) {
        wx.showModal({
          title: '集齐全部打卡点',
          content: `恭喜集齐全部能量印章，获得专属能量勋章：${res.medal_code || ''}`,
          confirmText: '查看勋章',
          cancelText: '继续',
          success: (confirmRes) => {
            if (confirmRes.confirm) {
              this.goToMedal();
            }
          }
        });
      } else if (res.stamp_earned) {
        wx.showToast({ title: '打卡成功，获得本展区能量印章', icon: 'none', duration: 2000 });
      } else if (res.completed) {
        wx.showToast({ title: '本次全部答对，已获得印章', icon: 'none' });
      }

      // 逐题答题结果（对错 + 正确答案），合并到题目上用于展示，答题仍不限次数
      this.applyResults(res.results || []);
    } catch (err) {
      console.warn('submit conference quiz failed:', err);
      wx.showToast({ title: '提交失败，请重试', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  },

  // 把后端返回的逐题对错/正确答案合并到 questions，供 WXML 展示
  applyResults(results) {
    const map = {};
    (results || []).forEach((r) => {
      map[r.question_id] = r;
    });
    const questions = (this.data.questions || []).map((q) => {
      const fb = map[q.id];
      return {
        ...q,
        feedback: fb
          ? { is_correct: !!fb.is_correct, correct_answer: fb.correct_answer },
          : null,
        answered: !!(fb && fb.user_answer)
      };
    });
    const allCorrect = (results || []).length > 0 && (results || []).every((r) => r.is_correct);
    this.setData({
      questions,
      allCorrect,
      submitted: (results || []).length > 0
    });
  },

  goToMedal() {
    wx.navigateTo({
      url: '/pages/conference/my-medal/index'
    });
  }
});
