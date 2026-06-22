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
        lang: str = "zh",
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
                lines.append(f"  - {schedule.time}：【{schedule.title}】 (分類/Preference: {schedule.preference})")
                lines.append(f"    說明/Description：{schedule.content}")
            original_schedule_text = "\n".join(lines)
        else:
            original_schedule_text = "  (當日目前無安排任何行程 / No schedule planned for this day)"

        # 2. 取得向量資料庫資料 (把修改意見當 Query 去找景點)
        candidate_spots = self.get_candidate_spots_from_vdb(db=db, query=message, top_k=5)

        # 3. 🧠 依據語系定義 System Instruction / Prompt 框架
        if lang == "en":
            role_instruction = "You are a professional and attentive VIP concierge itinerary planner."
            task_instruction = f"Please replan the itinerary for {date} based on the customer's request."
            output_requirement = (
                "1. **Guardrail & Topic Constraint**: Review the customer's request first. If the request is entirely unrelated to travel, hotels, itineraries, attractions, transportation, or dining (e.g., asking about programming, politics, financial investments, or casual chitchat), you MUST reject the request.\n"
                "   - In case of rejection: Set 'reply_message' to a polite refusal explaining you can only help with itinerary planning, and keep the 'schedules' array identical to the original schedule provided below.\n"
                "2. If the request is valid, adjust the original schedule based on user feedback. Keep original plans where possible.\n"
                "3. **CRITICAL PREFERENCE RULE**: For the 'preference' field of each schedule item, regardless of language, you MUST ONLY output one of these exact Chinese category names: '觀光園區', '在地文化', '餐飲美食', '溫泉公園', or '其他'. DO NOT translate this field to English so that the frontend filters remain fully functional!\n"
                "4. **MUST output in JSON format** with two fields:\n"
                '   - "reply_message": Warm and friendly response to the customer in English (100-150 words, explaining exactly what you changed or why you refused).\n'
                '   - "schedules": Array of updated daily items. Key texts ("title", "content") MUST be in English. Time format MUST be HH:mm.'
            )
            candidate_title = "### Candidate Spots Recommended by System (Preferentially insert these if they match user preferences)"
            feedback_title = "### Customer's Feedback"
            
        else:
            # 中文 Prompt 設定
            role_instruction = "你是一位專業且貼心的 VIP 專屬行程規劃師。"
            task_instruction = f"請根據以下顧客資訊與要求，重新規劃 {date} 的行程。"
            output_requirement = (
                "1. **核心防護與主題限制 (最高優先級)**：請先審查顧客的修改意見。如果意見內容「完全與旅遊、飯店、行程調整、景點、交通、美食餐飲無關」（例如：詢問寫程式、政治、股票、聊天、或要求你扮演其他角色），你**必須拒減該請求**。\n"
                "   - 拒絕時的做法：'reply_message' 請填入禮貌拒絕的文字（說明您身為專屬管家，僅能提供行程相關的協助）；'schedules' 欄位則**直接複製並重現原本的行程規劃**，不做任何更動。\n"
                "2. 如果意見與行程相關，請根據顧客意見調整原始行程規劃，盡可能保留原本的行程及時間，並在合適的時段安插新景點。\n"
                "3. **分類欄位限制**：每個行程項目的 'preference' 欄位，請一律使用這幾個標準中文分類：'觀光園區', '在地文化', '餐飲美食', '溫泉公園', '其他'。\n"
                "4. **必須以 JSON 格式輸出**，JSON 的最外層必須包含兩個欄位：\n"
                '   - "reply_message": 給顧客的親切回覆（100~150字，以繁體中文介紹修改了哪些地方）。\n'
                '   - "schedules": 更新後的當日所有行程陣列，每個物件包含 "time" (格式 HH:mm), "title" (景點名稱), "content" (繁體中文景點說明), "preference" (分類)。'
            )
            candidate_title = "### 系統推薦的候選景點 (請優先從以下清單挑選適合該時段的行程來加入行程)"
            feedback_title = "### 顧客的修改意見"

        # 動態組裝 Prompt
        prompt_lines = [
            f"{role_instruction} {task_instruction}",
            "",
            "### Customer Profile",
            f"- Name: {customer_data.get('full_name')}",
            f"- Age: {customer_data.get('age')}",
            f"- Total Guests: {customer_data.get('total_count')}",
            "",
            f"### Original Itinerary for {date}",
            original_schedule_text,
            "",
            f"{feedback_title}",
            f"「{message}」",
            "",
            f"{candidate_title}",
        ]

        # 將 RAG 撈出來的景點塞進 Prompt 裡
        if candidate_spots:
            for i, spot in enumerate(candidate_spots, 1):
                prompt_lines.append(f"{i}. 【{spot['title']}】({spot['preference']}) - {spot['content']}...")
        else:
            prompt_lines.append("- No specific candidate spots found.")

        # 加入輸出限制
        prompt_lines.extend([
            "",
            "### Requirements",
            output_requirement
        ])

        final_prompt = "\n".join(prompt_lines)

        print(f"\n================== 準備送給 Vertex AI 的 Prompt ==================")
        print(final_prompt)
        print(f"================================================================\n")

        # 4. 呼叫 LLM 產生回應
        llm_response_text = ""

        if HAS_GENAI_SDK:
            try:
                client = genai.Client(vertexai=True, location='global') 
                
                print("🚀 正在呼叫 Vertex AI (Gemini) 模型...")
                
                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=final_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2, 
                        response_mime_type="application/json", # 強制模型回傳標準 JSON
                    )
                )
                
                # 5. 解析 LLM 回傳的 JSON 資料
                result_data = json.loads(response.text)
                llm_response_text = result_data.get("reply_message", "行程已根據您的需求更新！")
                new_schedules = result_data.get("schedules", [])

                print("✅ LLM 行程解析成功！開始安全與意圖檢查...")
                print(llm_response_text)
              
                # =====================================================================
                # 🛡️ 深度安全與無變更檢查機制 (完美修復：刪除行程與部分修改衝突問題)
                # =====================================================================
                is_unchanged = False
                
                # 只有在新舊行程長度相同時，才需要做深層內容比對
                if target_itinerary and len(new_schedules) == len(target_itinerary.schedules):
                    all_identical = True
                    for new_sch, orig_sch in zip(new_schedules, target_itinerary.schedules):
                        # 正規化字串比對，防範多餘空白干擾
                        new_title = str(new_sch.get("title", "")).strip()
                        orig_title = str(orig_sch.title or "").strip()
                        
                        new_time = str(new_sch.get("time", "")).strip()
                        orig_time = str(orig_sch.time or "").strip()
                        
                        new_content = str(new_sch.get("content", "")).strip()
                        orig_content = str(orig_sch.content or "").strip()
                        
                        if new_title != orig_title or new_time != orig_time or new_content != orig_content:
                            all_identical = False
                            break # 只要有任何一筆、一個欄位發生改變，就代表有合理修改！
                    
                    if all_identical:
                        is_unchanged = True
                
                # 情境 B：原本就沒有行程，且新產生的也是空陣列 (完全沒行程，不需多做更新)
                elif (not target_itinerary or not target_itinerary.schedules) and len(new_schedules) == 0:
                    is_unchanged = True

                # 6.1 撈出該名顧客對應的 RecommendationId (主表 ID)
                rec_sql = text("""
                    SELECT TOP 1 RecommendationId 
                    FROM VipItineraryRecommendation 
                    WHERE CustomerId = :customer_id
                    ORDER BY CreatedAt DESC
                """)
                rec_record = db.execute(rec_sql, {"customer_id": customer_id}).mappings().first()

                # =====================================================================
                # 💾 資料庫寫入邏輯
                # =====================================================================
                if rec_record and not is_unchanged:
                    rec_id = rec_record["RecommendationId"]

                    # 1. 無論如何，先刪除該日期原本的舊行程 (達到清空/刪除的效果)
                    delete_sql = text("""
                        DELETE FROM VipItinerarySchedule
                        WHERE RecommendationId = :rec_id AND ScheduleDate = :date
                    """)
                    db.execute(delete_sql, {"rec_id": rec_id, "date": date})

                    # 2. 如果新行程有內容 (不是要全部刪光)，才一筆一筆 Insert 進去
                    if len(new_schedules) > 0:
                        insert_sql = text("""
                            INSERT INTO VipItinerarySchedule 
                                (ScheduleId, RecommendationId, ScheduleDate, ScheduleTime, Title, Content, Preference)
                            VALUES 
                                (:schedule_id, :rec_id, :date, :time, :title, :content, :preference)
                        """)

                        for schedule in new_schedules:
                            db.execute(insert_sql, {
                                "schedule_id": str(uuid.uuid4()).upper(), # GUID
                                "rec_id": rec_id,
                                "date": date,
                                "time": schedule.get("time", "00:00"),
                                "title": schedule.get("title", "未命名行程"),
                                "content": schedule.get("content", ""),
                                "preference": schedule.get("preference", "系統推薦")
                            })

                        print(f"💾 成功將 {date} 的 {len(new_schedules)} 筆新行程寫入資料庫！")
                    else:
                        print(f"🗑️ 使用者要求清空行程，已成功刪除 {date} 的所有行程！")

                    # 正式變更提交
                    db.commit()

                else:
                    # 如果判定為完全無關問題或無任何字句變動，直接 commit 釋放鎖定
                    db.commit() 
                    print("🛡️ 觸發安全攔截或行程完全無變更，跳過資料庫覆寫。")
                    
            except Exception as e:
                db.rollback() # 出錯時事務復原
                print(f"⚠️ 呼叫模型或更新資料庫時發生錯誤: {e}")
                if lang == "en":
                    llm_response_text = f"Dear {customer_data.get('full_name')}, we have received your request '{message}'. Our butler team will adjust your exclusive schedule shortly!"
                else:
                    llm_response_text = f"親愛的 {customer_data.get('full_name')} 您好，我們已收到您「{message}」的需求，專屬管家將盡快為您人工調整專屬行程！"
        else:
            print("⚠️ 尚未安裝 google-genai SDK，使用預設模擬回覆。")
            if lang == "en":
                llm_response_text = (
                    f"Dear {customer_data.get('full_name')}! We've received your request for '{message}'. "
                    f"We have handpicked the best activities to make your journey extraordinary!"
                )
            else:
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