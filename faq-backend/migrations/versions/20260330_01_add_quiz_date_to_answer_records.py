"""Add quiz_date and uniqueness guard to answer_records.

Revision ID: 20260330_01
Revises:
Create Date: 2026-03-30 11:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260330_01"
down_revision = None
branch_labels = None
depends_on = None

TABLE_NAME = "answer_records"
COLUMN_NAME = "quiz_date"
INDEX_NAME = "ix_answer_records_quiz_date"
UNIQUE_NAME = "uq_user_question_source_date"


def _get_inspector():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = _get_inspector()
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _unique_exists(table_name: str, constraint_name: str) -> bool:
    inspector = _get_inspector()
    return any(
        constraint["name"] == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def _backfill_quiz_date(dialect_name: str) -> None:
    if dialect_name == "mysql":
        op.execute(
            sa.text(
                """
                UPDATE answer_records
                SET quiz_date = CASE
                    WHEN TIME(created_at) >= '09:00:00'
                        THEN DATE_FORMAT(created_at, '%Y-%m-%d')
                    ELSE DATE_FORMAT(DATE_SUB(created_at, INTERVAL 1 DAY), '%Y-%m-%d')
                END
                WHERE source = 'daily' AND quiz_date IS NULL
                """
            )
        )
        return

    if dialect_name == "sqlite":
        op.execute(
            sa.text(
                """
                UPDATE answer_records
                SET quiz_date = CASE
                    WHEN time(created_at) >= '09:00:00'
                        THEN strftime('%Y-%m-%d', created_at)
                    ELSE strftime('%Y-%m-%d', datetime(created_at, '-1 day'))
                END
                WHERE source = 'daily' AND quiz_date IS NULL
                """
            )
        )
        return

    raise RuntimeError(f"Unsupported dialect for quiz_date backfill: {dialect_name}")


def _deduplicate_daily_records() -> set[str]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, user_id, question_id, source, quiz_date, created_at
            FROM answer_records
            WHERE source = 'daily' AND quiz_date IS NOT NULL
            ORDER BY user_id, question_id, source, quiz_date, created_at, id
            """
        )
    ).mappings().all()

    if not rows:
        return set()

    seen_keys: set[tuple[str, int, str, str]] = set()
    delete_ids: list[int] = []
    affected_user_ids: set[str] = set()

    for row in rows:
        key = (
            row["user_id"],
            row["question_id"],
            row["source"],
            row["quiz_date"],
        )
        if key in seen_keys:
            delete_ids.append(row["id"])
            affected_user_ids.add(row["user_id"])
            continue
        seen_keys.add(key)

    if delete_ids:
        bind.execute(
            sa.text("DELETE FROM answer_records WHERE id = :id"),
            [{"id": row_id} for row_id in delete_ids],
        )

    return affected_user_ids


def _recalculate_user_stats(user_ids: set[str]) -> None:
    if not user_ids:
        return

    bind = op.get_bind()

    for user_id in user_ids:
        stats = bind.execute(
            sa.text(
                """
                SELECT
                    COALESCE(SUM(score), 0) AS total_score,
                    COUNT(*) AS total_count,
                    COALESCE(SUM(CASE WHEN is_correct THEN 1 ELSE 0 END), 0) AS correct_count
                FROM answer_records
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        ).mappings().one()

        bind.execute(
            sa.text(
                """
                UPDATE users
                SET total_score = :total_score,
                    total_count = :total_count,
                    correct_count = :correct_count
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "total_score": stats["total_score"],
                "total_count": stats["total_count"],
                "correct_count": stats["correct_count"],
            },
        )


def _ensure_no_duplicate_daily_records() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT user_id, question_id, source, quiz_date, COUNT(*) AS row_count
            FROM answer_records
            WHERE source = 'daily' AND quiz_date IS NOT NULL
            GROUP BY user_id, question_id, source, quiz_date
            HAVING COUNT(*) > 1
            LIMIT 10
            """
        )
    ).fetchall()

    if not rows:
        return

    preview = "; ".join(
        f"user_id={row.user_id}, question_id={row.question_id}, source={row.source}, quiz_date={row.quiz_date}, count={row.row_count}"
        for row in rows
    )
    raise RuntimeError(
        "迁移自动去重后，answer_records 中仍存在重复 daily 记录，无法创建唯一约束。"
        f" 样例: {preview}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.add_column(sa.Column(COLUMN_NAME, sa.String(length=10), nullable=True))

    _backfill_quiz_date(dialect_name)

    if not _index_exists(TABLE_NAME, INDEX_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.create_index(INDEX_NAME, [COLUMN_NAME], unique=False)

    if not _unique_exists(TABLE_NAME, UNIQUE_NAME):
        affected_user_ids = _deduplicate_daily_records()
        _recalculate_user_stats(affected_user_ids)
        _ensure_no_duplicate_daily_records()
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.create_unique_constraint(
                UNIQUE_NAME,
                ["user_id", "question_id", "source", COLUMN_NAME],
            )


def downgrade() -> None:
    if _unique_exists(TABLE_NAME, UNIQUE_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.drop_constraint(UNIQUE_NAME, type_="unique")

    if _index_exists(TABLE_NAME, INDEX_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.drop_index(INDEX_NAME)

    if _column_exists(TABLE_NAME, COLUMN_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch_op:
            batch_op.drop_column(COLUMN_NAME)
