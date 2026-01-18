from fastapi import status

from app.infra.errors import ApiError


class SubmissionConflict(ApiError):
    """Raised when a submission already exists."""

    def __init__(self, detail: str = "Task already submitted"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="SUBMISSION_CONFLICT",
            retryable=False,
        )


class SubmissionOrderError(ApiError):
    """Raised when tasks are submitted out of order."""

    def __init__(self, detail: str = "Task out of order"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="TASK_OUT_OF_ORDER",
            retryable=False,
        )


class SimulationComplete(ApiError):
    """Raised when the simulation is already complete."""

    def __init__(self, detail: str = "Simulation already completed"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="SIMULATION_COMPLETED",
            retryable=False,
        )


class WorkspaceMissing(ApiError):
    """Raised when workspace is required but not found."""

    def __init__(
        self,
        detail: str = "Workspace not initialized. Call /codespace/init first.",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        super().__init__(
            status_code=status_code,
            detail=detail,
            error_code="WORKSPACE_NOT_INITIALIZED",
            retryable=True,
        )
