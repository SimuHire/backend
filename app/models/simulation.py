from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Simulation(Base, TimestampMixin):
    """Simulation configuration assigned to candidates."""

    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(255))
    tech_stack: Mapped[str] = mapped_column(String(255))
    seniority: Mapped[str] = mapped_column(String(100))
    scenario_template: Mapped[str] = mapped_column(String(255))

    focus: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="", default=""
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="active")

    company = relationship("Company", back_populates="simulations")
    tasks = relationship("Task", back_populates="simulation")
    candidate_sessions = relationship("CandidateSession", back_populates="simulation")
