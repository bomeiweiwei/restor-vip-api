class TrafficService:

    def search(
        self,
        message: str,
    ) -> str:

        return (
            f"已進入 Traffic API 查詢流程。"
            f"問題：{message}。"
            f"目前尚未串接真實交通 API。"
        )


traffic_service = TrafficService()