from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(str, enum.Enum):
    """User roles available in the application."""

    RECRUITER = "recruiter"
    CANDIDATE = "candidate"
    ADMIN = "admin"


class SimulationStatus(str, enum.Enum):
    """Lifecycle states for a simulation."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class TaskType(str, enum.Enum):
    """Types of tasks a candidate can receive."""

    DESIGN = "design"
    CODE = "code"
    DEBUG = "debug"
    DOCUMENTATION = "documentation"
    BEHAVIORAL = "behavioral"


class CandidateSessionStatus(str, enum.Enum):
    """Status of a candidate's session."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


class Company(Base):
    """Organization that owns users and simulations."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    users: Mapped[list[User]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    simulations: Mapped[list[Simulation]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class User(Base):
    """System user representing recruiters or candidates."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.RECRUITER
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    company: Mapped[Company | None] = relationship(back_populates="users")
    created_simulations: Mapped[list[Simulation]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Simulation.created_by",
    )
    candidate_sessions: Mapped[list[CandidateSession]] = relationship(
        back_populates="candidate_user",
        foreign_keys="CandidateSession.candidate_user_id",
    )


class Simulation(Base):
    """Simulation assigned to candidates."""

    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    tech_stack: Mapped[str] = mapped_column(String(255), nullable=False)
    seniority: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_template: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    status: Mapped[SimulationStatus] = mapped_column(
        Enum(SimulationStatus, name="simulation_status"),
        nullable=False,
        default=SimulationStatus.ACTIVE,
    )

    company: Mapped[Company] = relationship(back_populates="simulations")
    created_by_user: Mapped[User] = relationship(back_populates="created_simulations")
    tasks: Mapped[list[Task]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )
    candidate_sessions: Mapped[list[CandidateSession]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan"
    )


class Task(Base):
    """Individual task within a simulation."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "simulation_id",
            "day_index",
            name="uq_task_simulation_day_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="task_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    starter_code_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    test_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    simulation: Mapped[Simulation] = relationship(back_populates="tasks")
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class CandidateSession(Base):
    """Invitation and state for a candidate taking a simulation."""

    __tablename__ = "candidate_sessions"
    __table_args__ = (UniqueConstraint("token", name="uq_candidate_sessions_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simulation_id: Mapped[int] = mapped_column(
        ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    invite_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[CandidateSessionStatus] = mapped_column(
        Enum(CandidateSessionStatus, name="candidate_session_status"),
        nullable=False,
        default=CandidateSessionStatus.NOT_STARTED,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    simulation: Mapped[Simulation] = relationship(back_populates="candidate_sessions")
    candidate_user: Mapped[User | None] = relationship(
        back_populates="candidate_sessions"
    )
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="candidate_session",
        cascade="all, delete-orphan",
    )


class Submission(Base):
    """Submission for a specific task by a candidate."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_session_id",
            "task_id",
            name="uq_submissions_candidate_task",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_session_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_repo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tests_passed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tests_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate_session: Mapped[CandidateSession] = relationship(
        back_populates="submissions"
    )
    task: Mapped[Task] = mapped_column(
        relationship("Task", back_populates="submissions")
    )
