const app = getApp();

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
    T: 'TRUE',
    F: 'FALSE',
    Y: 'TRUE',
    N: 'FALSE',
    对: 'TRUE',
    错: 'FALSE',
    正确: 'TRUE',
    错误: 'FALSE',
    是: 'TRUE',
    否: 'FALSE'
  };

  return mapping[text] || text;
}

function isTrueFalseType(questionType) {
  return questionType === 'true_false';
}

function getTrueFalseDisplay(value) {
  const normalized = normalizeTrueFalseValue(value);
  if (normalized === 'TRUE') return '正确';
  if (normalized === 'FALSE') return '错误';
  return value || '';
}

const QUESTION_TYPE_LABELS = {
  single_choice: '单选题',
  multiple_choice: '多选题',
  fill_blank: '填空题',
  short_answer: '问答题',
  true_false: '判断题'
};

Page({
  data: {
    categoryName: '',
    questionCategory: '',
    legacyQuestionType: '',
    questions: [],
    currentIndex: 0,
    currentQuestion: null,
    selectedMap: {},
    blankInputs: [],
    blankCorrects: [],
    fillText: '',
    submitted: false,
    isCorrect: false,
    correctAnswer: '',
    currentExplanation: '',
    correctMap: {},
    answerStatus: [],
    userAnswers: [],
    cardVisible: false,
    knowledgeSavedMap: {},
    knowledgeSaving: false,
    knowledgeSaved: false,
    optLabels: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'],
    questionTypeLabels: QUESTION_TYPE_LABELS,
    loading: true,
    startTime: 0
  },

  onLoad(options) {
    const categoryName = decodeURIComponent(options.name || '题库');
    const questionCategory = decodeURIComponent(options.category || '');
    const legacyQuestionType = options.type || '';

    wx.setNavigationBarTitle({ title: categoryName });
    this.setData({ categoryName, questionCategory, legacyQuestionType });
    this.loadAllQuestions();
  },

  async loadAllQuestions() {
    try {
      const requestData = {
        page: 1,
        page_size: 9999
      };

      if (this.data.questionCategory) {
        requestData.category = this.data.questionCategory;
      } else if (this.data.legacyQuestionType) {
        requestData.question_type = this.data.legacyQuestionType;
      }

      const res = await app.request({
        url: '/api/questions/bank',
        data: requestData
      });

      const questions = res.questions || [];
      const answerStatus = new Array(questions.length);
      const userAnswers = new Array(questions.length);

      this.setData({
        questions,
        answerStatus,
        userAnswers,
        loading: false
      });

      this.showQuestion(0);
    } catch (err) {
      console.error('加载题目失败:', err);
      this.setData({ loading: false });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  countBlanks(content) {
    if (!content) return 1;
    const count = (content.match(/锛堬級/g) || []).length + (content.match(/\(\)/g) || []).length;
    return Math.max(count, 1);
  },

  showQuestion(index) {
    const { questions, userAnswers, answerStatus } = this.data;
    if (index < 0 || index >= questions.length) return;

    const question = questions[index];
    const questionType = question.question_type || '';
    const isShortAnswer = questionType === 'short_answer';
    const knowledgeSaved = !!this.data.knowledgeSavedMap[question.id];
    let submitted = answerStatus[index] !== undefined;

    let selectedMap = {};
    let blankInputs = [];
    let blankCorrects = [];
    let fillText = '';
    let correctMap = {};
    let isCorrect = false;
    let correctAnswer = '';
    let currentExplanation = '';

    if (userAnswers[index]) {
      const saved = userAnswers[index];
      selectedMap = saved.selectedMap || {};
      blankInputs = saved.blankInputs || [];
      blankCorrects = saved.blankCorrects || [];
      fillText = saved.fillText || '';
      correctMap = saved.correctMap || {};
      isCorrect = saved.isCorrect || false;
      correctAnswer = saved.correctAnswer || '';
      currentExplanation = saved.currentExplanation || '';
    }

    if (questionType === 'fill_blank' && blankInputs.length === 0) {
      const blankCount = this.countBlanks(question.content);
      blankInputs = new Array(blankCount).fill('');
      blankCorrects = new Array(blankCount).fill(false);
    }

    if (isShortAnswer) {
      submitted = true;
      isCorrect = true;
      correctAnswer = question.answer || '';
      currentExplanation = question.explanation || '';
    }

    this.setData({
      currentIndex: index,
      currentQuestion: question,
      selectedMap,
      blankInputs,
      blankCorrects,
      fillText,
      submitted,
      isCorrect,
      correctAnswer,
      currentExplanation,
      correctMap,
      startTime: Date.now(),
      knowledgeSaved,
      knowledgeSaving: false
    });
  },

  tapOption(e) {
    if (this.data.submitted) return;

    const idx = e.currentTarget.dataset.idx;
    const currentQuestionType = (this.data.currentQuestion && this.data.currentQuestion.question_type) || '';
    const { selectedMap } = this.data;

    if (currentQuestionType === 'multiple_choice') {
      const newMap = { ...selectedMap };
      if (newMap[idx]) {
        delete newMap[idx];
      } else {
        newMap[idx] = true;
      }
      this.setData({ selectedMap: newMap });
      return;
    }

    this.setData({ selectedMap: { [idx]: true } });
  },

  onBlankInput(e) {
    const idx = e.currentTarget.dataset.idx;
    const val = e.detail.value;
    const blankInputs = [...this.data.blankInputs];
    blankInputs[idx] = val;
    this.setData({ blankInputs });
  },

  onFillInput(e) {
    this.setData({ fillText: e.detail.value });
  },

  async submitAnswer() {
    const {
      currentQuestion,
      selectedMap,
      blankInputs,
      fillText,
      optLabels,
      startTime
    } = this.data;

    if (!currentQuestion) return;
    const questionType = currentQuestion.question_type || '';
    if (questionType === 'short_answer') return;

    const hasOptions = currentQuestion.options && currentQuestion.options.length > 0;

    if (hasOptions) {
      const selected = Object.keys(selectedMap).filter((k) => selectedMap[k]);
      if (selected.length === 0) {
        wx.showToast({ title: '请先选择答案', icon: 'none' });
        return;
      }
    } else if (questionType === 'fill_blank') {
      const hasAny = blankInputs.some((v) => v.trim());
      if (!hasAny) {
        wx.showToast({ title: '请先填写答案', icon: 'none' });
        return;
      }
    } else if (!fillText.trim()) {
      wx.showToast({ title: '请先输入答案', icon: 'none' });
      return;
    }

    let selectedAnswerValue = '';
    let sortedSelectedIndices = [];
    if (hasOptions) {
      sortedSelectedIndices = Object.keys(selectedMap)
        .filter((k) => selectedMap[k])
        .map(Number)
        .sort((a, b) => a - b);

      selectedAnswerValue = isTrueFalseType(questionType)
        ? sortedSelectedIndices.map((i) => currentQuestion.options[i]).join('')
        : sortedSelectedIndices.map((i) => optLabels[i]).join('');
    } else if (questionType === 'fill_blank') {
      selectedAnswerValue = blankInputs.join(';');
    } else {
      selectedAnswerValue = fillText.trim();
    }

    const timeSpent = Math.max(0, Math.floor((Date.now() - (startTime || Date.now())) / 1000));

    try {
      const result = await app.request({
        url: '/api/answer',
        method: 'POST',
        data: {
          user_id: app.globalData.userId,
          question_id: currentQuestion.id,
          selected_answer: selectedAnswerValue,
          time_spent: timeSpent
        }
      });

      const correctAnswer = result.correct_answer || '';
      let correctMap = {};
      let blankCorrects = [];

      if (hasOptions) {
        if (isTrueFalseType(questionType)) {
          const normalizedCorrect = normalizeTrueFalseValue(correctAnswer);

          currentQuestion.options.forEach((optionText, index) => {
            if (normalizeTrueFalseValue(optionText) === normalizedCorrect) {
              correctMap[index] = true;
            }
          });
        } else {
          const normalizedCorrect = normalizeAnswerText(correctAnswer);

          for (let i = 0; i < optLabels.length; i += 1) {
            if (normalizedCorrect.includes(optLabels[i])) {
              correctMap[i] = true;
            }
          }
        }
      } else if (questionType === 'fill_blank') {
        const correctParts = correctAnswer.split(';');
        blankCorrects = blankInputs.map((input, i) => {
          const expected = (correctParts[i] || '').trim();
          return input.trim() === expected;
        });
      }

      let displayAnswer = isTrueFalseType(questionType)
        ? getTrueFalseDisplay(correctAnswer)
        : correctAnswer;

      if (questionType === 'fill_blank' && correctAnswer.includes(';')) {
        const parts = correctAnswer.split(';');
        displayAnswer = parts.map((p, i) => `空${i + 1}: ${p}`).join('  ');
      }

      const { currentIndex, answerStatus, userAnswers } = this.data;
      answerStatus[currentIndex] = result.is_correct ? 'correct' : 'wrong';
      userAnswers[currentIndex] = {
        selectedMap: { ...selectedMap },
        blankInputs: [...blankInputs],
        blankCorrects: [...blankCorrects],
        fillText,
        correctMap,
        isCorrect: !!result.is_correct,
        correctAnswer: displayAnswer,
        currentExplanation: result.explanation || ''
      };

      this.setData({
        submitted: true,
        isCorrect: !!result.is_correct,
        correctAnswer: displayAnswer,
        currentExplanation: result.explanation || '',
        correctMap,
        blankCorrects,
        answerStatus,
        userAnswers
      });
      app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy']);
      app.refreshCurrentUserProfile().catch((refreshErr) => {
        console.warn('refreshCurrentUserProfile after practice submit failed:', refreshErr);
      });
    } catch (err) {
      console.error('提交答案失败:', err);
      wx.showToast({ title: '提交失败', icon: 'none' });
    }
  },

  async saveCurrentExplanation() {
    const { currentQuestion, currentExplanation, knowledgeSaving, knowledgeSavedMap } = this.data;
    if (!currentQuestion || !currentQuestion.id || !currentExplanation) return;
    if (knowledgeSaving || knowledgeSavedMap[currentQuestion.id]) return;

    this.setData({ knowledgeSaving: true });
    try {
      const res = await app.request({
        url: '/api/knowledge',
        method: 'POST',
        data: {
          user_id: app.globalData.userId,
          question_id: currentQuestion.id,
          source: 'bank'
        }
      });
      const data = res.data || res;
      const nextMap = {
        ...knowledgeSavedMap,
        [currentQuestion.id]: true
      };
      this.setData({
        knowledgeSavedMap: nextMap,
        knowledgeSaved: true,
        knowledgeSaving: false
      });
      wx.showToast({
        title: data.already_saved ? '已在知识集' : '已加入',
        icon: 'success'
      });
    } catch (err) {
      console.error('Save knowledge failed:', err);
      this.setData({ knowledgeSaving: false });
      wx.showToast({ title: '加入失败', icon: 'none' });
    }
  },

  nextQuestion() {
    const { currentIndex, questions } = this.data;
    if (currentIndex < questions.length - 1) {
      this.showQuestion(currentIndex + 1);
      return;
    }

    wx.showToast({ title: '已经是最后一题了', icon: 'none' });
  },

  prevQuestion() {
    const { currentIndex } = this.data;
    if (currentIndex > 0) {
      this.showQuestion(currentIndex - 1);
      return;
    }

    wx.showToast({ title: '已经是第一题了', icon: 'none' });
  },

  skipQuestion() {
    this.nextQuestion();
  },

  showAnswerCard() {
    this.setData({ cardVisible: true });
  },

  hideAnswerCard() {
    this.setData({ cardVisible: false });
  },

  jumpToQuestion(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ cardVisible: false });
    this.showQuestion(index);
  },

});
