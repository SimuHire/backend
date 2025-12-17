from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ExecutionProfile(Base):
    """Model for storing execution profiles for candidate sessions."""

    __tablename__ = "execution_profiles"
    __table_args__ = (
        UniqueConstraint(
            "candidate_session_id",
            name="uq_execution_profiles_candidate_session_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    candidate_session = relationship(
        "CandidateSession", back_populates="execution_profile"
    )
