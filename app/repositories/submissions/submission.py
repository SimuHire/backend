from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base import Base


class Submission(Base):
    """Candidate submission for a task."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_session_id",
            "task_id",
            name="uq_submissions_candidate_session_task",
        ),
        Index("ix_submissions_candidate_session_id", "candidate_session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id")
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_text: Mapped[str | None] = mapped_column(Text)
    code_repo_path: Mapped[str | None] = mapped_column(String(500))
    commit_sha: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    diff_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tests_passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    candidate_session = relationship("CandidateSession", back_populates="submissions")
    task = relationship("Task", back_populates="submissions")
