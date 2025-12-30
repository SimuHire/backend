from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User record for recruiters and candidates."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(50))  # recruiter | candidate
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company = relationship("Company", back_populates="users")
    candidate_sessions = relationship(
        "CandidateSession", back_populates="candidate_user"
    )
