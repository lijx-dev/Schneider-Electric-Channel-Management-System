# 分销商学堂 — 项目架构文档

> **用途**：新 AI 会话启动时，读取本文档即可快速理解项目全局规范与架构。
> **维护**：当项目结构、技术选型、核心约定发生变化时，请同步更新本文档。

---

## 1. 项目概述

**"分销商学堂"** 是面向施耐德电气分销商的移动端培训与学习系统，基于微信小程序构建，提供答题闯关、积分排行、能量商城、AI 智能问答等核心功能。

| 属性       | 值                                                                |
| ---------- | ----------------------------------------------------------------- |
| 项目名称   | 分销商学堂 (Distributor Academy)                                  |
| 目标用户   | 施耐德电气分销商员工                                              |
| 小程序名称 | 分销商学堂                                                        |
| 后端基域名 | `https://faq-backend-229183-5-1407839340.sh.run.tcloudbase.com` |
| 微信云环境 | `prod-6gi7p6rt55f8e998`                                         |

---

## 2. 技术栈总览

### 2.1 后端 (`faq-backend/`)

| 类别        | 技术选型                        | 说明                               |
| ----------- | ------------------------------- | ---------------------------------- |
| 语言        | Python 3.11+                    |                                    |
| Web 框架    | FastAPI                         | 异步，自动生成 OpenAPI 文档        |
| ASGI 服务器 | Uvicorn                         | 生产通过 Docker 运行               |
| ORM         | SQLAlchemy 2.x (async)          | 异步会话，声明式模型               |
| 数据校验    | Pydantic v2 + pydantic-settings | 请求体校验 +`.env` 配置管理      |
| 数据库      | SQLite (开发) / MySQL (生产)    | 通过 `DB_TYPE` 环境变量切换      |
| 迁移工具    | Alembic                         | `migrations/versions/` 管理      |
| 认证        | JWT (python-jose)               | Bearer Token, 7 天过期             |
| 日志        | structlog                       | 结构化 JSON 日志，敏感字段自动脱敏 |
| HTTP 客户端 | httpx                           | 调用微信 API、HiAgent (Coze)       |
| 对象存储    | 腾讯云 COS                      | 头像/文件上传，自动回退本地存储    |
| 部署        | Docker + 微信云托管             |                                    |

### 2.2 小程序前端 (`faq-miniprogram/`)

| 类别     | 技术选型                     | 说明                               |
| -------- | ---------------------------- | ---------------------------------- |
| 框架     | 微信原生小程序               | WXML + WXSS + JS (非 Taro/uni-app) |
| 云服务   | 微信云开发 (`wx.cloud`)    | 头像上传至云存储                   |
| 语音插件 | WechatSI v0.3.5              | AI 问答页语音输入                  |
| 样式方案 | 原生 WXSS + CSS 变量         | 主题色在 `app.wxss` 定义         |
| 状态管理 | `App.globalData` + Storage | 无第三方状态库                     |
| 网络请求 | `wx.cloud.callContainer`   | 通过微信云托管内网调用后端         |

### 2.3 管理后台

| 类别                  | 技术选型                     | 说明                                 |
| --------------------- | ---------------------------- | ------------------------------------ |
| `backcontrol/`      | 原生 HTML + CSS + Vanilla JS | 独立管理后台，可本地打开             |
| `app/static/admin/` | 同上                         | 内嵌于后端，通过 `/admin` 路由访问 |

---

## 3. 目录结构详解

```
分销系统/
├── README.md                    # 项目总文档（可能过时，本文档为准）
├── claude.md                    # ⚠️ AI 开发规则 (11条硬性约束，新会话必读)
├── PROJECT_ARCHITECTURE.md      # ← 本文档
│
├── faq-backend/                 # 后端服务 (FastAPI)
│   ├── app/
│   │   ├── main.py              # ★ 应用入口：FastAPI 实例化、CORS、lifespan、路由挂载
│   │   ├── api/
│   │   │   ├── deps.py          # 依赖注入：JWT 验证(get_current_user_id)、限流、用户权限
│   │   │   └── v1/
│   │   │       ├── router.py    # ★ 路由总汇 (所有子路由注册于此)
│   │   │       ├── auth.py      # 微信登录 + 手机号登录 + 密码登录
│   │   │       ├── users.py     # 用户信息 CRUD
│   │   │       ├── admin.py     # 管理后台接口 (用户管理、数据统计)
│   │   │       ├── questions.py # 题库浏览 + 答题
│   │   │       ├── daily.py     # 每日答题 (每周一 9 点刷新)
│   │   │       ├── chat.py      # AI 问答 (SSE 流式 + WebSocket)
│   │   │       ├── energy.py    # 能量积分 (获取、消费、兑换记录)
│   │   │       ├── leaderboard.py      # 实时排行榜
│   │   │       ├── monthly_leaderboard.py # 月度排行榜 + 结算
│   │   │       ├── lottery.py   # 抽奖系统
│   │   │       ├── rewards.py   # 奖励兑换
│   │   │       ├── certificates.py     # 证书管理
│   │   │       ├── guides.py    # 产品导购指南 (树形结构)
│   │   │       ├── knowledge.py # 知识库条目
│   │   │       ├── distributor_data.py # 分销商注册数据 (省份/公司)
│   │   │       └── upload.py    # 文件上传 (COS / 本地)
│   │   ├── core/
│   │   │   ├── config.py        # ★ 全局配置 (Settings, 读取 .env)
│   │   │   ├── security.py      # JWT 生成/验证
│   │   │   └── logging.py       # structlog 结构化日志 (敏感字段脱敏)
│   │   ├── db/
│   │   │   ├── session.py       # ★ 数据库引擎 + 会话工厂 (SQLite/MySQL 自动切换)
│   │   │   └── base.py          # ORM 基类 + TimestampMixin (created_at/updated_at)
│   │   ├── models/              # 数据库模型 (SQLAlchemy)
│   │   │   ├── user.py          # 用户表
│   │   │   ├── question.py      # 题目表 (5种题型)
│   │   │   ├── record.py        # 答题记录 + 每日答题轮次
│   │   │   ├── energy.py        # 能量交易 + 兑换记录
│   │   │   ├── energy_product.py # 能量商城商品
│   │   │   ├── certificate.py   # 证书记录
│   │   │   ├── guide.py         # 产品导购节点
│   │   │   ├── knowledge.py     # 知识库条目
│   │   │   ├── lottery.py       # 抽奖活动 + 中奖记录
│   │   │   └── monthly.py       # 月度排行快照
│   │   ├── schemas/             # Pydantic 请求/响应 Schema
│   │   ├── services/            # ★ 业务逻辑层 (核心逻辑在此)
│   │   │   ├── agent.py         # AI 智能体 (HiAgent/Coze) 调用
│   │   │   ├── quiz.py          # 答题逻辑 (⚠️ 含 MVP 硬编码题库, 历史遗留)
│   │   │   ├── wechat.py        # 微信服务端 API (code2session, 获取手机号)
│   │   │   ├── energy.py        # 能量/积分业务
│   │   │   ├── lottery.py       # 抽奖业务
│   │   │   ├── ranking.py       # 排行计算
│   │   │   ├── storage.py       # 存储服务 (本地/COS 自适应)
│   │   │   ├── admin_auth.py    # 管理后台认证
│   │   │   ├── monthly_leaderboard.py # 月度排行服务
│   │   │   └── monthly_reward_scheduler.py # 月度奖励定时调度 (asyncio)
│   │   ├── static/admin/        # 内嵌管理后台 (HTML/JS/CSS)
│   │   └── utils/
│   │       └── province.py      # 中国省份数据
│   ├── migrations/              # Alembic 迁移脚本
│   ├── scripts/                 # 运维/数据导入脚本 (30+)
│   ├── tests/                   # pytest + httpx 异步测试
│   ├── loadtests/               # Locust 压力测试
│   ├── Dockerfile               # 生产镜像
│   ├── requirements.txt         # Python 依赖
│   ├── .env.example             # 环境变量模板
│   └── alembic.ini              # Alembic 配置
│
├── faq-miniprogram/             # 微信小程序
│   ├── app.js                   # ★ 全局入口：GlobalData、request()、认证管理、Dirty Scope
│   ├── app.json                 # ★ 页面注册 + TabBar 配置 (4个Tab)
│   ├── app.wxss                 # 全局样式 + CSS 变量主题
│   ├── config/
│   │   ├── env.js               # 环境配置 (云环境ID、后端URL)
│   │   └── runtime.js           # 运行时配置解析 (区分 develop/trial/release)
│   ├── pages/
│   │   ├── shouye_Home_Dashboard_Green/  # Tab1: 首页仪表盘
│   │   ├── zhinengwenda_AI_Assistant_Green/ # Tab2: AI 问答 ("母线豆包")
│   │   ├── energy-mall/         # Tab3: 能量商城
│   │   ├── wode_User_Profile_Green/      # Tab4: 个人中心
│   │   ├── quiz/                # 答题页 (5种题型)
│   │   ├── question-bank/       # 题库浏览
│   │   ├── question-list/       # 题目列表
│   │   ├── question-detail/     # 题目详情
│   │   ├── leaderboard/         # 完整排行榜
│   │   ├── certificate/         # 证书页
│   │   ├── knowledge/           # 知识库
│   │   ├── login/               # 登录 (微信授权 + 手机号 + 密码)
│   │   ├── register/            # 注册 (完善个人信息)
│   │   ├── profile-edit/        # 编辑资料
│   │   ├── redeem-record/       # 兑换记录
│   │   ├── reward-record/       # 奖励记录
│   │   ├── studyRecord/         # 学习记录
│   │   ├── help-center/         # 帮助中心
│   │   ├── about-academy/       # 关于学堂
│   │   └── legal/               # 隐私政策 / 用户协议
│   └── images/                  # TabBar 图标 + 功能图标
│
├── backcontrol/                 # 独立管理后台 (功能与 static/admin 重叠)
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
└── docs/                        # 设计文档
    └── superpowers/
        ├── plans/               # 实施计划
        └── specs/               # 设计规范
```

---

## 4. 入口文件与启动流程

### 4.1 后端入口 `faq-backend/app/main.py`

```
启动顺序:
  1. setup_logging()            → structlog 初始化
  2. lifespan.startup:
     a. settings.validate_runtime_requirements() → 环境变量校验
     b. init_db()               → 创建引擎 + 自动执行 Alembic 迁移
     c. start_monthly_reward_scheduler() → 月度奖励定时器 (需 ENABLE_MONTHLY_REWARD_SCHEDULER=true)
  3. FastAPI app 实例创建:
     - CORS: 仅允许 https://servicewechat.com
     - 路由挂载: /api → api_v1_router
     - 静态文件: /static → static/ 目录
     - 管理后台: /admin → static/admin/index.html
  4. lifespan.shutdown:
     a. stop_monthly_reward_scheduler()
     b. close_db()
```

### 4.2 路由注册 `faq-backend/app/api/v1/router.py`

所有业务路由在此统一注册，每个模块自行定义 `prefix` 和 `tags`：

| 路由模块            | 典型前缀              | 核心功能                     |
| ------------------- | --------------------- | ---------------------------- |
| auth                | `/api/auth`         | 微信登录、手机登录、密码登录 |
| admin               | `/api/admin`        | 管理后台 CRUD                |
| questions           | `/api/questions`    | 题库浏览、答题、提交答案     |
| daily               | `/api/daily`        | 每日答题管理                 |
| chat                | `/api/chat`         | AI 问答 (SSE + WebSocket)    |
| energy              | `/api/energy`       | 能量积分管理                 |
| leaderboard         | `/api/leaderboard`  | 实时排行榜                   |
| monthly_leaderboard | `/api/monthly`      | 月度排行 + 结算              |
| lottery             | `/api/lottery`      | 抽奖                         |
| rewards             | `/api/rewards`      | 奖励兑换                     |
| certificates        | `/api/certificates` | 证书                         |
| guides              | `/api/guides`       | 产品导购树                   |
| knowledge           | `/api/knowledge`    | 知识库                       |
| distributor_data    | `/api/distributor`  | 省份/公司数据                |
| upload              | `/api/upload`       | 文件上传                     |

### 4.3 小程序入口 `faq-miniprogram/app.js`

```
启动顺序:
  1. installSafeConsole()       → 生产环境静默日志 + 敏感字段脱敏
  2. getRuntimeConfig()         → 读取 env.js + 分辨率环境版本
  3. wx.cloud.init()            → 微信云开发初始化
  4. syncAuthWithRuntimeConfig() → 环境切换时清除旧认证
  5. getUserProfile()           → 从 Storage 恢复 userId/token/userInfo 到 globalData
```

### 4.4 页面注册 `faq-miniprogram/app.json`

- **4 个 Tab 页**：首页 → 母线豆包(AI) → 能量商城 → 我的
- **主题色**：`#00B050` (施耐德绿)
- **21 个页面**：含登录、注册、答题、排行榜、题库、证书、知识库、帮助中心、法律条款等

---

## 5. 核心开发规范

### 5.1 如何发起后端请求

**统一入口**：`app.request(options)`，全项目仅此一处网络请求。

```javascript
// 标准调用模式
const result = await app.request({
  url: '/api/questions/daily',     // 必填: API 路径 (自动拼接 baseUrl 或走 callContainer)
  method: 'POST',                   // 可选: 默认 GET
  data: { category: '产品知识' },   // 可选: 请求体
  timeout: 20000,                   // 可选: 超时时间 (ms), 默认 20000
  retryCount: 2,                    // 可选: 重试次数, GET 默认 2, POST 默认 0
  dedupe: true,                     // 可选: 是否去重, GET 默认 true
  debugTag: 'my-page-load'          // 可选: 日志标签, 用于调试追踪
});
```

**关键行为**：

- 自动注入 `Authorization: Bearer <token>`
- 自动注入 `X-WX-SERVICE: faq-backend` (云托管内网调用)
- 响应自动解包：`{ code: 0, data: ... }` → 直接返回 `data`
- `code !== 0` 或 HTTP 错误 → Promise reject
- 401 → 自动清除认证状态并跳转登录页
- 5xx → 自动重试 (retryCount 未耗尽时)

**⚠️ 禁止事项**：不要在页面中直接使用 `wx.request` 或 `wx.cloud.callContainer`，必须通过 `app.request()`。

### 5.2 如何管理用户认证

```
认证流程:
  1. wx.login() 获取 code
  2. app.request({ url: '/api/auth/login', data: { code } }) → 获取 token + userId
  3. 存储: wx.setStorageSync('userId', ...) / wx.setStorageSync('token', ...)
  4. globalData: app.globalData.userId / app.globalData.token 同步更新
```

**关键 API**：

| 方法                                       | 作用                                 |
| ------------------------------------------ | ------------------------------------ |
| `app.getUserProfile()`                   | 从 Storage 恢复认证状态到 globalData |
| `app.checkLogin(autoRedirect)`           | 检查登录状态，未登录自动跳转登录页   |
| `app.requireLogin()`                     | `checkLogin(true)` 的简写          |
| `app.handleUnauthorized()`               | 清除认证 + 跳转登录页                |
| `app.shouldRequireProfileVerification()` | 检查是否需要完善个人信息             |
| `app.redirectToRegister()`               | 跳转注册页 (reLaunch)                |
| `app.syncAuthWithRuntimeConfig()`        | 环境版本变更时清除旧认证             |

### 5.3 全局状态管理

**全局状态 (globalData)**：

```javascript
app.globalData = {
  userInfo: null,     // 用户完整信息 (含 avatar_url, phone, company 等)
  userId: '',         // 用户 UUID
  token: '',          // JWT Bearer Token
  guestMode: false,   // 游客模式 (未登录)
  runtimeConfig: null,// 运行时配置 (环境版本、baseUrl 等)
  baseUrl: ''         // 后端 API 基地址
}
```

**持久化 Key 约定**：

| Storage Key                  | 值                          |
| ---------------------------- | --------------------------- |
| `userId`                   | 用户 UUID                   |
| `token`                    | JWT Bearer Token            |
| `userInfo`                 | 用户完整信息对象            |
| `guestMode`                | 游客模式标记                |
| `runtimeSignature`         | 环境签名 (用于检测环境切换) |
| `apiBaseUrl`               | 后端 API 基地址             |
| `dataDirtyScopes:{userId}` | Dirty Scope 脏标记 Map      |

### 5.4 数据脏标记系统 (Dirty Scope)

一种轻量级的跨页面缓存失效机制：

```javascript
// 写入方：数据变更后标记脏范围
app.markDataDirty('energy');     // 标记能量相关数据需刷新

// 消费方：页面 onShow 时检测并消费标记
if (app.consumeDataDirty('energy')) {
  this.loadData();               // 重新加载数据
}
```

常用 scope 名称：`energy`、`profile`、`leaderboard`、`daily`、`certificate`。

### 5.5 页面自动刷新

```javascript
Page({
  onShow() {
    app.startPageAutoRefresh(this, {
      timerKey: '_liveRefreshTimer',  // 定时器标识
      intervalMs: 15000,              // 刷新间隔(ms), 最小 5000
      refresh: () => this.loadData()  // 刷新回调
    });
  },
  onHide() {
    app.stopPageAutoRefresh(this, '_liveRefreshTimer');
  }
});
```

### 5.6 样式规范

- **主题色**：绿色 `#00B050`，辅助色蓝色 `#2B5AED`
- **CSS 变量** (定义于 `app.wxss`)：
  ```css
  --primary-color: #2B5AED;
  --success-color: #07C160;
  --error-color: #FA5151;
  --text-primary: #333333;
  --text-secondary: #666666;
  --text-hint: #999999;
  --bg-color: #F5F7FA;
  --card-bg: #FFFFFF;
  --border-color: #EEEEEE;
  ```
- **通用样式类**：`.container`、`.card`、`.btn-primary`、`.btn-secondary`、`.badge-gold` 等
- **尺寸单位**：使用 `rpx` (微信小程序响应式像素)
- **没有 UI 组件库**：所有 UI 均手写 WXML + WXSS，未抽取通用组件

### 5.7 如何添加新页面

1. 在 `pages/` 下创建目录 `pages/my-new-page/`
2. 创建四个文件：`my-new-page.js`、`my-new-page.json`、`my-new-page.wxml`、`my-new-page.wxss`
3. 在 `app.json` 的 `pages` 数组中注册路径
4. 使用 `wx.navigateTo({ url: '/pages/my-new-page/my-new-page' })` 跳转
5. 如需传参：`url: '/pages/my-new-page/my-new-page?id=123'`，在 `onLoad(options)` 中接收 `options.id`

### 5.8 如何添加后端 API

1. 在 `app/api/v1/` 下创建或修改对应模块文件
2. 定义 Pydantic Schema (如有新的请求/响应结构) 到 `app/schemas/`
3. 实现 Service 逻辑到 `app/services/` (如涉及复杂业务)
4. 在 `app/api/v1/router.py` 中注册 `router.include_router(xxx.router)`
5. API 响应统一使用格式：`{ "code": 0, "data": ... }` 或 `{ "code": 1, "message": "错误信息" }`

### 5.9 认证依赖注入

```python
from app.api.deps import get_current_user_id, ensure_same_user

@router.get("/profile")
async def get_profile(
    current_user_id: str = Depends(get_current_user_id),  # 自动解析 JWT
    db: AsyncSession = Depends(get_db),
):
    # current_user_id 即为当前登录用户的 UUID
    ...
```

### 5.10 数据库迁移

```bash
# 在 faq-backend/ 目录下执行
alembic revision --autogenerate -m "描述你的变更"
alembic upgrade head
```

迁移文件存放在 `migrations/versions/`，命名格式：`YYYYMMDD_NN_描述.py`。

---

## 6. 关键业务模块说明

### 6.1 答题系统

- **题型**：单选、多选、判断、填空、简答 (5种)
- **每日答题**：每周一 9:00 刷新，随机 5 题，即时反馈
- **题库**：分类管理，支持难度分级 (1-3 星)
- **答题流程**：`/api/questions/daily` 获取题目 → 逐题作答 → 提交答案 `/api/questions/answer`
- **⚠️ 注意**：`app/services/quiz.py` 中的 `QUESTIONS` 数组是 MVP 阶段的硬编码数据，生产环境已废弃，实际数据来自数据库。该文件保留仅作为参考，不应被调用。

### 6.2 AI 问答 (母线豆包)

- **后端对接**：HiAgent (Coze 平台)，通过 `AgentService.chat()` 调用
- **前端模式**：
  - **产品导购模式**：本地维护树形导航 `productGuidesTree`，点击节点展开子节点或直接显示答案
  - **自由问答模式**：调用 SSE 流式接口 `/api/chat/stream`，支持打字机效果
- **特有功能**：语音输入 (WechatSI 插件)、深度思考提示、富文本图片解析、反馈(点赞/踩)
- **聊天缓存**：`chatSessionCache.js` 实现会话持久化，关闭小程序后重新打开可恢复对话

### 6.3 能量系统

- **获取途径**：每日答题正确、参与排行、系统奖励等
- **消费途径**：能量商城兑换实物/虚拟商品
- **后台调度**：`monthly_reward_scheduler.py` 按月结算排行榜并发放奖励
- **兑换流程**：选择商品 → 填写收货信息 → 扣减能量 → 生成兑换记录

### 6.4 排行榜

- **实时排行**：`/api/leaderboard`，按积分降序
- **月度排行**：`/api/monthly`，按月快照并支持结算
- **首页 TOP3**：在首页加载时优先展示金银铜前三名

### 6.5 抽奖系统

- 月度结算后触发抽奖
- 支持多奖品配置
- 中奖记录持久化到 `lottery_winners` 表

---

## 7. 注意事项与技术债

### 7.1 AI 开发规则 (`claude.md`)

项目根目录 `claude.md` 记录了 11 条硬性规则，新 AI 会话必须遵守，核心要点：

1. 编写代码前先描述方案并等待批准
2. 超过 3 个文件修改需拆分任务
3. 发现 Bug 先写测试再修复
4. 添加数据库字段后必须更新登录/认证接口返回值
5. 多选题必须支持多选 + 独立提交按钮，不能点击单个选项后自动提交
6. 测试多账号隔离需配置真实 WECHAT_APPID/SECRET (本地 Mock 模式会使所有手机号返回 `13800000000`)
7. AI 返回的 Markdown 图文混排必须在 JS 层正则分段解析，WXML 分离 `<image>` 标签渲染

### 7.2 已知技术债

| 问题                  | 位置                                 | 严重程度 | 说明                             |
| --------------------- | ------------------------------------ | -------- | -------------------------------- |
| 硬编码题库残留        | `services/quiz.py` L15-56          | 低       | MVP 遗留，不应在生产使用         |
| 两套管理后台          | `backcontrol/` + `static/admin/` | 中       | 功能重叠，维护成本高             |
| 无 TypeScript         | 全局                                 | 中       | 缺乏编译期类型检查               |
| 无前端组件化          | `pages/` 所有页面                  | 中       | 大量重复 WXML 代码，无复用       |
| 头像 URL 归一化链过长 | `app.js` L82-L267                  | 低       | 5 层函数嵌套处理多种格式，可简化 |
| 聊天会话缓存一致性    | `chatSessionCache.js`              | 中       | 离线恢复可能与服务端状态不同步   |
| 无自动化 CI/CD        | 全局                                 | 中       | 仅手动部署和测试                 |

### 7.3 环境变量关键配置

```bash
# 后端 .env 核心配置项
DB_TYPE=sqlite              # sqlite | mysql | memory
DATABASE_URL=               # MySQL 连接串 (生产必填)
SECRET_KEY=                 # JWT 签名密钥 (生产必须更换)
WECHAT_APPID=               # 微信小程序 AppID
WECHAT_SECRET=              # 微信小程序 Secret
HIAGENT_API_KEY=            # HiAgent/Coze API Key
ENABLE_MONTHLY_REWARD_SCHEDULER=true  # 启用月度奖励定时器
CORS_ORIGINS=https://servicewechat.com
```

### 7.4 测试

- 框架：pytest + pytest-asyncio + httpx (ASGI 传输)
- 数据库：测试使用 SQLite 内存数据库，通过 `dependency_overrides` 注入
- 位置：`faq-backend/tests/`
- 运行：`pytest` (在 `faq-backend/` 目录下)
- 压力测试：`faq-backend/loadtests/` (Locust)

---

## 8. 快速启动

### 后端

```bash
cd faq-backend
cp .env.example .env        # 编辑 .env 填入真实配置
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# API 文档: http://localhost:8000/docs
```

### 小程序

1. 微信开发者工具打开 `faq-miniprogram/` 目录
2. 填入 AppID
3. 确保 `config/env.js` 中的 `legacyBaseUrl` 指向后端地址
4. 编译运行

### Docker

```bash
cd faq-backend
docker build -t faq-backend .
docker run -p 8000:8000 --env-file .env faq-backend
```

---

> **文档版本**: 1.0 | **最后更新**: 2026-06-09 | **基于代码审查生成**
