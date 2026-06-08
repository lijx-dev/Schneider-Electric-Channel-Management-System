"""File upload endpoints."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_rate_limit, get_current_user_id
from app.db.session import get_db
from app.models.user import User
from app.services.storage import StorageService

router = APIRouter(tags=["上传"])

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024


@router.post("/upload/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    display_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Upload a user avatar and return the relative URL."""
    enforce_rate_limit("upload_avatar", current_user_id, limit=10, window_seconds=300)

    extension = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 jpg、jpeg、png、webp 图片")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="非法文件类型")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件不能为空")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="图片不能超过 5MB")

    resolved_display_name = (display_name or "").strip()
    resolved_phone = ""
    if not resolved_display_name:
        stmt = select(User.real_name, User.nickname, User.phone).where(User.id == current_user_id)
        result = await db.execute(stmt)
        user_row = result.one_or_none()
        if user_row:
            resolved_display_name = (user_row.real_name or user_row.nickname or "").strip()
            resolved_phone = (user_row.phone or "").strip()
    else:
        stmt = select(User.phone).where(User.id == current_user_id)
        result = await db.execute(stmt)
        user_row = result.one_or_none()
        if user_row:
            resolved_phone = (user_row.phone or "").strip()

    try:
        avatar_url = StorageService.upload_avatar(
            content=content,
            extension=extension,
            user_id=current_user_id,
            content_type=file.content_type,
            display_name=resolved_display_name,
            phone=resolved_phone,
        )
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=f"上传图片失败: {exc}") from exc

    avatar_reference = StorageService.normalize_avatar_reference(avatar_url)
    public_url = StorageService.build_avatar_access_url(avatar_url, str(request.base_url).rstrip("/"))
    return {
        "code": 0,
        "message": "上传成功",
        "data": {
            "url": public_url,
            "avatar_url": public_url,
            "avatar_file_id": avatar_reference,
            "avatar": avatar_reference,
        },
    }
    return {"code": 0, "message": "上传成功", "url": public_url}


@router.get("/upload/avatar/view")
async def view_avatar(key: str):
    object_key = StorageService.extract_cos_object_key(key)
    if not object_key or not object_key.startswith("avatars/"):
        raise HTTPException(status_code=404, detail="头像不存在")

    try:
        signed_url = StorageService.create_presigned_avatar_url(object_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"头像读取失败: {exc}") from exc

    return RedirectResponse(url=signed_url, status_code=302)
