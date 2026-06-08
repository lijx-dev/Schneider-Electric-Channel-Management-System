const app = getApp();

const TYPE_LABELS = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  fill_blank: '填空题',
  short_answer: '问答题',
  true_false: '判断题'
};

function normalizeAnswerText(value) {
  if (value === undefined || value === null) return '';
  return String(value).trim().toUpperCase().replace(/\s+/g, '');
}

function normalizeTrueFalseValue(value) {
  const text = normalizeAnswerText(value);
  const mapping = {
    A: 'TRUE',
    B: 'FALSE',
    TRUE: 'TRUE',
    FALSE: 'FALSE',
    对: 'TRUE',
    错: 'FALSE',
    正确: 'TRUE',
    错误: 'FALSE',
    是: 'TRUE',
    否: 'FALSE'
  };

  return mapping[text] || text;
}

Page({
  data: {
    question: null,
    typeLabel: '',
    showAnswer: false,
    loading: true,
    optLabels: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']
  },

  onLoad(options) {
    const questionId = options.id;
    if (questionId) {
      this.loadDetail(questionId);
    }
  },

  async loadDetail(id) {
    try {
      const question = await app.request({
        url: `/api/questions/detail/${id}`
      });

      this.setData({
        question,
        typeLabel: TYPE_LABELS[question.question_type] || question.question_type,
        loading: false
      });

      wx.setNavigationBarTitle({
        title: TYPE_LABELS[question.question_type] || '题目详情'
      });
    } catch (err) {
      console.error('加载题目详情失败:', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  toggleAnswer() {
    this.setData({ showAnswer: true });
  },

  isCorrectOption(optIdx) {
    const { question, optLabels } = this.data;
    if (!question || !question.answer) return false;

    if (question.question_type === 'true_false' && Array.isArray(question.options)) {
      return normalizeTrueFalseValue(question.options[optIdx]) === normalizeTrueFalseValue(question.answer);
    }

    const letter = optLabels[optIdx];
    return normalizeAnswerText(question.answer).includes(letter);
  }
});
