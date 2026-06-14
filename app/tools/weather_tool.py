import requests

from app.core.config import settings


class WeatherTool:

    def get_weather(
        self,
        city: str,
    ) -> str:

        api_key = settings.OPEN_WEATHER_MAP_API_KEY

        if not api_key:
            return "OpenWeatherMap API key is not set."

        url = (
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q={city}"
            f"&appid={api_key}"
            "&units=metric"
            "&lang=zh_tw"
        )

        try:
            response = requests.get(
                url,
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            weather_description = data["weather"][0]["description"]
            temperature = data["main"]["temp"]

            print('=====weather api query=====')

            return (
                f"{city} 目前天氣："
                f"{weather_description}，"
                f"氣溫 {temperature}°C。"
            )

        except requests.exceptions.RequestException as e:
            return f"Weather API error: {str(e)}"


weather_tool = WeatherTool()