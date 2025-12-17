from .base import Base  # ensure Base metadata is loaded
from .candidate_session import CandidateSession
from .company import Company
from .execution_profile import ExecutionProfile
from .simulation import Simulation
from .submission import Submission
from .task import Task

# Import all models so SQLAlchemy's registry knows them
from .user import User

__all__ = [
    "Base",
    "User",
    "Company",
    "Simulation",
    "Task",
    "CandidateSession",
    "Submission",
    "ExecutionProfile",
]
