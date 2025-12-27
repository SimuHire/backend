from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base import Base


class Task(Base):
    """Task definition assigned within a simulation."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    day_index: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(50))  # design, code, debug, documentation
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    starter_code_path: Mapped[str | None] = mapped_column(String(500))
    test_file_path: Mapped[str | None] = mapped_column(String(500))
    template_repo: Mapped[str | None] = mapped_column(String(255))
    max_score: Mapped[int | None] = mapped_column(Integer)

    simulation = relationship("Simulation", back_populates="tasks")
    submissions = relationship("Submission", back_populates="task")
    workspaces = relationship("Workspace", back_populates="task")
