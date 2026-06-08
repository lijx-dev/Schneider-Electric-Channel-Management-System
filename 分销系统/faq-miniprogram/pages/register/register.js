const app = getApp();

function normalizeProvinceName(value) {
    if (!value) return '';

    const text = String(value).trim().replace(/\s+/g, '');
    const specialMappings = {
        北京市: '北京',
        上海市: '上海',
        天津市: '天津',
        重庆市: '重庆',
        广西壮族自治区: '广西',
        内蒙古自治区: '内蒙古',
        宁夏回族自治区: '宁夏',
        新疆维吾尔自治区: '新疆',
        西藏自治区: '西藏',
        香港特别行政区: '香港',
        澳门特别行政区: '澳门'
    };

    if (specialMappings[text]) {
        return specialMappings[text];
    }

    if (text.endsWith('省')) {
        return text.slice(0, -1);
    }

    if (text.endsWith('市') && ['北京', '上海', '天津', '重庆'].includes(text.slice(0, -1))) {
        return text.slice(0, -1);
    }

    return text;
}

function prioritizeProvince(list, targetName) {
    if (!Array.isArray(list) || !list.length || !targetName) {
        return Array.isArray(list) ? list.slice() : [];
    }

    const normalizedTarget = normalizeProvinceName(targetName);
    const nextList = list.slice();
    const targetIndex = nextList.findIndex((item) => normalizeProvinceName(item) === normalizedTarget);

    if (targetIndex <= 0) {
        return nextList;
    }

    const [targetItem] = nextList.splice(targetIndex, 1);
    nextList.unshift(targetItem);
    return nextList;
}

Page({
    data: {
        realName: '',
        provinceList: [],
        provinceIndex: 0,
        selectedProvince: '',
        companyList: [],
        companyIndex: 0,
        selectedCompany: '',
        loadingCompanies: false,
        companyPlaceholder: '请先选择省份',
        userInfo: {
            avatar_url: '',
            avatar_file_id: '',
            nickname: ''
        },
        isUploadingAvatar: false
    },

    async onLoad() {
        if (!app.globalData.userId || !app.globalData.token) {
            wx.navigateTo({ url: '/pages/login/login' });
            return;
        }
        wx.hideHomeButton && wx.hideHomeButton();

        const currentUserInfo = wx.getStorageSync('userInfo') || {};
        if (currentUserInfo.profile_verified) {
            wx.switchTab({ url: '/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green' });
            return;
        }
        await this.loadAvatarProfile(currentUserInfo);
        await this.loadProvinces();
    },

    async loadAvatarProfile(currentUserInfo = {}) {
        const resolvedProfile = await app.resolveAvatarFields(currentUserInfo, {
            avatarField: 'avatar_url',
            fileIdField: 'avatar_file_id'
        });
        this.setData({
            userInfo: {
                avatar_url: resolvedProfile.avatar_url || '',
                avatar_file_id: resolvedProfile.avatar_file_id || '',
                nickname: resolvedProfile.nickname || ''
            }
        });
    },

    async loadProvinces() {
        try {
            const res = await app.request({ url: '/api/distributor/provinces' });
            if (res && Array.isArray(res)) {
                this.setData({
                    provinceList: prioritizeProvince(res, '施耐德电气')
                });
            }
        } catch (err) { console.error('获取省份列表失败:', err); }
    },

    async loadCompanies(province) {
        if (!province) return;

        this.setData({
            loadingCompanies: true,
            companyPlaceholder: '加载公司列表中...'
        });

        try {
            const res = await app.request({ url: '/api/distributor/companies', data: { province } });
            if (res && Array.isArray(res)) {
                this.setData({
                    companyList: res,
                    loadingCompanies: false,
                    companyPlaceholder: res.length ? '请选择公司' : '当前省份暂无公司'
                });
            }
        } catch (err) {
            console.error('获取公司列表失败:', err);
            this.setData({
                loadingCompanies: false,
                companyPlaceholder: '加载失败，请重试'
            });
        }
    },

    onRealNameInput(e) { this.setData({ realName: e.detail.value }); },

    async onProvinceChange(e) {
        const province = normalizeProvinceName(this.data.provinceList[e.detail.value]);
        this.setData({
            provinceIndex: e.detail.value,
            selectedProvince: province,
            companyList: [],
            companyIndex: 0,
            selectedCompany: '',
            companyPlaceholder: '加载公司列表中...'
        });
        await this.loadCompanies(province);
    },

    onCompanyChange(e) {
        this.setData({
            companyIndex: e.detail.value,
            selectedCompany: this.data.companyList[e.detail.value]
        });
    },

    async onChooseWechatAvatar(event) {
        if (this.data.isUploadingAvatar) {
            return;
        }

        const avatarUrl = String((event && event.detail && event.detail.avatarUrl) || '').trim();
        if (!avatarUrl) {
            return;
        }

        await this.uploadSelectedAvatar(avatarUrl);
    },

    async uploadSelectedAvatar(avatarUrl) {
        const matched = String(avatarUrl).match(/\.([a-zA-Z0-9]+)(?:$|\?)/);
        const extension = matched ? matched[1].toLowerCase() : 'png';
        const safeExtension = ['jpg', 'jpeg', 'png', 'webp'].includes(extension) ? extension : 'png';

        this.setData({ isUploadingAvatar: true });
        wx.showLoading({ title: '上传中...' });

        try {
            const cachedUserInfo = app.globalData.userInfo || wx.getStorageSync('userInfo') || {};
            const result = await app.uploadAvatar({
                filePath: avatarUrl,
                userId: app.globalData.userId,
                phone: cachedUserInfo.phone || '',
                displayName: this.data.realName || cachedUserInfo.real_name || cachedUserInfo.nickname || '',
                extension: safeExtension
            });

            const nextUserInfo = app.setUserInfo({
                ...cachedUserInfo,
                avatar_url: result.avatar_url || '',
                avatar_file_id: result.avatar_file_id || ''
            });

            const resolvedProfile = await app.resolveAvatarFields(nextUserInfo, {
                avatarField: 'avatar_url',
                fileIdField: 'avatar_file_id'
            });

            this.setData({
                userInfo: {
                    avatar_url: resolvedProfile.avatar_url || '',
                    avatar_file_id: resolvedProfile.avatar_file_id || '',
                    nickname: resolvedProfile.nickname || ''
                }
            });

            wx.hideLoading();
            wx.showToast({ title: '头像已更新', icon: 'success' });
        } catch (err) {
            wx.hideLoading();
            console.error('上传头像失败:', err);
            wx.showToast({ title: '网络异常，上传失败', icon: 'none' });
        } finally {
            this.setData({ isUploadingAvatar: false });
        }
    },

    async submitAuth() {
        const { realName, selectedProvince, selectedCompany } = this.data;
        if (!realName || !selectedProvince || !selectedCompany) {
            wx.showToast({ title: '请填写完整信息', icon: 'none' });
            return;
        }

        wx.showLoading({ title: '提交中...' });
        try {
            const userInfo = wx.getStorageSync('userInfo') || {};
            const nickname = userInfo.nickname || `用户${app.globalData.userId.substring(0, 6)}`;

            let avatarToSave = userInfo.avatar_file_id || userInfo.avatar_url || '';
            if (avatarToSave && (avatarToSave.includes('__usr__') || avatarToSave.includes('tmp/') || avatarToSave.includes('wxfile://'))) {
                avatarToSave = '';
            }

            await app.request({
                url: '/api/user/profile',
                method: 'POST',
                data: {
                    user_id: app.globalData.userId,
                    nickname: nickname,
                    avatar: avatarToSave,
                    real_name: realName,
                    province: selectedProvince,
                    company: selectedCompany
                }
            });

            // 更新本地缓存
            userInfo.real_name = realName;
            userInfo.province = selectedProvince;
            userInfo.company = selectedCompany;
            userInfo.profile_verified = true;
            app.setUserInfo(userInfo);
            app.markDataDirty(['profile', 'home', 'leaderboard', 'study', 'energy', 'redeem']);

            wx.hideLoading();
            wx.showToast({ title: '认证成功', icon: 'success' });

            // 成功后跳转到首页
            setTimeout(() => {
                wx.switchTab({ url: '/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green' });
            }, 1500);

        } catch (err) {
            console.error('提交失败:', err);
            wx.hideLoading();
            wx.showModal({
                title: '认证失败',
                content: err.detail || err.message || '资料填写错误，不予通过',
                showCancel: false
            });
        }
    }
});
