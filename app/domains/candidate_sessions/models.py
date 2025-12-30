from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base


class CandidateSession(Base):
    """Candidate session record for invited candidates."""

    __tablename__ = "candidate_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(
        ForeignKey("simulations.id"), nullable=False
    )

    candidate_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    invite_email: Mapped[str] = mapped_column(String(255), nullable=False)

    token: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    access_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(String(50), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    simulation = relationship("Simulation", back_populates="candidate_sessions")
    candidate_user = relationship("User", back_populates="candidate_sessions")
    submissions = relationship(
        "Submission",
        back_populates="candidate_session",
        cascade="all, delete-orphan",
    )

    execution_profile = relationship(
        "ExecutionProfile",
        back_populates="candidate_session",
        uselist=False,
        cascade="all, delete-orphan",
    )

    workspaces = relationship(
        "Workspace",
        back_populates="candidate_session",
        cascade="all, delete-orphan",
    )
