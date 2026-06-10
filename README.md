# Resort VIP API

渡假村 VIP 前台 API

技術架構：

* FastAPI
* SQL Server
* SQLAlchemy
* JWT Authentication
* RAG（規劃中）
* Vector Database（規劃中）

---

# Python Environment

```bash
Python 3.12.9
```

---

# Installation

建立虛擬環境：

```bash
python -m venv .venv
```

啟用：

```bash
.venv\Scripts\activate
```

安裝套件：

```bash
pip install -r requirements.txt
```

啟動：

```bash
uvicorn app.main:app --reload --port 8001
```

Swagger：

```text
http://localhost:8001/docs
```

---

# Important Package Versions

## Password Hash

本專案需與 Resort VIP Admin API 相容。

請固定使用以下版本：

```txt
passlib==1.7.4
bcrypt==4.0.1
```

禁止升級至：

```txt
bcrypt>=5.0.0
```

否則登入驗證可能出現：

```txt
ValueError:
password cannot be longer than 72 bytes
```

或與既有 PasswordHash 不相容問題。

安裝指令：

```bash
pip uninstall bcrypt -y
pip install bcrypt==4.0.1
```

驗證版本：

```bash
pip show passlib
pip show bcrypt
```

預期結果：

```txt
passlib 1.7.4
bcrypt 4.0.1
```

---

# API

## Authentication

### Login

```http
POST /api/auth/login
```

Request

```json
{
  "login_account": "YOUR_LOGIN_ACCOUNT",
  "password": "YOUR_PASSWORD"
}
```

Response

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "customer_vip_account_id": "...",
  "customer_id": "...",
  "login_account": "TNS1PUBO",
  "full_name": "王小明",
  "email": "test@example.com",
  "mobile_phone": "0912345678"
}
```

---

# Database

主要登入資料表：

```text
CustomerVipAccount
```

關聯：

```text
CustomerVipAccount
    ↓ CustomerId
Customer
```

登入時檢查：

* LoginAccount
* PasswordHash
* IsActive
* ExpireAt

登入成功更新：

```text
LastLoginAt
```
