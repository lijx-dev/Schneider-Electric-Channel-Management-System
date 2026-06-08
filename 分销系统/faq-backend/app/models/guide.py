"""Product guide tree models for quick navigation and leaf assets."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ProductGuideNode(Base, TimestampMixin):
    """Store the tree structure for product quick-guide navigation."""

    __tablename__ = "product_guide_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("product_guide_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    product_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(20), nullable=False, default="branch")
    layout: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    response_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped[Optional["ProductGuideNode"]] = relationship(
        "ProductGuideNode",
        remote_side="ProductGuideNode.id",
        back_populates="children",
    )
    children: Mapped[List["ProductGuideNode"]] = relationship(
        "ProductGuideNode",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="ProductGuideNode.sort_order",
    )
    assets: Mapped[List["ProductGuideAsset"]] = relationship(
        "ProductGuideAsset",
        back_populates="node",
        cascade="all, delete-orphan",
        order_by="ProductGuideAsset.sort_order",
    )

    __table_args__ = (
        UniqueConstraint("product_key", "node_key", name="uq_product_guide_nodes_product_node_key"),
        CheckConstraint("node_type in ('branch', 'leaf')", name="ck_product_guide_nodes_node_type"),
        CheckConstraint(
            "response_mode in ('text', 'image', 'mixed')",
            name="ck_product_guide_nodes_response_mode",
        ),
        Index(
            "ix_product_guide_nodes_product_parent_sort",
            "product_key",
            "parent_id",
            "sort_order",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProductGuideNode product={self.product_key} key={self.node_key} type={self.node_type}>"


class ProductGuideAsset(Base, TimestampMixin):
    """Store COS-backed assets for leaf nodes, primarily images."""

    __tablename__ = "product_guide_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("product_guide_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, default="image")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cos_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    node: Mapped["ProductGuideNode"] = relationship("ProductGuideNode", back_populates="assets")

    __table_args__ = (
        CheckConstraint(
            "asset_type in ('image', 'pdf', 'link')",
            name="ck_product_guide_assets_asset_type",
        ),
        Index("ix_product_guide_assets_node_sort", "node_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<ProductGuideAsset node={self.node_id} type={self.asset_type}>"
