# Knowledge Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-synced "知识集" feature that lets users save and later view question explanations as standalone knowledge points.

**Architecture:** Add a dedicated `knowledge_items` table and API that stores explanation snapshots by user and question. Add a mini program knowledge page, a third home entry card, and save buttons in the two existing answer flows. The list API and page intentionally expose only explanation-centered fields, never full question content or answers.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, pytest, WeChat mini program WXML/WXSS/JS.

---

## File Structure

- Create `faq-backend/app/models/knowledge.py`: SQLAlchemy `KnowledgeItem` model.
- Modify `faq-backend/app/models/__init__.py`: import `KnowledgeItem`.
- Modify `faq-backend/app/db/session.py`: include the new model in metadata imports.
- Create `faq-backend/migrations/versions/20260509_01_create_knowledge_items.py`: Alembic migration.
- Create `faq-backend/app/api/v1/knowledge.py`: list, create, and delete API.
- Modify `faq-backend/app/api/v1/router.py`: register the knowledge router.
- Create `faq-backend/tests/test_knowledge_api.py`: backend tests for save/list/delete and field privacy.
- Modify `faq-miniprogram/app.json`: register `pages/knowledge/index`.
- Create `faq-miniprogram/pages/knowledge/index.js`: fetch, render, and delete knowledge items.
- Create `faq-miniprogram/pages/knowledge/index.wxml`: explanation-only list UI.
- Create `faq-miniprogram/pages/knowledge/index.wxss`: page styling.
- Create `faq-miniprogram/pages/knowledge/index.json`: navigation title.
- Modify `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.wxml`: add the third card.
- Modify `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.js`: add navigation method.
- Modify `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.wxss`: fit three cards.
- Modify `faq-miniprogram/pages/quiz/quiz.js`: save knowledge state and request.
- Modify `faq-miniprogram/pages/quiz/quiz.wxml`: add save button near explanation.
- Modify `faq-miniprogram/pages/quiz/quiz.wxss`: style save button.
- Modify `faq-miniprogram/pages/question-list/question-list.js`: save knowledge state and request.
- Modify `faq-miniprogram/pages/question-list/question-list.wxml`: add save button near explanation.
- Modify `faq-miniprogram/pages/question-list/question-list.wxss`: style save button.

## Task 1: Backend Model, Migration, and Router Registration

**Files:**

- Create: `faq-backend/app/models/knowledge.py`
- Modify: `faq-backend/app/models/__init__.py`
- Modify: `faq-backend/app/db/session.py`
- Create: `faq-backend/migrations/versions/20260509_01_create_knowledge_items.py`
- Modify: `faq-backend/app/api/v1/router.py`

- [ ] **Step 1: Create the model file**

Add this focused model:

```python
"""Saved explanation knowledge points."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KnowledgeItem(Base, TimestampMixin):
    """Store a user's saved explanation snapshot."""

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="bank")

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_knowledge_user_question"),
        Index("ix_knowledge_items_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeItem user={self.user_id[:8]} q={self.question_id}>"
```

- [ ] **Step 2: Import the model**

In `faq-backend/app/models/__init__.py`, add:

```python
from app.models.knowledge import KnowledgeItem
```

- [ ] **Step 3: Include the model in session metadata imports**

In `faq-backend/app/db/session.py`, update the model import line inside metadata initialization from:

```python
from app.models import certificate, energy, energy_product, guide, question, record, user  # noqa: F401
```

to:

```python
from app.models import certificate, energy, energy_product, guide, knowledge, question, record, user  # noqa: F401
```

- [ ] **Step 4: Create the migration**

Add `faq-backend/migrations/versions/20260509_01_create_knowledge_items.py`:

```python
"""Create knowledge items table.

Revision ID: 20260509_01
Revises: 20260507_01
Create Date: 2026-05-09 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_01"
down_revision = "20260507_01"
branch_labels = None
depends_on = None

TABLE_NAME = "knowledge_items"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="bank"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "question_id", name="uq_knowledge_user_question"),
    )
    op.create_index("ix_knowledge_items_user_id", TABLE_NAME, ["user_id"], unique=False)
    op.create_index("ix_knowledge_items_question_id", TABLE_NAME, ["question_id"], unique=False)
    op.create_index("ix_knowledge_items_user_created", TABLE_NAME, ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    op.drop_index("ix_knowledge_items_user_created", table_name=TABLE_NAME)
    op.drop_index("ix_knowledge_items_question_id", table_name=TABLE_NAME)
    op.drop_index("ix_knowledge_items_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
```

- [ ] **Step 5: Register the router import**

In `faq-backend/app/api/v1/router.py`, update the import list to include `knowledge`:

```python
from app.api.v1 import admin, auth, certificates, chat, daily, distributor_data, energy, guides, knowledge, leaderboard, questions, upload, users
```

Then add:

```python
router.include_router(knowledge.router)
```

after `guides` or near the question routes.

- [ ] **Step 6: Run migration status check**

Run:

```powershell
cd faq-backend
..\venv\Scripts\python.exe -m alembic -c alembic.ini current
```

Expected: command completes and shows the current revision. If the local venv path differs, use the existing project venv path that other backend commands use.

## Task 2: Backend Knowledge API and Tests

**Files:**

- Create: `faq-backend/app/api/v1/knowledge.py`
- Create: `faq-backend/tests/test_knowledge_api.py`

- [ ] **Step 1: Write API tests**

Create `faq-backend/tests/test_knowledge_api.py`:

```python
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem
from app.models.question import Question
from app.models.user import User


async def create_user(db: AsyncSession, user_id: str = "knowledge-user") -> User:
    user = User(id=user_id, openid=f"openid-{user_id}", nickname="Knowledge User")
    db.add(user)
    await db.flush()
    return user


async def create_question(db: AsyncSession, explanation: str = "这是一个可收藏的解析知识点。") -> Question:
    question = Question(
        question_type="single_choice",
        content="题干不应出现在知识集响应里",
        options=["A", "B"],
        answer="A",
        explanation=explanation,
        difficulty=1,
        category="测试分类",
        is_active=True,
    )
    db.add(question)
    await db.flush()
    return question


@pytest.mark.asyncio
async def test_create_knowledge_item_saves_explanation_only(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session)
    question = await create_question(db_session)
    await db_session.commit()

    response = await async_client.post(
        "/api/knowledge",
        json={"user_id": user.id, "question_id": question.id, "source": "bank"},
        headers={"X-User-Id": user.id},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["explanation"] == "这是一个可收藏的解析知识点。"
    assert body["source"] == "bank"
    assert body["already_saved"] is False
    assert "content" not in body
    assert "answer" not in body
    assert "options" not in body


@pytest.mark.asyncio
async def test_create_knowledge_item_is_idempotent(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, "knowledge-user-2")
    question = await create_question(db_session, "重复收藏只保存一条。")
    await db_session.commit()

    payload = {"user_id": user.id, "question_id": question.id, "source": "daily"}
    first = await async_client.post("/api/knowledge", json=payload, headers={"X-User-Id": user.id})
    second = await async_client.post("/api/knowledge", json=payload, headers={"X-User-Id": user.id})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["already_saved"] is False
    assert second.json()["data"]["already_saved"] is True

    result = await db_session.execute(select(KnowledgeItem))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_list_knowledge_items_returns_explanations_only(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, "knowledge-user-3")
    question = await create_question(db_session, "列表里只有解析。")
    db_session.add(
        KnowledgeItem(
            user_id=user.id,
            question_id=question.id,
            explanation=question.explanation,
            source="bank",
        )
    )
    await db_session.commit()

    response = await async_client.get("/api/knowledge", headers={"X-User-Id": user.id})

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["explanation"] == "列表里只有解析。"
    assert "question_id" not in items[0]
    assert "content" not in items[0]
    assert "answer" not in items[0]
    assert "options" not in items[0]


@pytest.mark.asyncio
async def test_delete_knowledge_item_enforces_ownership(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    owner = await create_user(db_session, "knowledge-owner")
    other = await create_user(db_session, "knowledge-other")
    question = await create_question(db_session, "只能删除自己的知识点。")
    item = KnowledgeItem(
        user_id=owner.id,
        question_id=question.id,
        explanation=question.explanation,
        source="bank",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    forbidden = await async_client.delete(f"/api/knowledge/{item.id}", headers={"X-User-Id": other.id})
    allowed = await async_client.delete(f"/api/knowledge/{item.id}", headers={"X-User-Id": owner.id})

    assert forbidden.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["data"]["deleted"] is True
```

- [ ] **Step 2: Run tests to verify they fail before implementation**

Run:

```powershell
cd faq-backend
..\venv\Scripts\python.exe -m pytest tests/test_knowledge_api.py -q
```

Expected: FAIL because `app.models.knowledge` or `/api/knowledge` does not exist.

- [ ] **Step 3: Implement the router**

Create `faq-backend/app/api/v1/knowledge.py`:

```python
"""Knowledge set APIs for saved explanation snapshots."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_same_user, get_current_user_id
from app.db.session import get_db
from app.models.knowledge import KnowledgeItem
from app.models.question import Question

router = APIRouter(prefix="/knowledge", tags=["知识集"])

ALLOWED_SOURCES = {"daily", "bank", "practice"}


class KnowledgeCreate(BaseModel):
    user_id: str
    question_id: int
    source: str = Field(default="bank", max_length=20)


def serialize_item(item: KnowledgeItem, already_saved: bool | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "id": item.id,
        "explanation": item.explanation,
        "source": item.source,
        "created_at": item.created_at.isoformat() if isinstance(item.created_at, datetime) else None,
    }
    if already_saved is not None:
        data["already_saved"] = already_saved
    return data


@router.get("")
async def list_knowledge_items(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    stmt = (
        select(KnowledgeItem)
        .where(KnowledgeItem.user_id == current_user_id)
        .order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.id.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 0,
        "data": {
            "items": [serialize_item(item) for item in items],
        },
    }


@router.post("")
async def create_knowledge_item(
    body: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user_id = ensure_same_user(current_user_id, body.user_id)
    source = body.source if body.source in ALLOWED_SOURCES else "bank"

    existing_stmt = select(KnowledgeItem).where(
        KnowledgeItem.user_id == user_id,
        KnowledgeItem.question_id == body.question_id,
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {"code": 0, "data": serialize_item(existing, already_saved=True)}

    question_stmt = select(Question).where(Question.id == body.question_id)
    question_result = await db.execute(question_stmt)
    question = question_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    explanation = (question.explanation or "").strip()
    if not explanation:
        raise HTTPException(status_code=400, detail="该题暂无解析，无法加入知识集")

    item = KnowledgeItem(
        user_id=user_id,
        question_id=question.id,
        explanation=explanation,
        source=source,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()
        if existing:
            return {"code": 0, "data": serialize_item(existing, already_saved=True)}
        raise

    await db.refresh(item)
    return {"code": 0, "data": serialize_item(item, already_saved=False)}


@router.delete("/{item_id}")
async def delete_knowledge_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.id == item_id,
        KnowledgeItem.user_id == current_user_id,
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="知识点不存在")

    await db.delete(item)
    await db.flush()
    return {"code": 0, "data": {"deleted": True}}
```

- [ ] **Step 4: Run backend tests**

Run:

```powershell
cd faq-backend
..\venv\Scripts\python.exe -m pytest tests/test_knowledge_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Run related backend regression tests**

Run:

```powershell
cd faq-backend
..\venv\Scripts\python.exe -m pytest tests/test_daily.py tests/test_db_session.py tests/test_user_profile_api.py -q
```

Expected: PASS.

## Task 3: Mini Program Knowledge Page

**Files:**

- Modify: `faq-miniprogram/app.json`
- Create: `faq-miniprogram/pages/knowledge/index.js`
- Create: `faq-miniprogram/pages/knowledge/index.wxml`
- Create: `faq-miniprogram/pages/knowledge/index.wxss`
- Create: `faq-miniprogram/pages/knowledge/index.json`

- [ ] **Step 1: Register the page**

In `faq-miniprogram/app.json`, add this page after `pages/question-detail/question-detail`:

```json
"pages/knowledge/index",
```

- [ ] **Step 2: Add page config**

Create `faq-miniprogram/pages/knowledge/index.json`:

```json
{
  "navigationBarTitleText": "知识集",
  "navigationBarBackgroundColor": "#00B050",
  "navigationBarTextStyle": "white"
}
```

- [ ] **Step 3: Add page logic**

Create `faq-miniprogram/pages/knowledge/index.js`:

```javascript
const app = getApp();

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hour}:${minute}`;
}

Page({
  data: {
    loading: true,
    items: []
  },

  onLoad() {
    if (!app.requireLogin()) return;
    this.loadKnowledgeItems();
  },

  onShow() {
    if (!app.globalData.userId) return;
    this.loadKnowledgeItems();
  },

  async loadKnowledgeItems() {
    this.setData({ loading: true });

    try {
      const res = await app.request({
        url: '/api/knowledge'
      });
      const data = res.data || res;
      const items = (data.items || []).map((item) => ({
        ...item,
        createdAtText: formatTime(item.created_at)
      }));

      this.setData({ items, loading: false });
    } catch (err) {
      console.error('Knowledge load error:', err);
      this.setData({ loading: false, items: [] });
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  deleteKnowledgeItem(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;

    wx.showModal({
      title: '删除知识点',
      content: '确认从知识集中删除这条解析吗？',
      confirmColor: '#00B050',
      success: async (modalRes) => {
        if (!modalRes.confirm) return;
        try {
          await app.request({
            url: `/api/knowledge/${id}`,
            method: 'DELETE'
          });
          this.setData({
            items: this.data.items.filter((item) => item.id !== id)
          });
          wx.showToast({ title: '已删除', icon: 'success' });
        } catch (err) {
          console.error('Knowledge delete error:', err);
          wx.showToast({ title: '删除失败', icon: 'none' });
        }
      }
    });
  }
});
```

- [ ] **Step 4: Add page markup**

Create `faq-miniprogram/pages/knowledge/index.wxml`:

```xml
<view class="knowledge-page">
  <view wx:if="{{loading}}" class="loading-wrap">
    <text>加载中...</text>
  </view>

  <view wx:elif="{{!items.length}}" class="empty-card">
    <text class="empty-title">还没有知识点</text>
    <text class="empty-copy">答题后可以把解析加入知识集。</text>
  </view>

  <view wx:else class="knowledge-list">
    <view class="knowledge-card" wx:for="{{items}}" wx:key="id">
      <text class="knowledge-text">{{item.explanation}}</text>
      <view class="knowledge-footer">
        <text class="knowledge-time">{{item.createdAtText}}</text>
        <text class="knowledge-delete" data-id="{{item.id}}" bindtap="deleteKnowledgeItem">删除</text>
      </view>
    </view>
  </view>
</view>
```

- [ ] **Step 5: Add page styles**

Create `faq-miniprogram/pages/knowledge/index.wxss`:

```css
.knowledge-page {
  min-height: 100vh;
  padding: 32rpx;
  box-sizing: border-box;
  background: #f5f7fa;
}

.loading-wrap,
.empty-card,
.knowledge-card {
  border-radius: 32rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 24rpx rgba(15, 23, 42, 0.06);
}

.loading-wrap {
  padding: 48rpx 32rpx;
  text-align: center;
  color: #64748b;
  font-size: 26rpx;
}

.empty-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 72rpx 32rpx;
}

.empty-title {
  color: #0f172a;
  font-size: 32rpx;
  font-weight: 700;
  line-height: 40rpx;
}

.empty-copy {
  margin-top: 16rpx;
  color: #64748b;
  font-size: 25rpx;
  line-height: 36rpx;
  text-align: center;
}

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 24rpx;
}

.knowledge-card {
  padding: 30rpx;
}

.knowledge-text {
  display: block;
  color: #1f2937;
  font-size: 28rpx;
  line-height: 44rpx;
  white-space: pre-wrap;
}

.knowledge-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 24rpx;
  padding-top: 20rpx;
  border-top: 1rpx solid #edf2f7;
}

.knowledge-time {
  color: #94a3b8;
  font-size: 22rpx;
  line-height: 28rpx;
}

.knowledge-delete {
  color: #ef4444;
  font-size: 24rpx;
  line-height: 30rpx;
}
```

## Task 4: Home Third Entry

**Files:**

- Modify: `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.wxml`
- Modify: `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.js`
- Modify: `faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.wxss`

- [ ] **Step 1: Add navigation method**

In the page methods near `goToQuestionBank`, add:

```javascript
goToKnowledge() {
  if (!app.requireLogin()) return;
  wx.navigateTo({ url: '/pages/knowledge/index' });
},
```

- [ ] **Step 2: Add third feature card**

In the `equal-division` block, add this third card after the question bank card:

```xml
<view class="ml-16 flex-col items-center section_6 equal-division-item feature-card" bindtap="goToKnowledge">
  <view class="feature-icon-wrap feature-icon-knowledge">
    <text class="feature-icon-text">知</text>
  </view>
  <text class="mt-8 font_3 text_12 feature-title">知识集</text>
  <text class="feature-subtitle">收藏解析知识点</text>
</view>
```

- [ ] **Step 3: Adjust card layout styles**

Update the related styles:

```css
.equal-division {
  margin-top: 46.15rpx;
  gap: 14rpx;
}

.section_6 {
  flex: 1 1 0;
  min-width: 0;
}

.equal-division-item {
  padding: 24rpx 0 22rpx;
  height: 210rpx;
}

.image_5 {
  border-radius: 40rpx;
  width: 64rpx;
  height: 64rpx;
}

.feature-icon-wrap {
  margin-top: 2rpx;
  width: 92rpx;
  height: 92rpx;
  border-radius: 46rpx;
}

.feature-title {
  margin-top: 10rpx;
  font-size: 24rpx;
  line-height: 30rpx;
}

.feature-subtitle {
  margin-top: 8rpx;
  padding: 0 8rpx;
  font-size: 17rpx;
  line-height: 23rpx;
}

.feature-icon-knowledge {
  background: radial-gradient(circle at 30% 30%, #ffffff 0%, #dcfce7 55%, #86efac 100%);
}

.feature-icon-text {
  color: #00b050;
  font-size: 36rpx;
  line-height: 1;
  font-weight: 700;
}
```

If the existing `.ml-16` creates too much spacing with `gap`, remove `ml-16` from the second and third card classes and rely on `gap`.

## Task 5: Weekly Quiz Save Button

**Files:**

- Modify: `faq-miniprogram/pages/quiz/quiz.js`
- Modify: `faq-miniprogram/pages/quiz/quiz.wxml`
- Modify: `faq-miniprogram/pages/quiz/quiz.wxss`

- [ ] **Step 1: Add save state**

Add these fields to `data`:

```javascript
knowledgeSavedMap: {},
knowledgeSaving: false,
```

- [ ] **Step 2: Reset visible save state per question**

In `showQuestion(index)`, after computing `question`, set:

```javascript
const knowledgeSaved = !!this.data.knowledgeSavedMap[question.id];
```

Then include this field in `setData`:

```javascript
knowledgeSaved,
knowledgeSaving: false,
```

- [ ] **Step 3: Add save method**

Add this method before `nextQuestion()`:

```javascript
async saveCurrentExplanation() {
  const { currentQuestion, currentExplanation, knowledgeSaving, knowledgeSavedMap } = this.data;
  if (!currentQuestion || !currentQuestion.id || !currentExplanation) return;
  if (knowledgeSaving || knowledgeSavedMap[currentQuestion.id]) return;

  this.setData({ knowledgeSaving: true });
  try {
    const res = await app.request({
      url: '/api/knowledge',
      method: 'POST',
      data: {
        user_id: app.globalData.userId,
        question_id: currentQuestion.id,
        source: 'daily'
      }
    });
    const data = res.data || res;
    const nextMap = {
      ...knowledgeSavedMap,
      [currentQuestion.id]: true
    };
    this.setData({
      knowledgeSavedMap: nextMap,
      knowledgeSaved: true,
      knowledgeSaving: false
    });
    wx.showToast({
      title: data.already_saved ? '已在知识集' : '已加入',
      icon: 'success'
    });
  } catch (err) {
    console.error('Save knowledge failed:', err);
    this.setData({ knowledgeSaving: false });
    wx.showToast({ title: '加入失败', icon: 'none' });
  }
},
```

- [ ] **Step 4: Add button markup**

In `quiz.wxml`, inside the `analysis-block` after `analysis-text`, add:

```xml
<button class="knowledge-save-btn {{knowledgeSaved ? 'saved' : ''}}" loading="{{knowledgeSaving}}" disabled="{{knowledgeSaving || knowledgeSaved}}" bindtap="saveCurrentExplanation">
  {{knowledgeSaved ? '已加入' : '加入知识集'}}
</button>
```

- [ ] **Step 5: Add styles**

In `quiz.wxss`, add:

```css
.knowledge-save-btn {
  margin: 22rpx 0 0;
  padding: 0 24rpx;
  height: 64rpx;
  border-radius: 32rpx;
  background: #00b050;
  color: #ffffff;
  font-size: 25rpx;
  line-height: 64rpx;
}

.knowledge-save-btn.saved {
  background: #e2e8f0;
  color: #64748b;
}
```

## Task 6: Question Bank Practice Save Button

**Files:**

- Modify: `faq-miniprogram/pages/question-list/question-list.js`
- Modify: `faq-miniprogram/pages/question-list/question-list.wxml`
- Modify: `faq-miniprogram/pages/question-list/question-list.wxss`

- [ ] **Step 1: Add save state**

Add these fields to `data`:

```javascript
knowledgeSavedMap: {},
knowledgeSaving: false,
knowledgeSaved: false,
```

- [ ] **Step 2: Reset visible save state per question**

In `showQuestion(index)`, after `const question = questions[index];`, add:

```javascript
const knowledgeSaved = !!this.data.knowledgeSavedMap[question.id];
```

Then include this in `setData`:

```javascript
knowledgeSaved,
knowledgeSaving: false,
```

- [ ] **Step 3: Add save method**

Add this method before `nextQuestion()`:

```javascript
async saveCurrentExplanation() {
  const { currentQuestion, currentExplanation, knowledgeSaving, knowledgeSavedMap } = this.data;
  if (!currentQuestion || !currentQuestion.id || !currentExplanation) return;
  if (knowledgeSaving || knowledgeSavedMap[currentQuestion.id]) return;

  this.setData({ knowledgeSaving: true });
  try {
    const res = await app.request({
      url: '/api/knowledge',
      method: 'POST',
      data: {
        user_id: app.globalData.userId,
        question_id: currentQuestion.id,
        source: 'bank'
      }
    });
    const data = res.data || res;
    const nextMap = {
      ...knowledgeSavedMap,
      [currentQuestion.id]: true
    };
    this.setData({
      knowledgeSavedMap: nextMap,
      knowledgeSaved: true,
      knowledgeSaving: false
    });
    wx.showToast({
      title: data.already_saved ? '已在知识集' : '已加入',
      icon: 'success'
    });
  } catch (err) {
    console.error('Save knowledge failed:', err);
    this.setData({ knowledgeSaving: false });
    wx.showToast({ title: '加入失败', icon: 'none' });
  }
},
```

- [ ] **Step 4: Add button markup in both explanation blocks**

In each `analysis-block` that displays `currentExplanation`, add after `analysis-text`:

```xml
<button class="knowledge-save-btn {{knowledgeSaved ? 'saved' : ''}}" loading="{{knowledgeSaving}}" disabled="{{knowledgeSaving || knowledgeSaved}}" bindtap="saveCurrentExplanation">
  {{knowledgeSaved ? '已加入' : '加入知识集'}}
</button>
```

This must be added in the short-answer reference panel and the submitted result section because both can display explanations.

- [ ] **Step 5: Add styles**

In `question-list.wxss`, add:

```css
.knowledge-save-btn {
  margin: 22rpx 0 0;
  padding: 0 24rpx;
  height: 64rpx;
  border-radius: 32rpx;
  background: #00b050;
  color: #ffffff;
  font-size: 25rpx;
  line-height: 64rpx;
}

.knowledge-save-btn.saved {
  background: #e2e8f0;
  color: #64748b;
}
```

## Task 7: Final Verification

**Files:**

- All files changed above.

- [ ] **Step 1: Run backend focused tests**

Run:

```powershell
cd faq-backend
..\venv\Scripts\python.exe -m pytest tests/test_knowledge_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run backend related tests**

Run:

```powershell
cd faq-backend
..\venv\Scripts\python.exe -m pytest tests/test_daily.py tests/test_db_session.py tests/test_user_profile_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Inspect API privacy**

Run:

```powershell
rg -n "\"content\"|\"answer\"|\"options\"|question_id" faq-backend/app/api/v1/knowledge.py faq-miniprogram/pages/knowledge
```

Expected: the knowledge API serializer and knowledge page do not return or render `content`, `answer`, or `options`. `question_id` may appear only in the create request body, not in list item rendering.

- [ ] **Step 4: Inspect changed files**

Run:

```powershell
git diff --stat
git diff -- faq-backend/app/api/v1/knowledge.py faq-miniprogram/pages/knowledge/index.wxml
```

Expected: changes are limited to the knowledge feature and the knowledge page renders only `item.explanation`, time, and delete.

- [ ] **Step 5: Commit implementation**

Run:

```powershell
git add faq-backend/app/models/knowledge.py faq-backend/app/models/__init__.py faq-backend/app/db/session.py faq-backend/migrations/versions/20260509_01_create_knowledge_items.py faq-backend/app/api/v1/knowledge.py faq-backend/app/api/v1/router.py faq-backend/tests/test_knowledge_api.py faq-miniprogram/app.json faq-miniprogram/pages/knowledge/index.js faq-miniprogram/pages/knowledge/index.wxml faq-miniprogram/pages/knowledge/index.wxss faq-miniprogram/pages/knowledge/index.json faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.wxml faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.js faq-miniprogram/pages/shouye_Home_Dashboard_Green/shouye_Home_Dashboard_Green.wxss faq-miniprogram/pages/quiz/quiz.js faq-miniprogram/pages/quiz/quiz.wxml faq-miniprogram/pages/quiz/quiz.wxss faq-miniprogram/pages/question-list/question-list.js faq-miniprogram/pages/question-list/question-list.wxml faq-miniprogram/pages/question-list/question-list.wxss
git commit -m "feat: add knowledge set"
```

Expected: commit succeeds and does not include unrelated pre-existing workspace changes.
