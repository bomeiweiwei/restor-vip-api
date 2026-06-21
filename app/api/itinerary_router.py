from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.services.itinerary_service import itinerary_service
from app.schemas.itinerary import (
    ItineraryDateGroupResponse,
    ItineraryFeedbackRequest,
    ItineraryFeedbackResponse,
)

router = APIRouter(
    prefix="/api/itinerary",
    tags=["Itinerary"],
)


@router.get(
    "/exclusive-itinerary",
    response_model=list[ItineraryDateGroupResponse],
)
def get_exclusive_itinerary(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return itinerary_service.get_exclusive_itinerary(
        db=db,
        current_user=current_user,
    )


@router.post(
    "/feedback",
    response_model=ItineraryFeedbackResponse,
)
def submit_feedback(
    request: ItineraryFeedbackRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return itinerary_service.submit_feedback(
        db=db,                        # 1. 將 db 傳給 service
        current_user=current_user,    # 2. 將 current_user 傳給 service
        message=request.message,      # 指定參數名：message=...
        date=request.date             # 指定參數名：date=...
    )