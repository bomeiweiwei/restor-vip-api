from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.ai.factory import create_ai_langchain
from app.core.config import settings
from app.prompts.weather_prompt import WEATHER_CITY_PROMPT
from app.schemas.weather import WeatherQuery
from app.tools.weather_tool import weather_tool


class WeatherAgentService:

    def __init__(self):
        self.llm = create_ai_langchain(settings.AI_PROVIDER).llm

        self.parser = PydanticOutputParser(
            pydantic_object=WeatherQuery
        )

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    WEATHER_CITY_PROMPT
                    + "\n\n請務必遵守以下輸出格式：\n{format_instructions}",
                ),
                (
                    "human",
                    "使用者天氣查詢：{query}",
                ),
            ]
        )

        self.chain = self.prompt | self.llm | self.parser

    def answer(
        self,
        query: str,
    ) -> str:

        weather_query = self.extract_city(query)

        return weather_tool.get_weather(
            city=weather_query.city,
        )

    def extract_city(
        self,
        query: str,
    ) -> WeatherQuery:

        return self.chain.invoke(
            {
                "query": query,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )


weather_agent_service = WeatherAgentService()