from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base


class Workspace(Base):
    """GitHub workspace repository provisioned for a candidate task."""

    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint(
            "candidate_session_id", "task_id", name="uq_workspaces_session_task"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )

    template_repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_template_sha: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    latest_commit_sha: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_workflow_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_workflow_conclusion: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    last_test_summary_json: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # JSON string with counts/output

    candidate_session = relationship("CandidateSession", back_populates="workspaces")
    task = relationship("Task", back_populates="workspaces")
