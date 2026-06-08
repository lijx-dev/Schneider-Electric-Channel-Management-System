const app = getApp();
const {
  mergeModelsAcrossCategories,
  mergeDetailRecordGroups
} = require('./aggregation');

const COMPANIES = [
  {
    id: 'schneider',
    name: '施耐德',
    desc: 'Electrical equipment & automation',
    logoUrl: '/认证图标/施耐德.png',
    logoText: 'Schneider',
    logoClass: 'logo-schneider'
  },
  {
    id: 'abb',
    name: 'ABB威腾',
    desc: 'Power grids & robotics',
    logoUrl: '/认证图标/ABB.png',
    logoText: 'ABB',
    logoClass: 'logo-abb'
  },
  {
    id: 'siemens',
    name: '西门子',
    desc: 'Industry & infrastructure',
    logoUrl: '/认证图标/西门子.png',
    logoText: 'SIEMENS',
    logoClass: 'logo-siemens'
  },
  {
    id: 'weiteng',
    name: '威腾',
    desc: 'Busway & electrical systems',
    logoUrl: '/认证图标/威腾.png',
    logoText: 'W',
    logoClass: 'logo-weiteng'
  },
  {
    id: 'eaton',
    name: '伊顿',
    desc: 'Power management solutions',
    logoUrl: '/认证图标/伊顿.png',
    logoText: 'EATON',
    logoClass: 'logo-eaton'
  }
];

const CERT_TYPE_LOGOS = [
  { keywords: ['CQC', '3C', 'CCC'], url: '/认证图标/CQC.png' },
  { keywords: ['KEMA'], url: '/认证图标/KEMA-KEUR.png' },
  { keywords: ['ASTA', 'DIAMOND'], url: '/认证图标/ASTA.png' },
  { keywords: ['CB'], url: '/认证图标/CB.png' }
];

const CERT_TYPE_DISPLAY_NAMES = {
  CQC: 'CQC（3C）',
  KEMA: 'KEMA-KEUR（DEKRA MARK）',
  ASTA: 'ASTA-DIAMOND',
  CB: 'CB'
};

const LEVELS = {
  COMPANIES: 'companies',
  CERT_TYPES: 'certTypes',
  CATEGORIES: 'categories',
  MODELS: 'models',
  DETAILS: 'details'
};

const DETAIL_FIELD_ORDER = [
  '证书编号',
  '证书类型',
  '企业名称',
  '制造商',
  '产品描述',
  '标准',
  '证书数量',
  '额定参数',
  'In（A）',
  'In(A)',
  '额定工作电压 Ue',
  'Ue',
  '额定冲击耐受电压 Uimp',
  'Uimp',
  'Icw(kA)',
  'Icw(kA）',
  '系统',
  'IP',
  'with PIU？',
  'with PIU?',
  '防火焰蔓延',
  '建筑结构防火',
  '耐火',
  '线路完整性',
  '初始获证时间',
  '说明',
  '备注'
];

const DETAIL_FIELD_ORDER_MAP = DETAIL_FIELD_ORDER.reduce((map, label, index) => {
  map[String(label).toLowerCase().replace(/\s+/g, '')] = index;
  return map;
}, {});

function getCertTypeLogoUrl(name) {
  const text = String(name || '').toUpperCase();
  const matched = CERT_TYPE_LOGOS.find((item) => item.keywords.some((keyword) => text.includes(keyword)));
  return matched ? matched.url : '';
}

function getCertTypeKey(name) {
  const text = String(name || '').toUpperCase();
  if (/(CQC|3C|CCC)/.test(text)) return 'CQC';
  if (/(KEMA|DEKRA)/.test(text)) return 'KEMA';
  if (/(ASTA|DIAMOND)/.test(text)) return 'ASTA';
  if (/\bCB\b|CB证书/.test(text)) return 'CB';
  return '';
}

function getCertTypeDisplayName(name) {
  const key = getCertTypeKey(name);
  return CERT_TYPE_DISPLAY_NAMES[key] || String(name || '');
}

function normalizeCertName(name) {
  return String(name || '')
    .toUpperCase()
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[^A-Z0-9]/g, '');
}

function isRedundantCategory(certTypeName, categoryName) {
  const certKey = getCertTypeKey(certTypeName);
  const categoryKey = getCertTypeKey(categoryName);
  const certText = normalizeCertName(certTypeName);
  const categoryText = normalizeCertName(categoryName);

  if (!categoryText) return false;
  if (certText && certText === categoryText) return true;
  if (certKey && certKey === categoryKey) return true;
  if (certKey === 'KEMA' && /(KEMA|DEKRA)/i.test(String(categoryName || ''))) return true;
  if (certKey === 'CQC' && /(CQC|3C|CCC)/i.test(String(categoryName || ''))) return true;
  if (certKey === 'ASTA' && /(ASTA|DIAMOND)/i.test(String(categoryName || ''))) return true;
  if (certKey === 'CB' && /CB/i.test(String(categoryName || ''))) return true;
  return false;
}

function sortDetailPairs(pairs) {
  return (Array.isArray(pairs) ? pairs : [])
    .filter((item) => item && item.label && item.value !== undefined && item.value !== null && item.value !== '')
    .slice()
    .sort((a, b) => {
      const labelA = String(a.label || '').toLowerCase().replace(/\s+/g, '');
      const labelB = String(b.label || '').toLowerCase().replace(/\s+/g, '');
      const orderA = DETAIL_FIELD_ORDER_MAP[labelA] === undefined ? DETAIL_FIELD_ORDER.length : DETAIL_FIELD_ORDER_MAP[labelA];
      const orderB = DETAIL_FIELD_ORDER_MAP[labelB] === undefined ? DETAIL_FIELD_ORDER.length : DETAIL_FIELD_ORDER_MAP[labelB];
      if (orderA !== orderB) return orderA - orderB;
      return labelA.localeCompare(labelB);
    });
}

Page({
  data: {
    companies: COMPANIES,
    currentLevel: LEVELS.COMPANIES,
    selectedCompany: null,
    selectedCertType: null,
    selectedCategory: null,
    selectedModel: null,
    certTypes: [],
    categories: [],
    models: [],
    detailRecords: [],
    loading: false,
    emptyText: '',
    breadcrumbs: [],
    modelLevelTitle: '',
    detailPathText: ''
  },

  onLoad() {
    if (!app.requireLogin()) return;
    this.updateNavTitle();
  },

  async onCompanyTap(e) {
    const id = e.currentTarget.dataset.id;
    const company = this.data.companies.find((item) => item.id === id);
    if (!company || this.data.loading) return;

    this.setData({
      selectedCompany: company,
      selectedCertType: null,
      selectedCategory: null,
      selectedModel: null,
      certTypes: [],
      categories: [],
      models: [],
      detailRecords: [],
      currentLevel: LEVELS.CERT_TYPES,
      emptyText: ''
    });
    this.updateNavTitle();
    await this.loadCertTypes();
  },

  async onCertTypeTap(e) {
    const id = e.currentTarget.dataset.id;
    const certType = this.data.certTypes.find((item) => item.id === id);
    if (!certType || this.data.loading) return;

    this.setData({
      selectedCertType: certType,
      selectedCategory: null,
      selectedModel: null,
      categories: [],
      models: [],
      detailRecords: [],
      currentLevel: LEVELS.MODELS,
      emptyText: ''
    });
    this.updateNavTitle();
    await this.loadFlattenedModels();
  },

  async onCategoryTap(e) {
    const id = e.currentTarget.dataset.id;
    const category = this.data.categories.find((item) => item.id === id);
    if (!category || this.data.loading) return;

    this.setData({
      selectedCategory: category,
      selectedModel: null,
      models: [],
      detailRecords: [],
      currentLevel: LEVELS.MODELS,
      emptyText: ''
    });
    this.updateNavTitle();
    await this.loadModels();
  },

  async onModelTap(e) {
    const id = e.currentTarget.dataset.id;
    const model = this.data.models.find((item) => item.id === id);
    if (!model || this.data.loading) return;

    this.setData({
      selectedModel: model,
      detailRecords: [],
      currentLevel: LEVELS.DETAILS,
      emptyText: ''
    });
    this.updateNavTitle();
    await this.loadDetails();
  },

  goBack() {
    if (this.data.loading) return;

    const level = this.data.currentLevel;
    if (level === LEVELS.DETAILS) {
      this.setData({
        currentLevel: LEVELS.MODELS,
        selectedModel: null,
        detailRecords: [],
        emptyText: ''
      });
    } else if (level === LEVELS.MODELS) {
      this.setData({
        currentLevel: LEVELS.CERT_TYPES,
        selectedCertType: null,
        selectedCategory: null,
        selectedModel: null,
        categories: [],
        models: [],
        emptyText: ''
      });
    } else if (level === LEVELS.CATEGORIES) {
      this.setData({
        currentLevel: LEVELS.CERT_TYPES,
        selectedCertType: null,
        categories: [],
        emptyText: ''
      });
    } else if (level === LEVELS.CERT_TYPES) {
      this.setData({
        currentLevel: LEVELS.COMPANIES,
        selectedCompany: null,
        certTypes: [],
        emptyText: ''
      });
    }

    this.updateNavTitle();
  },

  async loadCertTypes() {
    const company = this.data.selectedCompany;
    if (!company) return;

    return this.loadList({
      url: '/api/certificates/cert-types',
      data: { company_key: company.id },
      targetKey: 'certTypes',
      emptyText: '该企业的证书资料正在整理中。'
    });
  },

  async loadCategories() {
    const { selectedCompany, selectedCertType } = this.data;
    if (!selectedCompany || !selectedCertType) return;

    return this.loadList({
      url: '/api/certificates/categories',
      data: {
        company_key: selectedCompany.id,
        cert_type: selectedCertType.name
      },
      targetKey: 'categories',
      emptyText: '该证书类别下暂无产品类型数据。'
    });
  },

  async loadModels() {
    const { selectedCompany, selectedCertType, selectedCategory } = this.data;
    if (!selectedCompany || !selectedCertType || !selectedCategory) return;

    return this.loadList({
      url: '/api/certificates/models',
      data: {
        company_key: selectedCompany.id,
        cert_type: selectedCertType.name,
        category_name: selectedCategory.name
      },
      targetKey: 'models',
      emptyText: '该产品类型下暂无型号数据。'
    });
  },

  async loadFlattenedModels() {
    const { selectedCompany, selectedCertType } = this.data;
    if (!selectedCompany || !selectedCertType) return [];

    this.setData({ loading: true, emptyText: '', categories: [], models: [] });

    try {
      const categories = await this.fetchListData({
        url: '/api/certificates/categories',
        data: {
          company_key: selectedCompany.id,
          cert_type: selectedCertType.name
        },
        targetKey: 'categories'
      });

      if (!categories.length) {
        this.setData({
          categories: [],
          models: [],
          loading: false,
          emptyText: '该证书类别下暂无产品系列数据。'
        });
        return [];
      }

      const categoryGroups = await Promise.all(
        categories.map(async (category) => ({
          ...category,
          models: await this.fetchListData({
            url: '/api/certificates/models',
            data: {
              company_key: selectedCompany.id,
              cert_type: selectedCertType.name,
              category_name: category.name
            },
            targetKey: 'models'
          })
        }))
      );

      const mergedModels = mergeModelsAcrossCategories(categoryGroups);
      this.setData({
        categories,
        models: mergedModels,
        loading: false,
        emptyText: mergedModels.length ? '' : '该证书类别下暂无产品系列数据。'
      });
      return mergedModels;
    } catch (err) {
      console.error('加载聚合产品系列失败:', err);
      this.setData({
        categories: [],
        models: [],
        loading: false,
        emptyText: '产品系列加载失败，请稍后重试。'
      });
      return [];
    }
  },

  async autoOpenRedundantCategory(categories) {
    const list = Array.isArray(categories) ? categories : [];
    const { selectedCertType } = this.data;

    if (list.length !== 1 || !selectedCertType || !isRedundantCategory(selectedCertType.name, list[0].name)) {
      return;
    }

    const category = {
      ...list[0],
      displayName: selectedCertType.displayName || getCertTypeDisplayName(selectedCertType.name),
      autoSkipped: true
    };

    this.setData({
      selectedCategory: category,
      models: [],
      detailRecords: [],
      currentLevel: LEVELS.MODELS,
      emptyText: ''
    });
    this.updateNavTitle();
    await this.loadModels();
  },

  async loadDetails() {
    const { selectedCompany, selectedCertType, selectedCategory, selectedModel } = this.data;
    if (!selectedCompany || !selectedCertType || !selectedModel) return;

    this.setData({ loading: true, emptyText: '' });
    try {
      const categoryNames = Array.isArray(selectedModel.categoryNames) && selectedModel.categoryNames.length
        ? selectedModel.categoryNames
        : selectedCategory && selectedCategory.name
          ? [selectedCategory.name]
          : [];

      const detailGroups = await Promise.all(
        categoryNames.map(async (categoryName) => {
          const res = await app.request({
            url: '/api/certificates/details',
            method: 'GET',
            data: {
              company_key: selectedCompany.id,
              cert_type: selectedCertType.name,
              category_name: categoryName,
              model: selectedModel.name
            },
            debugTag: 'cert-details'
          });

          return (Array.isArray(res && res.records) ? res.records : []).map((record) => ({
            ...record,
            detail_pairs: sortDetailPairs(record.detail_pairs)
          }));
        })
      );

      const records = mergeDetailRecordGroups(detailGroups);
      this.setData({
        detailRecords: records,
        loading: false,
        emptyText: records.length ? '' : '该型号暂无可展示的证书详情。'
      });
    } catch (err) {
      console.error('加载证书详情失败:', err);
      this.setData({
        loading: false,
        detailRecords: [],
        emptyText: '证书详情加载失败，请稍后重试。'
      });
    }
  },

  async loadList({ url, data, targetKey, emptyText }) {
    this.setData({ loading: true, emptyText: '' });

    try {
      const res = await app.request({
        url,
        method: 'GET',
        data,
        debugTag: `cert-${targetKey}`
      });
      const rawList = Array.isArray(res) ? res : [];
      const list = targetKey === 'certTypes'
        ? rawList.map((item) => ({
          ...item,
          logoUrl: getCertTypeLogoUrl(item && item.name),
          displayName: getCertTypeDisplayName(item && item.name),
          shortName: String(getCertTypeDisplayName(item && item.name) || '').slice(0, 2) || '证'
        }))
        : targetKey === 'categories'
          ? rawList.map((item) => ({
            ...item,
            displayName: getCertTypeDisplayName(item && item.name)
          }))
        : rawList;
      this.setData({
        [targetKey]: list,
        loading: false,
        emptyText: list.length ? '' : emptyText
      });
      return list;
    } catch (err) {
      console.error('加载证书层级失败:', err);
      this.setData({
        [targetKey]: [],
        loading: false,
        emptyText: '证书资料加载失败，请稍后重试。'
      });
      return [];
    }
  },

  async fetchListData({ url, data, targetKey }) {
    const res = await app.request({
      url,
      method: 'GET',
      data,
      debugTag: `cert-${targetKey}`
    });
    const rawList = Array.isArray(res) ? res : [];
    return this.formatListData(targetKey, rawList);
  },

  formatListData(targetKey, rawList = []) {
    return targetKey === 'certTypes'
      ? rawList.map((item) => ({
        ...item,
        logoUrl: getCertTypeLogoUrl(item && item.name),
        displayName: getCertTypeDisplayName(item && item.name),
        shortName: String(getCertTypeDisplayName(item && item.name) || '').slice(0, 2) || '证书'
      }))
      : targetKey === 'categories'
        ? rawList.map((item) => ({
          ...item,
          displayName: getCertTypeDisplayName(item && item.name)
        }))
        : rawList;
  },

  updateNavTitle() {
    const titleMap = {
      [LEVELS.COMPANIES]: '证书查询',
      [LEVELS.CERT_TYPES]: '证书类别',
      [LEVELS.CATEGORIES]: '产品类型',
      [LEVELS.MODELS]: '产品系列',
      [LEVELS.DETAILS]: '证书详情'
    };
    wx.setNavigationBarTitle({
      title: titleMap[this.data.currentLevel] || '证书查询'
    });

    this.setData({
      breadcrumbs: this.buildBreadcrumbs(),
      modelLevelTitle: this.buildModelLevelTitle(),
      detailPathText: this.buildDetailPathText()
    });
  },

  buildBreadcrumbs() {
    const items = [];
    const { selectedCompany, selectedCertType, selectedModel } = this.data;
    if (selectedCompany) items.push(selectedCompany.name);
    if (selectedCertType) items.push(selectedCertType.displayName || selectedCertType.name);
    if (selectedModel) items.push(selectedModel.name);
    return items;
  },

  buildModelLevelTitle() {
    const { selectedCertType } = this.data;
    return selectedCertType ? (selectedCertType.displayName || selectedCertType.name) : '';
  },

  buildDetailPathText() {
    const items = [];
    const { selectedCompany, selectedCertType } = this.data;
    if (selectedCompany) items.push(selectedCompany.name);
    if (selectedCertType) items.push(selectedCertType.displayName || selectedCertType.name);
    return items.join(' / ');
  }
});

