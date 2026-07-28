const app = getApp();

Page({
  data: {
    // 分析模式：'extract'（资料提取）或 'analyze'（智能分析）
    mode: 'extract',

    // 权限状态
    noPermission: false,

    // 分析状态
    loading: false,
    analyzing: false,
    errorMsg: '',

    // 文件
    fileName: '',
    fileSize: '',

    // 分析结果（通用）
    analysis: null,
    riskLevelClass: '',
    riskLevelText: '',

    // 模式一：资料提取
    recommendedDocs: [],
    hasSections: false,
    hasBiddingRequirements: false,

    // 模式二：智能分析
    summary: '',
    favorableClauses: [],
    missingClauses: [],
    competitorTraces: [],
    productMatch: null,
    strategy: [],
    hasBrandDetection: false,
  },

  onLoad(options) {
    // 检查标书功能白名单
    const userInfo = app.globalData.userInfo || wx.getStorageSync('userInfo') || {};
    if (!userInfo.bidding_whitelisted) {
      this.setData({ noPermission: true });
      return;
    }

    // 读取分析模式
    const mode = options.mode || 'extract';
    this.setData({ mode });
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
          hasSections: false,
          hasBiddingRequirements: false,
          favorableClauses: [],
          missingClauses: [],
          competitorTraces: [],
          productMatch: null,
          strategy: [],
          summary: '',
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
   * 策略：先上传到云存储 → 获取临时下载链接 → 传给后端下载分析
   */
  uploadAndAnalyze(filePath) {
    const that = this;
    const token = app.globalData.token || wx.getStorageSync('token') || '';
    const fileName = this.data.fileName;
    const mode = this.data.mode;

    // 步骤1：上传到微信云存储
    const cloudPath = 'bidding/' + Date.now() + '_' + fileName.replace(/[^a-zA-Z0-9._\u4e00-\u9fff]/g, '_');
    wx.cloud.uploadFile({
      cloudPath: cloudPath,
      filePath: filePath,
      success(uploadRes) {
        const fileID = uploadRes.fileID;
        console.log('[bidding] cloud upload success, fileID:', fileID, 'mode:', mode);

        // 步骤2：获取临时下载链接
        wx.cloud.getTempFileURL({
          fileList: [fileID],
          success(tempRes) {
            const downloadUrl = tempRes.fileList[0] && tempRes.fileList[0].tempFileURL;
            if (!downloadUrl) {
              that.setData({ analyzing: false, errorMsg: '获取文件下载链接失败' });
              return;
            }
            console.log('[bidding] got temp download URL');

            // 步骤3：根据模式调用不同后端接口
            const apiPath = mode === 'analyze' ? '/api/bidding/analyze' : '/api/bidding/extract';
            wx.cloud.callContainer({
              config: app.getCallContainerConfig(),
              path: apiPath,
              method: 'POST',
              timeout: 120000,
              header: {
                'X-WX-SERVICE': 'faq-backend',
                'Authorization': 'Bearer ' + token,
              },
              data: {
                download_url: downloadUrl,
                filename: fileName,
              },
              success(res) {
                console.log('[bidding] analyze success, statusCode:', res.statusCode);
                if (res.statusCode === 200 && res.data) {
                  if (res.data.code === 0) {
                    const result = res.data.data || res.data;
                    if (mode === 'analyze') {
                      that.renderDeepAnalysisResult(result);
                    } else {
                      that.renderExtractResult(result);
                    }
                  } else {
                    let errorMsg = '分析失败，请重试';
                    if (typeof res.data.message === 'string') {
                      errorMsg = res.data.message;
                    } else if (typeof res.data.detail === 'string') {
                      errorMsg = res.data.detail;
                    }
                    that.setData({ analyzing: false, errorMsg });
                  }
                } else {
                  let errorMsg = '服务器返回异常，请重试';
                  if (res.data && typeof res.data.detail === 'string') {
                    errorMsg = res.data.detail;
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
          fail(err) {
            console.error('[bidding] getTempFileURL failed', err);
            that.setData({ analyzing: false, errorMsg: '获取文件链接失败，请重试' });
          },
        });
      },
      fail(err) {
        console.error('[bidding] cloud upload failed', err);
        let errorMsg = '上传失败，请重试';
        if (err.errMsg && typeof err.errMsg === 'string') {
          errorMsg = err.errMsg;
        }
        that.setData({ analyzing: false, errorMsg });
      },
    });
  },

  /**
   * 模式一：渲染资料提取结果
   */
  renderExtractResult(data) {
    const analysis = data.analysis || data;
    const riskLevel = analysis.risk_level || '未知';

    let riskLevelClass = 'risk-unknown';
    let riskLevelText = '未知';

    switch (riskLevel) {
      case '高风险':
        riskLevelClass = 'risk-high';
        riskLevelText = '高风险';
        break;
      case '中风险':
        riskLevelClass = 'risk-medium';
        riskLevelText = '中风险';
        break;
      case '低风险':
        riskLevelClass = 'risk-low';
        riskLevelText = '低风险';
        break;
      default:
        riskLevelClass = 'risk-unknown';
        riskLevelText = '未知';
        break;
    }

    const sections = analysis.sections || {};
    const hasSections = Object.keys(sections).length > 0;
    const biddingReqs = analysis.bidding_requirements || {};
    const hasBiddingRequirements = Object.keys(biddingReqs).length > 0;

    this.setData({
      analyzing: false,
      analysis,
      hasSections,
      hasBiddingRequirements,
      riskLevelClass,
      riskLevelText,
      recommendedDocs: data.recommended_documents || [],
      fileName: data.filename || this.data.fileName,
      fileSize: this.formatFileSize(data.file_size || 0),
    });
  },

  /**
   * 模式二：渲染智能分析结果
   */
  renderDeepAnalysisResult(data) {
    const analysis = data.analysis || data;
    const riskLevel = analysis.risk_level || '未知';

    let riskLevelClass = 'risk-unknown';
    let riskLevelText = '未知';

    switch (riskLevel) {
      case '高风险':
        riskLevelClass = 'risk-high';
        riskLevelText = '高风险';
        break;
      case '中风险':
        riskLevelClass = 'risk-medium';
        riskLevelText = '中风险';
        break;
      case '低风险':
        riskLevelClass = 'risk-low';
        riskLevelText = '低风险';
        break;
      default:
        riskLevelClass = 'risk-unknown';
        riskLevelText = '未知';
        break;
    }

    const favorableClauses = analysis.favorable_clauses || [];
    const missingClauses = analysis.missing_clauses || [];
    const competitorTraces = analysis.competitor_traces || [];
    const productMatch = analysis.product_match || {};
    const strategy = analysis.strategy || [];
    const hasBrandDetection = favorableClauses.length > 0 || missingClauses.length > 0;

    this.setData({
      analyzing: false,
      analysis,
      riskLevelClass,
      riskLevelText,
      summary: analysis.summary || '',
      favorableClauses,
      missingClauses,
      competitorTraces,
      productMatch,
      strategy,
      hasBrandDetection,
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

  /**
   * 下载投标文件
   * 通过云托管 API 接口下载（支持传递 Authorization 头部进行白名单校验）
   */
  downloadFile(e) {
    const url = e.currentTarget.dataset.url;
    const filename = e.currentTarget.dataset.filename || '文件.pdf';
    if (!url) {
      wx.showToast({ title: '暂无可下载文件', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '下载中...' });

    const token = app.globalData.token || wx.getStorageSync('token') || '';

    wx.cloud.callContainer({
      config: app.getCallContainerConfig(),
      path: url,
      method: 'GET',
      timeout: 120000,
      header: {
        'X-WX-SERVICE': 'faq-backend',
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/pdf',
      },
      responseType: 'arraybuffer',
      success(res) {
        wx.hideLoading();
        if (res.statusCode === 200 && res.data) {
          const tempFilePath = `${wx.env.USER_DATA_PATH}/${Date.now()}_${filename}`;
          wx.getFileSystemManager().writeFile({
            filePath: tempFilePath,
            data: res.data,
            encoding: 'binary',
            success() {
              wx.openDocument({
                filePath: tempFilePath,
                fileType: 'pdf',
                showMenu: true,
                success() {
                  console.log('[bidding] open document success:', filename);
                },
                fail(err) {
                  console.error('[bidding] open document failed:', err);
                  wx.showToast({ title: '文件打开失败', icon: 'none' });
                },
              });
            },
            fail(err) {
              console.error('[bidding] write file failed:', err);
              wx.showToast({ title: '文件保存失败', icon: 'none' });
            },
          });
        } else {
          let errorMsg = '下载失败，请重试';
          if (res.data && typeof res.data.detail === 'string') {
            errorMsg = res.data.detail;
          }
          wx.showToast({ title: errorMsg, icon: 'none' });
        }
      },
      fail(err) {
        wx.hideLoading();
        console.error('[bidding] download API failed:', err);
        let msg = '下载失败，请重试';
        if (err.errMsg && err.errMsg.indexOf('timeout') > -1) {
          msg = '文件较大，下载超时，请重试';
        }
        wx.showToast({ title: msg, icon: 'none' });
      },
    });
  },

  /**
   * 切换分析模式
   */
  switchMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({
      mode,
      analysis: null,
      recommendedDocs: [],
      favorableClauses: [],
      missingClauses: [],
      competitorTraces: [],
      productMatch: null,
      strategy: [],
      summary: '',
      errorMsg: '',
      fileName: '',
      fileSize: '',
    });
  },
});