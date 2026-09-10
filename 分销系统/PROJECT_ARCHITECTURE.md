# 分销商学堂 — 项目架构文档

> 用途：新 AI 会话启动时，读取本文档即可快速理解项目全局规范与架构。
> 维护：当项目结构、技术选型、核心约定发生变化时，请同步更新本文档。

---

## 1. 项目概述

"分销商学堂" 是面向施耐德电气分销商的移动端培训与学习系统，基于微信小程序构建，提供答题闯关、积分排行、能量商城、AI 智能问答（知识库 RAG 增强 + 样本下载）、招标文件分析、认可计划（内部积分评选）、每周答题提醒（订阅消息）、姓名水印（防截屏）、免责声明合规等核心功能。

| 属性 | 值 |
|------|-----|
| 项目名称 | 分销商学堂 (Distributor Academy) |
| 目标用户 | 施耐德电气分销商员工 |
| 小程序名称 | 分销商学堂 |
| 后端基域名 | `https://faq-backend-229183-5-1407839340.sh.run.tcloudbase.com` |
| 微信云环境 | `prod-6gi7p6rt55f8e998` |
| AI 智能体平台 | 字节跳动 HiAgent（底层 Coze 引擎） |
| 知识库引擎 | RAGFlow v0.17.0（文档型 RAG，替代纯问答对） |

---

## 2. 技术栈总览

### 2.1 后端 (`faq-backend/`)

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| 语言 | Python 3.11+ | |
| Web 框架 | FastAPI | 异步，自动生成 OpenAPI 文档 |
| ASGI 服务器 | Uvicorn | 生产通过 Docker 运行 |
| ORM | SQLAlchemy 2.x (async) | 异步会话，声明式模型 |
| 数据校验 | Pydantic v2 + pydantic-settings | 请求体校验 + `.env` 配置管理 |
| 数据库 | SQLite (开发) / MySQL (生产) | 通过 `DB_TYPE` 环境变量切换，MySQL 连接串必须含 `charset=utf8mb4` |
| 迁移工具 | Alembic | `migrations/versions/` 管理 |
| 认证 | JWT (python-jose) | Bearer Token, 7 天过期 |
| 日志 | structlog | 结构化 JSON 日志，敏感字段自动脱敏 |
| HTTP 客户端 | httpx | 调用微信 API、HiAgent (Coze)、RAGFlow API |
| PDF 解析 | pdfplumber | 招标文件分析 / PDF 文本提取 |
| Word 解析 | python-docx + 降级策略 | .docx→python-docx, .doc→ZIP检测+原始字节扫描 |
| 订阅消息 | 微信订阅消息 API + asyncio 调度 | 每周答题提醒（一次性订阅，见 6.9） |
| 样本代理下载 | httpx + 腾讯云 COS SDK | 智能体返回的样本链接代理下载（过期签名自动重签 + 分片传输，见 6.12） |
| 对象存储 | 腾讯云 COS | 头像/文件上传，自动回退本地存储 |
| 部署 | Docker + 微信云托管 | 云托管自动扩缩，Dockerfile 启动前执行 `alembic upgrade head`，容器重启需注意配置持久化 |

### 2.2 知识库引擎 (`ragflow/`)

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| RAG 平台 | RAGFlow v0.17.0 (full) | 开源 Apache 2.0，Docker Compose 部署 |
| 向量数据库 | Elasticsearch 8.11.3 | 内置，单节点模式 |
| 关系数据库 | MySQL 8.0 | 知识库元数据存储 |
| 缓存 | Redis 7.2-alpine | 会话/任务队列 |
| 对象存储 | MinIO | 文档文件存储 |
| Embedding 模型 | BGE-M3（内置） | 通过 HuggingFace 镜像加速下载 |
| 检索策略 | 混合检索（向量 + BM25 关键词） | 意图路由 + 多知识库召回 + 去重排序 |
| 部署端口 | Web UI: 8080, API: 9380 | |

### 2.3 小程序前端 (`faq-miniprogram/`)

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| 框架 | 微信原生小程序 | WXML + WXSS + JS (非 Taro/uni-app) |
| 云服务 | 微信云开发 (`wx.cloud`) | 头像上传 + 文件上传(招标文件)至云存储 |
| 语音插件 | WechatSI v0.3.5 | AI 问答页语音输入 |
| 样式方案 | 原生 WXSS + CSS 变量 | 主题色在 `app.wxss` 定义 |
| 状态管理 | `App.globalData` + Storage | 无第三方状态库 |
| 网络请求 | `wx.cloud.callContainer` | 通过微信云托管内网调用后端 |
| 文件下载 | `wx.cloud.callContainer`（分片协议） | 招标文件 + 赋能助手样本下载预览；规避 `wx.downloadFile` 合法域名限制与 1MB 响应上限 |
| 自定义组件 | 原生 Component | `components/watermark/` 姓名水印（页面级注册） |

### 2.4 管理后台

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| `backcontrol/` | 原生 HTML + CSS + Vanilla JS | 独立管理后台，可本地打开 |
| `app/static/admin/` | 同上 | 内嵌于后端，通过 `/admin` 路由访问 |

内嵌后台 Tab：公司排行榜、全员排行榜、学员能量统计、账户管理、兑换订单、奖励记录、答题参与统计、舍得每周排行榜、认可计划管理（`recognition.html` 独立页）。

---

## 3. 目录结构详解

```
分销系统/
├── README.md
├── claude.md                    # ⚠️ AI 开发规则 (11条硬性约束，新会话必读)
├── PROJECT_ARCHITECTURE.md      # ← 本文档
├── 知识库搭建方案.md             # 知识库升级 v2.0 方案文档
├── 知识库升级_TraeCode分阶段提示词.md  # 分阶段实施提示词
│
├── faq-backend/                 # 后端服务 (FastAPI)
│   ├── app/
│   │   ├── main.py              # ★ 应用入口
│   │   ├── api/
│   │   │   ├── deps.py          # 依赖注入：JWT 验证、限流、白名单校验
│   │   │   └── v1/
│   │   │       ├── router.py    # ★ 路由总汇
│   │   │       ├── auth.py      # 微信登录 + 手机号登录 + 密码登录
│   │   │       ├── users.py     # 用户信息 CRUD
│   │   │       ├── admin.py     # 管理后台接口
│   │   │       ├── questions.py # 题库浏览 + 答题
│   │   │       ├── daily.py     # 每日答题
│   │   │       ├── chat.py      # AI 问答 (SSE 流式 + WebSocket)
│   │   │       ├── energy.py    # 能量积分
│   │   │       ├── leaderboard.py      # 实时排行榜
│   │   │       ├── monthly_leaderboard.py # 月度排行榜
│   │   │       ├── lottery.py   # 抽奖系统
│   │   │       ├── rewards.py   # 奖励兑换
│   │   │       ├── certificates.py     # 证书管理
│   │   │       ├── guides.py    # 产品导购指南
│   │   │       ├── knowledge.py # 知识库条目
│   │   │       ├── distributor_data.py # 分销商注册数据
│   │   │       ├── upload.py    # 文件上传
│   │   │       ├── samples.py   # ★ 样本/资料分片代理下载（见 6.12）
│   │   │       ├── subscription.py    # 订阅消息授权/状态（见 6.9）
│   │   │       ├── recognition.py     # 表彰系统
│   │   │       └── bidding.py   # ★ 招标文件分析
│   │   ├── core/
│   │   │   ├── config.py        # ★ 全局配置 (含 RAGFlow 配置)
│   │   │   ├── security.py      # JWT 生成/验证
│   │   │   └── logging.py       # structlog 结构化日志
│   │   ├── db/
│   │   │   ├── session.py       # ★ 数据库引擎 + 会话工厂
│   │   │   └── base.py          # ORM 基类 + TimestampMixin
│   │   ├── models/              # 数据库模型
│   │   │   ├── user.py          # 用户表（含 bidding_whitelisted, recognition 字段）
│   │   │   ├── question.py      # 题目表 (5种题型)
│   │   │   ├── record.py        # 答题记录 (source=daily/bank, quiz_date) + DailyQuizRound 每周题库
│   │   │   ├── energy.py        # 能量交易 + 兑换记录
│   │   │   ├── energy_product.py # 能量商城商品
│   │   │   ├── certificate.py   # 证书记录
│   │   │   ├── guide.py         # 产品导购节点
│   │   │   ├── knowledge.py     # 知识库条目
│   │   │   ├── hiagent_conversation.py # HiAgent 会话持久化
│   │   │   ├── lottery.py       # 抽奖活动 + 中奖记录
│   │   │   ├── monthly.py       # 月度排行快照
│   │   │   └── recognition.py   # 表彰记录
│   │   ├── schemas/             # Pydantic 请求/响应 Schema
│   │   ├── services/            # ★ 业务逻辑层
│   │   │   ├── agent.py         # ★ AI 智能体 (HiAgent + RAGFlow 检索增强)
│   │   │   ├── ragflow_retriever.py  # ★ RAGFlow 检索桥接 (意图路由 + 多知识库)
│   │   │   ├── bidding_analyzer.py   # 招标文件分析器
│   │   │   ├── bidding_features.py   # 招标分析特征库
│   │   │   ├── bidding_param_extractor.py # 招标参数提取
│   │   │   ├── bidding_semantic.py   # 招标语义分析
│   │   │   ├── quiz.py          # 答题逻辑
│   │   │   ├── wechat.py        # 微信服务端 API
│   │   │   ├── energy.py        # 能量/积分业务
│   │   │   ├── lottery.py       # 抽奖业务
│   │   │   ├── ranking.py       # 排行计算
│   │   │   ├── recognition.py   # 表彰业务
│   │   │   ├── storage.py       # 存储服务 (本地/COS 自适应)
│   │   │   ├── admin_auth.py    # 管理后台认证
│   │   │   ├── monthly_leaderboard.py # 月度排行服务
│   │   │   ├── monthly_reward_scheduler.py # 月度奖励定时调度
│   │   │   └── subscription_reminder_scheduler.py # ★ 订阅消息调度（每周一 09:00 答题提醒）
│   │   ├── static/
│   │   │   ├── admin/           # 内嵌管理后台 (index.html + recognition.html)
│   │   │   ├── avatars/         # 用户头像
│   │   │   └── bidding-docs/    # 投标文件资源库 (21个PDF)
│   │   └── utils/
│   │       └── province.py      # 中国省份数据
│   ├── migrations/              # Alembic 迁移脚本 (23个版本)
│   ├── scripts/                 # 运维/数据导入脚本 (35+，含 refresh_guide_asset_urls.py COS 签名刷新)
│   ├── tests/                   # pytest 测试 (含 test_ragflow_retriever.py, test_energy_products.py)
│   ├── loadtests/               # Locust 压力测试
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example             # 环境变量模板 (含 RAGFlow 配置)
│   └── alembic.ini
│
├── faq-miniprogram/             # 微信小程序
│   ├── app.js                   # ★ 全局入口
│   ├── app.json                 # ★ 页面注册 + TabBar
│   ├── app.wxss                 # 全局样式 + CSS 变量
│   ├── config/
│   │   ├── env.js               # 环境配置
│   │   └── runtime.js           # 运行时配置解析
│   ├── pages/
│   │   ├── shouye_Home_Dashboard_Green/  # Tab1: 首页仪表盘 (含 weeklyQuizBadge 周答题徽章)
│   │   ├── zhinengwenda_AI_Assistant_Green/ # Tab2: AI 问答
│   │   ├── energy-mall/         # Tab3: 能量商城
│   │   ├── wode_User_Profile_Green/      # Tab4: 个人中心
│   │   ├── bidding-result/      # 招标文件分析结果页
│   │   ├── quiz/                # 答题页
│   │   ├── question-bank/       # 题库浏览
│   │   ├── question-list/       # 题目列表
│   │   ├── question-detail/     # 题目详情
│   │   ├── leaderboard/         # 完整排行榜
│   │   ├── certificate/         # 证书页
│   │   ├── knowledge/           # 知识库
│   │   ├── login/               # 登录
│   │   ├── register/            # 注册
│   │   ├── legal/terms + legal/privacy   # 服务条款 / 隐私政策
│   │   ├── profile-edit/        # 编辑资料
│   │   ├── redeem-record/       # 兑换记录
│   │   ├── reward-record/       # 奖励记录
│   │   ├── studyRecord/         # 学习记录
│   │   ├── help-center/         # 帮助中心
│   │   ├── about-academy/       # 关于学堂
│   │   ├── disclaimer/          # ★ 免责声明同意页 (2026-08 新增，见 6.10)
│   │   └── recognition/         # ★ 认可计划 (2026-08 新增，见 6.7)
│   │       ├── submit/          # 申报类型入口
│   │       ├── submit-form/     # 申报表单
│   │       ├── sales-rate/      # 销售满意度评分
│   │       ├── survey-detail/   # 评分明细页（经理端，2026-09 新增）
│   │       ├── my-awards/       # 我的获奖/积分
│   │       └── ranking/         # 认可排行
│   ├── images/                  # 图标资源
│   └── components/
│       └── watermark/           # ★ 姓名水印组件（页面级注册，见 6.11）
│
├── ragflow/                     # ★ RAGFlow 知识库引擎 (2026-08 新增)
│   ├── docker-compose.yml       # RAGFlow + MySQL + ES + Redis + MinIO
│   ├── .env                     # RAGFlow 环境变量 (API Key, KB IDs)
│   ├── import_pdfs.py           # PDF 批量导入 + 分块策略配置
│   ├── migrate_faq.py           # HiAgent 问答对 → 结构化文档迁移
│   ├── test_retrieval.py        # 检索精度测试 (5 条基线用例)
│   ├── eval_accuracy.py         # 检索精度评测 (20 条全场景用例)
│   ├── compare_systems.py       # 新旧系统对比测试 (50 条用例)
│   ├── check_chunks.py          # 知识库分块配置验证
│   ├── check_docs_status.py     # 文档导入状态检查
│   ├── compare_report.json      # 系统对比测试结果
│   ├── eval_report.json         # 检索精度评测结果
│   ├── knowledge_docs/          # ★ 迁移生成的结构化文档 (44 份)
│   │   ├── 友商层/              # 13 份竞品参数对比文档
│   │   ├── 话术层/              # 20 份销售话术指南
│   │   └── 通用知识层/          # 11 份通用知识文档
│   ├── es-data/                 # Elasticsearch 数据卷
│   ├── mysql-data/              # MySQL 数据卷
│   └── minio-data/              # MinIO 对象存储卷
│
├── schneider_pdfs/              # 施耐德 PDF 产品样本 (8 份)
│   └── 00 2026/                 # I-Line B/H/HL/HN/C/V/W 系列
│
├── 友商产品样本/                 # 友商 PDF 产品样本 (17 份)
│                               # Eaton 8 份 + 正泰/德力西 5 份 + LS/Starline 各 1 份
│
├── FAQ集/                       # HiAgent 原始问答对数据
│   ├── 产品库FAQ/               # 1,269 条 (含 qa.jsonl + index.yaml)
│   ├── 友商数据/                # 1,316 条
│   ├── 政策库/                  # 108 条
│   ├── 无具体型号的FAQ库/        # 199 条
│   ├── 施耐德FAQ知识库.xlsx      # Excel 汇总版
│   └── convert_to_excel.py      # JSONL → Excel 转换脚本
│
├── VBA工具/                     # 商机筛选导出 Excel 工具
│   ├── 商机筛选导出工具_v1.0.xlam
│   ├── 代码A_v3修复版.txt
│   └── 同事使用指南.txt
│
├── scripts/                     # 知识库审核与数据提取脚本
│   ├── schneider_pdf_texts/     # 施耐德 PDF 提取文本
│   ├── pdf_texts/               # 友商 PDF 提取文本
│   ├── audit_faq_against_pdfs.py      # FAQ vs PDF 交叉审核
│   ├── generate_schneider_faq_v4.py   # 从 PDF 自动生成 FAQ
│   └── FAQ审核报告_20260624_141820.xlsx
│
├── backcontrol/                 # 独立管理后台
├── docs/                        # 设计文档
│   └── superpowers/
│       ├── plans/               # 实施计划
│       └── specs/               # 设计规范
└── .gitignore
```

---

## 4. 入口文件与启动流程

### 4.1 后端入口 `faq-backend/app/main.py`

```
启动顺序:
  1. setup_logging()            → structlog 初始化
  2. lifespan.startup:
     a. settings.validate_runtime_requirements() → 环境变量校验
     b. init_db()               → 校验数据库连接 + Alembic head 一致性（不再自动执行迁移）
     c. start_monthly_reward_scheduler() → 月度奖励定时器（管理员手动触发）
     d. start_subscription_scheduler()  → 订阅提醒调度器（每 60s 扫描待发送授权）
  3. FastAPI app 实例创建:
     - CORS: 仅允许 https://servicewechat.com
     - 路由挂载: /api → api_v1_router
     - 静态文件: /static → static/ 目录
     - 管理后台: /admin → static/admin/index.html
     - /health 健康检查
  4. lifespan.shutdown: 停止两个调度器 + close_db()

数据库迁移：生产由 Dockerfile CMD 在启动前执行 `alembic upgrade head`（二进制包含 alembic.ini + migrations/），应用启动仅校验 head 一致性并报错提示；本地开发手动执行。
```

### 4.2 路由注册 `faq-backend/app/api/v1/router.py`

| 路由模块 | 典型前缀 | 核心功能 |
|---------|---------|---------|
| auth | `/api/auth` | 微信登录、手机登录、密码登录 |
| admin | `/api/admin` | 管理后台 CRUD |
| questions | `/api/questions` | 题库浏览、答题、提交答案 |
| daily | `/api/daily` | 每日答题管理 |
| chat | `/api/chat` | AI 问答 (SSE + WebSocket) |
| energy | `/api/energy` | 能量积分管理 |
| leaderboard | `/api/leaderboard` | 实时排行榜 |
| monthly_leaderboard | `/api/monthly` | 月度排行 + 结算 |
| lottery | `/api/lottery` | 抽奖 |
| rewards | `/api/rewards` | 奖励兑换 |
| certificates | `/api/certificates` | 证书 |
| guides | `/api/guides` | 产品导购树 |
| knowledge | `/api/knowledge` | 知识库 |
| distributor_data | `/api/distributor` | 省份/公司数据 |
| upload | `/api/upload` | 文件上传 |
| samples | `/api/samples` | 智能体样本/资料分片代理下载（meta+part，COS 过期自动重签） |
| subscription | `/api/subscription` | 订阅消息授权与状态查询（每周答题提醒） |
| recognition | `/api/recognition` | 认可计划（申报/评分/评选/积分） |
| bidding | `/api/bidding` | 招标文件分析（extract/analyze/upload） |

### 4.2.1 管理后台报告接口 (`/api/admin/`)

| 接口 | 说明 |
|------|------|
| `/reports/quiz-participation/weekly` + `/export` | 答题参与周报（按周次聚合，可导出 Excel） |
| `/reports/quiz-participation/monthly` + `/export` | 答题参与月报 |
| `/reports/quiz-participation/all/export` | 全部参与记录导出 |
| `/reports/suzhou-shede-weekly-quiz` + `/export` | 苏州舍得每周答题排行榜（见 6.8） |

### 4.3 小程序入口 `faq-miniprogram/app.js`

```
启动顺序:
  1. installSafeConsole()       → 生产环境静默日志 + 敏感字段脱敏
  2. getRuntimeConfig()         → 读取 env.js + 分辨率环境版本
  3. wx.cloud.init()            → 微信云开发初始化
  4. syncAuthWithRuntimeConfig() → 环境切换时清除旧认证
  5. getUserProfile()           → 从 Storage 恢复 userId/token/userInfo
```

---

## 5. 核心开发规范

### 5.1 如何发起后端请求

统一入口：`app.request(options)`，全项目仅此一处网络请求。

```javascript
const result = await app.request({
  url: '/api/questions/daily',
  method: 'POST',
  data: { category: '产品知识' },
  timeout: 20000,
  retryCount: 2,
  dedupe: true,
  debugTag: 'my-page-load'
});
```

关键行为：
- 自动注入 `Authorization: Bearer <token>`
- 自动注入 `X-WX-SERVICE: faq-backend` (云托管内网调用)
- 响应自动解包：`{ code: 0, data: ... }` → 直接返回 `data`
- 401 → 自动清除认证状态并跳转登录页

**禁止事项**：不要在页面中直接使用 `wx.request` 或 `wx.cloud.callContainer`，必须通过 `app.request()`。仅两处例外（均需自定义请求头，`wx.downloadFile` 无法满足）：
1. 招标文件分析页 (`bidding-result.js`)：直接传递 `download_url` 且超时 120s
2. 赋能助手样本下载 (`zhinengwenda_AI_Assistant_Green.js`)：调用 `/api/samples/download` 分片下载，并通过 `Authorization` 头透传登录态（见 6.12）

### 5.2 如何管理用户认证

```
认证流程:
  1. wx.login() 获取 code
  2. app.request({ url: '/api/auth/login', data: { code } }) → 获取 token + userId
  3. 存储: wx.setStorageSync('userId', ...) / wx.setStorageSync('token', ...)
  4. globalData 同步更新
```

**强制登录（2026-09 整改）**：微信"取消授权/返回"无效，未登录用户不可停留在需登录页面，统一跳转登录。

**免责声明合规（2026-08-31 新增，见 6.10）**：登录后未同意的用户会被三层拦截（登录成功 → 首页 `onShow` → 需登录页 `checkLogin`）引导至 `pages/disclaimer/`，同意后通过 `POST /api/auth/consent` 落库，未同意无法使用系统。

### 5.3 全局状态管理

```javascript
app.globalData = {
  userInfo: null,     // 用户完整信息
  userId: '',         // 用户 UUID
  token: '',          // JWT Bearer Token
  guestMode: false,   // 游客模式
  runtimeConfig: null,// 运行时配置
  baseUrl: ''         // 后端 API 基地址
}
```

### 5.4 数据脏标记系统 (Dirty Scope)

```javascript
app.markDataDirty('energy');           // 标记能量相关数据需刷新
if (app.consumeDataDirty('energy')) {  // 消费标记
  this.loadData();
}
```

常用 scope：`energy`、`profile`、`leaderboard`、`daily`、`certificate`。

### 5.5 样式规范

- 主题色：绿色 `#00B050`，辅助色蓝色 `#2B5AED`
- CSS 变量（定义于 `app.wxss`）：`--primary-color`、`--success-color`、`--error-color` 等
- 尺寸单位：使用 `rpx`
- 没有 UI 组件库：所有 UI 均手写 WXML + WXSS

### 5.6 如何添加新页面

1. 在 `pages/` 下创建目录 `pages/my-new-page/`
2. 创建四个文件：`.js`、`.json`、`.wxml`、`.wxss`
3. 在 `app.json` 的 `pages` 数组中注册路径
4. 使用 `wx.navigateTo({ url: '/pages/my-new-page/my-new-page' })` 跳转

### 5.7 如何添加后端 API

1. 在 `app/api/v1/` 下创建或修改对应模块文件
2. 定义 Pydantic Schema 到 `app/schemas/`
3. 实现 Service 逻辑到 `app/services/`
4. 在 `app/api/v1/router.py` 中注册 `router.include_router(xxx.router)`
5. API 响应统一格式：`{ "code": 0, "data": ... }` 或 `{ "code": 1, "message": "错误信息" }`

### 5.8 认证依赖注入

`get_current_user_id` 支持**双 token 验证**（`app/api/deps.py`）：
1. 小程序用户 token（`sub = user UUID`，SECRET_KEY 签发）
2. 后台管理员 token（`sub = login_username`，ADMIN_SECRET_KEY 签发）

```python
from app.api.deps import get_current_user_id, require_bidding_whitelist, require_manager_role

@router.get("/profile")
async def get_profile(
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ...

@router.post("/bidding/analyze")
async def analyze(
    current_user_id: str = Depends(require_bidding_whitelist),
):
    ...

# 认可计划角色校验 (2026-08 新增)
@router.get("/recognition/rules")
async def get_rules(
    user_id: str = Depends(require_manager_role),
):
    ...
```

可用角色依赖：`require_recognition_access`（基座）、`require_manager_role`、`require_sales_role`、`require_specialist_role`、`require_specialist_or_manager`。

### 5.9 数据库迁移

```bash
cd faq-backend
alembic revision --autogenerate -m "描述你的变更"
alembic upgrade head
```

迁移文件命名格式：`YYYYMMDD_NN_描述.py`。当前共 23 个迁移版本（清单见第 10 章）。

---

## 6. 关键业务模块说明

### 6.1 答题系统

- 题型：单选、多选、判断、填空、简答 (5种)
- **每日答题（每周一刷新）**：每周随机 **10 题**（`DailyQuizRound`，`question_count=10`），记录 `source='daily'` + `quiz_date`
- **积分规则**：只有每周这 10 道题（`source='daily'` 且 `is_correct=1`）计入能量积分；题库刷题（`source='bank'`）**只计入答对数、不累计能量积分**
- 周答题徽章：首页 `shouye_Home_Dashboard_Green/weeklyQuizBadge.js` 判断当周是否已答每日题
- 题库：分类管理，支持难度分级 (1-3 星)，`20260810_01` 迁移新增题目图片 URL 字段
- 注意：`app/services/quiz.py` 中的 `QUESTIONS` 数组是 MVP 硬编码数据，生产环境已废弃

### 6.2 AI 问答 (赋能助手) — RAG 增强版 ★

> AI 助手原名为「母线豆包」，已于 2026-09-05 更名为「赋能助手」（Tab 文案、帮助中心、服务条款同步更新）。
> 助手回答中返回的"样本下载"链接由前端通过 `/api/samples/download` 分片代理下载（见 6.12），不直接 `wx.downloadFile`。

核心架构：**RAGFlow 文档检索 → HiAgent LLM 生成**。在调用 HiAgent 之前，先从 RAGFlow 检索相关文档片段作为上下文注入 Prompt。

#### 6.2.1 调用流程

```
用户提问
  → AgentService.chat_stream()
    → HiAgentService._build_rag_enhanced_query()  # 灰度判断
      → RAGFlowRetriever.retrieve()               # 意图路由 + 多知识库检索
        → route_intent()                          # 关键词匹配选择优先层
        → _retrieve_from_dataset() × N            # 并行检索多个知识库
        → _deduplicate_chunks() + 排序            # 去重、按相似度降序
      → format_context()                          # 格式化为 Prompt 上下文
    → 注入 enhanced_message 到 HiAgent Query
  → HiAgent SSE 流式返回
  → 末尾追加 sources 事件（参考来源）
```

#### 6.2.2 四层知识库架构

| 层级 | RAGFlow 知识库 | 数据来源 | 文档数 | 用途 |
|------|--------------|---------|--------|------|
| 事实层 | 施耐德事实层 | 8 份施耐德 PDF 样本 | 8 | 电气参数精确查询 |
| 话术层 | 施耐德话术层 | 1,269 条产品库FAQ 迁移 | 20 | 销售话术、客户疑虑应答 |
| 友商层 | 施耐德友商层 | 1,316 条友商数据 + 17 份友商 PDF | 13 | 竞品参数对比、优势分析 |
| 通用知识层 | 施耐德通用知识层 | 108 条政策库 + 199 条通用FAQ | 11 | 安装测量、认证标准、商务政策 |

#### 6.2.3 意图路由规则

| 触发关键词 | 优先检索层 | 典型问题 |
|-----------|-----------|---------|
| 对比/vs/区别/哪个好/伊顿/ABB/西门子 | 友商层 | "I-Line H 和 XAP-S 哪个好" |
| 怎么推荐/客户说/话术/如何介绍 | 话术层 | "客户说价格贵怎么回应" |
| 安装/测量/认证/标准/施工/维护 | 通用知识层 | "配电房母线测量步骤" |
| 其他（默认） | 事实层 + 通用知识层 | "I-Line H 630A Icw 是多少" |

#### 6.2.4 灰度控制

通过 `RAGFLOW_GRAYSCALE_RATIO` 控制灰度比例（0.0=全关，1.0=全量），基于 `hash(user_id) % 100` 判断。`RAGFLOW_ENABLED=false` 可完全关闭 RAG 检索，回退纯 HiAgent 模式。

#### 6.2.5 配置项

```bash
# .env 中 RAGFlow 相关配置
RAGFLOW_ENABLED=true
RAGFLOW_API_BASE=http://localhost:9380/api/v1
RAGFLOW_API_KEY=<api-key>
RAGFLOW_KNOWLEDGE_BASE_ID=<fact-kb-id>
RAGFLOW_TALK_KB_ID=<talk-kb-id>
RAGFLOW_COMPETITOR_KB_ID=<competitor-kb-id>
RAGFLOW_GENERAL_KB_ID=<general-kb-id>
RAGFLOW_RETRIEVAL_TOP_K=5
RAGFLOW_SIMILARITY_THRESHOLD=0.2
RAGFLOW_GRAYSCALE_RATIO=0.0
```

#### 6.2.6 关键文件

| 文件 | 作用 |
|------|------|
| `app/services/ragflow_retriever.py` | RAGFlow 检索桥接：意图路由、多知识库检索、去重排序、上下文格式化 |
| `app/services/agent.py` | HiAgent 调用 + RAG 增强注入 + 灰度控制 |
| `app/core/config.py` | RAGFlow 全部配置项定义 |
| `tests/test_ragflow_retriever.py` | 检索服务单元测试 |

### 6.3 招标文件分析系统 (v2.0)

完整的招标文件分析功能，使用白名单权限控制，v2.0 引入语义分析 + 参数精确提取 + 智能推荐。

#### 6.3.1 架构概览

```
用户上传文件 → wx.chooseMessageFile → wx.cloud.uploadFile
  → wx.cloud.getTempFileURL → POST /api/bidding/extract 或 /api/bidding/analyze
  → 后端下载文件 → 提取文本 → 分析 → 返回结果 → 前端展示
```

#### 6.3.2 三种接口

| 接口 | 说明 |
|------|------|
| `/api/bidding/extract` | 资料提取：识别要求的证书/报告，匹配已有文件提供下载 |
| `/api/bidding/analyze` | 智能深度分析（`BiddingAnalyzer.deep_analyze`） |
| `/api/bidding/upload` | 向后兼容的旧上传接口（内部转 extract） |

`deep_analyze` 产出：语义要求识别、参数提取与施耐德产品对比、有利/风险条款、产品匹配、投标策略与话术建议。

#### 6.3.3 分析引擎组成

| 模块 | 作用 |
|------|------|
| `bidding_analyzer.py` | 主分析器：文本提取（PDF/docx/doc 降级链）、关键词匹配、deep_analyze 编排 |
| `bidding_semantic.py` | 语义分析：否定句式检测、同义词映射、章节解析、需求匹配 |
| `bidding_param_extractor.py` | 参数提取与比较：`extract_all_params` + `compare_param_with_schneider` |
| `bidding_features.py` | 特征库：友商标识、施耐德条款、风险指标、产品系列参数对比 |

文本提取降级链：`.docx`→python-docx，`.doc`→ZIP 检测 + 原始字节扫描，PDF→pdfplumber（扫描件/图片型 PDF 无法提取文字，属已知限制）。

#### 6.3.4 白名单管理

- 数据库字段：`users.bidding_whitelisted` (TINYINT(1))
- 后端依赖注入：`require_bidding_whitelist` → 校验 `bidding_whitelisted == 1`
- 登录返回值：`auth.py` 返回 `bidding_whitelisted` 字段
- 前端权限检查：`bidding-result.js` 的 `onLoad` 检查权限

### 6.4 能量系统

- 获取途径：每日答题正确、参与排行、系统奖励等
- 消费途径：能量商城兑换实物/虚拟商品
- 后台调度：`monthly_reward_scheduler.py`（管理员手动触发）
- total_score 规则：仅累计赚取，不扣除已兑换，不包含退款

### 6.5 排行榜

- 实时排行：`/api/leaderboard`，按积分降序
- 月度排行：`/api/monthly`，按月快照并支持结算
- 排除规则：施耐德内部员工/管理员不参与排名

### 6.6 抽奖与奖励系统

- 月度奖励：前3名30能量，4-10名20能量，11-20名10能量，21-50名5能量
- 月度抽奖：一等奖10人30能量，二等奖10人20能量，三等奖10人10能量
- 防重复：通过 (user_id, related_month, type) 检查
- 撤销机制：支持撤销指定月份的奖励/抽奖操作

### 6.7 认可计划系统 (2026-08 新增) ★

面向内部员工的积分激励与评选体系，与答题/能量中的"徽章"无关，是独立的一条业务线。管理员通过后台「认可计划管理」页（`static/admin/recognition.html`）配置，员工/销售在小程序端 `pages/recognition/` 参与。

#### 6.7.1 角色体系

| 角色 | `users.recognition_role` | 说明 |
|------|--------------------------|------|
| 分销商 | `distributor` | 默认角色，不参与认可计划 |
| 销售 | `sales` | 对对接专员进行满意度评分 |
| 专员 | `specialist` | 提交成就申报、查看积分/排行 |
| 经理 | `manager` | 审核申报、评分查看、评选计算与发布、配置规则 |

角色依赖（`app/api/deps.py`）：`require_recognition_access` 统一封装 → `require_manager_role` / `require_sales_role` / `require_specialist_role` / `require_specialist_or_manager`。

#### 6.7.2 数据库表（8 张，迁移 `20260805_01_create_recognition_tables.py`）

| 表 | 作用 |
|----|------|
| `recognition_submissions` | 统一成就申报表（含 5 种类型） |
| `recognition_surveys` | 销售满意度评分（效率/响应/培训/沟通 4 维度） |
| `recognition_points` | 认可积分流水 |
| `recognition_awards` | 获奖记录 |
| `recognition_rules_config` | 积分/名额等规则配置（`rule_key`-`rule_value`，后台可改） |
| `recognition_scoring_criteria` | 季度奖项评分标准（动态配置，表单选项数据源） |
| `sales_specialist_mapping` | 销售-专员对接关系表（2026-09-07 自选专员后已废弃，表保留未删） |
| `recognition_annual_snapshots` | 年度快照 |

用户表新增字段：`recognition_role`（默认 `distributor`）、`recognition_score`（认可积分，独立于能量 `total_score`）。

#### 6.7.3 成就申报（5 种类型）

- 微光提名 `nomination`（月度评选，不可自提）
- 报备秩序卫士 `order_guardian`（季度）
- 分销商支持先锋 `distributor_pioneer`（季度）
- 分销商成长伯乐 `distributor_mentor`（季度）
- 效率提升创新 `efficiency_innovator`（季度）

状态机：`draft → submitted → approved / rejected`。季度奖项得分由 `recognition_scoring_criteria` 动态计算（checkbox 勾选得分 / text_list 按条数计分，可设 `max_points`），经理审核可加 `review_score` 附加分。

#### 6.7.4 销售评分（满意度）

- 页面/指引标题统一为**「销售对渠道专员满意度评分」**，评分为**上月表现**（2026-09-08 统一）；评分值措辞统一「不适用」→「N/A」（可选择 N/A）。
- 销售从**系统展示的全部专员**中自行选择评分对象（多选/取消、逐位提交），**不设人数上限**，不再依赖销售-专员映射。
- 周期为**每月**（曾于 08-17 改为季度，08-25 回滚为月度，还原 `survey_month` 字段）；唯一约束 `(rater_id, target_id, survey_month)` 保证同一销售对同一专员每月只能评一次。
- 4 维度整数 0~5（0=N/A，后端归一化为 `None` 不计入均值，前端要求每项必选"打分或 N/A"）：
  - `score_efficiency` 报备处理效率
  - `score_response` 分销商诉求响应
  - `score_training` 赋能培训支持
  - `score_communication` 沟通对接顺畅度
- 接口：`GET /surveys/status`（返回全部专员 + 已评状态）、`POST /surveys`、`GET /surveys/results`（专员端匿名汇总）、`GET /surveys/details` + `GET /surveys/export`（经理端明细/导出，2026-09-09 新增）。
- 角色缓存：`GET /api/user/rank` 返回 `recognition_role` 与 `recognition_score`，前端按日刷新，避免角色缓存过期导致 403 刷屏（2026-09-07）。

#### 6.7.5 评选与积分

- **月度·微光之星**：按月提名次数取前 N 名
- **月度·销圈人气王**：取对某专员评分总分的**中位数**，前 2 名
- **季度奖项**：按动态评分标准得分取前 N 名（`QUARTERLY_AWARD_TYPES`）
- **年度·渠道之星**：综合加权 `积分40% + 获奖20% + 人气王15% + 微光之星10% + 经理15%`
- 排名展示：积分/奖项名次统一用数字序号 1、2、3、4…（2026-08-17 由"金银铜"改为 1234）
- 积分发放：经理先 `calculate-monthly/quarterly/annual` 生成 `RecognitionAward`（`published=False`），再 `publish` 统一发放积分并置为已发布。

积分等级（`users.recognition_score` 判定）：启明星☆(0-100) → 灿星★(101-300) → 耀星✦(301-600) → 极星✧(601+)。

#### 6.7.6 核心接口前缀 `/api/recognition`

`/submissions`（申报 CRUD+审核+提名统计）、`/surveys`（评分状态/提交/结果/明细/进度）、`/points`（我的积分/积分排行/流水/手动调整）、`/awards`（月度/季度/年度计算、发布、结果）、`/ranking`（认可排行完整页）、`/rules`、`/scoring-criteria`（经理配置）、`/users`（角色管理）。

#### 6.7.7 小程序页面 `pages/recognition/`

| 页面 | 角色 | 功能 |
|------|------|------|
| `submit/` | 专员 | 选择申报类型入口 |
| `submit-form/` | 专员 | 申报表单（选项从 scoring_criteria 动态加载） |
| `sales-rate/` | 销售 | 满意度评分（自选专员、逐位提交） |
| `survey-detail/` | 经理 | 查看销售评分明细与反馈（2026-09-09 新增） |
| `my-awards/` | 专员 | 我的获奖/积分 |
| `ranking/` | 专员/经理 | 认可排行页 |

#### 6.7.8 关键文件

| 文件 | 作用 |
|------|------|
| `app/models/recognition.py` | 8 张表模型 |
| `app/services/recognition.py` | 计算引擎：评选、积分、等级、表单配置 |
| `app/api/v1/recognition.py` | 认可计划 API |
| `app/schemas/recognition.py` | 认可计划请求/响应 Schema |
| `app/static/admin/recognition.html` | 管理后台：评审、配置、发布 |

### 6.8 苏州舍得每周答题排行榜 (2026-08 新增)

针对「苏州舍得电力科技有限公司」定制化的周答题排行榜，供后台查看与导出。

- 白名单：`admin.py` 内 `SUZHOU_SHEDE_WHITELIST` 硬编码该公司 **98 人**手机号→姓名/角色映射（销售/技术），2026-08~09 陆续追加（16 名新导入用户、袁孝威、江乐群、陈新瑞等）
- 按周聚合：`week_start`（周一）起 7 天内的答题记录，按答对数降序 + 用时升序排名；未答题者红色高亮
- 接口：`/api/admin/reports/suzhou-shede-weekly-quiz`（列表）+ `/export`（Excel，文件名 `舍得每周答题排行榜-{weekStart}.xlsx`）
- 后台入口：`index.html`「舍得每周排行榜」Tab

### 6.9 每周答题提醒（订阅消息）(2026-09 新增) ★

基于微信**一次性订阅消息**实现"每周一 09:00 答题提醒"，解决学员遗忘答题问题（微信限制：一次性订阅每次授权仅可推一条，需用户每周再次授权）。

```
用户点击（首页引导条 / 答题完成页"开启每周提醒"）
  → wx.requestSubscribeMessage(tmplIds=[subscriptionTemplateId])   # 必须在用户点击行为后触发
  → 授权成功 → POST /api/subscription/auth（幂等）→ 记录 SubscriptionAuth(status=waiting)
  → 计算 target_send_at = 授权后最近的下一个周一 09:00（距目标<2h 顺延一周，避免授权即扣次）
  → 调度器每 60s 扫描 waiting 且到期记录 → 发送后置为 sent/failed
```

- 模板：`env.js → subscriptionTemplateId`（模板 77696「分销商培训答题提醒」，thing1/thing2 字段，value≤20 字符）
- 数据表：`subscription_auths`（迁移 `20260903_02`，含 `ix_subscription_auths_status_target` 索引）
- 接口：`POST /api/subscription/auth`（幂等：已有 waiting 记录直接返回）、`GET /api/subscription/status`
- 调度器：`app/services/subscription_reminder_scheduler.py`，由 `main.py` 启动；`ENABLE_SUBSCRIPTION_SCHEDULER=true` 时开启
- 前端触发点：首页引导条（`shouye_*`）+ 答题完成页交卷即弹引导卡片（`pages/quiz/quiz.js`，每天最多弹一次，可有 `quizReminderPopupDismiss_*` 关闭标记）；未登录/游客不弹

### 6.10 免责声明合规 (2026-08-31 新增)

首次登录及老用户升级后必须同意免责声明后方可使用系统，声明文案："本系统内容仅供授权合作伙伴开展业务活动使用，不得对外传播、复制或向第三方披露"。

- 同意记录：`users` 表 `disclaimer_agreed` / `disclaimer_version` / `disclaimer_agreed_at`（迁移 `20260820_01`）
- 后端接口：`POST /api/auth/consent`（仅登录用户，写版本与时间）；登录返回值携带三个字段
- 前端拦截：登录成功 → 首页 `onShow` → 需登录页 `checkLogin` 三层（`app.js`），跳 `pages/disclaimer/`
- 页面：勾选后才能点"同意"，拒绝显示"无法继续使用"提示且不能使用系统

### 6.11 姓名水印（防截屏追责）(2026-09-06 新增) ★

在**学员答题**（`quiz/`）、**题库练习**（`question-list/`）、**赋能助手 AI 问答**（`zhinengwenda_*`）页面叠加半透明斜体姓名水印，防止内容截屏外泄并追责。

- 文案：**真实姓名 + 手机尾号 4 位**；优先级 `real_name > nickname`，未登录/游客不渲染
- 组件：`faq-miniprogram/components/watermark/`（`name` 属性，`wm-class` 外部类覆盖底栏）；页面级注册（`quiz.json` / `question-list.json` / `zhinengwenda_*.json`），**禁止全局注册**（组件缓存兼容问题，操作"清缓存→清全部缓存→重新编译"生效）
- 样式：#00B050 半透明斜体 -30°，`position:fixed`，`pointer-events:none`，z-index 50，按屏幕尺寸动态行列斜排平铺，避开底部操作栏
- 注意：禁止使用 `hidden` 属性，用 `wx:if` 按 `name` 判显隐

### 6.12 智能体样本下载代理 (2026-09-02 新增) ★

赋能助手（HiAgent 工作流）返回的"样本下载"链接为腾讯云 COS 带时效签名地址（`https://{bucket}.tcb.qcloud.la/{key}?sign=..&t=..`）。直连 `wx.downloadFile` 会因**签名过期 403** 或 **COS 域名未配置合法域名被拦截**失败，因此统一走后端代理。

```
前端解析出 COS 链接
  → wx.cloud.callContainer GET /api/samples/download?url=..&action=meta → {size, parts}
  → 按 part 并发/串行取片（每片 786KB，byte 区间）→ 写临时文件 → wx.openDocument
```

- 路由：`GET /api/samples/download`（`app/api/v1/samples.py`），参数 `url/filename/action(meta|download)/part/part_size`
- **分片协议**：微信云托管 `wx.cloud.callContainer` 响应包上限 **1000KiB**（超限报 `-606002`），故 `meta` 返回文件大小后按字节区间切片；旧版整包返回的部署会被 `version=2` 区分
- **COS 过期自动重签**：请求 401/403 时用 COS SDK（`COS_SECRET_ID/KEY`）按 host 推断 bucket/region 重新签发 900s 签名后重试（Range GET 校验，避免 HEAD 403 假删除）
- **安全**：SSRF 防护——仅允许 `.tcb.qcloud.la / .myqcloud.com / .qcloud.la / .qcloud.com`（可 `SAMPLE_DOWNLOAD_ALLOWED_SUFFIXES` 追加），拦截内网 IP；文件 ≤50MB、分片 ≤200 片；文件名清洗防 header 注入
- 前端：`zhinengwenda_AI_Assistant_Green.js` 解析富文本中的 PDF/文件链接自动触发下载
- 配套脚本：`scripts/refresh_guide_asset_urls.py` 批量刷新 `product_guide_assets` 表过期签名（env 读取 COS 密钥，幂等，失败保留原值告警，已 `COPY scripts` 进 Docker 镜像）

---

## 7. AI 智能体平台信息

### 7.1 HiAgent 平台

- 平台：字节跳动 HiAgent（底层基于 Coze 引擎）
- 调用方式：`app/services/agent.py` → `HiAgentService.chat_stream()` 通过 HTTP API 调用
- 会话管理：通过 `AppConversationID` 实现数据库持久化（`hiagent_conversation` 表），避免 HiAgent 平台重启导致会话丢失
- API Key：通过环境变量 `HIAGENT_API_KEY` 配置

### 7.2 RAGFlow 知识库引擎 ★

- 版本：v0.17.0 (full)，Apache 2.0 开源
- 部署：Docker Compose（5 个容器：ragflow-server + MySQL + Elasticsearch + Redis + MinIO）
- 端口：Web UI `8080`，API `9380`
- Embedding 模型：BGE-M3（通过 HuggingFace 镜像 `hf-mirror.com` 加速下载）
- 检索方式：混合检索（向量语义 + BM25 关键词），意图路由 + 四层知识库
- 评测结果：Precision@5 = 0.83，Recall@5 = 0.65（参数查询和产品对比表现优秀，话术层和认证标准需改进）
- 知识库文档：共 44 份结构化 Markdown 文档，覆盖 2,892 条原始问答对 + 8 份施耐德 PDF + 17 份友商 PDF

### 7.3 FAQ 原始数据

- FAQ 问答对：2,892 条（产品库FAQ 1,269 + 友商数据 1,316 + 政策库 108 + 通用FAQ 199）
- 数据格式：JSONL（`qa.jsonl`）+ YAML 索引（`index.yaml`）+ Excel 汇总
- 数据位置：`FAQ集/` 目录

---

## 8. 注意事项与技术债

### 8.1 AI 开发规则 (`claude.md`)

项目根目录 `claude.md` 记录了 11 条硬性规则，核心要点：

1. 编写代码前先描述方案并等待批准
2. 超过 3 个文件修改需拆分任务
3. 发现 Bug 先写测试再修复
4. 添加数据库字段后必须更新登录/认证接口返回值
5. 多选题必须支持多选 + 独立提交按钮
6. 测试多账号隔离需配置真实 WECHAT_APPID/SECRET
7. AI 返回的 Markdown 图文混排必须在 JS 层正则分段解析
8. 添加新数据库字段后检查所有登录/认证接口返回值
9. 选择题逻辑严格区分单选/多选
10. 后端 .env 配置真实微信密钥（否则本地 Mock 模式数据穿透）
11. 小程序中 Markdown 图文混排需 JS 正则解析 + WXML 分离 `<image>` 标签

### 8.2 已知技术债

| 问题 | 位置 | 严重程度 | 说明 |
|------|------|---------|------|
| 硬编码题库残留 | `services/quiz.py` | 低 | MVP 遗留，不应在生产使用 |
| 两套管理后台 | `backcontrol/` + `static/admin/` | 中 | 功能重叠，维护成本高 |
| 无 TypeScript | 全局 | 中 | 缺乏编译期类型检查 |
| 无前端组件化 | `pages/` 所有页面 | 中 | 大量重复 WXML 代码 |
| 聊天会话缓存一致性 | `chatSessionCache.js` | 中 | 离线恢复可能与服务端状态不同步 |
| 无自动化 CI/CD | 全局 | 中 | 仅手动部署和测试 |
| 招标文件仅支持文字版 | `bidding_analyzer.py` | 低 | 扫描件/图片型PDF无法提取文字 |
| RAGFlow source 字段为"未知来源" | `ragflow_retriever.py` | 中 | 检索结果中文档名未正确传递，影响前端展示 |
| RAGFlow 检索返回 HTML 表格 | `ragflow_retriever.py` | 中 | 上下文含 `<table>` 标签，影响 HiAgent 理解精度 |
| 话术层检索命中率为 0 | `ragflow_retriever.py` | 高 | 话术知识库可能未正确索引或 KB ID 配置错误 |
| 认证标准检索不完整 | `ragflow_retriever.py` | 中 | 4 条认证查询仅 5 个 chunks，3 条返回 0 结果 |
| HiAgent 403 限流 | `agent.py` | 高 | 对比测试时大量请求返回 403，需确认 API Key 配额和限流策略 |
| 施耐德 PDF 知识带 HTML 表格 | RAGFlow 上下文 | 中 | 检索上下文可能含 `<table>` 标签，影响 LLM 理解 |
| 订阅消息一次性限制 | 微信平台机制 | 外部限制 | 一次性订阅每次授权只能推一条，需用户每周再次授权（非代码可解） |

> 注：微信云托管 `callContainer` 1MB 响应上限（`-606002`）已通过分片下载协议解决（见 6.12）；脑机 AI 会话记忆依赖 `hiagent_conversations` 表，必须确保迁移 `20260903_01` 已执行，否则持久化报错。

### 8.3 环境变量关键配置

```bash
# 后端 .env 核心配置项
DB_TYPE=sqlite
DATABASE_URL=               # MySQL 连接串 (生产必填，含 charset=utf8mb4)
SECRET_KEY=                 # JWT 签名密钥 (生产必须更换)
WECHAT_APPID=               # 微信小程序 AppID
WECHAT_SECRET=              # 微信小程序 Secret
HIAGENT_API_KEY=            # HiAgent/Coze API Key

# RAGFlow 知识库引擎
RAGFLOW_ENABLED=true
RAGFLOW_API_BASE=http://localhost:9380/api/v1
RAGFLOW_API_KEY=
RAGFLOW_KNOWLEDGE_BASE_ID=  # 事实层
RAGFLOW_TALK_KB_ID=         # 话术层
RAGFLOW_COMPETITOR_KB_ID=   # 友商层
RAGFLOW_GENERAL_KB_ID=      # 通用知识层
RAGFLOW_RETRIEVAL_TOP_K=5
RAGFLOW_SIMILARITY_THRESHOLD=0.2
RAGFLOW_GRAYSCALE_RATIO=0.0

ENABLE_MONTHLY_REWARD_SCHEDULER=true
CORS_ORIGINS=https://servicewechat.com

# 每周答题提醒订阅消息（2026-09 新增，见 6.9）
ENABLE_SUBSCRIPTION_SCHEDULER=true
SUBSCRIPTION_SEND_INTERVAL_SECONDS=60
SUBSCRIPTION_SEND_BATCH_SIZE=50
SUBSCRIPTION_SEND_BETWEEN_SECONDS=1.0
SUBSCRIPTION_TEMPLATE_ID=nTjfKzlUIeYoYH4N-xS1d-dBCNFx6PDsw9hk0PM21Kk   # 模板77696 分销商培训答题提醒
SUBSCRIPTION_MINIPROGRAM_STATE=formal   # developer/trial/formal，正式环境必须为 formal

# 样本下载代理（2026-09 新增，见 6.12）：额外允许的下载域名后缀（逗号分隔）
SAMPLE_DOWNLOAD_ALLOWED_SUFFIXES=
```

### 8.4 测试

- 框架：pytest + pytest-asyncio + httpx (ASGI 传输)
- 数据库：测试使用 SQLite 内存数据库，通过 `dependency_overrides` 注入
- 位置：`faq-backend/tests/`（含 `test_ragflow_retriever.py`、`test_energy_products.py`）
- 运行：`pytest` (在 `faq-backend/` 目录下)
- 压力测试：`faq-backend/loadtests/` (Locust)
- RAGFlow 评测：`ragflow/eval_accuracy.py` + `ragflow/compare_systems.py`

---

## 9. 快速启动

### 后端

```bash
cd faq-backend
cp .env.example .env        # 编辑 .env 填入真实配置
pip install -r requirements.txt
alembic upgrade head        # 先执行迁移（生产由 Dockerfile 启动前自动执行）
uvicorn app.main:app --reload --port 8000
```

### RAGFlow 知识库引擎

```bash
cd ragflow
docker-compose up -d         # 启动所有容器（首次需等待镜像拉取和初始化）
# Web UI: http://localhost:8080
# API: http://localhost:9380
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

## 10. 数据库迁移版本清单

| 版本 | 日期 | 描述 |
|------|------|------|
| 20260330_01 | 2026-03-30 | 答题记录添加 quiz_date 字段 |
| 20260401_01 | 2026-04-01 | 用户表添加 profile_verified 字段 |
| 20260413_01 | 2026-04-13 | 删除 mistakes 表 |
| 20260414_01 | 2026-04-14 | 创建产品导购表 |
| 20260422_01 | 2026-04-22 | 创建证书记录表 |
| 20260424_01 | 2026-04-24 | 创建能量兑换记录表 |
| 20260424_02 | 2026-04-24 | 创建能量商品表 |
| 20260427_01 | 2026-04-27 | 兑换记录添加收货字段 |
| 20260429_01 | 2026-04-29 | 兑换记录添加批次字段 |
| 20260430_01 | 2026-04-30 | 用户表添加密码登录字段 |
| 20260507_01 | 2026-05-07 | 题目表添加解析字段 |
| 20260509_01 | 2026-05-09 | 创建知识库条目表 |
| 20260513_01 | 2026-05-13 | 创建月度奖励表 |
| 20260514_01 | 2026-05-14 | 创建抽奖奖励表 |
| 20260520_01 | 2026-05-20 | 用户表添加岗位角色字段 |
| 20260531_01 | 2026-05-31 | 能量交易添加通知已读字段 |
| 20260805_01 | 2026-08-05 | 创建认可计划 8 张表 |
| 20260806_01 | 2026-08-06 | 评分周期字段 月度→季度（配套 02 回滚，保留链） |
| 20260806_02 | 2026-08-06 | 评分周期字段 季度→月度（最终态为月度） |
| 20260810_01 | 2026-08-10 | 题目表添加图片 URL 字段 |
| 20260820_01 | 2026-08-20 | 用户表添加免责声明同意字段（disclaimer_*） |
| 20260903_01 | 2026-09-03 | 创建 hiagent_conversations 会话表（AI 会话记忆持久化） |
| 20260903_02 | 2026-09-03 | 创建订阅授权表 subscription_auths |

> 注：2026-08 曾出现迁移多 head 导致部署失败（ddbf975 / 1fa485d 线性化），后续新增迁移须线性追加，禁止分叉产生多 head。

---

## 11. 近期功能更新记录 (2026-07-28 之后)

> 本表用于新会话快速定位近期改动，对应仓库 git 提交记录。

| 日期 | 提交 | 变更 | 涉及文件 |
|------|------|------|---------|
| 09-09 | 2d92039, e994aa0 | 答题交卷即弹每周提醒引导卡片 + 适配模板77696填入真实模板ID | `pages/quiz/`、`config/env.js` |
| 09-09 | 5acf45f | ★ 经理端评分反馈：小程序新增评分明细页 + 后端 surveys/export 导出 | `recognition/survey-detail/`、`api/v1/recognition.py` |
| 09-08 | 00b7e56, 36c7c8f, 287debf, 3024be8, 1df1852 | 渠道专员评分优化：评上月表现/无人数上限/每项必选，「不适用」→N/A，标题统一「销售对渠道专员满意度评分」，未登录欢迎语去"分销商" | `sales-rate.*`、评分指引.md/html、`shouye_*` |
| 09-07 | 1681034, 99298e5 | 销售评分自选专员（废弃映射）+ /api/user/rank 返回认可角色与积分修复403刷屏 | `api/v1/recognition.py`、`services/recognition.py`、`sales-rate.js` |
| 09-06 | 19567be, 3cdb66a | ★ 姓名水印组件：学员答题/题库练习/赋能助手页叠加"姓名+尾号4位"防截屏追责，页面级注册 | `components/watermark/`、`utils/watermark.js`、quiz/question-list/zhinengwenda |
| 09-05 | 4b3610a | AI 助手更名：母线豆包 → 赋能助手 | `app.json`、帮助中心、条款/隐私文案 |
| 09-04 | 901848c, 9bff41e | 经理看板待审核改提示电脑端后台地址 + 修复申报表 text_list 输入丢失(wx:for变量遮蔽) | `shouye_*`、`recognition/submit-form.wxml` |
| 09-03 | 3a28bff, 025d185, 93379ac, 294f78b | ★ 每周答题提醒订阅消息 + hiagent_conversations 迁移补建 + COS签名刷新脚本(打入镜像) + 分片meta解码 | `api/v1/subscription.py`、`subscription_reminder_scheduler.py`、`models/subscription.py`、`scripts/refresh_guide_asset_urls.py` |
| 09-03 | da7bd85 | 登录规范整改：取消/返回无效、强制登录 | `pages/login/` |
| 09-02 | 3cb1ee4, 2617f3a, f0430db, d3c7a66, 56777ca, 281f230, 92d656e, f778d48 | ★ 样本下载代理：/api/samples/download + COS过期自动重签 + 分片协议规避 callContainer 1MB(-606002) + 直连优先 | `api/v1/samples.py`、`zhinengwenda_AI_Assistant_Green.js` |
| 09-01 | f6dfe4a | 修复抽奖发放能量提示显示0格（run_monthly_lottery 缺 _raw_winners 返回值） | `services/lottery.py` |
| 08-31 | 2888540 | ★ 首次登录免责声明同意功能，同意记录留存备查 | `api/v1/auth.py`、`pages/disclaimer/`、迁移 `20260820_01` |
| 08-27 | 1fa485d, ceb97a5 | alembic 迁移链线性化(消除多head) + 能量商城商品按分档内能量升序 + 回归测试 | `migrations/`、`api/v1/energy.py`、`tests/test_energy_products.py` |
| 08-25 | 6a7f2db | 销售评分从季度改回每月一次，还原 survey_month 字段 | `api/v1/recognition.py`、`services/recognition.py` |
| 08-24 | 3836c93, deb02f1, e3a92ec, c7c5062 | 舍得每周排行榜名单追加（16名新用户 + 袁孝威/江乐群/陈新瑞等，白名单达98人） | `api/v1/admin.py` |
| 08-18 | c86f0ee | 2026版 I-Line H 新样本 PDF（SCDOC1874/1896/1936）替换旧版权威样本 | `schneider_pdfs/00 2026/` |
| 08-17 | 9b02acf | 认可计划积分排名金银铜改数字1234 + 销售评分由月度改为季度 | `services/recognition.py`、`api/v1/recognition.py` |
| 08-14 | fc7cdb4, ec3d07e, 7a2c8ec | RAGFlow 检索桥接层 + 话术/友商/通用知识库迁移 + 友商 PDF 导入 + 精度评测 | `services/ragflow_retriever.py`、`services/agent.py`、`ragflow/` |
| 08-10 | 3b2f73c | 题目图片支持 | 迁移 `20260810_01`、questions 相关 |
| 08-07 | a8d7b3a, acca1d0 | 标书分析修复：云托管超时 + PDF 识别鲁棒性 + E-11/框招识别优化 | `services/bidding_analyzer.py`、`api/v1/bidding.py` |
| 08-06 | 57b742f, 63d7b2a, 30e4f3c | 认可后台认证修复 / Tab切换与API路径 + Dockerfile 启动前执行 alembic upgrade head | `api/deps.py`、`static/admin/`、`Dockerfile` |
| 08-05 | c2b18f3, e2a0430 | ★ 认可计划系统完整实现 | models/services/api/schemas/`recognition*`、`static/admin/recognition.html`、小程序 `pages/recognition/` |
| 08-04 | c5c191c | 修复导出活动奖励时"名次/奖项"列误显排名 | `api/v1/admin.py` |
| 08-03 | 5da9dea | 统一抽奖月份逻辑，操作月份=参与月份，月初抽奖→月度抽奖 | `services/lottery.py`、`services/monthly_reward_scheduler.py`、`api/v1/rewards.py`、`static/admin/` |
| 08-03 | c8eb1ce, 348709a | ★ 苏州舍得每周答题排行榜 + 导出排序修复 | `api/v1/admin.py`、`static/admin/app.js` |
| 07-31 | afc5535 | ★ 招标分析 v2.0：语义分析 + 参数提取 + 智能推荐 | `services/bidding_semantic.py`、`bidding_param_extractor.py`、`bidding_analyzer.py` |
| 07-29 | 81de401, b09d3b9 | 兑换订单新增「已完成」状态（删除按钮已移除） | `api/v1/admin.py`、`services/energy.py`、`static/admin/` |

---

> 文档版本: 5.0 | 最后更新: 2026-09-10 | 增加了订阅消息提醒、免责声明合规、姓名水印、样本下载代理（分片协议），更新认可计划评分规则（自选专员/月度/评上月表现）、赋能助手更名、苏州舍得白名单至 98 人、迁移清单 18→23，并线性化重写近期变更记录（08-04 ~ 09-09）