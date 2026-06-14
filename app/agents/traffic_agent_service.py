from app.tools.traffic_tool import traffic_tool


class TrafficAgentService:

    def answer(
        self,
        query: str,
    ) -> str:

        return traffic_tool.search(query)


traffic_agent_service = TrafficAgentService()