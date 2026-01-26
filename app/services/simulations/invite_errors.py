from __future__ import annotations


class InviteRejectedError(Exception):
    """Raised when an invite cannot be issued because the session is completed."""

    def __init__(
        self,
        *,
        code: str = "candidate_already_completed",
        message: str = "Candidate already completed simulation",
        outcome: str = "rejected",
    ) -> None:
        self.code = code
        self.message = message
        self.outcome = outcome
        super().__init__(message)
