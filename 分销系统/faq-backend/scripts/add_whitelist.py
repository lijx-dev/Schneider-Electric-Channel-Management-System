"""
手动向数据库添加分销商手机号（用于白名单准入）

用法:
    cd faq-backend
    python scripts/add_whitelist.py 13800138000 "测试管理员" "某某公司"
"""
import sys
import os
import asyncio

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def add_to_whitelist(phone, real_name="管理员", company="演示公司"):
    async with AsyncSessionLocal() as session:
        # 检查是否已存在
        stmt = select(User).where(User.phone == phone)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            print(f"ℹ️  手机号 {phone} 已在名单中 (ID: {user.id})")
            user.real_name = real_name
            user.company = company
        else:
            # 创建预导入占位用户
            user = User(
                openid=f"manual_{phone}",
                phone=phone,
                real_name=real_name,
                company=company,
                nickname=real_name,
                province="北京市"
            )
            session.add(user)
            print(f"✅ 已添加 {real_name} ({phone}) 到白名单")
        
        await session.commit()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/add_whitelist.py <手机号> [姓名] [公司]")
        sys.exit(1)
        
    phone = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "管理员"
    company = sys.argv[3] if len(sys.argv) > 3 else "开发测试"
    
    asyncio.run(add_to_whitelist(phone, name, company))
