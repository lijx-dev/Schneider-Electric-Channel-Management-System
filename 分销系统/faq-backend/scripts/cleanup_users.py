"""
数据库清理脚本：删除所有“路人”用户（没有手机号的用户）
这些用户是因为之前的逻辑漏洞，在未验证手机号白名单的情况下自动创建的。
"""
import sys
import os
import asyncio

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import delete, select

async def cleanup_users():
    async with AsyncSessionLocal() as session:
        # 1. 查找没有手机号的用户
        stmt = select(User).where(User.phone == None)
        result = await session.execute(stmt)
        to_delete = result.scalars().all()
        
        count = len(to_delete)
        if count == 0:
            print("✨ 数据库很干净，没有发现未授权的“路人”账号。")
            return

        print(f"🧹 发现 {count} 个未授权账号：")
        for u in to_delete:
            print(f"   - ID: {u.id}, Nickname: {u.nickname}")

        # 2. 执行删除
        delete_stmt = delete(User).where(User.phone == None)
        await session.execute(delete_stmt)
        await session.commit()
        print(f"\n✅ 已成功删除以上 {count} 个无效账号。")

if __name__ == "__main__":
    asyncio.run(cleanup_users())
