import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import settings


router = APIRouter(
    prefix="/api/bus-times",
    tags=["Bus"],
)


TDX_AUTH_URL = (
    "https://tdx.transportdata.tw/auth/realms/"
    "TDXConnect/protocol/openid-connect/token"
)

# 快取 TDX access token，避免每次查公車都重新申請
cached_token: dict[str, Any] = {
    "token": None,
    "expires_at": 0.0,
}

# 防止多人同時請求時，一次申請多個 token
token_lock = asyncio.Lock()


def get_bus_api_url() -> str:
    """
    組成宜蘭縣公車預估到站 API 網址。
    """
    api_base = settings.TDX_API_BASE.rstrip("/")
    city = settings.TDX_BUS_CITY.strip()

    return (
        f"{api_base}/Bus/"
        f"EstimatedTimeOfArrival/City/{city}"
    )


async def get_tdx_token() -> str:
    """
    向 TDX 取得 access token。

    若快取中的 token 尚未過期，就直接沿用，
    避免每次查詢公車都重新驗證。
    """
    now = time.time()

    if (
        cached_token["token"]
        and now < cached_token["expires_at"]
    ):
        return str(cached_token["token"])

    async with token_lock:
        # 等待鎖期間，可能已有其他請求取得新 token
        now = time.time()

        if (
            cached_token["token"]
            and now < cached_token["expires_at"]
        ):
            return str(cached_token["token"])

        client_id = settings.TDX_CLIENT_ID.strip()
        client_secret = settings.TDX_CLIENT_SECRET.strip()

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail="TDX_CLIENT_ID 或 TDX_CLIENT_SECRET 尚未設定",
            )

        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    TDX_AUTH_URL,
                    data=payload,
                )

            if response.status_code != 200:
                print(
                    "[TDX] token 狀態碼：",
                    response.status_code,
                )
                print(
                    "[TDX] token 回傳內容：",
                    response.text,
                )

                raise HTTPException(
                    status_code=502,
                    detail="TDX 身分驗證失敗",
                )

            data = response.json()

        except httpx.TimeoutException as error:
            raise HTTPException(
                status_code=504,
                detail="TDX 身分驗證逾時",
            ) from error

        except httpx.RequestError as error:
            raise HTTPException(
                status_code=502,
                detail="無法連線至 TDX 身分驗證服務",
            ) from error

        access_token = data.get("access_token")

        if not access_token:
            print("[TDX] token 回傳內容缺少 access_token：", data)

            raise HTTPException(
                status_code=502,
                detail="TDX 未回傳 access token",
            )

        expires_in = int(data.get("expires_in", 3600))

        cached_token["token"] = access_token
        cached_token["expires_at"] = (
            time.time() + max(expires_in - 60, 60)
        )

        return str(access_token)


@router.get("", response_model=None)
async def get_bus_times():
    """
    取得宜蘭縣公車預估到站資料。

    前端會再依照：
    - 站牌名稱「大眾北路」
    - Direction 去程／回程
    篩選需要的資料。
    """
    token = await get_tdx_token()
    bus_api_url = get_bus_api_url()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    # 只取前端目前真正需要的欄位
    params = {
    "$select": (
        "PlateNumb,"
        "StopUID,"
        "StopID,"
        "StopName,"
        "RouteUID,"
        "RouteID,"
        "RouteName,"
        "Direction,"
        "EstimateTime,"
        "StopStatus,"
        "SrcUpdateTime,"
        "UpdateTime"
    ),
    "$filter": "contains(StopName/Zh_tw,'大眾北路')",
    "$top": "100",
    "$format": "JSON",
}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                bus_api_url,
                headers=headers,
                params=params,
            )

        # Token 若剛好失效，清掉快取，讓下一次重新取得
        if response.status_code == 401:
            cached_token["token"] = None
            cached_token["expires_at"] = 0.0

        if response.status_code != 200:
            print(
                "[TDX] 公車 API 狀態碼：",
                response.status_code,
            )
            print(
                "[TDX] 公車 API 回傳：",
                response.text,
            )

            raise HTTPException(
                status_code=502,
                detail="無法取得 TDX 公車資料",
            )

        data = response.json()

        if not isinstance(data, list):
            print("[TDX] 公車資料格式異常：", data)

            raise HTTPException(
                status_code=502,
                detail="TDX 公車資料格式不正確",
            )

        return data

    except HTTPException:
        raise

    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="TDX 公車資料回應逾時",
        ) from error

    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="無法連線至 TDX 公車服務",
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="TDX 回傳的內容不是有效 JSON",
        ) from error