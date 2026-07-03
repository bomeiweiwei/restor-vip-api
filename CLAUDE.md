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

There are **two independent AI subsystems** in this project, each with its own provider switches:

- The **assistant** pipeline (`app/services/assistant_service.py` and friends) — controlled by `AI_PROVIDER` / `EMBEDDING_PROVIDER`, backed by the main Qdrant collection (`QDRANT_*`).
- The **Guide** ("專屬導遊") pipeline (`app/services/guide_service.py`) — controlled by `GUIDE_MODEL_PROVIDER` / `GUIDE_EMBEDDING_PROVIDER`, backed by its own Qdrant collection (`GUIDE_QDRANT_*`) and Azure Blob Storage for images.

`TTS_PROVIDER` and `SPEECH_PROVIDER` are shared — both the assistant and the Guide feature synthesize/transcribe speech through the same two switches.

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

# Speech-to-text provider (assistant + Guide): azure | gemini
SPEECH_PROVIDER=azure
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=

# Text-to-speech provider (assistant + Guide): gemini | azure
TTS_PROVIDER=gemini
AZURE_OPENAI_TTS_ENDPOINT=
AZURE_OPENAI_TTS_KEY=
# AZURE_OPENAI_TTS_VERSION defaults to 2025-03-01-preview
# AZURE_OPENAI_TTS_DEPLOYMENT defaults to gpt-4o-mini-tts
# AZURE_OPENAI_TTS_VOICE defaults to nova
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts   # reserved; GeminiTtsService currently calls Google Cloud TTS instead
GEMINI_TTS_VOICE=Kore                           # reserved, see above

# --- Assistant AI provider: azure | gemini | lmstudio ---
AI_PROVIDER=azure
EMBEDDING_PROVIDER=azure

# Azure OpenAI (required when AI_PROVIDER=azure, EMBEDDING_PROVIDER=azure, or GUIDE_MODEL_PROVIDER=azure)
AZURE_OPENAI_BASE_URL=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT_NAME=
AZURE_OPENAI_EMBEDDING_MODEL=

# Gemini (required when AI_PROVIDER=gemini or EMBEDDING_PROVIDER=gemini)
GEMINI_API_KEY=
GEMINI_MODEL_NAME=
GEMINI_EMBEDDING_MODEL=

# LM Studio (required when AI_PROVIDER=lmstudio)
LMSTUDIO_BASE_URL=
LMSTUDIO_API_KEY=
LMSTUDIO_MODEL_NAME=

# OpenWeatherMap
OPEN_WEATHER_MAP_API_KEY=

# Qdrant — main assistant RAG vector store
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=
QDRANT_TIMEOUT_SECONDS=

# Azure Translator (NLP / multilingual support for the assistant pipeline)
AZURE_TRANSLATOR_KEY=
AZURE_TRANSLATOR_ENDPOINT=
AZURE_TRANSLATOR_REGION=

# --- Google Cloud (Vertex AI + service-account auth) ---
# GOOGLE_APPLICATION_CREDENTIALS: file path, used by GeminiEmbeddings (Vertex AI genai.Client)
# GOOGLE_CREDENTIALS_JSON: raw service-account JSON string, used by GeminiTtsService
#   (Google Cloud Text-to-Speech) — this is a different auth path from GUIDE_GEMINI_API_KEY.
GOOGLE_CREDENTIALS_JSON=
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=

# --- Guide ("專屬導遊") feature: independent LLM/embedding provider switches ---
GUIDE_MODEL_PROVIDER=gemini       # gemini | azure
GUIDE_EMBEDDING_PROVIDER=gemini   # gemini only, currently
GUIDE_GEMINI_API_KEY=             # falls back to GEMINI_API_KEY if unset
GUIDE_GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GUIDE_EMBEDDING_DIM=3072
GUIDE_GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite

# Guide vector DB backend (currently only "qdrant" is wired up)
GUIDE_VECTOR_DB_BACKEND=qdrant
GUIDE_QDRANT_URL=
GUIDE_QDRANT_API_KEY=
GUIDE_QDRANT_COLLECTION_NAME=resort_guide
GUIDE_QDRANT_TIMEOUT_SECONDS=180

# Azure Blob Storage — stores Guide's source images (source_path in Qdrant payload = blob name)
AZURE_STORAGE_AUTH_MODE=connection_string
AZURE_STORAGE_ACCOUNT_NAME=
AZURE_STORAGE_CONTAINER_NAME=
AZURE_STORAGE_CONNECTION_STRING=

ASSET_BASE_URL=
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
  → ORM models  (app/models/)  — or raw SQL via `text()` for tables with no ORM model
```

### Layer Responsibilities

| Layer | Location | Notes |
|---|---|---|
| Config | `app/core/config.py` | `Settings` via pydantic-settings; singleton `settings` imported everywhere |
| Database | `app/core/database.py` | SQL Server via pyodbc (`mssql+pyodbc`); `get_db()` yields a session |
| Security | `app/core/security.py` | `verify_password` (bcrypt, slices input to 72 bytes), `create_access_token` (HS256 JWT) |
| Auth dep | `app/dependencies/auth_dependency.py` | `get_current_user` — decodes JWT Bearer, returns payload dict |
| Models | `app/models/` | SQLAlchemy ORM; table/column names match PascalCase SQL Server names exactly. Only covers Auth/Itinerary tables — Attraction/Guide data is queried with raw SQL or lives outside SQL Server entirely |
| Schemas | `app/schemas/` | Pydantic v2 request/response models |
| Services | `app/services/` | Business logic; see instantiation patterns below |
| Agents | `app/agents/` | Assistant-pipeline AI task agents (`ResortQAAgentService`, `WeatherAgentService`, `TrafficAgentService`) |
| AI | `app/ai/` | Swappable LLM backends for the assistant pipeline; `create_ai_langchain(ai_type)` returns a `BaseAILangchain` |
| Embedding | `app/ai/embedding_factory.py` | `get_embedding_function()` resolves from `EMBEDDING_PROVIDER` (assistant pipeline only — Guide has its own, see below) |
| Tools | `app/tools/` | LangChain tool wrappers (`rag_tool`, `weather_tool`, `traffic_tool`) |
| Prompts | `app/prompts/` | Prompt templates as module-level string constants |
| Enums | `app/enums/` | `AiType` (azure/gemini/lmstudio), `SpeechType` and `TtsType` (azure/gemini) |
| Routers | `app/api/` | FastAPI `APIRouter`; prefix pattern `/api/<domain>`; registered in `app/main.py` |
| Guide services | `app/services/guide_*.py` | See "AI Tour Guide Pipeline" below — a self-contained subsystem with its own model/embedding/vector-DB/image-storage wiring |
| Speech services | `app/services/speech_to_text_service.py`, `text_to_speech_service.py` | Thin dispatchers that route to `azure_*` or `gemini_*` implementations based on `SPEECH_PROVIDER` / `TTS_PROVIDER`; shared by the assistant and Guide routers |

### Service Instantiation Patterns

- **Per-request (stateful DB session):** `AuthService`, `ItineraryService` — instantiated inside the route function with `AuthService(db)`.
- **Module-level singletons:** Most other services (`assistant_service`, `intent_classifier_service`, `qa_service`, `nlp_service`, `judge_user_input_service`, `customer_service_request_service`, `attraction_service`, `speech_to_text_service`, `text_to_speech_service`, agents, tools) — created once at import time; receive `db` and `current_user` as method arguments when needed.
- **Lazy singleton via `@lru_cache`:** `get_rag_search_service()` (assistant RAG, connects to Qdrant on first call) and `get_guide_service()` (Guide feature — deliberately deferred so `uvicorn` startup doesn't eagerly connect to the Guide's Qdrant/Gemini clients; only the first `/api/guide/analyze` call constructs `GuideCoreService`).

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

# Queried via raw SQL (app/services/attraction_service.py) — no ORM model:
VipItineraryRecommendation (RecommendationId, CustomerId, ...)
VipItinerarySchedule (RecommendationId, Title, Preference, Latitude, Longitude, ...)
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
  ├─ [speech-to-text]  speech_to_text_service → SPEECH_PROVIDER (azure|gemini) → transcribed text + detected language
  │
  ├─ NlpService.analyze_user_text()
  │     Azure Translator: detect language → translate to zh-Hant
  │     Supported output languages: zh-TW, en-US, ja-JP, ko-KR
  │
  ├─ JudgeUserInputService.judge()
  │     IntentClassifierService.classify()  — LLM + PydanticOutputParser
  │       → IntentResult { intent: "qa" | "service_request" | "unsupported", qa_tasks: [...], confidence, reason }
  │
  │     intent == "qa"
  │       QAService.process()
  │         for each QATask:
  │           weather    → WeatherAgentService
  │           traffic    → TrafficAgentService
  │           others     → ResortQAAgentService → RagTool → RagSearchService (main Qdrant)
  │         LLM assembles final answer from all task results
  │
  │     intent == "service_request"
  │       CustomerServiceRequestService.process()
  │         Writes a row to CustomerServiceRequest (status=Pending, priority=Normal)
  │         Returns request number REQ-XXXXXX
  │
  └─ NlpService.translate_reply()  — translate answer back to user's language
```

### QA Categories (`qa_category` values, `app/tools/rag_tool.py`)

| Category | RAG Vector Store Filters |
|---|---|
| `facility_hours` | 戶外設施, 室內設施 |
| `attraction_hours` | 戶外/室內旅遊景點, 戶外/室內景點, 文化園區, 日式主題園區, 在地文化, 動物園, 博物館, 溫泉公園, 觀光園區, 觀光農場 |
| `facility_info` | 戶外設施, 室內設施 |
| `restaurant` | 餐飲美食 |
| `attraction` | all outdoor/indoor activities, facilities, sightseeing, and cultural categories, plus 基礎介紹 |
| `rules` | 基礎介紹 |
| `price` | 基礎介紹 |
| `room_facility` | 基礎介紹 |
| `room_service` | 基礎介紹 |
| `weather` | → `WeatherAgentService` (OpenWeatherMap), no RAG |
| `traffic` | → `TrafficAgentService`, no RAG |

### Swapping the Assistant's LLM Backend

Change `AI_PROVIDER` in `.env` to `azure`, `gemini`, or `lmstudio`. All assistant services call `create_ai_langchain(settings.AI_PROVIDER)` at singleton init time, so the server must be restarted after a change. `EMBEDDING_PROVIDER` controls vector embeddings independently. This is separate from the Guide feature's provider switches (below).

## AI Tour Guide Pipeline (`/api/guide/*`)

A second, independent AI subsystem ("專屬導遊") that identifies a resort attraction from a photo, voice clip, and/or text, then answers questions about it. It does not share Qdrant collections, embedding models, or LLM provider config with the assistant pipeline above — only `SPEECH_PROVIDER` and `TTS_PROVIDER` are shared.

```
POST /api/guide/analyze  (multipart: image?, text?, voice?, attraction_title?, user_name?, history?, language)
  │
  ├─ [voice provided] speech_to_text_service → SPEECH_PROVIDER → transcribed text
  │
  ├─ Regex-based language auto-detection on the combined user text
  │     (GuideCoreService._detect_language_from_text — CJK/Hangul/Kana/Latin ranges;
  │      NOT the same mechanism as the assistant's Azure-Translator-based NlpService)
  │
  ├─ Build query vector(s): text → GUIDE_EMBEDDING_PROVIDER embedding;
  │                          image bytes → embed_image_bytes (in-memory HEIC/WEBP/etc. → PNG conversion, never written to disk)
  │
  ├─ if `attraction_title` is set and there's no new image → answer_followup()
  │    else                                                → recognize_place()
  │       Search Guide's own Qdrant collection (GUIDE_QDRANT_COLLECTION_NAME, default "resort_guide")
  │       Aggregate hits by entity_id; reject if best_score < 0.70 confidence threshold
  │       Alias-matching guard prevents follow-up questions from being answered using a
  │       different attraction's data (e.g. asking about "台北101" while locked to "綠舞渡假村")
  │
  ├─ GUIDE_MODEL_PROVIDER (gemini|azure) LLM generates the answer from retrieved text chunks
  │     falls back to a short canned answer per-language if the LLM call fails/retries are exhausted
  │
  ├─ Representative images resolved from Qdrant payload `source_path` → served from Azure Blob Storage
  │     via GET /api/guide/images/{path} (HEIC/HEIF converted to JPEG in-memory on read)
  │
  └─ TTS_PROVIDER synthesizes the answer → returned inline as `audio_base64` (no /text-to-speech round trip needed)
```

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/guide/analyze` | Main entry point: identify an attraction and answer, per the flow above |
| POST | `/api/guide/text-to-speech` | Guide-specific TTS; returns `audio/mpeg` (does not persist audio) |
| GET | `/api/guide/images/{image_path:path}` | Streams an original image from Azure Blob Storage |
| GET | `/api/guide/converted-images/{filename}` | Legacy path for pre-converted HEIC→JPG images; current flow converts in-memory instead |

`GuideService` is a lazy `@lru_cache` singleton (`get_guide_service()`) wrapping `GuideCoreService`, so importing `app.services.guide_service` does not connect to Qdrant/Gemini until the first request.

## Adding a New Feature

1. Add an ORM model in `app/models/` if a new table is needed (or use raw SQL via `text()` for read-only/reporting queries, as `attraction_service.py` does).
2. Add Pydantic schemas in `app/schemas/`.
3. Add a service class (or method) in `app/services/`.
4. Add a router in `app/api/` and register it in `app/main.py` with `app.include_router(...)`.
5. Protected endpoints use `Depends(get_current_user)` and `Depends(get_db)`.
6. If adding a new assistant AI agent, follow the pattern in `app/agents/` — a thin class that delegates to a tool or service, exposed as a module-level singleton.
7. If adding a new QA category, register it in `QA_CATEGORY_TO_RAG_CATEGORIES` (`app/tools/rag_tool.py`) and in the `QATask` literal type (`app/schemas/assistant.py`).
