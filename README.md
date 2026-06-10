# Resort VIP API

渡假村 VIP 前台 API

**Tech stack:** FastAPI · SQL Server · SQLAlchemy · JWT · RAG / Vector Database（規劃中）

---

## Requirements

- Python 3.12.9
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
DB_SERVER=your_server
DB_DATABASE=your_database
DB_USERNAME=your_username
DB_PASSWORD=your_password
DB_DRIVER=ODBC Driver 18 for SQL Server

JWT_SECRET_KEY=your_secret_key

FRONTEND_ORIGIN=http://localhost:3000
```

---

## Running

```bash
uvicorn app.main:app --reload --port 8001
```

Swagger UI：[http://localhost:8001/docs](http://localhost:8001/docs)

---

## API

### Authentication

#### POST `/api/auth/login`

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

登入驗證流程：`IsActive` → `ExpireAt` → `PasswordHash`，成功後更新 `LastLoginAt`。

### Assistant

受 JWT Bearer 保護，請於 Header 帶入 `Authorization: Bearer <token>`。

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/assistant/speech-to-text` | 語音轉文字（stub） |
| POST | `/api/assistant/send-msg` | 傳送訊息給 AI 助理（stub） |

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

---

## Database

```
CustomerVipAccount
  └─ Customer
       └─ BookingStay → Room → RoomType
```
