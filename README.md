# Resort VIP API

渡假村 VIP 前台 API，提供 VIP 會員登入、AI 智慧助理、專屬導遊（AI 景點辨識與導覽）、景點推薦、行程查詢等服務。

**Tech stack:** FastAPI · SQL Server · SQLAlchemy · JWT · Azure OpenAI / Gemini (LLM、Embedding、TTS、STT) · Qdrant (RAG，兩套獨立向量庫) · Azure Speech · Azure Blob Storage

---

## Requirements

- Python 3.12+
- ODBC Driver 18 for SQL Server

---

## Installation

```bash
# 建立並啟用虛擬環境
python -m venv .venv
.venv\Scripts\activate

# 安裝套件
pip install -r requirements.txt
```

---

## Configuration

在專案根目錄建立 `.env` 檔案。本專案有**兩套獨立的 AI 子系統**，各自有自己的供應商切換：

- **智慧助理**（`AI_PROVIDER` / `EMBEDDING_PROVIDER`），使用主要 Qdrant collection。
- **專屬導遊**（`GUIDE_MODEL_PROVIDER` / `GUIDE_EMBEDDING_PROVIDER`），使用獨立的 Qdrant collection 與 Azure Blob Storage 存放景點圖片。

`TTS_PROVIDER`、`SPEECH_PROVIDER` 為共用設定，智慧助理與專屬導遊皆透過同一組開關做語音合成／辨識。

```env
# Database
DB_SERVER=your_server
DB_DATABASE=your_database
DB_USERNAME=your_username
DB_PASSWORD=your_password
DB_DRIVER=ODBC Driver 18 for SQL Server

# JWT
JWT_SECRET_KEY=your_secret_key

# CORS
FRONTEND_ORIGIN=http://localhost:3000

# 語音辨識 STT（智慧助理 + 專屬導遊共用）：azure | gemini
SPEECH_PROVIDER=azure
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=your_region

# 語音合成 TTS（智慧助理 + 專屬導遊共用）：gemini | azure
TTS_PROVIDER=gemini
AZURE_OPENAI_TTS_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_TTS_KEY=your_key
AZURE_OPENAI_TTS_VERSION=2025-03-01-preview
AZURE_OPENAI_TTS_DEPLOYMENT=gpt-4o-mini-tts
AZURE_OPENAI_TTS_VOICE=nova
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_TTS_VOICE=Kore

# 智慧助理 AI Provider：azure | gemini | lmstudio
AI_PROVIDER=azure
EMBEDDING_PROVIDER=azure

# Azure OpenAI（AI_PROVIDER=azure、EMBEDDING_PROVIDER=azure 或 GUIDE_MODEL_PROVIDER=azure 時必填）
AZURE_OPENAI_BASE_URL=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment
AZURE_OPENAI_EMBEDDING_MODEL=your_embedding_model

# Gemini（AI_PROVIDER=gemini 或 EMBEDDING_PROVIDER=gemini 時必填）
GEMINI_API_KEY=
GEMINI_MODEL_NAME=
GEMINI_EMBEDDING_MODEL=

# LM Studio（AI_PROVIDER=lmstudio 時必填）
LMSTUDIO_BASE_URL=
LMSTUDIO_API_KEY=
LMSTUDIO_MODEL_NAME=

# OpenWeatherMap
OPEN_WEATHER_MAP_API_KEY=your_key

# Qdrant — 智慧助理主要 RAG 向量庫
QDRANT_URL=your_url
QDRANT_API_KEY=your_key
QDRANT_COLLECTION_NAME=your_collection
QDRANT_TIMEOUT_SECONDS=30

# Azure Translator（智慧助理多語系）
AZURE_TRANSLATOR_KEY=your_key
AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com/
AZURE_TRANSLATOR_REGION=your_region

# Google Cloud（Vertex AI / service account）
# GOOGLE_APPLICATION_CREDENTIALS：金鑰檔案路徑，供 GeminiEmbeddings（Vertex AI）使用
# GOOGLE_CREDENTIALS_JSON：service account JSON 字串，供 GeminiTtsService（Google Cloud TTS）使用
GOOGLE_CREDENTIALS_JSON=
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=

# 專屬導遊（Guide）— 獨立的 LLM / Embedding Provider 設定
GUIDE_MODEL_PROVIDER=gemini       # gemini | azure
GUIDE_EMBEDDING_PROVIDER=gemini   # 目前僅支援 gemini
GUIDE_GEMINI_API_KEY=             # 未設定時退回使用 GEMINI_API_KEY
GUIDE_GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GUIDE_EMBEDDING_DIM=3072
GUIDE_GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite

# 專屬導遊向量資料庫（目前僅支援 qdrant）
GUIDE_VECTOR_DB_BACKEND=qdrant
GUIDE_QDRANT_URL=your_url
GUIDE_QDRANT_API_KEY=your_key
GUIDE_QDRANT_COLLECTION_NAME=resort_guide
GUIDE_QDRANT_TIMEOUT_SECONDS=180

# Azure Blob Storage — 儲存專屬導遊景點原始圖片
AZURE_STORAGE_AUTH_MODE=connection_string
AZURE_STORAGE_ACCOUNT_NAME=
AZURE_STORAGE_CONTAINER_NAME=
AZURE_STORAGE_CONNECTION_STRING=

ASSET_BASE_URL=
```

---

## Running

### 本地開發

```bash
uvicorn app.main:app --reload --port 8001
```

Swagger UI：[http://localhost:8001/docs](http://localhost:8001/docs)

### Docker

```bash
# 建置映像
docker build -t restor-vip-api .

# 執行容器（讀取 .env 設定）
docker run --env-file .env -p 8001:8001 restor-vip-api
```

容器使用非 root 使用者（`appuser`）運行，並內建 MSSQL ODBC Driver 18。

---

## Architecture

### Request Flow

```
HTTP request
  → CORSMiddleware (FRONTEND_ORIGIN allowlist)
  → APIRouter  (app/api/)
  → Depends(get_current_user)  — JWT Bearer 驗證
  → Depends(get_db)            — SQLAlchemy session
  → Service  (app/services/)
  → ORM models（app/models/）或 raw SQL（無 ORM model 的表）
```

### Layer Responsibilities

| Layer | Location | Notes |
|---|---|---|
| Config | `app/core/config.py` | pydantic-settings `Settings` singleton |
| Database | `app/core/database.py` | SQL Server via pyodbc (`mssql+pyodbc`) |
| Security | `app/core/security.py` | bcrypt 驗證、HS256 JWT 簽發 |
| Auth dep | `app/dependencies/auth_dependency.py` | `get_current_user` — 解碼 JWT Bearer |
| Models | `app/models/` | SQLAlchemy ORM，僅涵蓋 Auth / Itinerary 相關表 |
| Schemas | `app/schemas/` | Pydantic v2 request/response |
| Services | `app/services/` | 業務邏輯 |
| Agents | `app/agents/` | 智慧助理 AI agent 封裝（RAG、天氣、交通） |
| AI | `app/ai/` | 智慧助理可切換的 LLM 後端（Azure OpenAI / Gemini / LM Studio） |
| Tools | `app/tools/` | LangChain tools（RAG、天氣、交通） |
| Prompts | `app/prompts/` | Prompt 範本 |
| Guide services | `app/services/guide_*.py` | 專屬導遊子系統，獨立的 LLM / Embedding / 向量庫 / 圖片儲存設定，詳見下方「專屬導遊」章節 |
| Speech services | `app/services/speech_to_text_service.py`、`text_to_speech_service.py` | 依 `SPEECH_PROVIDER` / `TTS_PROVIDER` 分派到 Azure 或 Gemini 實作，智慧助理與專屬導遊共用 |
| Routers | `app/api/` | FastAPI `APIRouter`；前綴 `/api/<domain>` |

### Database Schema

```
CustomerVipAccount (CustomerVipAccountId, LoginAccount, PasswordHash, IsActive, ExpireAt, LastLoginAt, CustomerId)
  └─ Customer (CustomerId, FullName, Email, MobilePhone)
       └─ BookingStay → Room → RoomType

CustomerVipLoginToken (TokenHash, CustomerVipAccountId, ExpireAt, UsedAt, ...)
CustomerServiceRequest (RequestNo, CustomerVipAccountId, CustomerId, BookingStayId,
                        RoomId, RoomNo, CustomerName, Message, Status, PriorityLevel, CreatedAt)

# 以 raw SQL 查詢（app/services/attraction_service.py），未建立 ORM model：
VipItineraryRecommendation / VipItinerarySchedule (Title, Preference, Latitude, Longitude, ...)
```

### JWT Payload

```json
{ "sub": "<CustomerVipAccountId>", "customer_id": "<CustomerId>", "login_account": "<LoginAccount>", "exp": "..." }
```

Token 有效期：480 分鐘（8 小時）。

---

## API

### Auth

#### POST `/api/auth/login`

帳密登入。驗證流程：`IsActive` → `ExpireAt` → `PasswordHash`，成功後更新 `LastLoginAt`。

Request：

```json
{
  "login_account": "TNS1PUBO",
  "password": "your_password"
}
```

Response：

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "customer_vip_account_id": "uuid",
  "customer_id": "uuid",
  "login_account": "TNS1PUBO",
  "full_name": "王小明",
  "email": "test@example.com",
  "mobile_phone": "0912345678",
  "room_type_name": "豪華海景套房",
  "room_no": "A101"
}
```

#### POST `/api/auth/vip-login`

Magic Link 一次性 Token 登入（由 Admin API 發送信件）。驗證 `UsedAt IS NULL` 且 `ExpireAt > now`，成功後標記 `UsedAt`。

Request：

```json
{ "token": "one-time-token" }
```

---

### Assistant

受 JWT Bearer 保護。請於 Header 帶入 `Authorization: Bearer <token>`。

助理收到訊息後，經由以下流程處理：

```
使用者訊息
  → STT（SPEECH_PROVIDER：azure | gemini）
  → NLP（Azure Translator 語言偵測 + 翻譯為中文）
  → Intent Classifier（意圖分類）
      ├─ qa              → RAG 搜尋（主要 Qdrant）→ 組合回答
      └─ service_request → 寫入客服需求單（CustomerServiceRequest）
  → 翻譯回使用者語言
  → TTS（TTS_PROVIDER：gemini | azure）
  → 回傳
```

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/assistant/speech-to-text` | 上傳音訊檔，語音轉文字後送入助理處理 |
| POST | `/api/assistant/send-msg` | 傳送文字訊息給 AI 助理 |
| POST | `/api/assistant/text-to-speech` | 文字轉語音，回傳 `audio/mpeg` |

#### POST `/api/assistant/speech-to-text`

Request：`multipart/form-data`，欄位 `file`（音訊檔）。

Response：

```json
{
  "text": "辨識出的文字",
  "reply": "助理回覆",
  "language": "zh-TW"
}
```

#### POST `/api/assistant/send-msg`

Request：

```json
{ "message": "你好，請問游泳池幾點開放？" }
```

Response：

```json
{
  "reply": "游泳池開放時間為 07:00–22:00。",
  "language": "zh-TW"
}
```

#### POST `/api/assistant/text-to-speech`

Request：

```json
{
  "text": "歡迎光臨",
  "language": "zh-TW"
}
```

Response：`audio/mpeg` 二進位串流。

---

### Guide（專屬導遊）

受 JWT Bearer 保護。這是與智慧助理**完全獨立**的 AI 子系統：拍照 / 語音 / 文字辨識渡假村景點，並提供導覽解說與追問。使用獨立的 Qdrant collection、獨立的 LLM / Embedding provider（`GUIDE_MODEL_PROVIDER` / `GUIDE_EMBEDDING_PROVIDER`），圖片存放在 Azure Blob Storage。

```
使用者輸入（照片 / 語音 / 文字）
  → [有語音] STT（SPEECH_PROVIDER）
  → 依文字內容自動判斷回覆語言（正則判斷 CJK / 假名 / 諺文 / 拉丁字母，非 NLP 服務）
  → 建立查詢向量（文字 → GUIDE_EMBEDDING_PROVIDER；圖片 → 記憶體內轉檔後 embedding，不落地）
  → 已鎖定景點（帶 attraction_title 且無新圖片）→ 追問模式
     否則                                      → 景點辨識模式
       於專屬導遊 Qdrant collection 搜尋，依 entity_id 聚合，最低信心分數 0.70
       追問時會偵測是否切換到其他地點，避免誤用別的景點資料回答
  → LLM（GUIDE_MODEL_PROVIDER）產生導覽文字
  → 代表圖片由 Azure Blob Storage 讀取（HEIC/HEIF 於記憶體內轉 JPEG）
  → TTS（TTS_PROVIDER）合成語音，以 base64 直接回傳
```

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/guide/analyze` | 上傳照片 / 語音 / 文字，辨識景點並回傳導覽文字 + 語音 |
| POST | `/api/guide/text-to-speech` | 專屬導遊專用 TTS，回傳 `audio/mpeg`，不儲存音檔 |
| GET | `/api/guide/images/{image_path}` | 讀取 Azure Blob Storage 中的原始景點圖片 |
| GET | `/api/guide/converted-images/{filename}` | 舊版 HEIC→JPG 轉檔圖片路徑（目前流程改為即時記憶體轉檔） |

#### POST `/api/guide/analyze`

Request：`multipart/form-data`

| 欄位 | 說明 |
|---|---|
| `language` | 前端 UI 語言，作為無法從文字判斷語言時的 fallback（預設 `zh-TW`） |
| `image` | 選填，景點照片 |
| `text` | 選填，文字問題 |
| `voice` | 選填，語音檔，會先經 STT 轉文字 |
| `attraction_title` | 選填，已鎖定景點名稱（用於追問，不上傳新圖片時生效） |
| `user_name` | 選填，用於在回覆開頭稱呼使用者 |
| `history` | 選填，對話歷史 |

Response：

```json
{
  "success": true,
  "title": "綠舞觀光渡假村",
  "location": "基礎介紹",
  "guideMessage": "王小明，這裡是綠舞觀光渡假村...",
  "audioUrl": "",
  "imageUrl": "https://.../images/main.jpg",
  "user_text": "這是哪裡？",
  "responseLanguage": "zh-TW",
  "audio_base64": "..."
}
```

#### POST `/api/guide/text-to-speech`

Request：

```json
{
  "text": "歡迎來到綠舞觀光渡假村",
  "language": "zh-TW"
}
```

Response：`audio/mpeg` 二進位串流。

---

### Attractions

受 JWT Bearer 保護。

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/attractions/recommended` | 取得當前 VIP 會員的推薦景點清單（含經緯度，供前端地圖顯示） |

#### GET `/api/attractions/recommended`

依 `VipItineraryRecommendation` / `VipItinerarySchedule` 兩表 join 目前登入會員的推薦行程，回傳有經緯度的景點。

Response：

```json
[
  {
    "attraction_id": "蘭陽博物館",
    "place_name": "蘭陽博物館",
    "category": "文化園區",
    "latitude": 24.869,
    "longitude": 121.821
  }
]
```

---

### Itinerary

受 JWT Bearer 保護。

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/itinerary/exclusive-itinerary` | 取得當前 VIP 會員的專屬行程 |
| POST | `/api/itinerary/feedback` | 提交行程意見回饋 |

#### GET `/api/itinerary/exclusive-itinerary`

依入住日期分組回傳行程安排。

#### POST `/api/itinerary/feedback`

Request：

```json
{
  "message": "非常滿意，期待下次入住。",
  "date": "2026-07-03",
  "lang": "zh"
}
```

Response：

```json
{
  "success": true,
  "message": "感謝您的回饋！",
  "audio_base64": "..."
}
```

---

## Important: Package Version Lock

本專案需與 **Resort VIP Admin API** 共用相同的 bcrypt 密碼雜湊格式，**禁止升級 bcrypt 至 ≥ 5.0.0**。

```
passlib==1.7.4
bcrypt==4.0.1
```

升級後會導致：

- `ValueError: password cannot be longer than 72 bytes`
- 既有 `PasswordHash` 無法驗證

若版本錯誤，執行以下指令還原：

```bash
pip uninstall bcrypt -y
pip install bcrypt==4.0.1
```
