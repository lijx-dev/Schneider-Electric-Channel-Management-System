# 分销商学堂 — 项目架构文档

> 用途：新 AI 会话启动时，读取本文档即可快速理解项目全局规范与架构。
> 维护：当项目结构、技术选型、核心约定发生变化时，请同步更新本文档。

---

## 1. 项目概述

"分销商学堂" 是面向施耐德电气分销商的移动端培训与学习系统，基于微信小程序构建，提供答题闯关、积分排行、能量商城、AI 智能问答（知识库 RAG 增强）、招标文件分析等核心功能。

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
| 对象存储 | 腾讯云 COS | 头像/文件上传，自动回退本地存储 |
| 部署 | Docker + 微信云托管 | 云托管自动扩缩，容器重启需注意配置持久化 |

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
| 文件下载 | `wx.downloadFile` + `wx.openDocument` | 招标文件下载预览 |

### 2.4 管理后台

| 类别 | 技术选型 | 说明 |
|------|---------|------|
| `backcontrol/` | 原生 HTML + CSS + Vanilla JS | 独立管理后台，可本地打开 |
| `app/static/admin/` | 同上 | 内嵌于后端，通过 `/admin` 路由访问 |

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
│   │   │   ├── record.py        # 答题记录
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
│   │   │   └── monthly_reward_scheduler.py # 月度奖励定时调度
│   │   ├── static/
│   │   │   ├── admin/           # 内嵌管理后台
│   │   │   ├── avatars/         # 用户头像
│   │   │   └── bidding-docs/    # 投标文件资源库 (21个PDF)
│   │   └── utils/
│   │       └── province.py      # 中国省份数据
│   ├── migrations/              # Alembic 迁移脚本 (18个版本)
│   ├── scripts/                 # 运维/数据导入脚本 (30+)
│   ├── tests/                   # pytest 测试 (含 test_ragflow_retriever.py)
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
│   │   ├── shouye_Home_Dashboard_Green/  # Tab1: 首页仪表盘
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
│   │   ├── profile-edit/        # 编辑资料
│   │   ├── redeem-record/       # 兑换记录
│   │   ├── reward-record/       # 奖励记录
│   │   ├── studyRecord/         # 学习记录
│   │   ├── help-center/         # 帮助中心
│   │   └── about-academy/       # 关于学堂
│   └── images/                  # 图标资源
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
     b. init_db()               → 创建引擎 + 自动执行 Alembic 迁移
     c. start_monthly_reward_scheduler() → 月度奖励定时器
  3. FastAPI app 实例创建:
     - CORS: 仅允许 https://servicewechat.com
     - 路由挂载: /api → api_v1_router
     - 静态文件: /static → static/ 目录
     - 管理后台: /admin → static/admin/index.html
  4. lifespan.shutdown: close_db()
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
| recognition | `/api/recognition` | 表彰系统 |
| bidding | `/api/bidding` | 招标文件分析（三种接口） |

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

**禁止事项**：不要在页面中直接使用 `wx.request` 或 `wx.cloud.callContainer`，必须通过 `app.request()`。招标文件分析页 (`bidding-result.js`) 因需要直接传递 `download_url` 且超时 120s，使用了 `wx.cloud.callContainer` 直接调用，是唯一例外。

### 5.2 如何管理用户认证

```
认证流程:
  1. wx.login() 获取 code
  2. app.request({ url: '/api/auth/login', data: { code } }) → 获取 token + userId
  3. 存储: wx.setStorageSync('userId', ...) / wx.setStorageSync('token', ...)
  4. globalData 同步更新
```

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

```python
from app.api.deps import get_current_user_id, require_bidding_whitelist

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
```

### 5.9 数据库迁移

```bash
cd faq-backend
alembic revision --autogenerate -m "描述你的变更"
alembic upgrade head
```

迁移文件命名格式：`YYYYMMDD_NN_描述.py`。当前共 18 个迁移版本。

---

## 6. 关键业务模块说明

### 6.1 答题系统

- 题型：单选、多选、判断、填空、简答 (5种)
- 每日答题：每周一 9:00 刷新，随机 5 题，即时反馈
- 题库：分类管理，支持难度分级 (1-3 星)
- 注意：`app/services/quiz.py` 中的 `QUESTIONS` 数组是 MVP 硬编码数据，生产环境已废弃

### 6.2 AI 问答 (母线豆包) — RAG 增强版 ★

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

### 6.3 招标文件分析系统

完整的招标文件分析功能，支持两种模式，使用白名单权限控制。

#### 6.3.1 架构概览

```
用户上传文件 → wx.chooseMessageFile → wx.cloud.uploadFile
  → wx.cloud.getTempFileURL → POST /api/bidding/extract 或 /api/bidding/analyze
  → 后端下载文件 → 提取文本 → 分析 → 返回结果 → 前端展示
```

#### 6.3.2 两种模式

| 模式 | 接口 | 说明 |
|------|------|------|
| 资料提取 | `/api/bidding/extract` | 识别招标文件要求的证书/报告，匹配已有文件提供下载 |
| 智能分析 | `/api/bidding/analyze` | 品牌植入检测、友商痕迹、产品匹配、投标策略 |

#### 6.3.3 特征库 (`bidding_features.py`)

| 模块 | 内容 |
|------|------|
| `COMPETITOR_FEATURES` | 7家友商品牌关键词 |
| `SCHNEIDER_FEATURES` | 施耐德品牌关键词 + 系列型号 |
| `FAVORABLE_CLAUSES` | 24项施耐德有利条款 |
| `COMPETITOR_RISK_INDICATORS` | 10项友商风险指标 |
| `PRODUCT_SERIES` | I-Line B/H/W 三款产品26项技术参数对比 |

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

### 6.7 表彰系统 (2026-08 新增)

- 数据库表：`recognition_records`（表彰记录）
- 迁移版本：`20260805_01_create_recognition_tables.py`
- 接口：`/api/recognition`

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
| 无 Git 客户端 | 全局 | 低 | 当前环境未安装 Git，无法直接操作版本控制 |

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
```

### 8.4 测试

- 框架：pytest + pytest-asyncio + httpx (ASGI 传输)
- 数据库：测试使用 SQLite 内存数据库，通过 `dependency_overrides` 注入
- 位置：`faq-backend/tests/`（含 `test_ragflow_retriever.py`）
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
| 20260805_01 | 2026-08-05 | 创建表彰记录表 |
| 20260810_01 | 2026-08-10 | 题目表添加图片 URL 字段 |

---

> 文档版本: 3.0 | 最后更新: 2026-08-14 | 基于知识库 RAG 升级全面更新