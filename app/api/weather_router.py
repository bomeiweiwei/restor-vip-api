from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings


router = APIRouter(
    prefix="/api/weather",
    tags=["Weather"],
)


def get_location_name(location: dict[str, Any]) -> str:
    """
    取得中央氣象署地點名稱。
    同時支援不同大小寫格式。
    """
    return str(
        location.get("LocationName")
        or location.get("locationName")
        or ""
    )


def get_weather_elements(
    location: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    取得指定地點的 WeatherElement 清單。
    """
    elements = (
        location.get("WeatherElement")
        or location.get("weatherElement")
        or []
    )

    if isinstance(elements, list):
        return elements

    return []


def get_time_list(
    weather_element: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    取得單一 WeatherElement 裡的預報時間清單。
    """
    time_list = (
        weather_element.get("Time")
        or weather_element.get("time")
        or []
    )

    if isinstance(time_list, list):
        return time_list

    return []


def get_element_values(
    time_item: dict[str, Any],
) -> list[Any]:
    """
    取得單一預報時段內的 ElementValue 清單。
    """
    values = (
        time_item.get("ElementValue")
        or time_item.get("elementValue")
        or []
    )

    if isinstance(values, list):
        return values

    return []


def find_first_value(
    weather_elements: list[dict[str, Any]],
    value_keys: list[str],
) -> str | None:
    """
    從所有 WeatherElement 中尋找指定欄位。

    例如：
    - Temperature
    - Weather
    - WeatherDescription

    不依賴 ElementName，因此較不容易受到
    中英文名稱或資料格式差異影響。
    """
    for weather_element in weather_elements:
        for time_item in get_time_list(weather_element):
            for value_item in get_element_values(time_item):
                if not isinstance(value_item, dict):
                    continue

                for key in value_keys:
                    value = value_item.get(key)

                    if value is not None and str(value).strip():
                        return str(value).strip()

            # 部分中央氣象署資料可能使用 parameter 格式
            parameter = (
                time_item.get("Parameter")
                or time_item.get("parameter")
            )

            if isinstance(parameter, dict):
                for key in [
                    "ParameterName",
                    "parameterName",
                    "value",
                    "Value",
                ]:
                    value = parameter.get(key)

                    if value is not None and str(value).strip():
                        return str(value).strip()

    return None


def find_temperature(
    weather_elements: list[dict[str, Any]],
) -> str | None:
    """
    尋找溫度資料。
    """
    return find_first_value(
        weather_elements,
        [
            "Temperature",
            "temperature",
            "AverageTemperature",
            "averageTemperature",
            "MaxTemperature",
            "maxTemperature",
            "MinTemperature",
            "minTemperature",
        ],
    )


def find_weather_description(
    weather_elements: list[dict[str, Any]],
) -> str | None:
    """
    尋找天氣現象或天氣描述。
    """
    return find_first_value(
        weather_elements,
        [
            "Weather",
            "weather",
            "WeatherDescription",
            "weatherDescription",
        ],
    )


@router.get("")
async def get_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """
    取得中央氣象署五結鄉天氣。

    目前保留 lat、lon 參數，
    讓既有前端不需要修改。

    目前實際查詢地點固定使用：
    settings.CWA_LOCATION_NAME
    """
    # 暫時保留前端傳入的座標，但目前不使用
    _ = lat, lon

    api_key = (
        settings.CWA_API_KEY
        .strip()
        .strip('"')
        .strip("'")
    )

    dataset_id = settings.CWA_DATASET_ID.strip()
    location_name = settings.CWA_LOCATION_NAME.strip()

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="後端尚未設定 CWA_API_KEY",
        )

    if not dataset_id:
        raise HTTPException(
            status_code=500,
            detail="後端尚未設定 CWA_DATASET_ID",
        )

    if not location_name:
        raise HTTPException(
            status_code=500,
            detail="後端尚未設定 CWA_LOCATION_NAME",
        )

    url = (
        "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"
        f"{dataset_id}"
    )

    params = {
        "Authorization": api_key,
        "LocationName": location_name,
        "format": "JSON",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                params=params,
            )

        if response.status_code != 200:
            print(
                "中央氣象署狀態碼：",
                response.status_code,
            )
            print(
                "中央氣象署回傳內容：",
                response.text,
            )

            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "無法取得中央氣象署天氣資料",
                    "cwa_status": response.status_code,
                    "cwa_response": response.text,
                },
            )

        try:
            data = response.json()

        except ValueError as error:
            raise HTTPException(
                status_code=502,
                detail="中央氣象署回傳的內容不是有效 JSON",
            ) from error

        success = data.get("success")

        if success not in (True, "true"):
            print(
                "中央氣象署資料失敗：",
                data,
            )

            raise HTTPException(
                status_code=502,
                detail="中央氣象署回傳資料失敗",
            )

        records = data.get("records", {})

        locations_groups = (
            records.get("Locations")
            or records.get("locations")
            or []
        )

        if not isinstance(locations_groups, list):
            locations_groups = []

        if not locations_groups:
            print(
                "中央氣象署 records：",
                records,
            )

            raise HTTPException(
                status_code=502,
                detail="中央氣象署回傳格式不完整",
            )

        first_group = locations_groups[0]

        location_list = (
            first_group.get("Location")
            or first_group.get("location")
            or []
        )

        if not isinstance(location_list, list):
            location_list = []

        target_location = next(
            (
                location
                for location in location_list
                if get_location_name(location) == location_name
            ),
            None,
        )

        if target_location is None:
            available_locations = [
                get_location_name(location)
                for location in location_list
            ]

            print(
                "中央氣象署可用地點：",
                available_locations,
            )

            raise HTTPException(
                status_code=404,
                detail=f"找不到 {location_name} 的天氣資料",
            )

        weather_elements = get_weather_elements(
            target_location
        )

        if not weather_elements:
            print(
                "五結鄉資料內容：",
                target_location,
            )

            raise HTTPException(
                status_code=502,
                detail="五結鄉資料中沒有 WeatherElement",
            )

        print(
            "中央氣象署 WeatherElement 名稱：",
            [
                element.get("ElementName")
                or element.get("elementName")
                for element in weather_elements
            ],
        )

        temperature_text = find_temperature(
            weather_elements
        )

        description = find_weather_description(
            weather_elements
        )

        if temperature_text is None:
            print(
                "WeatherElement 內容：",
                weather_elements,
            )

            raise HTTPException(
                status_code=502,
                detail="中央氣象署資料中找不到溫度",
            )

        try:
            temperature = float(temperature_text)

        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    "中央氣象署溫度格式錯誤："
                    f"{temperature_text}"
                ),
            ) from error

        # 保留原本 OpenWeather 的回傳格式，
        # 因此前端暫時不需要修改。
        return {
            "main": {
                "temp": temperature,
            },
            "weather": [
                {
                    "description": (
                        description
                        or "天氣狀況不明"
                    ),
                }
            ],
            "location": location_name,
            "source": "中央氣象署",
        }

    except HTTPException:
        # 保留上方已經建立的 HTTP 錯誤狀態
        raise

    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="中央氣象署回應逾時",
        ) from error

    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="無法連線至中央氣象署",
        ) from error

    except Exception as error:
        print(
            "天氣 API 未預期錯誤：",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail="處理天氣資料時發生未預期錯誤",
        ) from error