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

# Swagger UI
# http://localhost:8001/docs
```

No test suite is currently configured.

## Required `.env` Variables

```env
DB_SERVER=
DB_DATABASE=
DB_USERNAME=
DB_PASSWORD=
DB_DRIVER=ODBC Driver 18 for SQL Server   # optional, this is the default
JWT_SECRET_KEY=
FRONTEND_ORIGIN=http://localhost:3000     # controls CORS allow_origins
```

## Critical Version Constraint

**Do not upgrade `bcrypt` to ≥ 5.0.0.** This API must stay compatible with password hashes created by the Resort VIP Admin API. The locked versions are:

```
passlib==1.7.4
bcrypt==4.0.1
```

Upgrading bcrypt breaks password verification (72-byte truncation error and hash incompatibility).

## Architecture

### Request Flow

```
HTTP request
  → CORSMiddleware (FRONTEND_ORIGIN allowlist)
  → APIRouter  (app/api/)
  → Depends(get_current_user)  — JWT bearer validation (app/dependencies/auth_dependency.py)
  → Depends(get_db)            — SQLAlchemy session (app/core/database.py)
  → Service class  (app/services/)
  → ORM models  (app/models/)
```

### Layer Responsibilities

| Layer | Location | Notes |
|---|---|---|
| Config | `app/core/config.py` | `Settings` via pydantic-settings; singleton `settings` imported everywhere |
| Database | `app/core/database.py` | SQL Server via pyodbc (`mssql+pyodbc`); `get_db()` yields a session |
| Security | `app/core/security.py` | `verify_password` (bcrypt, slices input to 72 bytes), `create_access_token` (HS256 JWT) |
| Auth dep | `app/dependencies/auth_dependency.py` | `get_current_user` — decodes JWT Bearer, returns payload dict |
| Models | `app/models/` | SQLAlchemy ORM; table names match PascalCase SQL Server columns exactly |
| Schemas | `app/schemas/` | Pydantic v2 request/response models |
| Services | `app/services/` | Business logic; `AuthService` is instantiated per-request with a `db` session; `AssistantService` is a module-level singleton |
| Routers | `app/api/` | FastAPI `APIRouter`; prefix pattern `/api/<domain>` |

### Database Schema (relevant tables)

```
CustomerVipAccount (LoginAccount, PasswordHash, IsActive, ExpireAt, LastLoginAt, CustomerId)
  └─ Customer (CustomerId, FullName, Email, MobilePhone)
       └─ BookingStay → Room → RoomType
```

Login validates `IsActive`, `ExpireAt`, and bcrypt hash, then stamps `LastLoginAt`.

### JWT Payload

```json
{ "sub": "<CustomerVipAccountId>", "customer_id": "<CustomerId>", "login_account": "<LoginAccount>", "exp": ... }
```

`get_current_user` returns this raw dict; downstream handlers access fields by key.

### Adding a New Feature

1. Add an ORM model in `app/models/` if a new table is needed.
2. Add Pydantic schemas in `app/schemas/`.
3. Add a service class (or method) in `app/services/`.
4. Add a router in `app/api/` and register it in `app/main.py` with `app.include_router(...)`.
5. Protected endpoints use `Depends(get_current_user)` and `Depends(get_db)`.
