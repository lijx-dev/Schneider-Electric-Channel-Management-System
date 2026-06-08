from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.models.user import User
from app.services.ranking import fetch_weekly_rank_entries, get_display_name
from app.services.storage import StorageService

router = APIRouter(tags=["排行榜"])


@router.get("/leaderboard")
async def get_leaderboard(
    request: Request,
    limit: int = 20,
    scope: str = Query("total", pattern="^(total|company)$"),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    base = str(request.base_url).rstrip("/")
    current_company = None

    if scope == "company":
        current_user_result = await db.execute(select(User).where(User.id == current_user_id))
        current_user = current_user_result.scalar_one_or_none()
        current_company = (current_user.company or "").strip() if current_user else ""
        if not current_company:
            return {"code": 0, "data": []}

    entries = (await fetch_weekly_rank_entries(db, company=current_company))[:limit]

    data = []
    previous_rank_key = None
    current_rank = 0

    for index, entry in enumerate(entries, start=1):
        user = entry.user
        rank_key = (entry.weekly_correct_count, entry.weekly_time_spent)
        if previous_rank_key is None or rank_key != previous_rank_key:
            current_rank = index
            previous_rank_key = rank_key

        avatar = StorageService.build_avatar_access_url(user.avatar_url, base)

        data.append(
            {
                "user_id": user.id,
                "nickname": get_display_name(user),
                "real_name": user.real_name or "",
                "company": user.company or "",
                "province": user.province or "",
                "avatar": avatar,
                "total_score": user.total_score or 0,
                "correct_count": user.correct_count or 0,
                "total_count": user.total_count or 0,
                "weekly_correct_count": entry.weekly_correct_count,
                "weekly_time_spent": entry.weekly_time_spent,
                "weekly_total_count": entry.weekly_total_count,
                "rank": current_rank,
            }
        )

    return {"code": 0, "data": data}
