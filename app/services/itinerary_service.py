import base64
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
from app.services.text_to_speech_itinerary import text_to_speech  # 🚀 直接從外部服務模組導入

import json
import uuid
import datetime # 🚀 引入日期模組進行後端防禦

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

    def _generate_tts_base64(self, text: str, country_code: str) -> str | None:
        """
        🚀 呼叫外部語音合成模組進行高品質 Wavenet 語音合成
        """
        # 國籍與 Google TTS 支援語系的對應分流
        lang_code_map = {
            "TW": "zh-TW",
            "US": "en-US",
            "JP": "ja-JP",
            "KR": "ko-KR"
        }
        target_lang = lang_code_map.get(country_code, "zh-TW")
        
        try:
            print(f"🔊 正在透過 text_to_speech_itinerary 合成管家語音... 語系：{target_lang}")
            
            # 🚀 呼叫外部方法：內建 1.15 語速與 +1.0 甜美音高，聲音乾淨俐落又親切！
            audio_content = text_to_speech(text=text, language=target_lang)
            
            if audio_content:
                # 將二進位音訊轉成前端 JavaScript 認識的 Base64 字串
                audio_b64 = base64.b64encode(audio_content).decode("utf-8")
                return audio_b64
            return None
            
        except Exception as e:
            print(f"❌ [TTS 整合錯誤] 無法生成語音導覽: {e}")
            return None
    
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

        # 將 ORDER BY 改為 ASC（日期遞增正序），使前後端天數與時間對應邏輯保持完全一致
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
            
            # 🚀 確保日期一定為乾淨的 YYYY-MM-DD 格式，排除可能帶有時間資訊 (如 00:00:00) 的字串，防範前端比對失敗跳頁
            if hasattr(schedule_date, "strftime"):
                date_text = schedule_date.strftime("%Y-%m-%d")
            elif schedule_date:
                date_text = str(schedule_date).strip().split(" ")[0].split("T")[0]
            else:
                date_text = ""

            if not date_text:
                continue

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
        """根據向量庫比對到的 source_file，回關聯式資料庫撈取真實的景點介紹與圖片網址"""
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
        """根據使用者的修改意見，從向量資料庫中尋找合適的候選景點"""
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
                    "pic_url": db_item.get("pic_url") or "",
                    "similarity_score": score
                }
            )

            used_places.add(place_name)

        return selected_items

    def _detect_target_date(self, message: str, selected_date: str, all_dates: list[str]) -> str:
        """
        🚀 智慧偵測：分析使用者對話中是否包含特定的行程日期或相對日期。
        若偵測到與目前 selected_date 不同的合法日期，則自動切換目標日期。
        """
        message_clean = message.replace(" ", "")
        
        # 1. 絕對日期格式比對（如 "6月19日"、"6/19" 等）
        for date_str in all_dates:
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                month = str(dt.month)
                day = str(dt.day)
                
                # 建構常見的日期對話樣式
                patterns = [
                    f"{month}月{day}日",
                    f"{month}月{day}號",
                    f"{month}/{day}",
                    f"{month}-{day}",
                ]
                
                # 補零相容性
                if dt.month < 10:
                    patterns.append(f"0{month}月{day}日")
                    patterns.append(f"0{month}月{day}號")
                    patterns.append(f"0{month}/{day}")
                if dt.day < 10:
                    patterns.append(f"{month}月0{day}日")
                    patterns.append(f"{month}月0{day}號")
                    patterns.append(f"{month}/0{day}")
                if dt.month < 10 and dt.day < 10:
                    patterns.append(f"0{month}/0{day}")

                for pattern in patterns:
                    if pattern in message_clean:
                        print(f"🎯 [智慧日期辨識] 偵測到使用者訊息提及特定日期關鍵字 '{pattern}'，自動將目標日期從 {selected_date} 切換至 {date_str}")
                        return date_str
            except Exception as e:
                print(f"⚠️ 解析日期 {date_str} 失敗: {e}")
                continue
                
        # 2. 相對日期意圖比對（如 "明天"、"後天"、"昨天" 等）
        try:
            sel_dt = datetime.datetime.strptime(selected_date, "%Y-%m-%d").date()
        except Exception:
            sel_dt = datetime.date.today()

        relative_map = {
            "今天": sel_dt,
            "明天": sel_dt + datetime.timedelta(days=1),
            "後天": sel_dt + datetime.timedelta(days=2),
            "大後天": sel_dt + datetime.timedelta(days=3),
            "昨天": sel_dt - datetime.timedelta(days=1),
        }

        for rel_word, target_dt in relative_map.items():
            if rel_word in message_clean:
                target_dt_str = target_dt.strftime("%Y-%m-%d")
                if target_dt_str in all_dates:
                    print(f"🎯 [智慧相對日期辨識] 偵測到相對日期關鍵字 '{rel_word}'，自動將目標日期切換至 {target_dt_str}")
                    return target_dt_str

        # 若皆未比對到，安全返回原本 UI 選取的 selected_date
        return selected_date

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

        # =====================================================================
        # 🚀 關鍵防禦邏輯：如果傳入的 date 為空字串、None 或無效值，自動降級預設為今天
        # =====================================================================
        if not date or str(date).strip() == "" or str(date) == "undefined" or str(date) == "null":
            date = datetime.date.today().strftime("%Y-%m-%d")
            print(f"⚠️ [後端防禦] 偵測到傳入的 ScheduleDate 為空值！已自動修復並重設為當日日期: {date}")
        else:
            # 🚀 容錯防護：確保傳入的日期格式乾淨，截去可能夾帶的時間字串 (如 2026-06-29 00:00:00)
            date = str(date).strip().split(" ")[0].split("T")[0]

        # 建立合法景點快取對照表 
        valid_places_sql = text("SELECT PlaceName, PicUrl FROM ResortKnowledgeItem")
        valid_places = db.execute(valid_places_sql).mappings().all()
        
        # 建立 PlaceName -> PicUrl 的字典對照表，並去除字串前後空格
        place_map = {
            item["PlaceName"].strip(): (item["PicUrl"] or "")
            for item in valid_places if item["PlaceName"]
        }
        place_names = list(place_map.keys())
        place_names_str = ", ".join(place_names) if place_names else "無特定可用景點"

        # 1. 取得顧客基本資料
        customer_data = self.get_customer_prompt_data(db, customer_id)
        country_code = customer_data.get("country_code", "TW")
        
        # 依據國籍代碼判斷目標顯示語系，若無匹配則預設 zh-TW
        determined_lang = self.LANGUAGE_MAP.get(country_code, "zh-TW")
        print(f"🌍 數據庫顧客國籍：{country_code} -> 系統自動切換語系至：{determined_lang}")

        # 🚀 2. 獲取所有行程日期，用於智慧對話日期意圖辨識
        all_itineraries = self.get_exclusive_itinerary(db, current_user)
        all_dates = [group.date for group in all_itineraries]
        
        # 🚀 3. 智慧對話日期辨識與對齊：如果使用者提及了與選單不同的日期，自動完成上下文切換
        detected_date = self._detect_target_date(message, date, all_dates)
        if detected_date != date:
            print(f"💡 [日期意圖切換] 使用者輸入提及其他日期。日期上下文已從 {date} 安全切換至 {detected_date}")
            date = detected_date

        # 🚀 4. 基於最終確定的目標日期，獲取該日期原本的行程規劃進行變更
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
                "role": "あなたはプロフェッショナルで細やかな気配りができるVIP専属의旅程플래너입니다。",
                "task": f"고객의 요청에 따라 {date}의 일정을 재계획해 주세요。",
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

        # 關鍵強化 4：大幅收緊 Prompt 規範，強力要求 AI「嚴禁修改標題，且動作描述字元只能塞進 content 內」
        # 關鍵強化 5：在 Requirements 中限制 AI 導覽內容簡短、精美 (適配 100-150 字)
        output_requirement = (
            f"1. **Guardrail & Topic Constraint**: Review the customer's request first. If the request is entirely unrelated to travel, hotels, itineraries, attractions, transportation, or dining (e.g., asking about programming, politics, financial investments, or casual chitchat), you MUST reject the request.\n"
            f"   - In case of rejection: 'reply_message' must be a polite refusal written in {cfg['reply_lang']} explaining you can only help with itinerary planning, and the 'schedules' array must remain identical to the original schedule provided below.\n"
            f"2. If the request is valid, adjust the original schedule based on user feedback. Keep original plans/times where possible, or clear them if requested.\n"
            f"3. **CRITICAL PREFERENCE RULE**: For the 'preference' field of each schedule item, regardless of output language, you MUST ONLY output one of these exact Chinese category names: '觀光園區', '在地文化', '餐飲美食', '溫泉公園', or '其他'. DO NOT translate or modify this specific field so frontend filters remain functional!\n"
            f"4. **STRICT RAG SCOPE GUARDRAIL**: If the user requests to add or change to a specific attraction, destination, restaurant, or activity that is NOT listed under '### Candidate Spots Recommended by System', you MUST NOT add it to the 'schedules' array. Instead, you should explain politely in the 'reply_message' (in {cfg['reply_lang']}) that the requested spot is currently unavailable or outside our resort's service scope, and keep the original itinerary unchanged for that specific slot.\n"
            f"5. **MUST output in JSON format** with two fields:\n"
            f'   - "reply_message": Warm, friendly, and extremely concise response to the customer written in {cfg["reply_lang"]}. It MUST be exactly 3 to 5 sentences long, structured beautifully with paragraph breaks (use standard newline characters like \\n\\n for paragraphs) to ensure elegant readability.\n'
            f'   - "schedules": Array of updated daily items. Each item MUST be a JSON object containing exactly these four keys: "time" (string, format: HH:mm), "title" (string, exact PlaceName), "content" (string), and "preference" (string). E.g. {{"time": "08:00", "title": "蝶舞咖啡廳", "content": "...", "preference": "餐飲美食"}}. Key texts ("title", "content") MUST be entirely written in {cfg["text_lang"]}.\n'
            f"6. **STRICT PLACE NAME MATCHING**: The 'title' field in the 'schedules' array MUST EXACTLY match one of the PlaceName keys from this list: {place_names_str}. DO NOT add any extra descriptions, action verbs (e.g., do not add '參觀', '體驗', '享用' to the title), emojis, or modify the title in any way. Keep the title exactly character-for-character identical to the list. Put descriptive action details ONLY inside the 'content' field.\n"
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
                        
                        # 🚀 容錯比對：讀取多元時間命名
                        new_time = str(
                            new_sch.get("time") or 
                            new_sch.get("Time") or 
                            new_sch.get("ScheduleTime") or 
                            new_sch.get("scheduleTime") or 
                            new_sch.get("schedule_time") or 
                            ""
                        ).strip()
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

                    # 1. 刪除該日期舊行程
                    delete_sql = text("DELETE FROM VipItinerarySchedule WHERE RecommendationId = :rec_id AND ScheduleDate = :date")
                    db.execute(delete_sql, {"rec_id": rec_id, "date": date})

                    if len(new_schedules) > 0:
                        insert_sql = text("""
                            INSERT INTO VipItinerarySchedule 
                                (ScheduleId, RecommendationId, ScheduleDate, ScheduleTime, Title, Content, Preference, PicUrl)
                            VALUES 
                                (:schedule_id, :rec_id, :date, :time, :title, :content, :preference, :pic_url)
                        """)

                        for schedule in new_schedules:
                            new_title = schedule.get("title", "").strip()
                            
                            # =====================================================================
                            # 🚀 精確與「模糊自動容錯修復比對」
                            # =====================================================================
                            matched_title = None
                            
                            # 1. 完全精確匹配
                            if new_title in place_map:
                                matched_title = new_title
                            else:
                                # 2. 子字串包含比對
                                for valid_name in place_map.keys():
                                    if valid_name in new_title or new_title in valid_name:
                                        matched_title = valid_name
                                        break
                                
                                # 3. 字元重合比對
                                if not matched_title:
                                    best_match = None
                                    max_overlap = 0
                                    for valid_name in place_map.keys():
                                        common_chars = len(set(valid_name) & set(new_title))
                                        if common_chars > max_overlap and common_chars >= 3:
                                            max_overlap = common_chars
                                            best_match = valid_name
                                    if best_match:
                                        matched_title = best_match

                            # 4. 成功匹配或自動修復後，安全寫入資料庫
                            if matched_title:
                                matched_pic_url = place_map[matched_title]
                                
                                # 🚀 核心修正：解決修改行程後常常沒圖片的問題！
                                # 如果 ResortKnowledgeItem 資料表中的 PicUrl 為空，進行智慧型後端配圖兜底，
                                # 確保寫入資料庫的 pic_url 永遠有效，前端能立刻顯示精美大圖！
                                pic_url_to_save = matched_pic_url if matched_pic_url else ""
                                if not pic_url_to_save:
                                    title_lower = matched_title.lower()
                                    if any(k in title_lower for k in ["溫泉", "spa", "湯屋", "風呂", "泡湯", "風呂浴場"]):
                                        pic_url_to_save = "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=600&q=80"
                                    elif any(k in title_lower for k in ["餐", "食", "料理", "咖啡", "下午茶", "烤肉", "饗宴", "咖啡廳", "私廚", "餐廳", "璽舞"]):
                                        pic_url_to_save = "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=600&q=80"
                                    elif any(k in title_lower for k in ["手作", "體驗", "工坊", "文化", "美術館", "學校", "傳藝"]):
                                        pic_url_to_save = "https://images.unsplash.com/photo-1528164344705-47542687000d?auto=format&fit=crop&w=600&q=80"
                                    else:
                                        # 依分類/Preference 兜底
                                        pref = schedule.get("preference", "").strip()
                                        fallback_map = {
                                            "餐飲美食": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=600&q=80",
                                            "在地文化": "https://images.unsplash.com/photo-1528164344705-47542687000d?auto=format&fit=crop&w=600&q=80",
                                            "溫泉公園": "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=600&q=80",
                                            "觀光園區": "https://images.unsplash.com/photo-1500627869374-13cd993b1115?auto=format&fit=crop&w=600&q=80",
                                        }
                                        pic_url_to_save = fallback_map.get(pref, "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=600&q=80")
                                
                                # 🚀 智慧鍵名相容層 (防禦性解析時間欄位)：
                                parsed_time = (
                                    schedule.get("time") or 
                                    schedule.get("Time") or 
                                    schedule.get("ScheduleTime") or 
                                    schedule.get("scheduleTime") or 
                                    schedule.get("schedule_time") or 
                                    "00:00"
                                ).strip()

                                db.execute(insert_sql, {
                                    "schedule_id": str(uuid.uuid4()).upper(),
                                    "rec_id": rec_id,
                                    "date": date,
                                    "time": parsed_time,  # 🚀 使用多重容錯後取出的時間，告別 00:00！
                                    "title": matched_title,  # 自動修正回資料庫完全合法的 PlaceName！
                                    "content": schedule.get("content", "").strip(),
                                    "preference": schedule.get("preference", "系統推薦"),
                                    "pic_url": pic_url_to_save  # 🚀 改為寫入兜底後的安全圖片！
                                })
                                print(f"💚 [智慧容錯對齊] 成功將 AI 行程標題【{new_title}】修復並寫入資料庫合法欄位【{matched_title}】，時間設為【{parsed_time}】，圖片設為【{pic_url_to_save}】。")
                            else:
                                print(f"🚫 [阻擋機制觸發] 行程標題【{new_title}】非合法景點名稱，且無法安全修復，已拒絕寫入. ")
                                continue
                    
                    db.commit()
                    print(f"💾 成功將 {date} 的新行程狀態寫入資料庫並完成 Transaction Commit。")
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

        # =====================================================================
        # 🚀 核心修改：完全對接並調用 text_to_speech_itinerary 產生語音回應
        # =====================================================================
        audio_b64 = self._generate_tts_base64(llm_response_text, country_code)

        # 🚀 關鍵回傳更新：傳回真實修改寫入的 target date 欄位，確保前端能同步定位，不發生跳頁跑色！
        return {
            "success": True,
            "message": llm_response_text,
            "audio_base64": audio_b64,
            "date": date 
        }

# 單例實例化
itinerary_service = ItineraryService()