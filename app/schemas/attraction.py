from pydantic import BaseModel


class AttractionResponse(BaseModel):
    attraction_id: str
    place_name: str
    category: str | None = None
    latitude: float
    longitude: float