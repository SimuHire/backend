from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base


class CandidateSession(Base):
    """Candidate session record for invited candidates."""

    __tablename__ = "candidate_sessions"
    __table_args__ = (
        UniqueConstraint(
            "simulation_id",
            "invite_email",
            name="uq_candidate_session_simulation_invite_email",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(
        ForeignKey("simulations.id"), nullable=False
    )

    candidate_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    invite_email: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_auth0_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_auth0_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    token: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
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

    invite_email_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    invite_email_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invite_email_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invite_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    simulation = relationship("Simulation", back_populates="candidate_sessions")
    candidate_user = relationship("User", back_populates="candidate_sessions")
    submissions = relationship(
        "Submission",
        back_populates="candidate_session",
        cascade="all, delete-orphan",
    )

    fit_profile = relationship(
        "FitProfile",
        back_populates="candidate_session",
        uselist=False,
        cascade="all, delete-orphan",
    )

    workspaces = relationship(
        "Workspace",
        back_populates="candidate_session",
        cascade="all, delete-orphan",
    )
