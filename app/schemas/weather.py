from pydantic import BaseModel


class WeatherQuery(BaseModel):
    city: str