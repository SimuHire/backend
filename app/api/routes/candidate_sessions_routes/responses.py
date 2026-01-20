from datetime import UTC, datetime

from app.domains.candidate_sessions.schemas import (
    CandidateSessionResolveResponse,
    CandidateSimulationSummary,
    CurrentTaskResponse,
    ProgressSummary,
)
from app.domains.tasks.schemas_public import TaskPublic


def render_claim_response(cs) -> CandidateSessionResolveResponse:
    sim = cs.simulation
    return CandidateSessionResolveResponse(
        candidateSessionId=cs.id,
        status=cs.status,
        startedAt=cs.started_at,
        completedAt=cs.completed_at,
        candidateName=cs.candidate_name,
        simulation=CandidateSimulationSummary(id=sim.id, title=sim.title, role=sim.role),
    )


def build_current_task_response(cs, current_task, completed_ids, completed, total, is_complete):
    return CurrentTaskResponse(
        candidateSessionId=cs.id,
        status=cs.status,
        currentDayIndex=None if is_complete else current_task.day_index,
        currentTask=(
            None
            if is_complete
            else TaskPublic(
                id=current_task.id,
                dayIndex=current_task.day_index,
                title=current_task.title,
                type=current_task.type,
                description=current_task.description,
            )
        ),
        completedTaskIds=sorted(completed_ids),
        progress=ProgressSummary(completed=completed, total=total),
        isComplete=is_complete,
    )


def utcnow():
    return datetime.now(UTC)
