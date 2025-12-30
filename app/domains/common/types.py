from typing import Literal

CandidateSessionStatus = Literal["not_started", "in_progress", "completed", "expired"]
TaskType = Literal["design", "code", "debug", "handoff", "documentation"]
