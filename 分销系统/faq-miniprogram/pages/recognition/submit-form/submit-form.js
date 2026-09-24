const app = getApp();

Page({
  data: {
    submissionType: '',
    typeName: '',
    isNomination: false,
    loading: true,
    // 预定义项
    predefinedItems: [],
    // 预定义值 {item_key: value}
    predefinedValues: {},
    // 自定义项 [{name, description}]
    customItems: [],
    // 微光提名专用
    nomineeId: '',
    nomineeName: '',
    nomineeList: [],
    nomineeIndex: -1,
    eventDescription: '',
    positiveImpact: '',
    // 底部
    submitting: false
  },

  onLoad(options) {
    const type = options.type || '';
    const typeNames = {
      nomination: '微光提名',
      order_guardian: '报备秩序卫士',
      distributor_pioneer: '分销商支持先锋',
      distributor_mentor: '分销商成长伯乐',
      efficiency_innovator: '效率提升创新'
    };
    this.setData({
      submissionType: type,
      typeName: typeNames[type] || type,
      isNomination: type === 'nomination'
    });
    this.loadFormConfig(type);
  },

  async loadFormConfig(type) {
    try {
      const result = await app.request({
        url: `/api/recognition/submissions/form-config?type=${type}`
      });
      if (result && result.is_nomination) {
        this.setData({ loading: false });
        this.loadNominees();
        return;
      }
      const items = (result && result.items) || [];
      // 初始化预定义值
      const predefinedValues = {};
      items.forEach(item => {
        if (item.item_type === 'checkbox') {
          predefinedValues[item.item_key] = false;
        } else if (item.item_type === 'text_list') {
          predefinedValues[item.item_key] = [];
        } else {
          predefinedValues[item.item_key] = '';
        }
      });
      this.setData({ predefinedItems: items, predefinedValues, loading: false });
    } catch (err) {
      console.error('Load form config error:', err);
      wx.showToast({ title: '加载表单配置失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  // 预定义项操作
  onCheckboxChange(e) {
    const { key } = e.currentTarget.dataset;
    const checked = e.detail.value.length > 0;
    this.setData({
      [`predefinedValues.${key}`]: checked
    });
  },

  onTextListInput(e) {
    const { key, index } = e.currentTarget.dataset;
    const value = e.detail.value;
    const list = [...this.data.predefinedValues[key]];
    list[index] = value;
    this.setData({
      [`predefinedValues.${key}`]: list
    });
  },

  addTextListItem(e) {
    const { key } = e.currentTarget.dataset;
    const list = [...(this.data.predefinedValues[key] || [])];
    list.push('');
    this.setData({
      [`predefinedValues.${key}`]: list
    });
  },

  removeTextListItem(e) {
    const { key, index } = e.currentTarget.dataset;
    const list = [...this.data.predefinedValues[key]];
    list.splice(index, 1);
    this.setData({
      [`predefinedValues.${key}`]: list
    });
  },

  onTextNumberInput(e) {
    const { key, field } = e.currentTarget.dataset;
    const value = e.detail.value;
    const current = this.data.predefinedValues[key] || {};
    if (field === 'text') {
      current.text = value;
    } else {
      current.number = value;
    }
    this.setData({
      [`predefinedValues.${key}`]: current
    });
  },

  // 自定义项操作
  addCustomItem() {
    const customItems = [...this.data.customItems];
    customItems.push({ name: '', description: '' });
    this.setData({ customItems });
  },

  removeCustomItem(e) {
    const index = e.currentTarget.dataset.index;
    const customItems = [...this.data.customItems];
    customItems.splice(index, 1);
    this.setData({ customItems });
  },

  onCustomItemChange(e) {
    const { index, field } = e.currentTarget.dataset;
    const value = e.detail.value;
    const customItems = [...this.data.customItems];
    customItems[index][field] = value;
    this.setData({ customItems });
  },

  // 微光提名专用：加载候选人员
  async loadNominees() {
    try {
      const list = await app.request({ url: '/api/recognition/nominees' });
      const myId = app.globalData.userId || '';
      // 过滤掉自己，避免自提
      const nomineeList = (list || []).filter(u => u.id !== myId);
      this.setData({ nomineeList });
    } catch (err) {
      console.error('Load nominees error:', err);
      wx.showToast({ title: '加载提名候选人失败', icon: 'none' });
    }
  },

  onNomineeChange(e) {
    const index = Number(e.detail.value);
    const item = this.data.nomineeList[index];
    if (!item) return;
    this.setData({
      nomineeIndex: index,
      nomineeId: item.id,
      nomineeName: item.real_name
    });
  },

  onEventInput(e) {
    this.setData({ eventDescription: e.detail.value });
  },

  onImpactInput(e) {
    this.setData({ positiveImpact: e.detail.value });
  },

  // 构建content_json
  buildContentJson() {
    if (this.data.isNomination) {
      return {
        nominee_id: this.data.nomineeId,
        event_description: this.data.eventDescription,
        positive_impact: this.data.positiveImpact
      };
    }
    const predefined = {};
    this.data.predefinedItems.forEach(item => {
      predefined[item.item_key] = this.data.predefinedValues[item.item_key];
    });
    return {
      predefined,
      custom: this.data.customItems.filter(c => c.name || c.description)
    };
  },

  // 提交
  async submitForm(e) {
    const action = e.currentTarget.dataset.action; // 'submit' or 'draft'
    if (this.data.submitting) return;

    const contentJson = this.buildContentJson();

    // 校验
    if (this.data.isNomination) {
      if (!contentJson.nominee_id) {
        wx.showToast({ title: '请选择被提名人', icon: 'none' });
        return;
      }
      if (!contentJson.event_description) {
        wx.showToast({ title: '请输入事件描述', icon: 'none' });
        return;
      }
    }

    this.setData({ submitting: true });

    try {
      const now = new Date();
      const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const quarter = Math.ceil((now.getMonth() + 1) / 3);

      await app.request({
        url: '/api/recognition/submissions',
        method: 'POST',
        data: {
          submission_type: this.data.submissionType,
          content_json: contentJson,
          quarter: this.data.isNomination ? undefined : quarter,
          year: now.getFullYear(),
          submission_month: month
        }
      });

      wx.showToast({
        title: action === 'draft' ? '草稿已保存' : '提交成功',
        icon: 'success'
      });
      setTimeout(() => wx.navigateBack(), 1200);
    } catch (err) {
      console.error('Submit error:', err);
      wx.showToast({ title: (err && err.message) || '提交失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  }
});