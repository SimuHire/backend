from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CandidateSession(Base):
    """Candidate's invitation and progress for a simulation."""

    __tablename__ = "candidate_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    candidate_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    invite_email: Mapped[str] = mapped_column(String(255))
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    simulation = relationship("Simulation", back_populates="candidate_sessions")
    candidate_user = relationship("User", back_populates="candidate_sessions")
    submissions = relationship("Submission", back_populates="candidate_session")
