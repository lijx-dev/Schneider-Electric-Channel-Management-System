"""
数据库修复脚本：将用户头像链接从绝对路径改为相对路径
解决公网域名变动导致的图片失效问题。
"""
import sys
import os
import asyncio
from sqlalchemy import select

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import AsyncSessionLocal
from app.models.user import User

async def fix_avatar_urls():
    print("🚀 开始修复头像链接...")
    async with AsyncSessionLocal() as session:
        # 查询所有有头像的用户
        stmt = select(User).where(User.avatar_url.isnot(None))
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        count = 0
        for user in users:
            old_url = user.avatar_url
            if not old_url or not isinstance(old_url, str):
                continue
                
            # 如果是绝对路径 (包含 http)
            if old_url.startswith("http"):
                # 提取相对路径部分 /static/avatars/...
                if "/static/avatars/" in old_url:
                    new_url = "/static/avatars/" + old_url.split("/static/avatars/")[-1]
                    if new_url != old_url:
                        user.avatar_url = new_url
                        count += 1
                        print(f"✅ 修复: {user.nickname} | {old_url} -> {new_url}")
                # 兼容旧版本可能只存了文件名的逻辑（如果有）
                elif "avatar_" in old_url and "." in old_url:
                    filename = old_url.split("/")[-1]
                    user.avatar_url = f"/static/avatars/{filename}"
                    count += 1
                    print(f"✅ 修复文件名: {user.nickname} | {old_url} -> {user.avatar_url}")

        await session.commit()
        print(f"\n✨ 修复完成！共处理 {count} 条记录。")

if __name__ == "__main__":
    asyncio.run(fix_avatar_urls())
