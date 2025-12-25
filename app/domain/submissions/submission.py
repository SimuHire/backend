from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id")
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_text: Mapped[str | None] = mapped_column(Text)
    code_repo_path: Mapped[str | None] = mapped_column(String(500))
    code_blob: Mapped[str | None] = mapped_column(Text)

    tests_passed: Mapped[int | None] = mapped_column(Integer)
    tests_failed: Mapped[int | None] = mapped_column(Integer)
    test_output: Mapped[str | None] = mapped_column(Text)

    candidate_session = relationship("CandidateSession", back_populates="submissions")
    task = relationship("Task", back_populates="submissions")
