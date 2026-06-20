class TrafficTool:

    def search(
        self,
        query: str,
    ) -> str:
        
        print('=====traffic api query=====')
        
        return (
            "[Traffic Tool]\n"
            f"查詢：{query}\n"
            "目前尚未串接真實交通 API。"
        )


traffic_tool = TrafficTool()