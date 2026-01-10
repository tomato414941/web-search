"""
Scoring API Router

Exposes the URL scoring algorithm as an API endpoint.
This allows other services (e.g., Frontend) to predict
URL priority scores without duplicating the scoring logic.
"""

from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from app.domain.scoring import calculate_url_score

router = APIRouter(prefix="/score")


class ScorePredictRequest(BaseModel):
    """Request model for score prediction."""

    url: HttpUrl
    parent_score: float = 100.0
    visits: int = 0


class ScorePredictResponse(BaseModel):
    """Response model for score prediction."""

    url: str
    inputs: dict
    predicted_score: float


@router.post("/predict", response_model=ScorePredictResponse)
async def predict_score(request: ScorePredictRequest):
    """
    Predict the crawler priority score for a URL.

    The score is based on:
    - Parent page score (inheritance)
    - Domain freshness (how often we've visited this domain)
    - URL depth (path hierarchy)
    - Path keywords (catalog pages vs login pages)

    Args:
        request: URL and scoring parameters

    Returns:
        Predicted score and input parameters
    """
    score = calculate_url_score(
        url=str(request.url),
        parent_score=request.parent_score,
        domain_visits=request.visits,
    )

    return ScorePredictResponse(
        url=str(request.url),
        inputs={
            "parent_score": request.parent_score,
            "domain_visits": request.visits,
        },
        predicted_score=round(score, 4),
    )
