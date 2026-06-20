# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtualenv (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run dev server (port 8001)
uvicorn app.main:app --reload --port 8001

# Swagger UI: http://localhost:8001/docs
```

```bash
# Docker build & run
docker build -t restor-vip-api .
docker run --env-file .env -p 8001:8001 restor-vip-api
```

No test suite is currently configured.

## Required `.env` Variables

```env
# Database (SQL Server)
DB_SERVER=
DB_DATABASE=
DB_USERNAME=
DB_PASSWORD=
DB_DRIVER=ODBC Driver 18 for SQL Server   # optional, this is the default

# JWT
JWT_SECRET_KEY=
# JWT_ALGORITHM defaults to HS256
# JWT_EXPIRE_MINUTES defaults to 480 (8 hours)

# CORS
FRONTEND_ORIGIN=http://localhost:3000

# Azure Speech (STT / TTS)
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=

# AI provider selection: azure | gemini | lmstudio
AI_PROVIDER=azure
EMBEDDING_PROVIDER=azure

# Azure OpenAI (required when AI_PROVIDER=azure or EMBEDDING_PROVIDER=azure)
AZURE_OPENAI_BASE_URL=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT_NAME=
AZURE_OPENAI_EMBEDDING_MODEL=

# Gemini (optional, required when AI_PROVIDER=gemini or EMBEDDING_PROVIDER=gemini)
GEMINI_API_KEY=
GEMINI_MODEL_NAME=
GEMINI_EMBEDDING_MODEL=

# LM Studio (optional, required when AI_PROVIDER=lmstudio)
LMSTUDIO_BASE_URL=
LMSTUDIO_API_KEY=
LMSTUDIO_MODEL_NAME=

# OpenWeatherMap
OPEN_WEATHER_MAP_API_KEY=

# Qdrant (vector DB / RAG)
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=
QDRANT_TIMEOUT_SECONDS=

# Azure Translator (NLP / multilingual support)
AZURE_TRANSLATOR_KEY=
AZURE_TRANSLATOR_ENDPOINT=
AZURE_TRANSLATOR_REGION=
```

## Critical Version Constraint

**Do not upgrade `bcrypt` to ≥ 5.0.0.** This API must stay compatible with password hashes created by the Resort VIP Admin API. The locked versions are:

```
passlib==1.7.4
bcrypt==4.0.1
```

Upgrading bcrypt breaks password verification (72-byte truncation error and hash incompatibility).

To restore if wrong version is installed:

```bash
pip uninstall bcrypt -y
pip install bcrypt==4.0.1
```

## Architecture

### Request Flow

```
HTTP request
  → CORSMiddleware (FRONTEND_ORIGIN allowlist)
  → APIRouter  (app/api/)
  → Depends(get_current_user)  — JWT Bearer validation (app/dependencies/auth_dependency.py)
  → Depends(get_db)            — SQLAlchemy session (app/core/database.py)
  → Service  (app/services/)
  → ORM models  (app/models/)
```

### Layer Responsibilities

| Layer | Location | Notes |
|---|---|---|
| Config | `app/core/config.py` | `Settings` via pydantic-settings; singleton `settings` imported everywhere |
| Database | `app/core/database.py` | SQL Server via pyodbc (`mssql+pyodbc`); `get_db()` yields a session |
| Security | `app/core/security.py` | `verify_password` (bcrypt, slices input to 72 bytes), `create_access_token` (HS256 JWT) |
| Auth dep | `app/dependencies/auth_dependency.py` | `get_current_user` — decodes JWT Bearer, returns payload dict |
| Models | `app/models/` | SQLAlchemy ORM; table/column names match PascalCase SQL Server names exactly |
| Schemas | `app/schemas/` | Pydantic v2 request/response models |
| Services | `app/services/` | Business logic; see instantiation patterns below |
| Agents | `app/agents/` | AI task agents (`ResortQAAgentService`, `WeatherAgentService`, `TrafficAgentService`) |
| AI | `app/ai/` | Swappable LLM backends; `create_ai_langchain(ai_type)` returns a `BaseAILangchain` |
| Embedding | `app/ai/embedding_factory.py` | `get_embedding_function()` resolves from `EMBEDDING_PROVIDER` |
| Tools | `app/tools/` | LangChain tool wrappers (`rag_tool`, `weather_tool`, `traffic_tool`) |
| Prompts | `app/prompts/` | Prompt templates as module-level string constants |
| Enums | `app/enums/ai_type.py` | `AiType` — values: `"azure"`, `"gemini"`, `"lmstudio"` |
| Routers | `app/api/` | FastAPI `APIRouter`; prefix pattern `/api/<domain>`; registered in `app/main.py` |

### Service Instantiation Patterns

- **Per-request (stateful DB session):** `AuthService`, `ItineraryService` — instantiated inside the route function with `AuthService(db)`.
- **Module-level singletons:** All other services (`assistant_service`, `intent_classifier_service`, `qa_service`, `nlp_service`, `judge_user_input_service`, `customer_service_request_service`, agents, tools) — created once at import time; receive `db` and `current_user` as method arguments when needed.
- **Lazy singleton via `@lru_cache`:** `get_rag_search_service()` — initialised on first call, connects to Qdrant.

### Database Schema (relevant tables)

```
CustomerVipAccount (CustomerVipAccountId, CustomerId, LoginAccount, PasswordHash,
                    IsActive, ExpireAt, LastLoginAt, CreatedAt, UpdatedAt)
  └─ Customer (CustomerId, FullName, Email, MobilePhone)
       └─ BookingStay (BookingStayId, CustomerId, RoomId, CheckInDate, ...)
            └─ Room (RoomId, RoomNo, RoomTypeId)
                 └─ RoomType (RoomTypeId, RoomTypeName)

CustomerVipLoginToken (TokenHash, CustomerVipAccountId, ExpireAt, UsedAt, ...)
CustomerServiceRequest (RequestNo, CustomerVipAccountId, CustomerId, LoginAccount,
                        BookingStayId, RoomId, RoomNo, CustomerName, Message,
                        Status, PriorityLevel, CreatedAt)
```

Login validates `IsActive`, `ExpireAt`, and bcrypt hash, then stamps `LastLoginAt`.

Magic-link login validates `UsedAt IS NULL` and `ExpireAt > now` against all active tokens using bcrypt comparison (not a direct hash lookup), then marks `UsedAt`.

### JWT Payload

```json
{ "sub": "<CustomerVipAccountId>", "customer_id": "<CustomerId>", "login_account": "<LoginAccount>", "exp": "..." }
```

`get_current_user` returns this raw dict; downstream handlers access fields by key (e.g. `current_user["sub"]`, `current_user["customer_id"]`).

## AI / Assistant Pipeline

### Full Message Flow

```
User input (text or audio)
  │
  ├─ [speech-to-text]  Azure Speech SDK → transcribed text + detected language
  │
  ├─ NlpService.analyze_user_text()
  │     Azure Translator: detect language → translate to zh-Hant
  │     Supported output languages: zh-TW, en-US, ja-JP, ko-KR
  │
  ├─ JudgeUserInputService.judge()
  │     IntentClassifierService.classify()  — LLM + PydanticOutputParser
  │       → IntentResult { intent: "qa" | "service_request", qa_tasks: [...], confidence, reason }
  │
  │     intent == "qa"
  │       QAService.process()
  │         for each QATask:
  │           weather    → WeatherAgentService
  │           traffic    → TrafficAgentService
  │           others     → ResortQAAgentService → RagTool → RagSearchService (Qdrant)
  │         LLM assembles final answer from all task results
  │
  │     intent == "service_request"
  │       CustomerServiceRequestService.process()
  │         Writes a row to CustomerServiceRequest (status=Pending, priority=Normal)
  │         Returns request number REQ-XXXXXX
  │
  └─ NlpService.translate_reply()  — translate answer back to user's language
```

### QA Categories (`qa_category` values)

| Category | RAG Vector Store Filters |
|---|---|
| `facility_hours` | 戶外設施, 室內設施 |
| `attraction_hours` | 戶外/室內旅遊景點, 文化園區, 日式主題園區, 動物園, 博物館, 溫泉公園, 觀光園區, 觀光農場 |
| `facility_info` | 戶外設施, 室內設施 |
| `restaurant` | 餐飲美食 |
| `attraction` | all outdoor/indoor activities, sightseeing, and cultural categories |
| `rules` | 基礎介紹 |
| `price` | 基礎介紹 |
| `room_facility` | 基礎介紹 |
| `room_service` | 基礎介紹 |
| `weather` | → `WeatherAgentService` (OpenWeatherMap), no RAG |
| `traffic` | → `TrafficAgentService`, no RAG |

### Swapping the LLM Backend

Change `AI_PROVIDER` in `.env` to `azure`, `gemini`, or `lmstudio`. All services call `create_ai_langchain(settings.AI_PROVIDER)` at singleton init time, so the server must be restarted after a change. `EMBEDDING_PROVIDER` controls vector embeddings independently.

## Adding a New Feature

1. Add an ORM model in `app/models/` if a new table is needed.
2. Add Pydantic schemas in `app/schemas/`.
3. Add a service class (or method) in `app/services/`.
4. Add a router in `app/api/` and register it in `app/main.py` with `app.include_router(...)`.
5. Protected endpoints use `Depends(get_current_user)` and `Depends(get_db)`.
6. If adding a new AI agent, follow the pattern in `app/agents/` — a thin class that delegates to a tool or service, exposed as a module-level singleton.
7. If adding a new QA category, register it in `QA_CATEGORY_TO_RAG_CATEGORIES` (`app/tools/rag_tool.py`) and in the `QATask` literal type (`app/schemas/assistant.py`).
