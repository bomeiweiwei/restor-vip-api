from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

from langchain_qdrant import QdrantVectorStore
from app.ai.embedding_factory import get_embedding_function

from app.schemas.itinerary import (
    ItineraryDateGroupResponse,
    ItineraryScheduleResponse,
)

import json
import uuid
import random # 🚀 新增隨機庫來指派不同主題的預設圖

# 直接從 Pydantic 的 settings 讀取（它會自動幫你對應環境變數）
credentials_json_str = settings.GOOGLE_CREDENTIALS_JSON
gcp_credentials = None

if credentials_json_str:
    try:
        credentials_info = json.loads(credentials_json_str)
        from google.oauth2 import service_account
        gcp_credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        print("✅ 成功從 Pydantic Settings 載入 GCP 憑證字串。")
    except Exception as e:
        print(f"❌ 解析 GCP 憑證環境變數失敗: {e}")
else:
    print("⚠️ 未找到 GCP 憑證環境變數，若需使用 Vertex AI 可能會發生驗證錯誤。")

# 2. 檢查 SDK 載入
try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

class ItineraryService:
    # 🚀 國籍代碼（CountryCode）與 LLM 輸出語系的對應表
    LANGUAGE_MAP = {
        "TW": "zh-TW",
        "US": "en",
        "JP": "ja",
        "KR": "ko"
    }

    # 🚀 新增：分類專屬高質感保底模擬圖庫（Unsplash 精選度假、餐飲、文化圖）
    DEFAULT_IMAGES = {
        "觀光園區": [
            "https://images.unsplash.com/photo-1513885535751-8b9238bd345a?auto=format&fit=crop&w=800&q=80",
            "https://images.unsplash.com/photo-1602631985686-2bb060a4e82b?auto=format&fit=crop&w=800&q=80"
        ],
        "在地文化": [
            "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?auto=format&fit=crop&w=800&q=80",
            "https://images.unsplash.com/photo-1506157786151-b8491531f063?auto=format&fit=crop&w=800&q=80"
        ],
        "餐飲美食": [
            "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=800&q=80",
            "https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=800&q=80"
        ],
        "溫泉公園": [
            "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=800&q=80",
            "https://images.unsplash.com/photo-1545239351-ef35f43d514b?auto=format&fit=crop&w=800&q=80"
        ],
        "其他": [
            "https://images.unsplash.com/photo-1571003123894-1f0594d2b5d9?auto=format&fit=crop&w=800&q=80",
            "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80"
        ]
    }

    def __init__(self):
        self._validate_settings()
        self.vector_db = self._load_vector_db()

    def _get_fallback_image(self, preference: str) -> str:
        """根據分類隨機回傳一張保底圖片"""
        pref = preference if preference in self.DEFAULT_IMAGES else "其他"
        return random.choice(self.DEFAULT_IMAGES[pref])

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
            print("⚠️ 尚未正確設定 QdrantVectorStore 的 import路徑，向量搜尋功能暫時停用。")
            return None

    def get_exclusive_itinerary(
        self,
        db: Session,
        current_user: dict,
    ) -> list[ItineraryDateGroupResponse]:

        customer_vip_account_id = current_user.get("sub")
        customer_id = current_user.get("customer_id")
        login_account = current_user.get("login_account")

        # 🚀 註：若資料庫已有 ImageUrl 欄位請加入 SELECT，此處先假設資料庫尚未擴充，以 ImageUrl 欄位不存在做防錯處理
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

            pref = row["Preference"] or "其他"
            # 🚀 修正 1：若資料庫內沒有撈到圖片（或欄位尚不存在），直接在此補上模擬圖網址
            db_img_url = row.get("ImageUrl") if "ImageUrl" in row else None
            final_img_url = db_img_url if db_img_url else self._get_fallback_image(pref)

            grouped[date_text].append(
                ItineraryScheduleResponse(
                    time=row["ScheduleTime"],
                    title=row["Title"] or "",
                    content=row["Content"] or "",
                    preference=pref,
                    imageUrl=final_img_url # 🚀 傳給前端 Pydantic Schema 的駝峰欄位
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
    
    def get_customer_prompt_data(self, db: Session, customer_id: str):
        sql = text("""
            SELECT 
                c.FullName AS full_name,
                sg.GenderName AS gender_name,
                bs.CheckInDate AS check_in_date,
                DATEDIFF(YEAR, c.BirthDate, GETDATE())
                -
                CASE 
                    WHEN DATEADD(YEAR, DATEDIFF(YEAR, c.BirthDate, GETDATE()), c.BirthDate) > GETDATE() 
                    THEN 1 ELSE 0 END AS age,
                sc.CountryName AS country_name,
                sc.CountryCode AS country_code,
                DATEDIFF(DAY, bs.CheckInDate, bs.CheckOutDate) AS stay_days,
                rt.RoomTypeName AS room_type_name,
                bs.AdultCount + bs.ChildCount AS total_count,
                CASE WHEN bs.HasParking = 1 THEN N'有' ELSE N'無' END AS has_parking
            FROM CustomerVipAccount cva
                INNER JOIN Customer c ON cva.CustomerId = c.CustomerId
                INNER JOIN SysGender sg ON c.GenderId = sg.GenderId
                INNER JOIN SysCountry sc ON c.CountryCode = sc.CountryCode
                INNER JOIN BookingStay bs ON c.CustomerId = bs.CustomerId
                INNER JOIN Room r ON bs.RoomId = r.RoomId
                INNER JOIN RoomType rt ON r.RoomTypeId = rt.RoomTypeId
            WHERE c.CustomerId = :customer_id
        """)
        result = db.execute(sql, {"customer_id": customer_id}).mappings().first()
        if result is None:
            raise ValueError(f"Customer {customer_id} prompt data not found.")
        return dict(result)

    def _get_knowledge_item_by_source_file(self, db: Session, source_file: str):
        sql = text("""
            SELECT PlaceName AS place_name, Feature AS feature, Category AS category 
            FROM ResortKnowledgeItem WHERE SourceFile = :source_file
        """)
        try:
            result = db.execute(sql, {"source_file": source_file}).mappings().first()
            return dict(result) if result else None
        except Exception as e:
            print(f"⚠️ 查詢景點 {source_file} 時發生錯誤: {e}")
            return None

    def get_candidate_spots_from_vdb(self, db: Session, query: str, top_k: int = 10) -> list[dict]:
        if self.vector_db is None:
            print("⚠️ 尚未連結向量資料庫，回傳空景點列表。")
            return []

        results = self.vector_db.similarity_search_with_score(query=query, k=top_k)
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

            pref = db_item.get("category") or "其他"
            # 🚀 修正 2：為 RAG 搜尋出來的景點，也先配好對應分類的保底模擬圖網址
            fallback_img = self._get_fallback_image(pref)

            selected_items.append(
                {
                    "title": db_item.get("place_name"),
                    "content": db_item.get("feature", "")[:100], 
                    "preference": pref,
                    "imageUrl": fallback_img, # 🚀 同步塞入
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
        lang: str = "zh"
    ):
        customer_id = current_user.get("customer_id")
        if not customer_id:
            raise ValueError("無法取得當前使用者的 Customer ID")

        customer_data = self.get_customer_prompt_data(db, customer_id)
        country_code = customer_data.get("country_code", "TW")
        determined_lang = self.LANGUAGE_MAP.get(country_code, "zh-TW")
        print(f"🌍 數據庫顧客國籍：{country_code} -> 系統自動切換語系至：{determined_lang}")

        all_itineraries = self.get_exclusive_itinerary(db, current_user)
        target_itinerary = next((group for group in all_itineraries if group.date == date), None)
        
        original_schedule_text = ""
        if target_itinerary and target_itinerary.schedules:
            lines = []
            for schedule in target_itinerary.schedules:
                lines.append(f"  - {schedule.time}：【{schedule.title}】 (分類/Preference: {schedule.preference})")
                lines.append(f"    說明/Description：{schedule.content}")
                lines.append(f"    圖片/ImageUrl：{getattr(schedule, 'imageUrl', '')}")
            original_schedule_text = "\n".join(lines)
        else:
            original_schedule_text = "  (當日目前無安排任何行程 / No schedule planned for this day)"

        candidate_spots = self.get_candidate_spots_from_vdb(db=db, query=message, top_k=5)

        lang_requirements = {
            "zh-TW": {
                "role": "你是一位專業且貼心的 VIP 專屬行程規劃師。",
                "task": f"請根據以下顧客資訊與要求，重新規劃 {date} 的行程。",
                "reply_lang": "繁體中文 (Traditional Chinese)",
                "text_lang": "繁體中文 (Traditional Chinese)"
            },
            "en": {
                "role": "You are a professional and attentive VIP concierge itinerary planner.",
                "task": f"Please replan the itinerary for {date} based on the customer's request.",
                "reply_lang": "English",
                "text_lang": "English"
            },
            "ja": {
                "role": "あなたはプロフェッショナルで細やかな気配りができるVIP専属の旅程プランナーです。",
                "task": f"顧客の要望に基づ기、{date}の旅程を再計画してください。",
                "reply_lang": "Japanese (日本語)",
                "text_lang": "Japanese (日本語)"
            },
            "ko": {
                "role": "당신은 전문적이고 세심한 VIP 전담 일정 플래너입니다.",
                "task": f"고객의 요청에 따라 {date}의 일정을 재계획해 주세요.",
                "reply_lang": "Korean (한국어)",
                "text_lang": "Korean (한국어)"
            }
        }

        cfg = lang_requirements.get(determined_lang, lang_requirements["zh-TW"])

        # 🚀 修正 3：在 LLM 的 Requirements 中，明確要求必須保留或回傳 "imageUrl" 欄位
        output_requirement = (
            f"1. **Guardrail & Topic Constraint**: Review the customer's request first. If the request is entirely unrelated to travel, hotels, itineraries, attractions, transportation, or dining, you MUST reject the request.\n"
            f"   - In case of rejection: 'reply_message' must be a polite refusal written in {cfg['reply_lang']}, and the 'schedules' array must remain identical to the original schedule.\n"
            f"2. If the request is valid, adjust the original schedule based on user feedback.\n"
            f"3. **CRITICAL PREFERENCE RULE**: For the 'preference' field, you MUST ONLY output one of these exact Chinese category names: '觀光園區', '在地文化', '餐飲美食', '溫泉公園', or '其他'.\n"
            f"4. **IMAGEURL HANDLING RULE**: You MUST include the 'imageUrl' field for each schedule item. If you pick a recommended candidate spot, use its provided 'imageUrl'. If you keep an original schedule item, preserve its original 'imageUrl'. If it's a completely new plan with no image, you can generate a relevant one from Unsplash or pass an empty string.\n"
            f"5. **MUST output in JSON format** with two fields:\n"
            f'   - "reply_message": Warm and friendly response in {cfg["reply_lang"]}.\n'
            f'   - "schedules": Array of items. Key texts ("title", "content") written in {cfg["text_lang"]}. Keys MUST be "time", "title", "content", "preference", and "imageUrl".'
        )

        candidate_title = f"### Candidate Spots Recommended by System (Preferentially insert these if they match user preferences)" if determined_lang != "zh-TW" else "### 系統推薦的候選景點 (請優先從以下清單挑選適合該時段的行程來加入行程)"
        feedback_title = "### Customer's Feedback" if determined_lang != "zh-TW" else "### 顧客的修改意見"

        prompt_lines = [
            f"{cfg['role']} {cfg['task']}",
            "",
            "### Customer Profile",
            f"- Name: {customer_data.get('full_name')}",
            f"- Age: {customer_data.get('age')} years old",
            f"- Total Guests: {customer_data.get('total_count')}",
            f"- Room Type: {customer_data.get('room_type_name')}",
            "",
            f"### Original Itinerary for {date}",
            original_schedule_text,
            "",
            f"{feedback_title}",
            f"「{message}」",
            "",
            f"{candidate_title}",
        ]

        if candidate_spots:
            for i, spot in enumerate(candidate_spots, 1):
                prompt_lines.append(f"{i}. 【{spot['title']}】({spot['preference']}) - {spot['content']}... [ImageUrl: {spot['imageUrl']}]")
        else:
            prompt_lines.append("- No specific candidate spots found.")

        prompt_lines.extend(["", "### Requirements", output_requirement])
        final_prompt = "\n".join(prompt_lines)

        print(f"\n================== 準備送給 Vertex AI 的 Prompt ==================")
        print(final_prompt)
        print(f"================================================================\n")

        llm_response_text = ""

        if HAS_GENAI_SDK:
            try:
                client = genai.Client(
                    vertexai=True,
                    project=settings.GOOGLE_CLOUD_PROJECT,
                    location=settings.GOOGLE_CLOUD_LOCATION,
                    credentials=gcp_credentials,
                )
                
                print("🚀 正在呼叫 Vertex AI (Gemini) 模型...")
                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=final_prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2, 
                        response_mime_type="application/json",
                    )
                )
                
                result_data = json.loads(response.text)
                llm_response_text = result_data.get("reply_message", "行程已根據您的需求更新！")
                new_schedules = result_data.get("schedules", [])

                print("✅ LLM 行程解析成功！開始安全與意圖深度檢查...")
              
                is_unchanged = False
                if target_itinerary and len(new_schedules) == len(target_itinerary.schedules):
                    all_identical = True
                    for new_sch, orig_sch in zip(new_schedules, target_itinerary.schedules):
                        if (str(new_sch.get("title", "")).strip() != str(orig_sch.title or "").strip() or
                            str(new_sch.get("time", "")).strip() != str(orig_sch.time or "").strip() or
                            str(new_sch.get("content", "")).strip() != str(orig_sch.content or "").strip()):
                            all_identical = False
                            break
                    if all_identical:
                        is_unchanged = True
                elif (not target_itinerary or not target_itinerary.schedules) and len(new_schedules) == 0:
                    is_unchanged = True

                rec_sql = text("SELECT TOP 1 RecommendationId FROM VipItineraryRecommendation WHERE CustomerId = :customer_id ORDER BY CreatedAt DESC")
                rec_record = db.execute(rec_sql, {"customer_id": customer_id}).mappings().first()

                if rec_record and not is_unchanged:
                    rec_id = rec_record["RecommendationId"]

                    delete_sql = text("DELETE FROM VipItinerarySchedule WHERE RecommendationId = :rec_id AND ScheduleDate = :date")
                    db.execute(delete_sql, {"rec_id": rec_id, "date": date})

                    if len(new_schedules) > 0:
                        # 🚀 註：若之後資料庫擴充了 ImageUrl 欄位，請解除下方註解並將其寫入 DB
                        insert_sql = text("""
                            INSERT INTO VipItinerarySchedule 
                                (ScheduleId, RecommendationId, ScheduleDate, ScheduleTime, Title, Content, Preference)
                            VALUES 
                                (:schedule_id, :rec_id, :date, :time, :title, :content, :preference)
                        """)

                        for schedule in new_schedules:
                            # 🚀 如果 LLM 沒生出保底圖，就在寫入/回傳前最後把關
                            pref_cat = schedule.get("preference", "其他")
                            final_schedule_img = schedule.get("imageUrl") or self._get_fallback_image(pref_cat)

                            db.execute(insert_sql, {
                                "schedule_id": str(uuid.uuid4()).upper(),
                                "rec_id": rec_id,
                                "date": date,
                                "time": schedule.get("time", "00:00"),
                                "title": schedule.get("title", "未命名行程"),
                                "content": schedule.get("content", ""),
                                "preference": pref_cat
                                # "image_url": final_schedule_img # 👈 資料庫實體欄位擴充後可解鎖
                            })

                        print(f"💾 成功將 {date} 的 {len(new_schedules)} 筆新行程寫入資料庫！")
                    db.commit()
                else:
                    db.commit() 
                    print("🛡️ 觸發安全攔截或行程完全無變更，跳過資料庫覆寫。")
                    
            except Exception as e:
                db.rollback()
                print(f"⚠️ 呼叫模型或更新資料庫時發生錯誤: {e}")
                if determined_lang == "en":
                    llm_response_text = f"Dear {customer_data.get('full_name')}, we have received your request '{message}'. Our concierge team will adjust your exclusive schedule shortly!"
                else:
                    llm_response_text = f"親愛的 {customer_data.get('full_name')} 您好，我們已收到您「{message}」的需求，專屬管家將盡快為您人工調整專屬行程！"
        else:
            if determined_lang == "en":
                llm_response_text = f"Dear {customer_data.get('full_name')}! We've received your request. We hope you have a wonderful trip!"
            else:
                llm_response_text = f"親愛的 {customer_data.get('full_name')} 您好！已經收到您的需求，希望能為您的旅程增添更多美好回憶！"

        return {
            "success": True,
            "message": llm_response_text, 
        }

itinerary_service = ItineraryService()