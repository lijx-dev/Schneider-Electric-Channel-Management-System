"""认可计划系统 Pydantic 请求/响应 Schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 公共 ─────────────────────────────────────────────────────────────────

class _BaseResponse(BaseModel):
    code: int = 0
    message: str = "success"


# ── 申报 (Submission) ────────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    """提交申报（content_json 结构: {"predefined": {...}, "custom": [...]}）"""
    submission_type: str = Field(..., description="nomination/order_guardian/distributor_pioneer/distributor_mentor/efficiency_innovator")
    content_json: dict[str, Any] = Field(..., description="预定义+自定义内容JSON")
    attachments: Optional[str] = Field(None, description="附件URL列表JSON")
    quarter: Optional[int] = Field(None, description="所属季度 1-4")
    year: Optional[int] = Field(None, description="所属年份")
    submission_month: Optional[str] = Field(None, description="提交月份 yyyy-mm")


class SubmissionUpdate(BaseModel):
    """修改申报（仅草稿状态可修改）"""
    content_json: Optional[dict[str, Any]] = None
    attachments: Optional[str] = None
    quarter: Optional[int] = None
    year: Optional[int] = None
    submission_month: Optional[str] = None


class SubmissionReview(BaseModel):
    """审核申报"""
    action: str = Field(..., description="approve / reject")
    review_comment: Optional[str] = None
    review_score: Optional[int] = Field(None, ge=1, le=5, description="经理评分 1-5")


class SubmissionResponse(BaseModel):
    """申报记录响应"""
    id: int
    applicant_id: str
    applicant_name: Optional[str] = None
    submission_type: str
    content_json: Any
    attachments: Optional[str] = None
    status: str
    reviewed_by: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None
    review_score: Optional[int] = None
    quarter: Optional[int] = None
    year: Optional[int] = None
    submission_month: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NominationStatsResponse(BaseModel):
    """当月提名统计"""
    month: str
    nominations: list[dict[str, Any]]  # [{nominee_id, nominee_name, count}]


# ── 表单配置 (Form Config) ───────────────────────────────────────────────

class ScoringCriteriaItem(BaseModel):
    """单个评分标准项（表单预定义选项）"""
    id: int
    item_name: str
    item_key: str
    item_type: str
    item_placeholder: Optional[str] = None
    item_help_text: Optional[str] = None
    allow_multiple: bool = True
    sort_order: int = 0


class FormConfigResponse(BaseModel):
    """申报表单配置（动态加载评分标准）"""
    submission_type: str
    award_name: str
    description: str
    items: list[ScoringCriteriaItem]


# ── 销售评分 (Survey) ───────────────────────────────────────────────────

class SurveyCreate(BaseModel):
    """提交满意度评分"""
    target_id: str = Field(..., description="被评分专员ID")
    survey_month: str = Field(..., description="评分月份 yyyy-mm")
    score_efficiency: Optional[int] = Field(None, ge=0, le=5, description="报备处理效率 0-5（0=N/A）")
    score_response: Optional[int] = Field(None, ge=0, le=5, description="分销商诉求响应 0-5（0=N/A）")
    score_training: Optional[int] = Field(None, ge=0, le=5, description="赋能培训支持 0-5（0=N/A）")
    score_communication: Optional[int] = Field(None, ge=0, le=5, description="沟通对接顺畅度 0-5（0=N/A）")


class SurveyStatusResponse(BaseModel):
    """本月评分状态 + 对接专员列表"""
    survey_month: str
    submitted: bool
    specialists: list[dict[str, Any]]  # [{specialist_id, specialist_name, scores(if submitted)}]


class SurveyResultResponse(BaseModel):
    """评分汇总（专员端匿名）"""
    survey_month: str
    target_id: str
    target_name: str
    avg_scores: dict[str, Optional[float]]  # {efficiency, response, training, communication}
    median_score: Optional[float]  # 中位数总分
    rater_count: int


class SurveyDetailResponse(BaseModel):
    """评分明细（经理端含提交人）"""
    survey_month: str
    rater_id: str
    rater_name: str
    target_id: str
    target_name: str
    scores: dict[str, Optional[int]]
    submitted_at: datetime


class SurveyProgressResponse(BaseModel):
    """评分进度"""
    survey_month: str
    total_sales: int
    submitted_count: int
    unsubmitted_sales: list[dict[str, Any]]


# ── 积分 (Points) ───────────────────────────────────────────────────────

class PointsStatusResponse(BaseModel):
    """我的积分和等级"""
    user_id: str
    total_score: int
    level: str
    level_icon: str
    next_level: Optional[str] = None
    points_to_next: Optional[int] = None


class PointsTransactionResponse(BaseModel):
    """积分明细"""
    id: int
    point_change: int
    reason: str
    award_type: Optional[str] = None
    related_month: Optional[str] = None
    related_quarter: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PointsAdjustRequest(BaseModel):
    """手动调整积分"""
    user_id: str = Field(..., description="用户ID")
    point_change: int = Field(..., description="积分变动（正数增加，负数减少）")
    reason: str = Field(..., description="调整原因")


class RankingEntry(BaseModel):
    """积分排行条目"""
    rank: int
    user_id: str
    user_name: str
    total_score: int
    level: str
    level_icon: str


# ── 获奖 (Award) ────────────────────────────────────────────────────────

class AwardResultResponse(BaseModel):
    """获奖记录"""
    id: int
    user_id: str
    user_name: str
    award_type: str
    award_name: str
    rank: Optional[int] = None
    score: Optional[float] = None
    points_awarded: int
    award_month: Optional[str] = None
    award_quarter: Optional[str] = None
    award_year: int
    certificate_url: Optional[str] = None
    published: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class RankingPageResponse(BaseModel):
    """认可排行页面完整数据"""
    year: int
    month: str
    points_ranking: list[RankingEntry]
    monthly_stars: Optional[list[AwardResultResponse]] = None  # 微光之星
    monthly_mvp: Optional[list[AwardResultResponse]] = None  # 销圈人气王
    quarterly_awards: Optional[list[AwardResultResponse]] = None  # 季度奖项（仅3/6/9/12月）
    annual_awards: Optional[list[AwardResultResponse]] = None  # 年度奖项


# ── 评选发布 (Calculate & Publish) ──────────────────────────────────────

class CalculateRequest(BaseModel):
    """触发评选计算"""
    month: Optional[str] = Field(None, description="月度 yyyy-mm")
    quarter: Optional[int] = Field(None, description="季度 1-4")
    year: Optional[int] = Field(None, description="年份")


class PublishRequest(BaseModel):
    """发布评选结果"""
    award_ids: list[int] = Field(..., description="要发布的获奖记录ID列表")


# ── 规则配置 (Rules) ────────────────────────────────────────────────────

class RuleConfigResponse(BaseModel):
    """规则配置"""
    id: int
    rule_key: str
    rule_value: str
    description: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class RuleConfigUpdate(BaseModel):
    """修改规则配置"""
    rule_value: str = Field(..., description="规则值")
    description: Optional[str] = None


# ── 评分标准 (Scoring Criteria) ─────────────────────────────────────────

class ScoringCriteriaFullResponse(BaseModel):
    """评分标准完整信息"""
    id: int
    award_type: str
    item_name: str
    item_key: str
    item_type: str
    item_placeholder: Optional[str] = None
    item_help_text: Optional[str] = None
    allow_multiple: bool = True
    points_per_unit: int
    unit_description: Optional[str] = None
    max_points: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScoringCriteriaCreate(BaseModel):
    """新增评分标准项"""
    award_type: str
    item_name: str
    item_key: str
    item_type: str = "text_list"
    item_placeholder: Optional[str] = None
    item_help_text: Optional[str] = None
    allow_multiple: bool = True
    points_per_unit: int
    unit_description: Optional[str] = None
    max_points: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True


class ScoringCriteriaUpdate(BaseModel):
    """修改评分标准项"""
    item_name: Optional[str] = None
    item_key: Optional[str] = None
    item_type: Optional[str] = None
    item_placeholder: Optional[str] = None
    item_help_text: Optional[str] = None
    allow_multiple: Optional[bool] = None
    points_per_unit: Optional[int] = None
    unit_description: Optional[str] = None
    max_points: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── 用户管理 (User Management) ──────────────────────────────────────────

class RecognitionUserResponse(BaseModel):
    """认可计划用户"""
    id: str
    real_name: Optional[str] = None
    company: Optional[str] = None
    recognition_role: str
    recognition_score: int

    class Config:
        from_attributes = True


class RoleUpdateRequest(BaseModel):
    """修改用户角色"""
    recognition_role: str = Field(..., description="distributor/sales/specialist/manager")


# ── 年度快照 (Annual Snapshot) ──────────────────────────────────────────

class AnnualSnapshotResponse(BaseModel):
    """年度快照"""
    id: int
    user_id: str
    user_name: str
    year: int
    final_score: int
    final_rank: str
    total_awards: int
    created_at: datetime

    class Config:
        from_attributes = True