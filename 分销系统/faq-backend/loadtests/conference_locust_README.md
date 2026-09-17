# 分销商大会 Locust 压测

模拟大会现场 **100 名分销商集中登录 + 打卡**的负载，验证三个目标：

1. **登录不限流**：100 人同一 IP 登录不命中 429（限流已放宽，见 `.env` 的
   `RATE_LIMIT_LOGIN` / `RATE_LIMIT_LOGIN_PHONE`，大会期间建议 ≥ 100）。
2. **无重复印记/勋章**：数据库唯一约束兜底，并发重复打卡不会重复发放。
3. **打卡性能**：`submit-quiz` P95 < 500ms。

## 准备

```bash
cd faq-backend

# 1. 生成压测用户 token 池（默认 500 个合成用户）
python scripts/prepare_locust_users.py --count 100 --prefix locust_conf

# 2. 将生成的用户置为大会白名单（或用 SQL 批量开启）
python -c "
import asyncio
from sqlalchemy import update
from app.db.session import AsyncSessionLocal
from app.models.user import User
async def main():
    async with AsyncSessionLocal() as db:
        await db.execute(update(User).where(User.nickname.like('locust_conf%')).values(conference_whitelisted=True))
        await db.commit()
asyncio.run(main())
"

# 3. 确认目标后端已部署最新代码（含迁移 20260917_01 与大会接口）
```

## 运行

```bash
# 本地直连（默认 http://localhost:8089 网页控制台）
locust -f loadtests/conference_locustfile.py --host https://faq-backend-229183-5-1407839340.sh.run.tcloudbase.com

# 或指定并发数直接命令行跑（100 并发、5 分钟、无 UI）：
locust -f loadtests/conference_locustfile.py \
  --host https://faq-backend-229183-5-1407839340.sh.run.tcloudbase.com \
  --headless -u 100 -r 100 -t 5m \
  --csv conference_report

# 结果查看
# - 网页模式：http://localhost:8089 实时曲线
# - headless 模式：conference_report_stats.csv / conference_report_failures.csv
```

## 判读

| 指标 | 期望 |
|------|------|
| `login` 请求中 429 数量 | 0（限流放宽生效） |
| `submit-quiz` 中 `mark_earned=True` 的用户数 | 每个白名单用户最多 1 次 |
| `submit-quiz` P95 | < 500ms |
| 失败计数 | 仅允许微信占位 code 登录的 400/500，无 403/401/429 |

> 提示：登录任务使用占位 code，微信校验必然失败（400/500 属预期），
> 但限流计数发生在调用微信之前，因此登录任务仍可验证限流是否被放宽。
