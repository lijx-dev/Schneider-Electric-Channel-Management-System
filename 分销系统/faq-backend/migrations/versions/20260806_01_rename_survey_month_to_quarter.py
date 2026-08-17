"""rename survey_month to survey_quarter

Revision ID: 20260806_01
Revises: 20260805_01
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260806_01'
down_revision = '20260805_01'
branch_labels = None
depends_on = None


def upgrade():
    # 1. 删除旧约束和索引
    op.drop_constraint("uq_survey_rater_target_month", "recognition_surveys", type_="unique")
    op.drop_index("ix_surveys_month_target", table_name="recognition_surveys")

    # 2. 重命名列
    op.alter_column("recognition_surveys", "survey_month", new_column_name="survey_quarter",
                    existing_type=sa.String(7), existing_nullable=False)

    # 3. 创建新约束和索引
    op.create_unique_constraint("uq_survey_rater_target_quarter", "recognition_surveys",
                                ["rater_id", "target_id", "survey_quarter"])
    op.create_index("ix_surveys_quarter_target", "recognition_surveys",
                    ["survey_quarter", "target_id"])


def downgrade():
    # 1. 删除新约束和索引
    op.drop_constraint("uq_survey_rater_target_quarter", "recognition_surveys", type_="unique")
    op.drop_index("ix_surveys_quarter_target", table_name="recognition_surveys")

    # 2. 重命名列回去
    op.alter_column("recognition_surveys", "survey_quarter", new_column_name="survey_month",
                    existing_type=sa.String(7), existing_nullable=False)

    # 3. 恢复旧约束和索引
    op.create_unique_constraint("uq_survey_rater_target_month", "recognition_surveys",
                                ["rater_id", "target_id", "survey_month"])
    op.create_index("ix_surveys_month_target", "recognition_surveys",
                    ["survey_month", "target_id"])