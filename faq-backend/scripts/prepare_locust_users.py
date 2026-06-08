from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=False)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import delete, func, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.models.question import Question  # noqa: E402
from app.models.record import AnswerRecord  # noqa: E402
from app.models.user import User  # noqa: E402

DEFAULT_COMPANIES = [
    "华东一区",
    "华东二区",
    "华北一区",
    "华北二区",
    "华南一区",
    "华南二区",
    "华中一区",
    "西南一区",
    "西北一区",
    "东北一区",
]

DEFAULT_PROVINCES = [
    "上海",
    "江苏",
    "浙江",
    "北京",
    "广东",
    "四川",
    "湖北",
    "陕西",
    "辽宁",
    "山东",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare load-test users for Locust and export a reusable token pool."
    )
    parser.add_argument("--count", type=int, default=500, help="Number of synthetic users to prepare.")
    parser.add_argument(
        "--prefix",
        default="locust500",
        help="OpenID prefix used to identify load-test users.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT_DIR / "loadtests" / "data" / "loadtest_users.json"),
        help="JSON output file for user tokens.",
    )
    parser.add_argument(
        "--company-mode",
        choices=["distributed", "same"],
        default="distributed",
        help="Whether users are spread across multiple companies or all share one company.",
    )
    parser.add_argument(
        "--company-name",
        default="压测分销商",
        help="Company name used when --company-mode=same.",
    )
    parser.add_argument(
        "--province-name",
        default="上海",
        help="Province used when --company-mode=same.",
    )
    parser.add_argument(
        "--keep-user-data",
        action="store_true",
        help="Do not clear answer records or counters for load-test users.",
    )
    return parser.parse_args()


def build_profile(index: int, prefix: str, company_mode: str, company_name: str, province_name: str) -> dict:
    if company_mode == "same":
        company = company_name
        province = province_name
    else:
        company = DEFAULT_COMPANIES[(index - 1) % len(DEFAULT_COMPANIES)]
        province = DEFAULT_PROVINCES[(index - 1) % len(DEFAULT_PROVINCES)]

    return {
        "openid": f"{prefix}-openid-{index:04d}",
        "nickname": f"压测用户{index:03d}",
        "real_name": f"压测{index:03d}",
        "phone": f"155{index:08d}",
        "company": company,
        "province": province,
    }


async def ensure_questions(session) -> int:
    stmt = select(func.count(Question.id)).where(
        Question.is_active.is_(True),
        Question.question_type != "short_answer",
    )
    result = await session.execute(stmt)
    question_count = result.scalar_one()
    if question_count < 10:
        raise RuntimeError("题库中可用于每周答题的激活题目少于 10 道，无法进行真实 weekly 接口压测。")
    return question_count


async def prepare_users(args: argparse.Namespace) -> None:
    if args.count <= 0:
        raise RuntimeError("--count 必须大于 0")

    database_url = settings.DATABASE_URL if settings.DB_TYPE == "mysql" else settings.DATABASE_URL
    if not database_url:
        raise RuntimeError("未找到 DATABASE_URL，请先在 .env 中配置测试 MySQL。")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    profiles = [
        build_profile(
            index=index,
            prefix=args.prefix,
            company_mode=args.company_mode,
            company_name=args.company_name,
            province_name=args.province_name,
        )
        for index in range(1, args.count + 1)
    ]
    openids = [profile["openid"] for profile in profiles]

    async with session_factory() as session:
        available_questions = await ensure_questions(session)

        existing_result = await session.execute(select(User).where(User.openid.in_(openids)))
        existing_users = {user.openid: user for user in existing_result.scalars().all()}

        users: list[User] = []
        created_count = 0
        reused_count = 0

        for profile in profiles:
            user = existing_users.get(profile["openid"])
            if user is None:
                user = User(
                    openid=profile["openid"],
                    nickname=profile["nickname"],
                    phone=profile["phone"],
                    real_name=profile["real_name"],
                    province=profile["province"],
                    company=profile["company"],
                    total_score=0,
                    correct_count=0,
                    total_count=0,
                )
                session.add(user)
                created_count += 1
            else:
                user.nickname = profile["nickname"]
                user.phone = profile["phone"]
                user.real_name = profile["real_name"]
                user.province = profile["province"]
                user.company = profile["company"]
                reused_count += 1
            users.append(user)

        await session.flush()
        user_ids = [user.id for user in users]

        if not args.keep_user_data and user_ids:
            await session.execute(delete(AnswerRecord).where(AnswerRecord.user_id.in_(user_ids)))
            await session.execute(
                update(User)
                .where(User.id.in_(user_ids))
                .values(
                    total_score=0,
                    correct_count=0,
                    total_count=0,
                    last_study_at=None,
                )
            )

        await session.commit()

    export_items = [
        {
            "user_id": user.id,
            "token": create_access_token(user.id),
            "nickname": user.nickname,
            "real_name": user.real_name,
            "company": user.company,
            "province": user.province,
            "openid": user.openid,
        }
        for user in users
    ]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "count": len(export_items),
                "secret_key_note": "Target backend must use the same SECRET_KEY, otherwise all load-test tokens return 401.",
                "users": export_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    await engine.dispose()

    print(f"Prepared {len(export_items)} load-test users.")
    print(f"Created: {created_count}, reused: {reused_count}")
    print(f"Available daily-quiz questions: {available_questions}")
    print(f"Token pool exported to: {output_path}")
    if args.keep_user_data:
        print("Existing answer records were kept.")
    else:
        print("Existing answer records and score counters for load-test users were reset.")
    print("Important: the target backend must use the same SECRET_KEY as this script when verifying Bearer tokens.")


def main() -> None:
    asyncio.run(prepare_users(parse_args()))


if __name__ == "__main__":
    main()
