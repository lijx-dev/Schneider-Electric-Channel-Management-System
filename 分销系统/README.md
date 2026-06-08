# 分销商学堂 - 使用文档

## 📋 目录

1. [项目概述](#项目概述)
2. [技术架构](#技术架构)
3. [项目结构](#项目结构)
4. [快速开始](#快速开始)
5. [配置说明](#配置说明)
6. [功能说明](#功能说明)
7. [常见问题](#常见问题)

---

## 项目概述

面向分销商的移动端培训与学习系统，基于微信小程序 + FastAPI 后端构建。

| 功能 | 说明 |
|------|------|
| **每周答题** | 每周一 9 点随机 5 题，即时反馈 |
| **题库** | 分类题目管理，支持难度分级 |
| **排行榜** | 实时积分排名，首页 TOP3 预览 |
| **AI 智能问答** | 对接 Coze Bot，知识库托管在 Coze 平台 |
| **我的** | 个人信息、学习统计 |

---

## 技术架构

```
微信小程序 (faq-miniprogram)
      │  HTTP/HTTPS
      ▼
FastAPI 后端 (faq-backend / app/)
      │
      ├── SQLite（本地开发）
      │   MySQL（生产，微信云托管）
      │
      └── Coze Bot API（AI 智能问答）
```

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 后端语言 |
| FastAPI | 最新 | Web 框架 |
| SQLAlchemy | 2.x | ORM（异步） |
| SQLite / MySQL | — | 数据存储 |
| Coze Bot | — | AI 智能问答 |
| 微信小程序 | — | 前端（WXML/JS） |

---

## 项目结构

```
分销系统/
│
├── faq-backend/                        # 后端服务（企业版）
│   ├── app/
│   │   ├── main.py                     # ⭐ FastAPI 应用入口
│   │   ├── api/v1/                     # API 路由层
│   │   │   ├── router.py               # 路由总汇
│   │   │   ├── auth.py                 # 微信登录 + JWT
│   │   │   ├── questions.py            # 题目接口
│   │   │   ├── leaderboard.py          # 排行榜接口
│   │   │   ├── users.py                # 用户接口
│   │   │   └── chat.py                 # AI 问答接口
│   │   ├── core/
│   │   │   ├── config.py               # 配置管理（读取 .env）
│   │   │   ├── security.py             # JWT 生成/验证
│   │   │   └── logging.py              # 结构化日志
│   │   ├── db/
│   │   │   ├── session.py              # 数据库连接管理
│   │   │   └── base.py                 # ORM 基类
│   │   ├── models/                     # 数据库表结构
│   │   │   ├── user.py                 # 用户表
│   │   │   ├── question.py             # 题目表
│   │   │   └── record.py               # 答题记录 + 错题表
│   │   ├── schemas/                    # 请求/响应数据格式
│   │   └── services/                   # 业务逻辑
│   │       ├── agent.py                # ⭐ Coze Bot 调用
│   │       ├── quiz.py                 # 答题逻辑
│   │       └── wechat.py               # 微信 API
│   ├── .env                            # ⭐ 本地环境变量（不提交 Git）
│   ├── .env.example                    # 环境变量模板
│   └── requirements.txt                # Python 依赖
│
├── faq-miniprogram/                    # 微信小程序
│   ├── app.js                          # 全局逻辑（含请求封装）
│   ├── app.json                        # 全局配置（页面、tabBar）
│   ├── app.wxss                        # 全局样式
│   └── pages/
│       ├── shouye_Home_Dashboard_Green/ # 首页（答题入口 + 排行榜 TOP3）
│       ├── quiz/                       # 答题页
│       ├── leaderboard/                # 排行榜完整页
│       ├── zhinengwenda_AI_Assistant_Green/ # AI 智能问答
│       └── wode_User_Profile_Green/    # 我的
│
├── 企业版升级规划.md                    # 开发阶段规划文档
└── README.md                           # 本文档
```

---

## 快速开始

### 启动后端

```bash
# 1. 进入后端目录
cd faq-backend

# 2. 激活虚拟环境（已创建则直接激活）
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. 安装依赖
pip install -r requirements.txt


# 5. 启动服务
uvicorn app.main:app --reload
```

启动成功后访问 API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)

---

### 打开小程序

1. 打开**微信开发者工具**
2. 导入项目，目录选择 `faq-miniprogram/`，AppID 选「测试号」或填写真实 AppID
3. 点击右上角「详情」→「本地设置」→ 勾选 ✅ **不校验合法域名**
4. 模拟器中即可预览

---

## 配置说明

所有配置在 `faq-backend/.env` 中管理：

```ini
# ==================== 基础配置 ====================
PROJECT_NAME=分销商学堂
DEBUG=true                          # 生产环境改为 false

# ==================== 数据库 ====================
# 本地开发：留空，自动使用 SQLite 内存数据库
# 生产环境（微信云 MySQL）：
DATABASE_URL=mysql+aiomysql://用户名:密码@内网地址:3306/数据库名

# ==================== JWT 认证 ====================
SECRET_KEY=your-secret-key-here     # 生产环境必须修改！

# ==================== 微信小程序 ====================
WECHAT_APPID=your_appid             # 小程序 AppID
WECHAT_SECRET=your_secret           # 小程序 AppSecret

# ==================== Coze AI ====================
COZE_API_TOKEN=pat_xxxxxxx          # Coze Personal Access Token
COZE_BOT_ID=7xxxxxxxxxxxxxxxxx      # Coze Bot ID

# ==================== CORS ====================
CORS_ORIGINS=https://servicewechat.com,http://localhost:8080
```

### 小程序后端地址

文件：`faq-miniprogram/app.js`

```javascript
baseUrl: 'http://localhost:8000'    // 本地开发
// baseUrl: 'http://192.168.x.x:8000' // 局域网测试
// baseUrl: 'https://your-cloud-url'   // 生产部署后换成云托管地址
```

---

## 功能说明

### 首页
- 用户信息卡片（积分、正确率、排名）
- 每周答题快捷入口
- 学习中心：题库
- 排行榜 TOP3 预览，点击「查看完整排行榜」跳转

### 每周答题
- 每周一早上 9 点刷新 5 道题，计时答题
- 选择后立即显示对错和解析
- 完成后显示本局得分

### AI 智能问答
- 对接 **Coze Bot**，知识库在 Coze 平台维护
- 支持多轮对话（按用户 ID 区分会话）
- 后端非流式轮询，等待 Bot 完成后返回

### 排行榜
- 完整排行榜显示所有用户积分排名
- 顶部金/银/铜牌展示前三名


---

## 常见问题

### Q1：小程序提示「网络请求失败」
1. 确认后端已启动（终端显示 `Uvicorn running`）
2. 确认 `app.js` 中 `baseUrl` 地址正确
3. 确认微信开发者工具已勾选「不校验合法域名」

### Q2：AI 问答返回「AI 问答功能配置中」
1. 检查 `.env` 中 `COZE_API_TOKEN` 和 `COZE_BOT_ID` 是否填写
2. 确认 Coze Bot 已**发布到 API 渠道**
3. 重启后端（`.env` 修改后必须重启才生效）

### Q3：数据重启后丢失
- 本地开发模式（`DATABASE_URL` 为空）使用 SQLite 内存数据库，重启即清空，这是**预期行为**
- 需要持久化请配置 `DATABASE_URL` 指向真实 MySQL 数据库

### Q4：如何添加题目
目前通过 API 或直接操作数据库添加，后续会提供管理后台。
临时方案：启动后访问 `/docs`，使用 Swagger UI 调用 `POST /api/questions` 接口添加题目。

---

> 📅 最后更新：2026-03-03
