const app =
  typeof getApp === 'function'
    ? getApp()
    : {
        globalData: {},
        request() {
          return Promise.reject(new Error('Mini program runtime is not available'));
        },
        refreshCurrentUserProfile() {
          return Promise.resolve({});
        },
        getUserProfile() {
          return null;
        },
        markDataDirty() {},
        startPageAutoRefresh() {},
        stopPageAutoRefresh() {},
        requireLogin() {
          return false;
        }
      };

const { decorateProductForMall } = require('./product-visuals.js');

function stripCompanySuffix(name) {
  if (!name) {
    return '';
  }

  return String(name)
    .replace(/\s*[（(][^（）()]*[)）]\s*$/, '')
    .trim();
}

function getSelectedTier(groups = [], currentTier = '') {
  if (currentTier && groups.some((group) => group.sectionId === currentTier)) {
    return currentTier;
  }
  return groups[0] ? groups[0].sectionId : '';
}

function getTierLabel(groups = [], sectionId = '') {
  const matched = groups.find((group) => group.sectionId === sectionId);
  return matched ? (matched.tierLabel || '') : '';
}

function buildTierTabs(groups = [], selectedTier = '') {
  return groups.map((group) => ({
    sectionId: group.sectionId,
    label: group.tierLabel || '',
    active: selectedTier === group.sectionId
  }));
}

function buildEmptyShippingForm(defaultName = '') {
  return {
    receiverName: defaultName || '',
    receiverPhone: '',
    receiverRegionParts: [],
    receiverRegion: '',
    receiverAddress: '',
    receiverNote: ''
  };
}

function normalizePhone(value) {
  return String(value || '').replace(/\s+/g, '');
}

function validateShippingForm(form) {
  const receiverName = String(form.receiverName || '').trim();
  const receiverPhone = normalizePhone(form.receiverPhone);
  const receiverRegion = String(form.receiverRegion || '').trim();
  const receiverAddress = String(form.receiverAddress || '').trim();
  const receiverNote = String(form.receiverNote || '').trim();
  const phoneDigits = receiverPhone.replace(/\D/g, '');

  if (!receiverName) {
    return { ok: false, message: '请填写收货人姓名' };
  }
  if (phoneDigits.length < 11) {
    return { ok: false, message: '请填写正确的联系电话' };
  }
  if (!receiverRegion) {
    return { ok: false, message: '请选择所在地区' };
  }
  if (!receiverAddress) {
    return { ok: false, message: '请填写详细地址' };
  }

  return {
    ok: true,
    payload: {
      receiver_name: receiverName,
      receiver_phone: receiverPhone,
      receiver_region: receiverRegion,
      receiver_address: receiverAddress,
      receiver_note: receiverNote
    }
  };
}

function normalizeCartItems(items = []) {
  return (items || [])
    .map((item) => ({
      id: String(item.id || '').trim(),
      name: String(item.name || '').trim(),
      cost: Math.max(0, Number(item.cost) || 0),
      quantity: Math.max(1, parseInt(item.quantity, 10) || 1),
      imageUrl: String(item.imageUrl || '').trim(),
      tag: String(item.tag || '').trim()
    }))
    .filter((item) => item.id);
}

function getCartQuantity(cartItems = [], productId = '') {
  const matched = (cartItems || []).find((item) => item.id === productId);
  return matched ? Math.max(1, parseInt(matched.quantity, 10) || 1) : 0;
}

function buildCartItem(product) {
  return {
    id: String(product.id || '').trim(),
    name: product.name || '',
    cost: Math.max(0, Number(product.cost) || 0),
    quantity: 1,
    imageUrl: String(product.displayImageUrl || product.imageUrl || '').trim(),
    tag: product.tag || ''
  };
}

function updateCartItems(cartItems, product, delta) {
  const normalizedItems = normalizeCartItems(cartItems);
  const productId = String(product && product.id ? product.id : '').trim();
  if (!productId || !delta) {
    return normalizedItems;
  }

  const matchedIndex = normalizedItems.findIndex((item) => item.id === productId);
  if (matchedIndex === -1) {
    if (delta < 0) {
      return normalizedItems;
    }
    return normalizedItems.concat(buildCartItem(product));
  }

  const nextItems = normalizedItems.slice();
  const matched = nextItems[matchedIndex];
  const nextQuantity = Math.max(0, (parseInt(matched.quantity, 10) || 1) + delta);

  if (nextQuantity <= 0) {
    nextItems.splice(matchedIndex, 1);
    return nextItems;
  }

  nextItems[matchedIndex] = {
    ...matched,
    name: product.name || matched.name,
    cost: Math.max(0, Number(product.cost) || matched.cost || 0),
    imageUrl: String(product.displayImageUrl || product.imageUrl || matched.imageUrl || '').trim(),
    tag: product.tag || matched.tag,
    quantity: nextQuantity
  };
  return nextItems;
}

function recalculateCartSummary(cartItems = []) {
  const items = normalizeCartItems(cartItems);
  return items.reduce(
    (summary, item) => {
      const quantity = Math.max(1, parseInt(item.quantity, 10) || 1);
      const cost = Math.max(0, Number(item.cost) || 0);
      return {
        items,
        cartKindCount: summary.cartKindCount + 1,
        cartTotalQuantity: summary.cartTotalQuantity + quantity,
        cartTotalCost: summary.cartTotalCost + cost * quantity
      };
    },
    {
      items,
      cartKindCount: 0,
      cartTotalQuantity: 0,
      cartTotalCost: 0
    }
  );
}

function buildBatchRedeemPayload(cartItems, shippingForm, clientBatchId) {
  const items = normalizeCartItems(cartItems);
  return {
    client_batch_id: clientBatchId,
    items: items.map((item) => ({
      product_id: item.id,
      quantity: item.quantity
    })),
    receiver_name: String(shippingForm.receiverName || '').trim(),
    receiver_phone: String(shippingForm.receiverPhone || '').trim(),
    receiver_region: String(shippingForm.receiverRegion || '').trim(),
    receiver_address: String(shippingForm.receiverAddress || '').trim(),
    receiver_note: String(shippingForm.receiverNote || '').trim()
  };
}

function createClientBatchId(cartItems = []) {
  const signature = normalizeCartItems(cartItems)
    .map((item) => `${item.id}:${item.quantity}`)
    .join('|');
  const randomToken = Math.random().toString(36).slice(2, 8);
  return `batch_${Date.now()}_${signature.length}_${randomToken}`;
}

function attachCartState(product, cartItems = []) {
  return {
    ...product,
    cartQuantity: getCartQuantity(cartItems, product.id)
  };
}

function decorateTierGroups(groups, availableEnergy, isGuestMode, cartItems = []) {
  return (groups || []).map((group) => ({
    ...group,
    products: (group.products || []).map((product) =>
      attachCartState(decorateProductForMall(product, availableEnergy, isGuestMode), cartItems)
    )
  }));
}

function pickFeaturedCandidate(group) {
  const products = Array.isArray(group && group.products) ? group.products : [];
  if (!products.length) {
    return null;
  }

  return (
    products.find((product) => String(product.imageUrl || product.image_url || '').trim()) ||
    products[0]
  );
}

function buildFeaturedProducts(featuredProduct, tierGroups, availableEnergy, isGuestMode, cartItems = []) {
  const byId = new Set();
  const selected = [];

  (tierGroups || []).forEach((group) => {
    if (selected.length >= 4) {
      return;
    }
    const candidate = pickFeaturedCandidate(group);
    if (candidate && candidate.id && !byId.has(candidate.id)) {
      byId.add(candidate.id);
      selected.push(candidate);
    }
  });

  if (selected.length < 4 && featuredProduct && featuredProduct.id && !byId.has(featuredProduct.id)) {
    byId.add(featuredProduct.id);
    selected.push(featuredProduct);
  }

  (tierGroups || []).forEach((group) => {
    (group.products || []).forEach((product) => {
      if (selected.length >= 4) {
        return;
      }
      if (product && product.id && !byId.has(product.id)) {
        byId.add(product.id);
        selected.push(product);
      }
    });
  });

  return selected.slice(0, 4).map((product) =>
    attachCartState(
      {
        ...decorateProductForMall(product, availableEnergy, isGuestMode),
        badge: product.badge || '热门推荐'
      },
      cartItems
    )
  );
}

const pageDefinition = {
  data: {
    isGuestMode: false,
    profileName: '',
    totalEnergy: 0,
    availableEnergy: 0,
    redeemedEnergy: 0,
    selectedTier: '',
    selectedTierLabel: '',
    tierTabs: [],
    tierGroups: [],
    featuredProducts: [],
    featuredSwiperIndex: 0,
    catalogFeaturedProduct: null,
    catalogTierGroups: [],
    cartItems: [],
    cartKindCount: 0,
    cartTotalQuantity: 0,
    cartTotalCost: 0,
    pendingBatchId: '',
    showCartSheet: false,
    showTierSheet: false,
    showShippingSheet: false,
    submittingRedemption: false,
    pendingBatchSummary: null,
    shippingForm: buildEmptyShippingForm()
  },

  onLoad() {
    this._isLoadingMallData = false;
    // 分销商大会渠道展区步骤3：白名单用户浏览施能量页时上报计数（失败静默不影响页面）
    this.reportEnergyViewIfWhitelisted();
  },

  reportEnergyViewIfWhitelisted() {
    try {
      const userInfo = (app.globalData && app.globalData.userInfo) || {};
      if (!userInfo.conference_whitelisted) {
        return;
      }
      app.request({
        url: '/api/conference/activity',
        method: 'POST',
        data: { action: 'energy_view' },
        dedupe: true,
        retryCount: 0
      }).catch(() => {
        // 静默失败，不阻塞能量商城页面
      });
    } catch (err) {
      console.warn('report energy_view failed:', err);
    }
  },

  onShow() {
    this.loadMallData();
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',
      intervalMs: 20000,
      refresh: () => this.loadMallData()
    });
  },

  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  onUnload() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  },

  async fetchCatalog() {
    const result = await app.request({
      url: '/api/energy/products',
      dedupe: false,
      debugTag: 'energy-products'
    });

    return {
      featuredProduct: result.featured_product || {},
      tierGroups: result.tier_groups || []
    };
  },

  buildMallState({
    isGuestMode,
    profileName,
    totalEnergy,
    availableEnergy,
    redeemedEnergy,
    featuredProduct,
    tierGroups,
    cartItems
  }) {
    const normalizedTotalEnergy = Math.max(0, Number(totalEnergy) || 0);
    const normalizedRedeemedEnergy = Math.max(0, Number(redeemedEnergy) || 0);
    const normalizedAvailableEnergy = Math.max(0, Number(availableEnergy) || 0);
    const selectedTier = getSelectedTier(tierGroups, this.data.selectedTier);
    const cartSummary = recalculateCartSummary(cartItems || this.data.cartItems || []);
    const nextFeaturedProducts = buildFeaturedProducts(
      featuredProduct,
      tierGroups,
      normalizedAvailableEnergy,
      isGuestMode,
      cartSummary.items
    );
    const currentFeaturedIndex = Math.max(0, Number(this.data.featuredSwiperIndex) || 0);
    const nextFeaturedIndex = nextFeaturedProducts.length
      ? Math.min(currentFeaturedIndex, nextFeaturedProducts.length - 1)
      : 0;

    return {
      isGuestMode,
      profileName,
      totalEnergy: normalizedTotalEnergy,
      availableEnergy: normalizedAvailableEnergy,
      redeemedEnergy: normalizedRedeemedEnergy,
      selectedTier,
      selectedTierLabel: getTierLabel(tierGroups, selectedTier),
      tierTabs: buildTierTabs(tierGroups, selectedTier),
      catalogFeaturedProduct: featuredProduct || null,
      catalogTierGroups: tierGroups || [],
      tierGroups: decorateTierGroups(tierGroups, normalizedAvailableEnergy, isGuestMode, cartSummary.items),
      featuredProducts: nextFeaturedProducts,
      featuredSwiperIndex: nextFeaturedIndex,
      cartItems: cartSummary.items,
      cartKindCount: cartSummary.cartKindCount,
      cartTotalQuantity: cartSummary.cartTotalQuantity,
      cartTotalCost: cartSummary.cartTotalCost,
      pendingBatchId: this.data.pendingBatchId || '',
      showCartSheet: false,
      showTierSheet: false
    };
  },

  setGuestView(catalog) {
    this.setData(
      this.buildMallState({
        isGuestMode: true,
        profileName: '登录后开启兑换',
        totalEnergy: 0,
        availableEnergy: 0,
        redeemedEnergy: 0,
        featuredProduct: catalog.featuredProduct,
        tierGroups: catalog.tierGroups,
        cartItems: this.data.cartItems
      })
    );
  },

  async loadMallData() {
    if (this._isLoadingMallData) {
      return;
    }

    this._isLoadingMallData = true;

    try {
      const catalog = await this.fetchCatalog();

      if (!app.globalData.userId && !app.getUserProfile()) {
        this.setGuestView(catalog);
        return;
      }

      const res = await app.refreshCurrentUserProfile();
      const profileName =
        stripCompanySuffix(res.real_name) ||
        stripCompanySuffix(res.nickname) ||
        '施能量用户';

      this.setData(
        this.buildMallState({
          isGuestMode: false,
          profileName,
          totalEnergy: res.total_score || 0,
          availableEnergy: res.available_energy,
          redeemedEnergy: res.redeemed_energy,
          featuredProduct: catalog.featuredProduct,
          tierGroups: catalog.tierGroups,
          cartItems: this.data.cartItems
        })
      );
    } catch (err) {
      console.error('Energy mall load error:', err);
      wx.showToast({
        title: '商城加载失败',
        icon: 'none'
      });
    } finally {
      this._isLoadingMallData = false;
    }
  },

  getProductById(productId) {
    for (const featured of this.data.featuredProducts || []) {
      if (featured.id === productId) {
        return featured;
      }
    }

    for (const group of this.data.tierGroups || []) {
      const matched = (group.products || []).find((product) => product.id === productId);
      if (matched) {
        return matched;
      }
    }

    const cartMatched = (this.data.cartItems || []).find((item) => item.id === productId);
    return cartMatched || null;
  },

  syncCartState(cartItems, extraData = {}) {
    const summary = recalculateCartSummary(cartItems);
    const catalogFeaturedProduct = this.data.catalogFeaturedProduct || null;
    const catalogTierGroups = this.data.catalogTierGroups || [];

    this.setData({
      cartItems: summary.items,
      cartKindCount: summary.cartKindCount,
      cartTotalQuantity: summary.cartTotalQuantity,
      cartTotalCost: summary.cartTotalCost,
      tierGroups: decorateTierGroups(
        catalogTierGroups,
        this.data.availableEnergy,
        this.data.isGuestMode,
        summary.items
      ),
      featuredProducts: buildFeaturedProducts(
        catalogFeaturedProduct,
        catalogTierGroups,
        this.data.availableEnergy,
        this.data.isGuestMode,
        summary.items
      ),
      ...extraData
    });
  },

  recalculateCartState() {
    this.syncCartState(this.data.cartItems || []);
  },

  handleFeaturedSwiperChange(event) {
    this.setData({
      featuredSwiperIndex: Number(event.detail.current) || 0
    });
  },

  goToLogin() {
    wx.navigateTo({
      url: '/pages/login/login'
    });
  },

  handleProfileTap() {
    if (this.data.isGuestMode) {
      this.goToLogin();
    }
  },

  goToRedeemRecord() {
    if (!app.requireLogin()) return;
    wx.navigateTo({
      url: '/pages/redeem-record/index'
    });
  },

  showRules() {
    wx.showModal({
      title: '兑换规则',
      showCancel: false,
      content: [
        '1. 每周答题可累积施能量。',
        '2. 购物车支持一次结算多个商品，成功后会生成多条兑换记录。',
        '3. 实物商品需要填写完整收货信息，平台审核后安排发放。',
        '4. 已消耗的施能量会从可用余额中扣除。'
      ].join('\n')
    });
  },

  goEarnEnergy() {
    if (!app.globalData.userId) {
      this.goToLogin();
      return;
    }

    wx.navigateTo({
      url: '/pages/quiz/quiz'
    });
  },

  scrollToTier(event) {
    const { target } = event.currentTarget.dataset;
    if (!target) {
      return;
    }

    this.setData({
      selectedTier: target,
      selectedTierLabel: getTierLabel(this.data.tierGroups, target),
      tierTabs: buildTierTabs(this.data.tierGroups, target),
      showTierSheet: false
    });

    wx.pageScrollTo({
      selector: `#${target}`,
      duration: 260
    });
  },

  openTierSheet() {
    this.setData({ showTierSheet: true });
  },

  closeTierSheet() {
    this.setData({ showTierSheet: false });
  },

  openShippingSheet() {
    const defaultName = stripCompanySuffix(this.data.profileName);
    const batchId = this.data.pendingBatchId || createClientBatchId(this.data.cartItems || []);
    this.setData({
      showShippingSheet: true,
      pendingBatchId: batchId,
      pendingBatchSummary: {
        itemCount: this.data.cartTotalQuantity,
        kindCount: this.data.cartKindCount,
        totalCost: this.data.cartTotalCost
      },
      shippingForm: buildEmptyShippingForm(defaultName)
    });
  },

  closeShippingSheet() {
    if (this.data.submittingRedemption) {
      return;
    }

    this.setData({
      showShippingSheet: false,
      pendingBatchSummary: null,
      shippingForm: buildEmptyShippingForm(stripCompanySuffix(this.data.profileName))
    });
  },

  onShippingInput(event) {
    const { field } = event.currentTarget.dataset;
    if (!field) {
      return;
    }

    this.setData({
      [`shippingForm.${field}`]: event.detail.value || ''
    });
  },

  onShippingRegionChange(event) {
    const regionParts = event.detail.value || [];
    this.setData({
      'shippingForm.receiverRegionParts': regionParts,
      'shippingForm.receiverRegion': regionParts.join(' ')
    });
  },

  noop() {},

  changeCartItemQuantity(productId, delta) {
    const product = this.getProductById(productId);
    if (!product) {
      return;
    }

    if (this.data.isGuestMode) {
      this.goToLogin();
      return;
    }

    const nextItems = updateCartItems(this.data.cartItems || [], product, delta);
    this.syncCartState(nextItems, {
      pendingBatchId: '',
      pendingBatchSummary: null
    });
  },

  increaseCartItem(event) {
    const { productId } = event.currentTarget.dataset;
    if (!productId) {
      return;
    }
    this.changeCartItemQuantity(productId, 1);
  },

  decreaseCartItem(event) {
    const { productId } = event.currentTarget.dataset;
    if (!productId) {
      return;
    }
    this.changeCartItemQuantity(productId, -1);
  },

  openCartSheet() {
    if (!(this.data.cartTotalQuantity > 0)) {
      return;
    }
    this.setData({ showCartSheet: true });
  },

  closeCartSheet() {
    if (this.data.submittingRedemption) {
      return;
    }
    this.setData({ showCartSheet: false });
  },

  proceedToShippingFromCart() {
    if (!(this.data.cartTotalQuantity > 0)) {
      wx.showToast({
        title: '请先选择礼品',
        icon: 'none'
      });
      return;
    }

    if (this.data.cartTotalCost > this.data.availableEnergy) {
      wx.showToast({
        title: '当前可用能量不足',
        icon: 'none'
      });
      return;
    }

    this.setData({ showCartSheet: false });
    this.openShippingSheet();
  },

  handleRedeem(event) {
    const { productId } = event.currentTarget.dataset;
    if (!productId) {
      return;
    }
    this.changeCartItemQuantity(productId, 1);
  },

  previewProductImage(event) {
    const imageUrl = String((event.currentTarget.dataset || {}).imageUrl || '').trim();
    if (!imageUrl) {
      return;
    }

    wx.previewImage({
      current: imageUrl,
      urls: [imageUrl]
    });
  },

  async submitRedeem() {
    if (this.data.submittingRedemption) {
      return;
    }

    const cartSummary = recalculateCartSummary(this.data.cartItems || []);
    if (!(cartSummary.cartTotalQuantity > 0)) {
      return;
    }

    const validated = validateShippingForm(this.data.shippingForm || {});
    if (!validated.ok) {
      wx.showToast({
        title: validated.message,
        icon: 'none'
      });
      return;
    }

    this.setData({ submittingRedemption: true });

    try {
      const batchId = this.data.pendingBatchId || createClientBatchId(this.data.cartItems || []);
      if (batchId !== this.data.pendingBatchId) {
        this.setData({ pendingBatchId: batchId });
      }
      const result = await app.request({
        url: '/api/energy/redemptions/batch',
        method: 'POST',
        data: buildBatchRedeemPayload(this.data.cartItems || [], this.data.shippingForm || {}, batchId),
        timeout: 20000,
        retryCount: 0,
        dedupe: false,
        debugTag: 'energy-redemption-batch-create'
      });
      const summary = result.summary || {};

      this.setData(
        Object.assign(
          this.buildMallState({
            isGuestMode: false,
            profileName: this.data.profileName,
            totalEnergy: summary.total_energy ?? this.data.totalEnergy,
            availableEnergy: summary.available_energy,
            redeemedEnergy: summary.redeemed_energy,
            featuredProduct: this.data.catalogFeaturedProduct || (this.data.featuredProducts || [])[0],
            tierGroups: this.data.catalogTierGroups || this.data.tierGroups,
            cartItems: []
          }),
          {
            showCartSheet: false,
            showShippingSheet: false,
            submittingRedemption: false,
            pendingBatchId: '',
            pendingBatchSummary: null,
            shippingForm: buildEmptyShippingForm(stripCompanySuffix(this.data.profileName))
          }
        )
      );
      app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy', 'redeem']);
      app.refreshCurrentUserProfile().catch((refreshErr) => {
        console.warn('refreshCurrentUserProfile after redemption failed:', refreshErr);
      });

      wx.showToast({
        title: '兑换申请已提交',
        icon: 'success'
      });
    } catch (err) {
      console.error('Energy redemption batch create error:', err);
      this.setData({ submittingRedemption: false });
      wx.showToast({
        title: err.detail || err.message || '兑换提交失败',
        icon: 'none'
      });
    }
  },

  onShareAppMessage() {
    return {};
  }
};

if (typeof Page === 'function') {
  Page(pageDefinition);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    stripCompanySuffix,
    buildEmptyShippingForm,
    validateShippingForm,
    normalizeCartItems,
    getCartQuantity,
    buildCartItem,
    updateCartItems,
    recalculateCartSummary,
    buildBatchRedeemPayload,
    createClientBatchId,
    pageDefinition
  };
}
