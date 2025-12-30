from fastapi import HTTPException, status


class SubmissionConflict(HTTPException):
    """Raised when a submission already exists."""

    def __init__(self, detail: str = "Task already submitted"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class SubmissionOrderError(HTTPException):
    """Raised when tasks are submitted out of order."""

    def __init__(self, detail: str = "Task out of order"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class SimulationComplete(HTTPException):
    """Raised when the simulation is already complete."""

    def __init__(self, detail: str = "Simulation already completed"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class WorkspaceMissing(HTTPException):
    """Raised when workspace is required but not found."""

    def __init__(
        self, detail: str = "Workspace not initialized. Call /codespace/init first."
    ):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
