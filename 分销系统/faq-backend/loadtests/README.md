# Locust 压测说明

这套脚本按你当前项目的真实接口约束来写，目标是压到你自己的后端和测试 MySQL，而不是把微信登录接口一起压进去。

## 为什么不压 `/auth/login`

`/auth/login` 和 `/auth/login_phone` 会调用微信接口，压它们会把外部依赖、网络抖动和微信限流一起算进去，结果不能代表你自己的 FastAPI + MySQL 能力。

所以这里的真实压测方案是：

1. 先准备 500 个压测用户。
2. 为这 500 个用户生成 Bearer token 池。
3. 用 Locust 按真实小程序行为去打以下接口：
   - `GET /api/daily/quiz`
   - `POST /api/daily/submit`
   - `GET /api/study/records`
   - `GET /api/leaderboard?scope=total`
   - `GET /api/leaderboard?scope=company`

## 先准备压测用户

在 `faq-backend` 目录执行：

```powershell
.\venv\Scripts\python.exe .\scripts\prepare_locust_users.py --count 500
```

默认行为：

- 准备 500 个压测用户
- 用户分散到多个省区和公司，避免公司榜查询过于失真
- 清空这些压测用户已有的答题记录和积分统计
- 生成 token 文件到 `loadtests\data\loadtest_users.json`

如果你想让 500 个用户都落在同一家公司：

```powershell
.\venv\Scripts\python.exe .\scripts\prepare_locust_users.py --count 500 --company-mode same --company-name 压测总公司 --province-name 上海
```

## 再启动后端

如果你本地启动后端，而 `.env` 里已经指向测试 MySQL，那么 Locust 打到的是“本地 FastAPI + 真实测试 MySQL”。

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

如果你要压远端测试环境接口，也可以直接把 `--host` 换成远端 URL。

注意：

- `prepare_locust_users.py` 生成的 token，必须和目标后端使用同一个 `SECRET_KEY`
- 如果 `SECRET_KEY` 不一致，所有请求都会返回 `401`

## 推荐运行方式

先安装依赖：

```powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements-dev.txt
New-Item -ItemType Directory -Force .\loadtests\reports | Out-Null
```

### 1. 烟雾压测

```powershell
$env:LOADTEST_TOKEN_FILE = "loadtests\\data\\loadtest_users.json"
.\venv\Scripts\python.exe -m locust -f .\loadtests\locustfile.py --host http://127.0.0.1:8000 --headless -u 30 -r 5 -t 5m --csv .\loadtests\reports\smoke
```

### 2. 日常峰值压测

这个档位更适合你“总用户约 500 人”的实际情况。

```powershell
$env:LOADTEST_TOKEN_FILE = "loadtests\\data\\loadtest_users.json"
.\venv\Scripts\python.exe -m locust -f .\loadtests\locustfile.py --host http://127.0.0.1:8000 --headless -u 80 -r 10 -t 10m --csv .\loadtests\reports\normal
```

### 3. 较高峰值压测

用于看早晚高峰或活动期的余量。

```powershell
$env:LOADTEST_TOKEN_FILE = "loadtests\\data\\loadtest_users.json"
.\venv\Scripts\python.exe -m locust -f .\loadtests\locustfile.py --host http://127.0.0.1:8000 --headless -u 150 -r 15 -t 15m --csv .\loadtests\reports\peak
```

## 这套脚本模拟了什么行为

- 50% 请求：获取每周答题
- 25% 请求：提交每周答题
- 15% 请求：查看学习记录
- 7% 请求：查看总榜
- 3% 请求：查看公司榜

这比“只压一个接口”更接近你的小程序真实使用路径。

## 重要限制

- 每个用户每周最多只能提交 5 道周题，所以一次压测跑久了以后，写请求会自然下降
- 如果你要重复做同一周的写入压测，先重新执行一次 `prepare_locust_users.py`
- 并发不要超过 500，否则会开始复用 token，结果会偏离真实场景
- 如果你要压远端测试环境，请确认远端服务连接的也是测试 MySQL，而不是本地 SQLite
