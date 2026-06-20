# Resort VIP API

渡假村 VIP 前台 API，提供 VIP 會員登入、AI 智慧助理、行程查詢等服務。

**Tech stack:** FastAPI · SQL Server · SQLAlchemy · JWT · Azure OpenAI · Qdrant (RAG) · Azure Speech

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

在專案根目錄建立 `.env` 檔案：

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

# Azure Speech
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=your_region

# AI Provider (azure | gemini | lmstudio)
AI_PROVIDER=azure
EMBEDDING_PROVIDER=azure

# Azure OpenAI
AZURE_OPENAI_BASE_URL=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment
AZURE_OPENAI_EMBEDDING_MODEL=your_embedding_model

# Gemini (optional)
GEMINI_API_KEY=
GEMINI_MODEL_NAME=
GEMINI_EMBEDDING_MODEL=

# LM Studio (optional)
LMSTUDIO_BASE_URL=
LMSTUDIO_API_KEY=
LMSTUDIO_MODEL_NAME=

# OpenWeatherMap
OPEN_WEATHER_MAP_API_KEY=your_key

# Qdrant (Vector DB / RAG)
QDRANT_URL=your_url
QDRANT_API_KEY=your_key
QDRANT_COLLECTION_NAME=your_collection
QDRANT_TIMEOUT_SECONDS=30

# Azure Translator
AZURE_TRANSLATOR_KEY=your_key
AZURE_TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com/
AZURE_TRANSLATOR_REGION=your_region
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
  → ORM models  (app/models/)
```

### Layer Responsibilities

| Layer | Location | Notes |
|---|---|---|
| Config | `app/core/config.py` | pydantic-settings `Settings` singleton |
| Database | `app/core/database.py` | SQL Server via pyodbc (`mssql+pyodbc`) |
| Security | `app/core/security.py` | bcrypt 驗證、HS256 JWT 簽發 |
| Auth dep | `app/dependencies/auth_dependency.py` | `get_current_user` — 解碼 JWT Bearer |
| Models | `app/models/` | SQLAlchemy ORM |
| Schemas | `app/schemas/` | Pydantic v2 request/response |
| Services | `app/services/` | 業務邏輯 |
| Agents | `app/agents/` | AI agent 封裝（RAG、天氣、交通） |
| AI | `app/ai/` | 可切換的 LLM 後端（Azure OpenAI / Gemini / LM Studio） |
| Tools | `app/tools/` | LangChain tools（RAG、天氣、交通） |
| Prompts | `app/prompts/` | Prompt 範本 |
| Routers | `app/api/` | FastAPI `APIRouter`；前綴 `/api/<domain>` |

### Database Schema

```
CustomerVipAccount (CustomerVipAccountId, LoginAccount, PasswordHash, IsActive, ExpireAt, LastLoginAt, CustomerId)
  └─ Customer (CustomerId, FullName, Email, MobilePhone)
       └─ BookingStay → Room → RoomType

CustomerVipLoginToken (TokenHash, CustomerVipAccountId, ExpireAt, UsedAt, ...)
CustomerServiceRequest (RequestNo, CustomerVipAccountId, CustomerId, BookingStayId,
                        RoomId, RoomNo, CustomerName, Message, Status, PriorityLevel, CreatedAt)
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
  → NLP（語言偵測 + 翻譯為中文）
  → Intent Classifier（意圖分類）
      ├─ qa              → RAG 搜尋（Qdrant）→ 組合回答
      └─ service_request → 寫入客服需求單（CustomerServiceRequest）
  → 翻譯回使用者語言
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
{ "message": "非常滿意，期待下次入住。" }
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
