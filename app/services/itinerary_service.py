from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

from langchain_qdrant import QdrantVectorStore
from app.ai.embedding_factory import get_embedding_function

from app.schemas.itinerary import (
    ItineraryDateGroupResponse,
    ItineraryScheduleResponse,
)

import os
import json
import uuid
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# 🛠️ 載入 Google GenAI 統一 SDK 與憑證設定
# ==========================================
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# 增加防呆：確保變數有值且檔案真的存在，才塞入系統環境變數
if CREDENTIALS_FILE and os.path.exists(CREDENTIALS_FILE):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_FILE
    print(f"✅ 成功載入 GCP 憑證檔案: {CREDENTIALS_FILE}")
else:
    print("⚠️ 未找到 GCP 憑證檔案，若需使用 Vertex AI 可能會發生驗證錯誤。")

try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False


class ItineraryService:

    def __init__(self):
        self._validate_settings()
        self.vector_db = self._load_vector_db()

    def _validate_settings(self):
        if not settings.QDRANT_URL:
            raise ValueError("缺少 QDRANT_URL")

        if not settings.QDRANT_API_KEY:
            raise ValueError("缺少 QDRANT_API_KEY")

        if not settings.QDRANT_COLLECTION_NAME:
            raise ValueError("缺少 QDRANT_COLLECTION_NAME")

    def _load_vector_db(self):
        try:
            embedding_function = get_embedding_function()

            return QdrantVectorStore.from_existing_collection(
                embedding=embedding_function,
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                collection_name=settings.QDRANT_COLLECTION_NAME,
            )
        except NameError:
            print("⚠️ 尚未正確設定 QdrantVectorStore 的 import 路徑，向量搜尋功能暫時停用。")
            return None

    def get_exclusive_itinerary(
        self,
        db: Session,
        current_user: dict,
    ) -> list[ItineraryDateGroupResponse]:

        customer_vip_account_id = current_user.get("sub")
        customer_id = current_user.get("customer_id")
        login_account = current_user.get("login_account")

        sql = text("""
            SELECT 
                vr.RecommendationId,
                vs.ScheduleId,
                vs.ScheduleDate,
                vs.ScheduleTime,
                vs.Title,
                vs.Content,
                vs.Preference
            FROM VipItineraryRecommendation vr
                INNER JOIN VipItinerarySchedule vs 
                    ON vr.RecommendationId = vs.RecommendationId
                INNER JOIN Customer c 
                    ON vr.CustomerId = c.CustomerId
                INNER JOIN CustomerVipAccount cva 
                    ON c.CustomerId = cva.CustomerId
            WHERE
                c.CustomerId = :customer_id
                AND cva.CustomerVipAccountId = :customer_vip_account_id
                AND cva.LoginAccount = :login_account
            ORDER BY 
                vs.ScheduleDate DESC, 
                vs.ScheduleTime
        """)

        rows = db.execute(
            sql,
            {
                "customer_id": customer_id,
                "customer_vip_account_id": customer_vip_account_id,
                "login_account": login_account,
            },
        ).mappings().all()

        grouped: dict[str, list[ItineraryScheduleResponse]] = {}

        for row in rows:

            schedule_date = row["ScheduleDate"]

            date_text = (
                schedule_date.strftime("%Y-%m-%d")
                if hasattr(schedule_date, "strftime")
                else str(schedule_date)
            )

            if date_text not in grouped:
                grouped[date_text] = []

            grouped[date_text].append(
                ItineraryScheduleResponse(
                    time=row["ScheduleTime"],
                    title=row["Title"] or "",
                    content=row["Content"] or "",
                    preference=row["Preference"] or "",
                )
            )

        result = []

        for date_text, schedules in grouped.items():
            result.append(
                ItineraryDateGroupResponse(
                    date=date_text,
                    schedules=schedules,
                )
            )

        return result
    
    # 顧客基本資料
    def get_customer_prompt_data(self, db: Session, customer_id: str):
        """撈取顧客與訂房詳細資料"""
        sql = text("""
            SELECT 
                c.FullName AS full_name,
                sg.GenderName AS gender_name,
                bs.CheckInDate AS check_in_date,
                
                DATEDIFF(YEAR, c.BirthDate, GETDATE())
                -
                CASE 
                    WHEN DATEADD(
                        YEAR, 
                        DATEDIFF(YEAR, c.BirthDate, GETDATE()), 
                        c.BirthDate
                    ) > GETDATE() 
                    THEN 1 
                    ELSE 0 
                END AS age,
                
                sc.CountryName AS country_name,
                sc.CountryCode AS country_code,
                
                DATEDIFF(DAY, bs.CheckInDate, bs.CheckOutDate) AS stay_days,
                rt.RoomTypeName AS room_type_name,
                bs.AdultCount + bs.ChildCount AS total_count,
                
                CASE 
                    WHEN bs.HasParking = 1 
                    THEN N'有' 
                    ELSE N'無' 
                END AS has_parking
                
            FROM CustomerVipAccount cva
                INNER JOIN Customer c 
                    ON cva.CustomerId = c.CustomerId
                INNER JOIN SysGender sg 
                    ON c.GenderId = sg.GenderId
                INNER JOIN SysCountry sc 
                    ON c.CountryCode = sc.CountryCode
                INNER JOIN BookingStay bs 
                    ON c.CustomerId = bs.CustomerId
                INNER JOIN Room r 
                    ON bs.RoomId = r.RoomId
                INNER JOIN RoomType rt 
                    ON r.RoomTypeId = rt.RoomTypeId
            WHERE 
                c.CustomerId = :customer_id
        """)

        result = db.execute(
            sql,
            {
                "customer_id": customer_id
            }
        ).mappings().first()

        if result is None:
            raise ValueError(
                f"Customer {customer_id} prompt data not found."
            )

        return dict(result)

    def _get_knowledge_item_by_source_file(self, db: Session, source_file: str):
        """
        根據向量庫比對到的 source_file，回關聯式資料庫撈取真實的景點介紹
        """
        sql = text("""
            SELECT 
                PlaceName AS place_name, 
                Feature AS feature, 
                Category AS category 
            FROM ResortKnowledgeItem 
            WHERE SourceFile = :source_file
        """)
        
        try:
            result = db.execute(sql, {"source_file": source_file}).mappings().first()
            return dict(result) if result else None
        except Exception as e:
            print(f"⚠️ 查詢景點 {source_file} 時發生錯誤: {e}")
            return None


    def get_candidate_spots_from_vdb(self, db: Session, query: str, top_k: int = 10) -> list[dict]:
        """
        根據使用者的修改意見，從向量資料庫中尋找合適的候選景點
        """
        if self.vector_db is None:
            print("⚠️ 尚未連結向量資料庫，回傳空景點列表。")
            return []

        results = self.vector_db.similarity_search_with_score(
            query=query,
            k=top_k, 
        )

        selected_items = []
        used_places = set()

        for doc, score in results:
            place_name = doc.metadata.get("place_name")
            source_file = doc.metadata.get("source_file")

            if not place_name or not source_file or place_name in used_places:
                continue

            db_item = self._get_knowledge_item_by_source_file(db=db, source_file=source_file)

            if db_item is None:
                continue

            feature = db_item.get("feature", "")

            selected_items.append(
                {
                    "title": db_item.get("place_name"),
                    "content": feature[:100], 
                    "preference": db_item.get("category"),
                    "similarity_score": score 
                }
            )

            used_places.add(place_name)

        return selected_items

    def submit_feedback(
        self,
        db: Session,
        current_user: dict,
        message: str,
        date: str,
    ):
        customer_id = current_user.get("customer_id")

        if not customer_id:
            raise ValueError("無法取得當前使用者的 Customer ID")

        # 1. 取得顧客基本資料
        customer_data = self.get_customer_prompt_data(db, customer_id)

        # 1.5 取得該日期「原本的行程規劃」
        all_itineraries = self.get_exclusive_itinerary(db, current_user)
        target_itinerary = next((group for group in all_itineraries if group.date == date), None)
        
        original_schedule_text = ""
        if target_itinerary and target_itinerary.schedules:
            lines = []
            for schedule in target_itinerary.schedules:
                lines.append(f"  - {schedule.time}：【{schedule.title}】 (分類: {schedule.preference})")
                lines.append(f"    說明：{schedule.content}")
            original_schedule_text = "\n".join(lines)
        else:
            original_schedule_text = "  (當日目前無安排任何行程)"

        # 2. 取得向量資料庫資料 (把修改意見當 Query 去找景點)
        candidate_spots = self.get_candidate_spots_from_vdb(db=db, query=message, top_k=5)

        # 3. 核心：動態組裝 LLM Prompt
        prompt_lines = [
            f"你是一位專業且貼心的 VIP 專屬行程規劃師。請根據以下顧客資訊與要求，重新規劃 {date} 的行程。",
            "",
            "### 顧客基本資料",
            f"- 姓名：{customer_data.get('full_name')}",
            f"- 年齡：{customer_data.get('age')} 歲",
            f"- 同行人數：{customer_data.get('total_count')} 人",
            f"- 入住房型：{customer_data.get('room_type_name')}",
            "",
            f"### {date} 原本的行程規劃",
            original_schedule_text,
            "",
            "### 顧客的修改意見",
            f"「{message}」",
            "",
            "### 系統推薦的候選景點 (請優先從以下清單挑選適合該時段的行程來加入行程)",
        ]

        # 將 RAG 撈出來的景點塞進 Prompt 裡
        if candidate_spots:
            for i, spot in enumerate(candidate_spots, 1):
                prompt_lines.append(
                    f"{i}. 【{spot['title']}】(分類: {spot['preference']}) - {spot['content']}..."
                )
        else:
            prompt_lines.append("- 目前無特定候選景點，請根據您的專業知識推薦。")

        # 加入輸出限制
        prompt_lines.extend([
            "",
            "### 任務要求",
            "1. 請根據顧客意見調整原始行程規劃，盡可能保留原本的行程及時間，並在合適的時段安插新景點。",
            "2. **必須以 JSON 格式輸出**，JSON 的最外層必須包含兩個欄位：",
            "   - \"reply_message\": 給顧客的親切回覆（100~150字，介紹修改了哪些地方）。",
            "   - \"schedules\": 更新後的當日所有行程陣列，每個物件包含 \"time\" (格式 HH:mm), \"title\" (景點名稱), \"content\" (景點說明), \"preference\" (分類)。"
        ])

        final_prompt = "\n".join(prompt_lines)

        print(f"\n================== 準備送給 Vertex AI 的 Prompt ==================")
        print(final_prompt)
        print(f"================================================================\n")

        # 4. 呼叫 LLM 產生回應
        llm_response_text = ""

        if HAS_GENAI_SDK:
            try:
                # 💡 已啟用：GCP 企業版 (使用 Service Account JSON)
                client = genai.Client(vertexai=True, location='global') 
                
                print("🚀 正在呼叫 Vertex AI (Gemini) 模型...")
                
                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=final_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7, 
                        response_mime_type="application/json", # 🚀 關鍵：強制模型回傳標準 JSON
                    )
                )
                
                # 5. 解析 LLM 回傳的 JSON 資料
                result_data = json.loads(response.text)
                llm_response_text = result_data.get("reply_message", "行程已根據您的需求更新！")
                new_schedules = result_data.get("schedules", [])

                print("✅ LLM 新行程生成成功！準備寫入資料庫...")
                print(llm_response_text)

                # =====================================================================
                # 6. 核心：將新行程覆寫回 SQL Server 資料庫
                # =====================================================================
                
                # 6.1 撈出該名顧客對應的 RecommendationId (主表 ID)
                rec_sql = text("""
                    SELECT TOP 1 RecommendationId 
                    FROM VipItineraryRecommendation 
                    WHERE CustomerId = :customer_id
                    ORDER BY CreatedAt DESC
                """)
                rec_record = db.execute(rec_sql, {"customer_id": customer_id}).mappings().first()

                if rec_record and new_schedules:
                    rec_id = rec_record["RecommendationId"]

                    # 6.2 刪除該日期原本的舊行程
                    delete_sql = text("""
                        DELETE FROM VipItinerarySchedule
                        WHERE RecommendationId = :rec_id AND ScheduleDate = :date
                    """)
                    db.execute(delete_sql, {"rec_id": rec_id, "date": date})

                    # 6.3 將 LLM 生成的新行程一筆一筆 Insert 進去
                    insert_sql = text("""
                        INSERT INTO VipItinerarySchedule 
                            (ScheduleId, RecommendationId, ScheduleDate, ScheduleTime, Title, Content, Preference)
                        VALUES 
                            (:schedule_id, :rec_id, :date, :time, :title, :content, :preference)
                    """)

                    for schedule in new_schedules:
                        db.execute(insert_sql, {
                            "schedule_id": str(uuid.uuid4()).upper(), # 產生新的 GUID
                            "rec_id": rec_id,
                            "date": date,
                            "time": schedule.get("time", "00:00"),
                            "title": schedule.get("title", "未命名行程"),
                            "content": schedule.get("content", ""),
                            "preference": schedule.get("preference", "系統推薦")
                        })

                    # 6.4 確認無誤後，正式提交變更到資料庫！
                    db.commit()
                    print(f"💾 成功將 {date} 的 {len(new_schedules)} 筆新行程寫入資料庫！")

            except Exception as e:
                db.rollback() # 如果中途發生任何錯誤（例如 JSON 解析失敗、SQL 錯誤），將資料庫復原
                print(f"⚠️ 呼叫模型或更新資料庫時發生錯誤: {e}")
                llm_response_text = f"親愛的 {customer_data.get('full_name')} 您好，我們已收到您「{message}」的需求，專屬管家將盡快為您人工調整專屬行程！"
        else:
            print("⚠️ 尚未安裝 google-genai SDK，使用預設模擬回覆。")
            llm_response_text = (
                f"親愛的 {customer_data.get('full_name')} 您好！已經收到您希望「{message}」的需求。 "
                f"我們為您挑選了最棒的活動，希望能為您的旅程增添更多美好回憶！"
            )

        return {
            "success": True,
            "message": llm_response_text, 
        }

# 單例實例化
itinerary_service = ItineraryService()