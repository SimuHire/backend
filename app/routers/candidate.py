from fastapi import APIRouter

router = APIRouter()


@router.get("/session")
async def get_candidate_session():
    """Placeholder endpoint for retrieving a candidate session."""
    return {"message": "candidate session placeholder"}
