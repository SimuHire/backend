from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse

from app.domains.candidate_sessions.schemas import (
    CandidateInviteErrorResponse,
    CandidateInviteResponse,
)


def render_invite_response(
    candidate_session, invite_url: str, outcome: str
) -> CandidateInviteResponse:
    return CandidateInviteResponse(
        candidateSessionId=candidate_session.id,
        token=candidate_session.token,
        inviteUrl=invite_url,
        outcome=outcome,
    )


def render_invite_error(exc) -> CandidateInviteErrorResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {"code": exc.code, "message": exc.message, "outcome": exc.outcome}
        },
    )


def render_invite_status(candidate_session) -> dict:
    return {
        "inviteEmailStatus": getattr(candidate_session, "invite_email_status", None),
        "inviteEmailSentAt": getattr(candidate_session, "invite_email_sent_at", None),
        "inviteEmailError": getattr(candidate_session, "invite_email_error", None),
    }
