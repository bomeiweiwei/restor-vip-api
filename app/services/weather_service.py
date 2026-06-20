class WeatherService:

    def search(
        self,
        message: str,
    ) -> str:

        return (
            f"已進入 Weather API 查詢流程。"
            f"問題：{message}。"
            f"目前尚未串接真實天氣 API。"
        )


weather_service = WeatherService()