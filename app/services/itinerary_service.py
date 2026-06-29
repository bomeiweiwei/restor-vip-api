from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

from langchain_qdrant import QdrantVectorStore
from app.ai.embedding_factory import get_embedding_function

from app.schemas.itinerary import (
    ItineraryDateGroupResponse,
    ItineraryScheduleResponse,
)

from app.utils.image_url import build_image_url

import json
import uuid
from app.core.config import settings

# 直接從 Pydantic 的 settings 讀取（它會自動對應環境變數）
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

# 檢查 SDK 載入
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

        # 🚀 修正：將 ORDER BY 改為 ASC（日期遞增正序），使前後端天數與時間對應邏輯保持完全一致
        sql = text("""
            SELECT 
                vr.RecommendationId,
                vs.ScheduleId,
                vs.ScheduleDate,
                vs.ScheduleTime,
                vs.Title,
                vs.Content,
                vs.Preference,
                vs.PicUrl
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
                vs.ScheduleDate ASC, 
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
                    imageUrl=build_image_url(row["PicUrl"]),
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
        """撈取顧客與訂房詳細資料以提供 LLM 脈絡"""
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
        根據向量庫比對到的 source_file，回關聯式資料庫撈取真實的景點介紹與圖片網址
        """
        sql = text("""
            SELECT 
                PlaceName AS place_name, 
                Feature AS feature, 
                Category AS category,
                PicUrl AS pic_url
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
                    "pic_url": db_item.get("pic_url") or "",  # 🚀 保留並提供原始圖片欄位
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

        # 1. 取得顧客基本資料
        customer_data = self.get_customer_prompt_data(db, customer_id)
        country_code = customer_data.get("country_code", "TW")
        
        # 依據國籍代碼判斷目標顯示語系，若無匹配則預設 zh-TW
        determined_lang = self.LANGUAGE_MAP.get(country_code, "zh-TW")
        print(f"🌍 數據庫顧客國籍：{country_code} -> 系統自動切換語系至：{determined_lang}")

        # 1.5 取得該日期原本的行程規劃
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

        # 3. 🧠 依據自動判斷的語系，動態生成四國語言對應的 Prompt 框架
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
                "task": f"顧客の要望に基づき、{date}の旅程を再計画してください。",
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

        # 獲取相對應語系的配置檔案
        cfg = lang_requirements.get(determined_lang, lang_requirements["zh-TW"])

        output_requirement = (
            f"1. **Guardrail & Topic Constraint**: Review the customer's request first. If the request is entirely unrelated to travel, hotels, itineraries, attractions, transportation, or dining (e.g., asking about programming, politics, financial investments, or casual chitchat), you MUST reject the request.\n"
            f"   - In case of rejection: 'reply_message' must be a polite refusal written in {cfg['reply_lang']} explaining you can only help with itinerary planning, and the 'schedules' array must remain identical to the original schedule provided below.\n"
            f"2. If the request is valid, adjust the original schedule based on user feedback. Keep original plans/times where possible, or clear them if requested.\n"
            f"3. **CRITICAL PREFERENCE RULE**: For the 'preference' field of each schedule item, regardless of output language, you MUST ONLY output one of these exact Chinese category names: '觀光園區', '在地文化', '餐飲美食', '溫泉公園', or '其他'. DO NOT translate or modify this specific field so frontend filters remain functional!\n"
            f"4. **STRICT RAG SCOPE GUARDRAIL**: If the user requests to add or change to a specific attraction, destination, restaurant, or activity that is NOT listed under '### Candidate Spots Recommended by System', you MUST NOT add it to the 'schedules' array. Instead, you should explain politely in the 'reply_message' (in {cfg['reply_lang']}) that the requested spot is currently unavailable or outside our resort's service scope, and keep the original itinerary unchanged for that specific slot.\n"
            f"5. **MUST output in JSON format** with two fields:\n"
            f'   - "reply_message": Warm and friendly response to the customer written in {cfg["reply_lang"]} (100-150 words).\n'
            f'   - "schedules": Array of updated daily items. Key texts ("title", "content") MUST be entirely written in {cfg["text_lang"]}. Time format: HH:mm.'
        )

        candidate_title = f"### Candidate Spots Recommended by System (Preferentially insert these if they match user preferences)" if determined_lang != "zh-TW" else "### 系統推薦的候選景點 (請優先從以下清單挑選適合該時段的行程來加入行程)"
        feedback_title = "### Customer's Feedback" if determined_lang != "zh-TW" else "### 顧客的修改意見"

        # 動態組裝 Prompt
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
                        response_mime_type="application/json", # 強制模型回傳標準 JSON
                    )
                )
                
                # 解析 LLM 回傳的 JSON 資料
                result_data = json.loads(response.text)
                llm_response_text = result_data.get("reply_message", "行程已根據您的需求更新！")
                new_schedules = result_data.get("schedules", [])

                print("✅ LLM 行程解析成功！開始安全與意圖深度檢查...")
                print(llm_response_text)
              
                # =====================================================================
                # 🛡️ 深度安全與無變更檢查機制
                # =====================================================================
                is_unchanged = False
                
                # 只有在新舊行程長度完全相同時，才逐一檢查內容
                if target_itinerary and len(new_schedules) == len(target_itinerary.schedules):
                    all_identical = True
                    for new_sch, orig_sch in zip(new_schedules, target_itinerary.schedules):
                        new_title = str(new_sch.get("title", "")).strip()
                        orig_title = str(orig_sch.title or "").strip()
                        
                        new_time = str(new_sch.get("time", "")).strip()
                        orig_time = str(orig_sch.time or "").strip()
                        
                        new_content = str(new_sch.get("content", "")).strip()
                        orig_content = str(orig_sch.content or "").strip()
                        
                        if new_title != orig_title or new_time != orig_time or new_content != orig_content:
                            all_identical = False
                            break
                    
                    if all_identical:
                        is_unchanged = True
                
                # 原本就空，且新產生的也是空陣列
                elif (not target_itinerary or not target_itinerary.schedules) and len(new_schedules) == 0:
                    is_unchanged = True

                # 撈出該名顧客對應的 RecommendationId (主表 ID)
                rec_sql = text("""
                    SELECT TOP 1 RecommendationId 
                    FROM VipItineraryRecommendation 
                    WHERE CustomerId = :customer_id
                    ORDER BY CreatedAt DESC
                """)
                rec_record = db.execute(rec_sql, {"customer_id": customer_id}).mappings().first()

                # =====================================================================
                # 💾 資料庫覆寫寫入邏輯
                # =====================================================================
                if rec_record and not is_unchanged:
                    rec_id = rec_record["RecommendationId"]

                    # 1. 先刪除該日期原本的舊行程
                    delete_sql = text("""
                        DELETE FROM VipItinerarySchedule
                        WHERE RecommendationId = :rec_id AND ScheduleDate = :date
                    """)
                    db.execute(delete_sql, {"rec_id": rec_id, "date": date})

                    # 2. 如果新行程有內容，才一筆一筆 Insert 進去
                    if len(new_schedules) > 0:
                        insert_sql = text("""
                            INSERT INTO VipItinerarySchedule 
                                (ScheduleId, RecommendationId, ScheduleDate, ScheduleTime, Title, Content, Preference, PicUrl)
                            VALUES 
                                (:schedule_id, :rec_id, :date, :time, :title, :content, :preference, :pic_url)
                        """)

                        for schedule in new_schedules:
                            new_title = schedule.get("title", "未命名行程").strip()
                            new_content = schedule.get("content", "").strip()
                            
                            matched_pic_url = ""
                            is_original_item = False
                            matched_spot = None

                            # 🚀 A. 檢查是否為「原本就有的行程」(比對標題相似度以繼承舊圖片)
                            if target_itinerary and target_itinerary.schedules:
                                for orig_sch in target_itinerary.schedules:
                                    orig_title = orig_sch.title.strip() if orig_sch.title else ""
                                    if orig_title and (orig_title in new_title or new_title in orig_title):
                                        is_original_item = True
                                        raw_pic = orig_sch.imageUrl
                                        if raw_pic:
                                            # 還原經由 build_image_url 包裝過的路徑
                                            if "/static/" in raw_pic:
                                                matched_pic_url = "/static/" + raw_pic.split("/static/")[-1]
                                            elif raw_pic.startswith("http"):
                                                matched_pic_url = raw_pic
                                        break

                            # 🚀 B. 檢查是否符合 RAG 推薦景點 (第一層：包含關係與模糊匹配)
                            for spot in candidate_spots:
                                spot_title = spot["title"].strip() if spot.get("title") else ""
                                if not spot_title:
                                    continue
                                
                                # 模糊比對規則：
                                # 1. 完全一致
                                # 2. 資料庫景點名被包含在 AI 新行程標題中 (例如 "溫泉公園" 被包含在 "前往礁溪溫泉公園" 中)
                                # 3. AI 新行程標題被包含在資料庫景點名中 (例如 "礁溪溫泉" 被包含在 "礁溪溫泉公園" 中)
                                # 4. 新行程內容描述提及了該推薦景點
                                if (new_title == spot_title or 
                                    spot_title in new_title or 
                                    new_title in spot_title or
                                    (spot_title in new_content)):
                                    
                                    matched_spot = spot
                                    if spot.get("pic_url"):
                                        matched_pic_url = spot["pic_url"]
                                    break

                            # 🚀 C. 核心阻擋機制 (Strict RAG Guardrail)
                            # 如果這筆行程既「不是原本就有的行程」，且「不符合任何一個 RAG 檢索到的推薦景點」
                            # 則認定為 LLM 的幻覺或使用者隨意要求的外部不合規景點，我們直接【阻擋不寫入】！
                            if not is_original_item and not matched_spot:
                                print(f"🚫 阻擋機制觸發：新行程【{new_title}】既非原行程，亦不在 RAG 推薦範圍內，已拒絕寫入。")
                                continue

                            # 🚀 D. 第三層終極防呆：若確定是合規的 RAG 景點但 PicUrl 為空，則指派推薦景點第一筆的圖片
                            if not matched_pic_url and matched_spot:
                                if matched_spot.get("pic_url"):
                                    matched_pic_url = matched_spot["pic_url"]
                            
                            if not matched_pic_url and candidate_spots:
                                # 萬一連 matched_spot 都沒有 (理應不會走到這)，防呆用第一筆推薦圖片
                                for spot in candidate_spots:
                                    if spot.get("pic_url"):
                                        matched_pic_url = spot["pic_url"]
                                        break

                            db.execute(insert_sql, {
                                "schedule_id": str(uuid.uuid4()).upper(),
                                "rec_id": rec_id,
                                "date": date,
                                "time": schedule.get("time", "00:00"),
                                "title": new_title,
                                "content": new_content,
                                "preference": schedule.get("preference", "系統推薦"),
                                "pic_url": matched_pic_url
                            })

                        print(f"💾 成功將 {date} 的 {len(new_schedules)} 筆新行程（已套用 RAG 景點阻擋過濾機制）寫入資料庫！")
                    else:
                        print(f"🗑️ 使用者要求清空行程，已成功刪除 {date} 的所有行程！")

                    db.commit()
                else:
                    db.commit() 
                    print("🛡️ 觸發安全攔截或行程完全無變更，跳過資料庫覆寫。")
                    
            except Exception as e:
                db.rollback()
                print(f"⚠️ 呼叫模型或更新資料庫時發生錯誤: {e}")
                if determined_lang == "en":
                    llm_response_text = f"Dear {customer_data.get('full_name')}, we have received your request '{message}'. Our concierge team will adjust your exclusive schedule shortly!"
                elif determined_lang == "ja":
                    llm_response_text = f"親愛なる {customer_data.get('full_name')} 様、ご要望「{message}」を承りました。専属コンシェルジュがすぐに手動で調整いたします！"
                elif determined_lang == "ko":
                    llm_response_text = f"친애하는 {customer_data.get('full_name')} 님, '{message}' 요청이 접수되었습니다. 전담 컨시어지가 곧 일정을 수동으로 조정해 드리겠습니다!"
                else:
                    llm_response_text = f"親愛的 {customer_data.get('full_name')} 您好，我們已收到您「{message}」的需求，專屬管家將盡快為您人工調整專屬行程！"
        else:
            print("⚠️ 尚未安裝 google-genai SDK，使用預設模擬回覆。")
            if determined_lang == "en":
                llm_response_text = f"Dear {customer_data.get('full_name')}! We've received your request. We hope you have a wonderful trip!"
            elif determined_lang == "ja":
                llm_response_text = f"親愛なる {customer_data.get('full_name')} 様！ご要望を承りました。素晴らしい旅になりますように！"
            elif determined_lang == "ko":
                llm_response_text = f"친애하는 {customer_data.get('full_name')} 님! 요청이 접수되었습니다. 즐거운 여행이 되시길 바랍니다!"
            else:
                llm_response_text = f"親愛的 {customer_data.get('full_name')} 您好！已經收到您的需求，希望能為您的旅程增添更多美好回憶！"

        return {
            "success": True,
            "message": llm_response_text, 
        }

# 單例實例化
itinerary_service = ItineraryService()