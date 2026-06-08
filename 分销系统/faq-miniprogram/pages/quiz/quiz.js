const app = getApp();

function normalizeTrueFalseValue(value) {
  if (value === undefined || value === null) return '';

  const text = String(value).trim().toUpperCase();
  const mapping = {
    A: 'TRUE',
    B: 'FALSE',
    对: 'TRUE',
    正确: 'TRUE',
    TRUE: 'TRUE',
    是: 'TRUE',
    错: 'FALSE',
    错误: 'FALSE',
    FALSE: 'FALSE',
    否: 'FALSE'
  };

  return mapping[text] || text;
}

function getTrueFalseDisplay(value) {
  const normalized = normalizeTrueFalseValue(value);
  if (normalized === 'TRUE') return '正确';
  if (normalized === 'FALSE') return '错误';
  return value || '';
}

function hasAnsweredQuestion(question) {
  if (!question) return false;
  return question.user_answer !== undefined && question.user_answer !== null && question.user_answer !== '';
}

function calculateAccuracy(correctCount, totalCount) {
  const safeTotal = Number(totalCount) || 0;
  if (safeTotal <= 0) return 0;
  return Math.round(((Number(correctCount) || 0) / safeTotal) * 100);
}

Page({
  data: {
    questions: [],
    currentIndex: 0,
    currentQuestion: {},
    displayOptions: [],
    difficultyStars: '',
    selectedAnswer: -1,
    selectedOptionsArr: [],
    inputText: '',
    showResult: false,
    isCorrect: false,
    correctAnswer: '',
    correctAnswerDisplay: '',
    currentExplanation: '',
    currentScore: 0,
    totalScore: 0,
    correctCount: 0,
    isFinished: false,
    accuracy: 0,
    startTime: 0,
    quizDate: '',
    answeredCount: 0,
    loading: true,
    isReviewMode: false,
    knowledgeSavedMap: {},
    knowledgeSaving: false,
    knowledgeSaved: false,
    optLabels: ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'],
    questionTypeMap: {
      single_choice: '单选题',
      multiple_choice: '多选题',
      true_false: '判断题',
      fill_blank: '填空题',
      short_answer: '简答题'
    }
  },

  getDifficultyStars(difficulty) {
    return '★'.repeat(difficulty || 1);
  },

  buildDisplayOptions(question, selectedAnswer, selectedOptionsArr, showResult, correctAnswer) {
    const options = question.options || [];
    const isTrueFalse = question.question_type === 'true_false';

    return options.map((optionText, index) => {
      const label = this.data.optLabels[index];
      const isSelected = question.question_type === 'multiple_choice'
        ? !!selectedOptionsArr[index]
        : selectedAnswer === index;

      const isOptionCorrect = isTrueFalse
        ? normalizeTrueFalseValue(optionText) === normalizeTrueFalseValue(correctAnswer)
        : !!correctAnswer && String(correctAnswer).includes(label);

      let optionClass = 'option-item';
      if (showResult) {
        if (isOptionCorrect) {
          optionClass += ' correct';
        } else if (isSelected) {
          optionClass += ' wrong';
        }
      } else if (isSelected) {
        optionClass += ' selected';
      }

      return {
        label,
        text: optionText,
        optionClass,
        showCorrectIcon: showResult && isOptionCorrect,
        showWrongIcon: showResult && isSelected && !isOptionCorrect
      };
    });
  },

  refreshDisplayOptions(extra = {}) {
    const currentQuestion = extra.currentQuestion || this.data.currentQuestion;
    if (!currentQuestion || !currentQuestion.question_type) {
      this.setData({ displayOptions: [] });
      return;
    }

    const selectedAnswer = extra.selectedAnswer !== undefined ? extra.selectedAnswer : this.data.selectedAnswer;
    const selectedOptionsArr = extra.selectedOptionsArr || this.data.selectedOptionsArr;
    const showResult = extra.showResult !== undefined ? extra.showResult : this.data.showResult;
    const correctAnswer = extra.correctAnswer !== undefined ? extra.correctAnswer : this.data.correctAnswer;

    this.setData({
      displayOptions: this.buildDisplayOptions(
        currentQuestion,
        selectedAnswer,
        selectedOptionsArr,
        showResult,
        correctAnswer
      )
    });
  },

  onLoad() {
    if (!app.requireLogin()) return;
    this.loadDailyQuiz();
  },

  async loadDailyQuiz() {
    wx.showLoading({ title: '加载中' });

    try {
      const res = await app.request({
        url: '/api/daily/quiz',
        data: { user_id: app.globalData.userId }
      });

      const data = res.data || res;
      const questions = data.questions || [];

      if (questions.length === 0) {
        wx.showToast({ title: '暂无题目', icon: 'none' });
        this.setData({ loading: false });
        return;
      }

      if (data.is_completed) {
        this.setData({
          questions,
          isFinished: true,
          totalScore: data.score || 0,
          correctCount: data.correct_count || 0,
          accuracy: calculateAccuracy(data.correct_count, questions.length),
          quizDate: data.quiz_date,
          answeredCount: data.answered_count || questions.length,
          loading: false
        });
        return;
      }

      let startIndex = 0;
      for (let i = 0; i < questions.length; i += 1) {
        if (!hasAnsweredQuestion(questions[i])) {
          startIndex = i;
          break;
        }
      }

      let totalScore = 0;
      let correctCount = 0;
      questions.forEach((question) => {
        if (question.score !== undefined) totalScore += question.score;
        if (question.is_correct) correctCount += 1;
      });

      this.setData({
        questions,
        quizDate: data.quiz_date,
        answeredCount: data.answered_count || 0,
        totalScore,
        correctCount,
        loading: false
      });

      this.showQuestion(startIndex);
    } catch (err) {
      console.error('加载周答题失败:', err);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    } finally {
      wx.hideLoading();
    }
  },

  showQuestion(index) {
    const { questions, optLabels } = this.data;
    if (index < 0 || index >= questions.length) return;

    const question = questions[index];
    const alreadyAnswered = hasAnsweredQuestion(question);
    const isTextQuestion = question.question_type === 'fill_blank' || question.question_type === 'short_answer';
    const isMultipleChoice = question.question_type === 'multiple_choice';
    const isTrueFalse = question.question_type === 'true_false';
    const knowledgeSaved = !!this.data.knowledgeSavedMap[question.id];

    let selectedOptionsArr = [];
    if (question.options) {
      selectedOptionsArr = question.options.map(() => false);
    }

    if (isMultipleChoice && alreadyAnswered && question.user_answer) {
      for (let i = 0; i < question.user_answer.length; i += 1) {
        const optionLabel = question.user_answer[i];
        const optionIndex = optLabels.indexOf(optionLabel);
        if (optionIndex !== -1) {
          selectedOptionsArr[optionIndex] = true;
        }
      }
    }

    let selectedAnswer = -1;
    if (!isTextQuestion && !isMultipleChoice && alreadyAnswered) {
      if (isTrueFalse && Array.isArray(question.options)) {
        const normalizedUserAnswer = normalizeTrueFalseValue(question.user_answer);
        selectedAnswer = question.options.findIndex(
          (optionText) => normalizeTrueFalseValue(optionText) === normalizedUserAnswer
        );
      } else {
        selectedAnswer = optLabels.indexOf(question.user_answer);
      }
    }

    const correctAnswer = alreadyAnswered ? question.answer : '';

    this.setData({
      currentIndex: index,
      currentQuestion: question,
      difficultyStars: this.getDifficultyStars(question.difficulty),
      selectedAnswer,
      selectedOptionsArr,
      inputText: isTextQuestion ? (alreadyAnswered ? question.user_answer : '') : '',
      showResult: alreadyAnswered,
      isCorrect: alreadyAnswered ? !!question.is_correct : false,
      correctAnswer,
      correctAnswerDisplay: alreadyAnswered && isTrueFalse ? getTrueFalseDisplay(question.answer) : correctAnswer,
      currentExplanation: alreadyAnswered ? (question.explanation || '') : '',
      currentScore: alreadyAnswered ? (Number(question.score) || 0) : 0,
      startTime: Date.now(),
      isFinished: false,
      knowledgeSaved,
      knowledgeSaving: false
    });

    this.refreshDisplayOptions({
      currentQuestion: question,
      selectedAnswer,
      selectedOptionsArr,
      showResult: alreadyAnswered,
      correctAnswer
    });
  },

  selectOption(e) {
    if (this.data.showResult) return;

    const index = e.currentTarget.dataset.index;
    const { currentQuestion, selectedOptionsArr } = this.data;

    if (currentQuestion.question_type === 'multiple_choice') {
      const nextSelectedOptions = [...selectedOptionsArr];
      nextSelectedOptions[index] = !nextSelectedOptions[index];
      this.setData({ selectedOptionsArr: nextSelectedOptions });
      this.refreshDisplayOptions({ selectedOptionsArr: nextSelectedOptions });
      return;
    }

    this.setData({ selectedAnswer: index });
    this.refreshDisplayOptions({ selectedAnswer: index });
  },

  submitMultipleChoice() {
    if (this.data.showResult) return;

    const { selectedOptionsArr, optLabels } = this.data;
    const selectedIndexes = [];

    for (let i = 0; i < selectedOptionsArr.length; i += 1) {
      if (selectedOptionsArr[i]) {
        selectedIndexes.push(i);
      }
    }

    if (selectedIndexes.length === 0) {
      wx.showToast({ title: '请至少选择一个选项', icon: 'none' });
      return;
    }

    selectedIndexes.sort((a, b) => a - b);
    const answerString = selectedIndexes.map((index) => optLabels[index]).join('');
    this.submitAnswer(answerString);
  },

  submitSelectedOption() {
    if (this.data.showResult) return;

    if (this.data.selectedAnswer < 0) {
      wx.showToast({ title: '请选择一个答案', icon: 'none' });
      return;
    }

    this.submitAnswer();
  },

  onInputAnswer(e) {
    this.setData({ inputText: e.detail.value });
  },

  submitTextAnswer() {
    if (!this.data.inputText || !this.data.inputText.trim()) {
      wx.showToast({ title: '请输入答案', icon: 'none' });
      return;
    }

    this.submitAnswer(this.data.inputText.trim());
  },

  async submitAnswer(textAnswer) {
    const { currentQuestion, selectedAnswer, startTime, totalScore, correctCount, optLabels } = this.data;
    const timeSpent = Math.floor((Date.now() - startTime) / 1000);

    let selectedAnswerValue = '';
    if (typeof textAnswer === 'string' && textAnswer) {
      selectedAnswerValue = textAnswer;
    } else if (
      currentQuestion.question_type === 'true_false' &&
      currentQuestion.options &&
      currentQuestion.options[selectedAnswer] !== undefined
    ) {
      selectedAnswerValue = currentQuestion.options[selectedAnswer];
    } else {
      selectedAnswerValue = optLabels[selectedAnswer] || String(selectedAnswer);
    }

    try {
      const res = await app.request({
        url: '/api/daily/submit',
        method: 'POST',
        data: {
          user_id: app.globalData.userId,
          question_id: currentQuestion.id,
          selected_answer: selectedAnswerValue,
          time_spent: timeSpent
        }
      });

      const result = res.data || res;
      const questions = [...this.data.questions];
      const currentIndex = this.data.currentIndex;
      const nextCorrectCount = result.is_correct ? correctCount + 1 : correctCount;

      questions[currentIndex].user_answer = selectedAnswerValue;
      questions[currentIndex].is_correct = result.is_correct;
      questions[currentIndex].score = result.score;
      questions[currentIndex].answer = result.correct_answer;
      questions[currentIndex].explanation = result.explanation || '';

      this.setData({
        questions,
        showResult: true,
        isCorrect: result.is_correct,
        correctAnswer: result.correct_answer,
        correctAnswerDisplay: currentQuestion.question_type === 'true_false'
          ? getTrueFalseDisplay(result.correct_answer)
          : result.correct_answer,
        currentExplanation: result.explanation || '',
        currentScore: result.score,
        totalScore: totalScore + result.score,
        correctCount: nextCorrectCount,
        answeredCount: this.data.answeredCount + 1,
        accuracy: calculateAccuracy(nextCorrectCount, questions.length)
      });

      this.refreshDisplayOptions({
        showResult: true,
        correctAnswer: result.correct_answer
      });
      app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy']);
      app.refreshCurrentUserProfile().catch((refreshErr) => {
        console.warn('refreshCurrentUserProfile after daily submit failed:', refreshErr);
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
          source: 'daily'
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
    const nextIndex = this.data.currentIndex + 1;
    if (nextIndex < this.data.questions.length) {
      this.showQuestion(nextIndex);
      return;
    }

    this.setData({
      isFinished: true,
      isReviewMode: false,
      accuracy: calculateAccuracy(this.data.correctCount, this.data.questions.length)
    });
  },

  viewDetails() {
    if (!this.data.questions || this.data.questions.length === 0) {
      wx.showToast({ title: '没有找到题目', icon: 'none' });
      return;
    }

    this.setData({
      isReviewMode: true,
      isFinished: false
    });
    this.showQuestion(0);
  },

  goBack() {
    wx.switchTab({
      url: '/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green'
    });
  }
});
