"""
根据 Excel 名单给「2026分销商大会拍视频奖励」发放 50 施能量，并记录到 energy_transactions 表。

用法:
    cd faq-backend
    # 预览模式（不写入数据库）
    python -m scripts.import_conference_video_rewards --dry-run

    # 正式执行（需用生产 DATABASE_URL 覆盖本机 .env 的 sqlite）
    python -m scripts.import_conference_video_rewards

Excel 文件: 拍视频奖励施能量人员名单(1).xlsx
Sheet: Sheet2
A 列 = 分销商 (company)
B 列 = 姓名 (real_name)
C 列 = 奖励施能量 (amount)

另追加测试用户「李俊贤」（施耐德内部管理员），仅按 real_name 匹配。

匹配逻辑:
  - 名单用户按 real_name + company 精确匹配 User 表
  - 李俊贤按 real_name='李俊贤' 匹配
  - 未匹配到的用户打印警告并跳过
  - 防重复：同一用户 + activity_reward + 2026-09 不可重复发放
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openpyxl import load_workbook
from sqlalchemy import select

from app.db.session import AsyncSessionLocal, close_db
from app.models.energy import EnergyTransaction
from app.models.user import User


# ========== 配置 ==========
EXCEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "拍视频奖励施能量人员名单(1).xlsx"
)
SHEET_NAME = "Sheet2"
REWARD_MONTH = "2026-09"
REWARD_TYPE = "activity_reward"
REWARD_TITLE = "2026分销商大会拍视频奖励"
REWARD_TEXT = "感谢您为2026年分销商大会提供视频素材，特此奖励50格施能量！"
REWARD_AMOUNT = 50

# 测试用户（施耐德内部管理员，仅按姓名匹配）
TEST_USER_NAME = "李俊贤"

COL_COMPANY = 1      # A 列
COL_NAME = 2         # B 列
COL_ENERGY = 3       # C 列
START_ROW = 2        # 数据从第 2 行开始


def read_excel():
    """读取 Excel，返回 [(name, company, energy), ...] 列表，同一（姓名+公司）合并金额。"""
    abs_path = os.path.abspath(EXCEL_PATH)
    print(f"读取 Excel: {abs_path}")

    if not os.path.exists(abs_path):
        print(f"错误: 文件不存在 - {abs_path}")
        sys.exit(1)

    wb = load_workbook(abs_path, read_only=True, data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        print(f"错误: 找不到 Sheet '{SHEET_NAME}'，可用: {wb.sheetnames}")
        sys.exit(1)

    ws = wb[SHEET_NAME]
    raw_records = []

    for row in ws.iter_rows(min_row=START_ROW):
        company = row[COL_COMPANY - 1].value
        name = row[COL_NAME - 1].value
        energy = row[COL_ENERGY - 1].value

        if not name or not company:
            continue

        name = str(name).strip()
        company = str(company).strip()
        energy = int(energy) if energy is not None else 0

        if energy <= 0:
            continue

        raw_records.append((name, company, energy))

    wb.close()

    # 合并同一（姓名+公司）的多条记录，累加能量值
    merged = {}
    for name, company, energy in raw_records:
        key = (name, company)
        merged[key] = merged.get(key, 0) + energy

    records = [(name, company, total) for (name, company), total in merged.items()]
    records.sort(key=lambda r: r[0])  # 按姓名排序

    print(f"读取完成: {len(records)} 条有效记录")
    return records


async def resolve_user(session, name: str, company: str | None):
    """解析用户：优先按 real_name + company 精确匹配；失败时降级按 real_name 唯一匹配。

    返回 (user, matched_company) 或 (None, None)。
    降级仅用于公司命名与库中不一致的情况（如 Excel 写「...电力工程有限公司」而库中为「...集团有限公司」），
    且要求按姓名唯一命中，避免误匹配重名用户。
    """
    # 1) 姓名 + 公司精确匹配
    if company:
        stmt = select(User).where(User.real_name == name, User.company == company)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user, company

    # 2) 降级：按姓名唯一匹配
    stmt = select(User).where(User.real_name == name)
    result = await session.execute(stmt)
    candidates = result.scalars().all()
    if len(candidates) == 1:
        return candidates[0], candidates[0].company

    if len(candidates) > 1:
        print(f"[多匹配] {name} 存在多个同名用户，跳过（需人工确认）")
        return None, None

    return None, None


async def run(dry_run: bool = False):
    # 名单用户（real_name + company 匹配）
    records = read_excel()

    # 追加测试用户「李俊贤」（仅姓名匹配）
    test_records = [(TEST_USER_NAME, None, REWARD_AMOUNT)]

    print(f"\n{'名字':<10} {'公司':<30} {'能量':>6}")
    print("-" * 48)
    for name, company, energy in records:
        print(f"{name:<10} {str(company)[:30]:<30} {energy:>6}")
    for name, company, energy in test_records:
        print(f"{name:<10} {'(测试/按姓名匹配)':<30} {energy:>6}")
    print()

    if dry_run:
        print("=== DRY-RUN 模式，不会写入数据库 ===\n")

    async with AsyncSessionLocal() as session:
        success = 0
        skipped_duplicate = 0
        not_found = 0
        errors = 0
        issued = []

        # 名单用户：优先 姓名+公司，失败则降级按姓名唯一匹配
        for name, company, energy in records:
            user, matched_company = await resolve_user(session, name, company)

            if not user:
                not_found += 1
                detail = f"（系统中无 real_name='{name}'+company='{company}' 的用户，跳过）"
                print(f"[未匹配] {name} - {company}{detail}")
                continue

            if company and matched_company and matched_company != company:
                print(f"[降级匹配] {name}：Excel 公司='{company}'，库中='{matched_company}'")

            # 防重复检查
            existing_stmt = select(EnergyTransaction).where(
                EnergyTransaction.user_id == user.id,
                EnergyTransaction.type == REWARD_TYPE,
                EnergyTransaction.related_month == REWARD_MONTH,
            )
            existing_result = await session.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                skipped_duplicate += 1
                print(f"[重复] {name} - {company}（已发放过 {REWARD_MONTH} 活动奖励，跳过）")
                continue

            if dry_run:
                success += 1
                print(f"[预览] {name} - {company} → +{energy} 能量")
                continue

            try:
                transaction = EnergyTransaction(
                    user_id=user.id,
                    amount=energy,
                    type=REWARD_TYPE,
                    title=REWARD_TITLE,
                    description=REWARD_TEXT,
                    related_month=REWARD_MONTH,
                    status="issued",
                )
                session.add(transaction)
                user.total_score = (user.total_score or 0) + energy
                success += 1
                issued.append((name, company))
                print(f"[发放] {name} - {company} → +{energy} 能量")
            except Exception as e:
                errors += 1
                print(f"[错误] {name} - {company}: {e}")

        # 测试用户：李俊贤仅按姓名匹配
        for name, company, energy in test_records:
            stmt = select(User).where(User.real_name == name)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                not_found += 1
                print(f"[未匹配] {name}（系统中无 real_name='{name}' 的用户，跳过）")
                continue

            existing_stmt = select(EnergyTransaction).where(
                EnergyTransaction.user_id == user.id,
                EnergyTransaction.type == REWARD_TYPE,
                EnergyTransaction.related_month == REWARD_MONTH,
            )
            existing_result = await session.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                skipped_duplicate += 1
                print(f"[重复] {name}（已发放过 {REWARD_MONTH} 活动奖励，跳过）")
                continue

            if dry_run:
                success += 1
                print(f"[预览] {name}（测试） → +{energy} 能量")
                continue

            try:
                transaction = EnergyTransaction(
                    user_id=user.id,
                    amount=energy,
                    type=REWARD_TYPE,
                    title=REWARD_TITLE,
                    description=REWARD_TEXT,
                    related_month=REWARD_MONTH,
                    status="issued",
                )
                session.add(transaction)
                user.total_score = (user.total_score or 0) + energy
                success += 1
                issued.append((name, company))
                print(f"[发放] {name}（测试） → +{energy} 能量")
            except Exception as e:
                errors += 1
                print(f"[错误] {name}: {e}")

        if not dry_run:
            await session.commit()

    # 输出报告
    print("\n" + "=" * 50)
    print("执行报告")
    print("=" * 50)
    print(f"  总记录数:     {len(records) + len(test_records)}")
    print(f"  成功发放:     {success}")
    print(f"  重复跳过:     {skipped_duplicate}")
    print(f"  未匹配用户:   {not_found}")
    print(f"  执行错误:     {errors}")
    if dry_run:
        print(f"\n  (DRY-RUN 模式，以上为预览结果，未实际写入数据库)")

    await close_db()


async def main():
    parser = argparse.ArgumentParser(description="导入2026分销商大会拍视频奖励")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入数据库")
    args = parser.parse_args()
    await run(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())