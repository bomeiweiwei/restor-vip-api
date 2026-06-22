from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth_dependency import get_current_user
from app.core.database import get_db
from app.schemas.attraction import AttractionResponse
from app.services.attraction_service import attraction_service

router = APIRouter(
    prefix="/api/attractions",
    tags=["Attractions"],
)


@router.get(
    "/recommended",
    response_model=list[AttractionResponse],
)
def get_recommended_attractions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    return attraction_service.get_recommended_attractions(
        db=db,
        current_user=current_user,
    )