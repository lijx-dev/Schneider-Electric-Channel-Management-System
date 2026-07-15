const app = getApp();

Page({
  data: {
    // 分析状态
    loading: false,
    analyzing: false,
    errorMsg: '',

    // 文件
    fileName: '',
    fileSize: '',

    // 分析结果
    analysis: null,
    recommendedDocs: [],

    // 风险等级样式
    riskLevelClass: '',
    riskLevelText: '',
    hasSections: false,
  },

  onLoad(options) {
    // 如果从其他页面传来数据，直接展示
    if (options.data) {
      try {
        const data = JSON.parse(decodeURIComponent(options.data));
        this.renderAnalysisResult(data);
      } catch (e) {
        console.error('解析传入数据失败', e);
      }
    }
  },

  /**
   * 选择文件并上传分析
   */
  chooseFile() {
    const that = this;
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf', 'doc', 'docx', 'dot', 'dotx'],
      success(res) {
        const file = res.tempFiles[0];
        that.setData({
          fileName: file.name,
          fileSize: that.formatFileSize(file.size),
          loading: false,
          analyzing: true,
          errorMsg: '',
          analysis: null,
          recommendedDocs: [],
        });
        that.uploadAndAnalyze(file.path);
      },
      fail(err) {
        if (err.errMsg.indexOf('cancel') === -1) {
          that.setData({ errorMsg: '选择文件失败，请重试' });
        }
      },
    });
  },

  /**
   * 上传文件到后端分析
   */
  uploadAndAnalyze(filePath) {
    const that = this;
    const token = app.globalData.token || wx.getStorageSync('token') || '';

    wx.cloud.callContainer({
      config: app.getCallContainerConfig(),
      path: '/api/bidding/upload',
      method: 'POST',
      timeout: 120000,
      header: {
        'X-WX-SERVICE': 'faq-backend',
        'Authorization': 'Bearer ' + token,
      },
      files: [{
        name: 'file',
        filePath: filePath,
      }],
      success(res) {
        console.log('[bidding] analyze success, statusCode:', res.statusCode, 'data:', JSON.stringify(res.data));
        if (res.statusCode === 200 && res.data) {
          if (res.data.code === 0) {
            const result = res.data.data || res.data;
            that.renderAnalysisResult(result);
          } else {
            let errorMsg = '分析失败，请重试';
            if (typeof res.data.message === 'string') {
              errorMsg = res.data.message;
            } else if (typeof res.data.detail === 'string') {
              errorMsg = res.data.detail;
            } else if (res.data.message && typeof res.data.message === 'object') {
              errorMsg = JSON.stringify(res.data.message);
            }
            that.setData({ analyzing: false, errorMsg });
          }
        } else {
          let errorMsg = '服务器返回异常，请重试';
          if (res.data) {
            if (typeof res.data.detail === 'string') {
              errorMsg = res.data.detail;
            } else if (typeof res.data.message === 'string') {
              errorMsg = res.data.message;
            }
          }
          that.setData({ analyzing: false, errorMsg });
        }
      },
      fail(err) {
        console.error('[bidding] analyze failed', JSON.stringify(err));
        let errorMsg = '网络错误，请重试';
        if (err.errMsg && typeof err.errMsg === 'string') {
          if (err.errMsg.indexOf('timeout') > -1) {
            errorMsg = '文件过大，分析超时，请尝试上传较小的文件';
          } else {
            errorMsg = err.errMsg;
          }
        }
        that.setData({ analyzing: false, errorMsg });
      },
    });
  },

  /**
   * 渲染分析结果
   */
  renderAnalysisResult(data) {
    const analysis = data.analysis || data;
    const riskLevel = analysis.risk_level || '未知';

    let riskLevelClass = 'risk-unknown';
    let riskLevelText = '未知';

    switch (riskLevel) {
      case '高风险':
        riskLevelClass = 'risk-high';
        riskLevelText = '⚠️ 高风险';
        break;
      case '中风险':
        riskLevelClass = 'risk-medium';
        riskLevelText = '⚡ 中风险';
        break;
      case '低风险':
        riskLevelClass = 'risk-low';
        riskLevelText = '✅ 低风险';
        break;
      default:
        riskLevelClass = 'risk-unknown';
        riskLevelText = '❓ 未知';
        break;
    }

    const sections = analysis.sections || {};
    const hasSections = Object.keys(sections).length > 0;

    this.setData({
      analyzing: false,
      analysis,
      hasSections: hasSections,
      riskLevelClass,
      riskLevelText,
      recommendedDocs: data.recommended_documents || [],
      fileName: data.filename || this.data.fileName,
      fileSize: this.formatFileSize(data.file_size || 0),
    });
  },

  /**
   * 格式化文件大小
   */
  formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i++;
    }
    return size.toFixed(1) + ' ' + units[i];
  },

  /**
   * 重新上传
   */
  retry() {
    this.chooseFile();
  },

  /**
   * 复制文本到剪贴板
   */
  copyText(e) {
    const text = e.currentTarget.dataset.text || '';
    wx.setClipboardData({
      data: text,
      success() {
        wx.showToast({ title: '已复制', icon: 'success' });
      },
    });
  },
});