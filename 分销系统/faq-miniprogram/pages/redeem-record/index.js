const app =
  typeof getApp === 'function'
    ? getApp()
    : {
        globalData: {},
        requireLogin() {
          return false;
        },
        syncEnergyRedemptions() {
          return Promise.resolve();
        },
        request() {
          return Promise.reject(new Error('Mini program runtime is not available'));
        },
        startPageAutoRefresh() {},
        stopPageAutoRefresh() {}
      };

function formatDateTime(value) {
  if (!value) {
    return '';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hour = `${date.getHours()}`.padStart(2, '0');
  const minute = `${date.getMinutes()}`.padStart(2, '0');
  return `${month}-${day} ${hour}:${minute}`;
}

function mapStatus(status) {
  if (status === 'approved') {
    return '已确认';
  }
  if (status === 'delivered') {
    return '已发货';
  }
  if (status === 'cancelled') {
    return '已取消';
  }
  return '待确认';
}

function normalizeQuantity(value) {
  const quantity = Number(value);
  if (!Number.isFinite(quantity) || quantity < 1) {
    return 1;
  }
  return Math.max(1, Math.floor(quantity));
}

function normalizeAmount(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}

function formatEnergyAmount(value) {
  const amount = normalizeAmount(value);
  return amount === null ? '' : `${amount}能量`;
}

function formatRedeemTitle(record) {
  const name = String(record?.product_name || record?.name || '未知商品').trim();
  const quantity = normalizeQuantity(record?.quantity);
  return `${name} x ${quantity}`;
}

function formatRedeemCostText(record) {
  const quantity = normalizeQuantity(record?.quantity);
  const unitCost = normalizeAmount(record?.unit_cost);
  const totalCost = normalizeAmount(record?.total_cost);
  const legacyCost = normalizeAmount(record?.cost);

  if (quantity <= 1) {
    return formatEnergyAmount(totalCost ?? unitCost ?? legacyCost);
  }

  if (unitCost !== null && totalCost !== null) {
    return `${unitCost}能量/件 · 共${totalCost}能量`;
  }

  if (unitCost !== null) {
    return `${unitCost}能量/件 · 共${unitCost * quantity}能量`;
  }

  if (totalCost !== null) {
    return `共${totalCost}能量`;
  }

  if (legacyCost !== null) {
    return `共${legacyCost}能量`;
  }

  return '';
}

const pageDefinition = {
  data: {
    loading: true,
    records: [],
    summary: {
      total: 0,
      pending: 0,
      spent: 0
    }
  },

  onLoad() {
    if (!app.requireLogin()) {
      return;
    }

    this.loadData();
  },

  onShow() {
    if (!app.globalData.userId) {
      return;
    }

    this.loadData();
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',
      intervalMs: 20000,
      refresh: () => this.loadData()
    });
  },

  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onUnload() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onPullDownRefresh() {
    this.loadData().finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadData() {
    if (!app.globalData.userId) {
      return;
    }

    this.setData({ loading: true });

    try {
      try {
        await app.syncEnergyRedemptions(app.globalData.userId);
      } catch (syncErr) {
        console.warn('Redeem record sync error:', syncErr);
      }

      const result = await app.request({
        url: '/api/energy/redemptions'
      });
      const summary = result.summary || {};
      const records = (result.records || []).map((item) => {
        const quantity = normalizeQuantity(item.quantity);
        const titleText = formatRedeemTitle(item);
        const costText = formatRedeemCostText(item);

        return {
          ...item,
          id: item.id || item.client_record_id,
          name: item.product_name || item.name || '',
          quantity,
          unitCost: normalizeAmount(item.unit_cost),
          totalCost: normalizeAmount(item.total_cost),
          legacyCost: normalizeAmount(item.cost),
          titleText,
          costText,
          createdAt: item.created_at,
          createdAtText: formatDateTime(item.created_at),
          statusText: mapStatus(item.status)
        };
      });

      this.setData({
        loading: false,
        records,
        summary: {
          total: Number(summary.total) || 0,
          pending: Number(summary.pending) || 0,
          spent: Number(summary.spent) || 0
        }
      });
    } catch (err) {
      console.error('Redeem record load error:', err);
      this.setData({
        loading: false,
        records: [],
        summary: {
          total: 0,
          pending: 0,
          spent: 0
        }
      });
      wx.showToast({
        title: '记录加载失败',
        icon: 'none'
      });
    }
  },

  goToMall() {
    wx.switchTab({
      url: '/pages/energy-mall/index'
    });
  }
};

if (typeof Page === 'function') {
  Page(pageDefinition);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    formatDateTime,
    mapStatus,
    normalizeQuantity,
    normalizeAmount,
    formatEnergyAmount,
    formatRedeemTitle,
    formatRedeemCostText,
    pageDefinition
  };
}
