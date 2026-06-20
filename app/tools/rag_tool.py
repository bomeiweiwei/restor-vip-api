from typing import Any

from app.services.rag_search_service import get_rag_search_service


QA_CATEGORY_TO_RAG_CATEGORIES: dict[str, list[str] | None] = {
    "facility_hours": [
        "戶外設施",
        "室內設施",
    ],
    "attraction_hours": [
        "戶外旅遊景點",
        "室內旅遊景點",
        "戶外景點",
        "室內景點",
        "文化園區",
        "日式主題園區",
        "在地文化",
        "動物園",
        "博物館",
        "溫泉公園",
        "觀光園區",
        "觀光農場",
    ],
    "facility_info": [
        "戶外設施",
        "室內設施",
    ],
    "restaurant": [
        "餐飲美食",
    ],
    "attraction": [
        "戶外活動",
        "戶外旅遊景點",
        "戶外設施",
        "戶外景點",
        "文化園區",
        "日式主題園區",
        "在地文化",
        "室內活動",
        "室內旅遊景點",
        "室內設施",
        "室內景點",
        "動物園",
        "基礎介紹",
        "博物館",
        "溫泉公園",
        "觀光園區",
        "觀光農場",
    ],

    "rules": ["基礎介紹"],
    "price": ["基礎介紹"],
    "room_facility": ["基礎介紹"],
    "room_service": ["基礎介紹"]
}


class RagTool:

    def search(
        self,
        query: str,
        qa_category: str,
        k: int = 1,
    ) -> list[dict[str, Any]]:

        categories = QA_CATEGORY_TO_RAG_CATEGORIES.get(
            qa_category,
            None,
        )

        service = get_rag_search_service()

        print(f'=====RAG:{qa_category} query=====')

        return service.search_knowledge_by_categories(
            user_question=query,
            categories=categories,
            k=k,
        )


rag_tool = RagTool()