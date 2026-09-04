import json
import math
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, render_template_string


app = Flask(__name__)


# ============================================================
# 自宅情報
# ============================================================

HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

JST = timezone(timedelta(hours=9))


# ============================================================
# 気象庁 AMeDAS
# ============================================================

JMA_LATEST_URL = (
    "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
)

JMA_STATION_URL = (
    "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
)

JMA_MAP_URL = (
    "https://www.jma.go.jp/bosai/amedas/data/map/{}.json"
)


# ============================================================
# MET Norway
# ============================================================

MET_URL = (
    "https://api.met.no/weatherapi/locationforecast/2.0/complete"
)

MET_CONTACT_EMAIL = os.environ.get(
    "MET_CONTACT_EMAIL",
    "contact@example.com"
)

MET_HEADERS = {
    "User-Agent": (
        f"NarabotoWeather/1.0 ({MET_CONTACT_EMAIL})"
    ),
    "Accept": "application/json",
}


# ============================================================
# 共通
# ============================================================

def safe_float(value):
    """安全にfloatへ変換"""

    try:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def format_number(value, digits=1):
    if value is None:
        return "—"

    return f"{value:.{digits}f}"


def coord_to_decimal(value):
    """
    AMeDASの座標
    [度, 分] または [度, 分, 秒]
    を十進法へ変換
    """

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, list) and len(value) >= 2:

        try:
            degree = float(value[0])
            minute = float(value[1])

            second = 0.0

            if len(value) >= 3:
                second = float(value[2])

            sign = -1 if degree < 0 else 1

            return sign * (
                abs(degree)
                + minute / 60
                + second / 3600
            )

        except (TypeError, ValueError):
            return None

    return None


def distance_km(lat1, lon1, lat2, lon2):
    """ハーサイン距離"""

    r = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return r * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


def jst_now():
    return datetime.now(JST)


def get_json(url, timeout=20, headers=None):
    response = requests.get(
        url,
        timeout=timeout,
        headers=headers
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# AMeDAS
# ============================================================

WIND_DIRECTIONS = {
    0: "静穏",
    1: "北",
    2: "北北東",
    3: "北東",
    4: "東北東",
    5: "東",
    6: "東南東",
    7: "南東",
    8: "南南東",
    9: "南",
    10: "南南西",
    11: "南西",
    12: "西南西",
    13: "西",
    14: "西北西",
    15: "北西",
    16: "北北西",
}


def get_latest_amedas_time():
    """AMeDAS最新時刻"""

    response = requests.get(
        JMA_LATEST_URL,
        timeout=20
    )

    response.raise_for_status()

    text = response.text.strip()

    dt = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    )

    return dt.astimezone(JST)


def amedas_value(obs, key):
    """
    AMeDAS値を取得。

    例:
    [値, 品質情報, ...]
    の場合は先頭の値を使用。
    """

    if not obs:
        return None

    value = obs.get(key)

    if isinstance(value, list):

        if len(value) == 0:
            return None

        return safe_float(value[0])

    return safe_float(value)


def make_station_list(stations):
    """
    全AMeDAS観測所を自宅から近い順にする。
    """

    result = []

    for station_id, station in stations.items():

        lat = coord_to_decimal(
            station.get("lat")
        )

        lon = coord_to_decimal(
            station.get("lon")
        )

        if lat is None or lon is None:
            continue

        distance = distance_km(
            HOME_LAT,
            HOME_LON,
            lat,
            lon
        )

        result.append({
            "id": str(station_id),
            "name": (
                station.get("kjName")
                or station.get("enName")
                or str(station_id)
            ),
            "lat": lat,
            "lon": lon,
            "distance": distance,
            "type": station.get("type"),
            "elems": station.get("elems", ""),
        })

    result.sort(
        key=lambda x: x["distance"]
    )

    return result


def get_station_observation(data, station_id):
    """
    JSONのキーが文字列・整数どちらでも対応。
    """

    obs = data.get(str(station_id))

    if obs is not None:
        return obs

    try:
        return data.get(int(station_id))
    except Exception:
        return None


def find_nearest_rain_station(
    stations,
    data
):
    """
    降水量を観測できる最寄りの観測所。

    天城山のような「雨」専用観測所も
    ここでは有効。
    """

    for station in stations:

        obs = get_station_observation(
            data,
            station["id"]
        )

        if not obs:
            continue

        rain10 = amedas_value(
            obs,
            "precipitation10m"
        )

        rain1h = amedas_value(
            obs,
            "precipitation1h"
        )

        if rain10 is not None or rain1h is not None:

            return station, obs

    return None, None


def find_nearest_four_element_station(
    stations,
    data
):
    """
    気温・湿度・風速・風向を取得できる
    最寄りの観測所を探す。

    観測所マスターだけで判定せず、
    実際の最新データに必要な項目が
    入っているか確認する。
    """

    for station in stations:

        obs = get_station_observation(
            data,
            station["id"]
        )

        if not obs:
            continue

        temp = amedas_value(
            obs,
            "temp"
        )

        humidity = amedas_value(
            obs,
            "humidity"
        )

        wind = amedas_value(
            obs,
            "wind"
        )

        wind_direction = amedas_value(
            obs,
            "windDirection"
        )

        # 少なくとも四要素系の観測所と判断できる条件
        available = sum(
            value is not None
            for value in (
                temp,
                humidity,
                wind,
                wind_direction
            )
        )

        if available >= 2:
            return station, obs

    return None, None


def get_amedas():
    """
    AMeDAS取得。

    ・降水 → 最寄りの降水観測所
    ・気温/湿度/風 → 最寄りの四要素系観測所

    を分離する。
    """

    try:

        latest_dt = get_latest_amedas_time()

        timestamp = latest_dt.strftime(
            "%Y%m%d%H%M%S"
        )

        stations_raw = get_json(
            JMA_STATION_URL
        )

        stations = make_station_list(
            stations_raw
        )

        if not stations:
            raise RuntimeError(
                "AMeDAS観測所が見つかりません"
            )

        data = get_json(
            JMA_MAP_URL.format(timestamp)
        )

        # ----------------------------------------------------
        # 降水観測所
        # ----------------------------------------------------

        rain_station, rain_obs = (
            find_nearest_rain_station(
                stations,
                data
            )
        )

        # ----------------------------------------------------
        # 四要素観測所
        # ----------------------------------------------------

        four_station, four_obs = (
            find_nearest_four_element_station(
                stations,
                data
            )
        )

        if rain_station is None:
            raise RuntimeError(
                "降水を観測できるAMeDASが見つかりません"
            )

        # ----------------------------------------------------
        # 降水
        # ----------------------------------------------------

        rain10 = amedas_value(
            rain_obs,
            "precipitation10m"
        )

        rain1h = amedas_value(
            rain_obs,
            "precipitation1h"
        )

        rain_visibility = amedas_value(
            rain_obs,
            "visibility"
        )

        # ----------------------------------------------------
        # 四要素
        # ----------------------------------------------------

        temp = None
        humidity = None
        wind = None
        wind_direction_value = None
        visibility = None

        if four_obs:

            temp = amedas_value(
                four_obs,
                "temp"
            )

            humidity = amedas_value(
                four_obs,
                "humidity"
            )

            wind = amedas_value(
                four_obs,
                "wind"
            )

            wind_direction_value = amedas_value(
                four_obs,
                "windDirection"
            )

            visibility = amedas_value(
                four_obs,
                "visibility"
            )

        wind_direction = "—"

        if wind_direction_value is not None:

            direction_int = int(
                round(wind_direction_value)
            )

            wind_direction = (
                WIND_DIRECTIONS.get(
                    direction_int,
                    "—"
                )
            )

        # ----------------------------------------------------
        # ログ
        # ----------------------------------------------------

        print(
            "AMeDAS RAIN:",
            rain_station["name"],
            f'{rain_station["distance"]:.1f}km',
            "rain10=",
            rain10,
            "rain1h=",
            rain1h
        )

        if four_station:

            print(
                "AMeDAS FOUR:",
                four_station["name"],
                f'{four_station["distance"]:.1f}km',
                "temp=",
                temp,
                "humidity=",
                humidity,
                "wind=",
                wind,
                "direction=",
                wind_direction
            )

        else:

            print(
                "AMeDAS FOUR: NOT FOUND"
            )

        return {
            "ok": True,

            # 降水
            "rain_station": rain_station["name"],
            "rain_station_id": rain_station["id"],
            "rain_distance": rain_station["distance"],
            "rain10": rain10,
            "rain1h": rain1h,
            "rain_visibility": rain_visibility,

            # 四要素
            "four_station": (
                four_station["name"]
                if four_station
                else "—"
            ),
            "four_station_id": (
                four_station["id"]
                if four_station
                else None
            ),
            "four_distance": (
                four_station["distance"]
                if four_station
                else None
            ),

            "temp": temp,
            "humidity": humidity,
            "wind": wind,
            "wind_direction": wind_direction,
            "visibility": visibility,

            "observed_at": latest_dt,

            "rain_raw": rain_obs or {},
            "four_raw": four_obs or {},
        }

    except Exception as e:

        print(
            "AMeDAS ERROR:",
            repr(e)
        )

        return {
            "ok": False,
            "error": str(e),

            "rain_station": "—",
            "rain_station_id": None,
            "rain_distance": None,

            "rain10": None,
            "rain1h": None,
            "rain_visibility": None,

            "four_station": "—",
            "four_station_id": None,
            "four_distance": None,

            "temp": None,
            "humidity": None,
            "wind": None,
            "wind_direction": "—",
            "visibility": None,

            "observed_at": None,

            "rain_raw": {},
            "four_raw": {},
        }


# ============================================================
# MET Norway
# ============================================================

def get_met_forecast():
    """
    奈良本・標高500mのMET Norway予報。
    """

    try:

        params = {
            "lat": HOME_LAT,
            "lon": HOME_LON,
            "altitude": HOME_ALTITUDE,
        }

        print(
            "MET REQUEST:",
            params
        )

        response = requests.get(
            MET_URL,
            params=params,
            headers=MET_HEADERS,
            timeout=30
        )

        print(
            "MET STATUS:",
            response.status_code
        )

        if response.status_code != 200:

            print(
                "MET RESPONSE:",
                response.text[:1000]
            )

            response.raise_for_status()

        return {
            "ok": True,
            "data": response.json(),
            "error": None,
        }

    except Exception as e:

        print(
            "MET ERROR:",
            repr(e)
        )

        return {
            "ok": False,
            "data": None,
            "error": str(e),
        }


def get_period_data(data):
    """
    利用可能な予報期間を取得。
    """

    for key in (
        "next_1_hours",
        "next_6_hours",
        "next_12_hours",
    ):

        value = data.get(key)

        if isinstance(value, dict):
            return value

    return {}


def symbol_to_japanese(symbol):

    if not symbol:
        return "—"

    s = symbol.lower()

    mapping = [
        ("heavyrain", "強い雨"),
        ("lightrain", "弱い雨"),
        ("rain", "雨"),
        ("sleet", "みぞれ"),
        ("snow", "雪"),
        ("fog", "霧"),
        ("thunderstorm", "雷雨"),
        ("clearsky", "快晴"),
        ("fair", "晴れ"),
        ("partlycloudy", "晴れ時々くもり"),
        ("cloudy", "くもり"),
    ]

    for key, value in mapping:

        if key in s:
            return value

    return "くもり"


def symbol_icon(symbol):

    if not symbol:
        return "🌤️"

    s = symbol.lower()

    if "thunder" in s:
        return "⛈️"

    if "heavyrain" in s:
        return "🌧️"

    if "lightrain" in s:
        return "🌦️"

    if "rain" in s:
        return "🌧️"

    if "sleet" in s:
        return "🌨️"

    if "snow" in s:
        return "❄️"

    if "fog" in s:
        return "🌫️"

    if "clearsky" in s:
        return "☀️"

    if "fair" in s:
        return "🌤️"

    if "partlycloudy" in s:
        return "⛅"

    if "cloudy" in s:
        return "☁️"

    return "🌤️"


def build_forecasts(met_json):

    if not met_json:
        return []

    timeseries = (
        met_json
        .get("properties", {})
        .get("timeseries", [])
    )

    forecasts = []

    now = datetime.now(JST)

    for item in timeseries:

        try:

            time_text = item.get("time")

            if not time_text:
                continue

            dt = datetime.fromisoformat(
                time_text.replace(
                    "Z",
                    "+00:00"
                )
            ).astimezone(JST)

            # 今から24時間
            if dt < now - timedelta(hours=1):
                continue

            if dt > now + timedelta(hours=24):
                continue

            data = item.get(
                "data",
                {}
            )

            instant = (
                data
                .get("instant", {})
                .get("details", {})
            )

            period = get_period_data(
                data
            )

            period_details = (
                period
                .get("details", {})
            )

            summary = (
                period
                .get("summary", {})
            )

            symbol = summary.get(
                "symbol_code"
            )

            temperature = safe_float(
                instant.get(
                    "air_temperature"
                )
            )

            humidity = safe_float(
                instant.get(
                    "relative_humidity"
                )
            )

            sea_pressure = safe_float(
                instant.get(
                    "air_pressure_at_sea_level"
                )
            )

            wind = safe_float(
                instant.get(
                    "wind_speed"
                )
            )

            wind_direction = safe_float(
                instant.get(
                    "wind_from_direction"
                )
            )

            precipitation = safe_float(
                period_details.get(
                    "precipitation_amount"
                )
            )

            rain_probability = safe_float(
                period_details.get(
                    "probability_of_precipitation"
                )
            )

            thunder_probability = safe_float(
                period_details.get(
                    "probability_of_thunder"
                )
            )

            # ------------------------------------------------
            # 標高500mでの地上気圧推定
            # ------------------------------------------------

            surface_pressure = None

            if (
                sea_pressure is not None
                and temperature is not None
            ):

                surface_pressure = (
                    sea_pressure
                    * math.exp(
                        -9.80665
                        * HOME_ALTITUDE
                        / (
                            287.05
                            * (
                                temperature
                                + 273.15
                            )
                        )
                    )
                )

            forecasts.append({

                "dt": dt,

                "temperature": temperature,
                "humidity": humidity,

                "sea_pressure": sea_pressure,
                "surface_pressure": surface_pressure,

                "wind": wind,
                "wind_direction": wind_direction,

                "precipitation": precipitation,
                "rain_probability": rain_probability,
                "thunder_probability": thunder_probability,

                "symbol": symbol,

                "weather": symbol_to_japanese(
                    symbol
                ),

                "icon": symbol_icon(
                    symbol
                ),
            })

        except Exception as e:

            print(
                "FORECAST ITEM ERROR:",
                repr(e)
            )

    forecasts.sort(
        key=lambda x: x["dt"]
    )

    return forecasts


def nearest_forecast(forecasts):

    if not forecasts:
        return None

    now = datetime.now(JST)

    return min(
        forecasts,
        key=lambda x: abs(
            (
                x["dt"] - now
            ).total_seconds()
        )
    )


# ============================================================
# 気圧
# ============================================================

def pressure_trend(forecasts):

    current = nearest_forecast(
        forecasts
    )

    if current is None:
        return "判定できません"

    current_pressure = (
        current.get(
            "surface_pressure"
        )
    )

    if current_pressure is None:
        return "判定できません"

    now = datetime.now(JST)

    future = [
        x
        for x in forecasts
        if x["dt"] >= now
    ]

    if len(future) < 2:
        return "判定できません"

    target = None

    for item in future:

        if (
            item["dt"] - now
            >= timedelta(hours=2)
        ):

            target = item
            break

    if target is None:
        target = future[-1]

    target_pressure = (
        target.get(
            "surface_pressure"
        )
    )

    if target_pressure is None:
        return "判定できません"

    difference = (
        target_pressure
        - current_pressure
    )

    if difference >= 2:
        return "上昇傾向"

    if difference <= -2:
        return "下降傾向"

    return "安定"


def pressure_level(pressure):

    if pressure is None:
        return "—"

    if pressure >= 1020:
        return "高め"

    if pressure <= 1000:
        return "低め"

    return "標準"


# ============================================================
# 現在の天気
# ============================================================

def current_weather_status(amedas):

    rain = amedas.get(
        "rain10"
    )

    visibility = amedas.get(
        "rain_visibility"
    )

    if (
        visibility is not None
        and visibility <= 1000
    ):

        return (
            "🌫️ 視程が低下しています",
            "周辺観測で視程1000m以下です。"
        )

    if rain is not None:

        if rain >= 0.5:

            return (
                "🌧️ 雨を観測しています",
                f"直近10分の降水量は {rain:.1f} mm です。"
            )

        if rain > 0:

            return (
                "🌦️ 降水を観測しています",
                f"直近10分の降水量は {rain:.1f} mm です。"
            )

        return (
            "✓ 現在、降水は観測されていません",
            "周辺観測では直近10分の降水はありません。"
        )

    return (
        "— 現在の降水状況を確認できません",
        "AMeDASの降水データを取得できませんでした。"
    )


# ============================================================
# 予報上の注意
# ============================================================

def build_alerts(forecasts):

    alerts = []

    for item in forecasts:

        rain = item.get(
            "precipitation"
        )

        wind = item.get(
            "wind"
        )

        thunder = item.get(
            "thunder_probability"
        )

        weather = item.get(
            "weather",
            ""
        )

        if (
            rain is not None
            and rain >= 5
        ):

            alerts.append(
                "🌧️ 今後、強い雨となる時間帯があります。"
            )

        if (
            wind is not None
            and wind >= 10
        ):

            alerts.append(
                "💨 今後、風が強まる予報があります。"
            )

        if (
            thunder is not None
            and thunder >= 30
        ):

            alerts.append(
                "⛈️ 雷の可能性があります。"
            )

        if "雷" in weather:

            alerts.append(
                "⛈️ 雷雨の予報があります。"
            )

        if "霧" in weather:

            alerts.append(
                "🌫️ 霧が発生する可能性があります。"
            )

    result = []

    for alert in alerts:

        if alert not in result:
            result.append(alert)

    return result[:5]


# ============================================================
# HTML
# ============================================================

HTML = r"""
<!doctype html>

<html lang="ja">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>奈良本｜天気・気圧</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;

    background: #171516;
    color: #eee8e8;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        "Noto Sans JP",
        sans-serif;
}

body {
    padding: 28px;
}

.page {
    max-width: 1180px;
    margin: 0 auto;
}

.header {
    border-bottom: 1px solid #393234;
    padding-bottom: 18px;
    margin-bottom: 28px;
}

.title {
    font-size: 26px;
    font-weight: 500;
    letter-spacing: .08em;
}

.title span {
    color: #c98991;
}

.subtitle {
    margin-top: 8px;
    color: #91888a;
    font-size: 13px;
}

.section {
    margin-top: 30px;
}

.section-title {
    font-size: 14px;
    letter-spacing: .12em;
    color: #c98991;
    margin-bottom: 14px;
}

.hero {
    display: grid;
    grid-template-columns:
        minmax(0, 1.3fr)
        minmax(0, .7fr);

    gap: 18px;
}

.panel {
    background: #201d1e;
    border: 1px solid #393234;
    border-radius: 14px;
    padding: 22px;
}

.hero-temp {
    font-size: 62px;
    font-weight: 300;
    line-height: 1;
    margin: 8px 0;
}

.hero-temp small {
    font-size: 24px;
    color: #b8afb1;
}

.weather-main {
    font-size: 20px;
    margin-top: 14px;
}

.muted {
    color: #91888a;
    font-size: 12px;
}

.time {
    color: #aaa1a3;
    font-size: 12px;
    margin-top: 8px;
}

.grid {
    display: grid;

    grid-template-columns:
        repeat(4, minmax(0, 1fr));

    gap: 12px;
}

.metric {
    background: #201d1e;
    border: 1px solid #393234;
    border-radius: 12px;
    padding: 17px;
}

.metric-label {
    color: #91888a;
    font-size: 12px;
    margin-bottom: 9px;
}

.metric-value {
    font-size: 24px;
    font-weight: 400;
}

.metric-unit {
    font-size: 12px;
    color: #91888a;
}

.station {
    margin-top: 8px;
    color: #aaa1a3;
    font-size: 12px;
}

.pressure {
    display: grid;

    grid-template-columns:
        repeat(3, minmax(0, 1fr));

    gap: 12px;
}

.pressure-box {
    background: #201d1e;
    border: 1px solid #393234;
    border-radius: 12px;
    padding: 20px;
}

.pressure-value {
    font-size: 30px;
    margin-top: 6px;
}

.pressure-note {
    margin-top: 6px;
    color: #c98991;
}

.forecast-wrap {
    overflow-x: auto;
    padding-bottom: 8px;
}

.forecast {
    display: grid;

    grid-template-columns:
        repeat(24, minmax(92px, 1fr));

    gap: 8px;

    min-width: 1150px;
}

.forecast-item {
    background: #201d1e;
    border: 1px solid #393234;
    border-radius: 11px;
    padding: 12px;
    text-align: center;
}

.forecast-time {
    font-size: 12px;
    color: #aaa1a3;
}

.forecast-icon {
    font-size: 25px;
    margin: 8px 0;
}

.forecast-temp {
    font-size: 20px;
}

.forecast-weather {
    font-size: 11px;
    color: #aaa1a3;
    min-height: 32px;
    margin-top: 5px;
}

.rain-prob {
    margin-top: 8px;
    color: #c98991;
    font-size: 12px;
}

.rain-amount {
    color: #aaa1a3;
    font-size: 11px;
    margin-top: 4px;
}

.chart-box {
    background: #201d1e;
    border: 1px solid #393234;
    border-radius: 14px;
    padding: 20px;
    height: 320px;
}

.alert {
    border-left: 3px solid #c98991;
    background: #201d1e;
    border-top: 1px solid #393234;
    border-right: 1px solid #393234;
    border-bottom: 1px solid #393234;
    border-radius: 8px;
    padding: 13px 16px;
    margin-bottom: 8px;
}

.observation-note {
    color: #91888a;
    font-size: 12px;
    line-height: 1.7;
    margin-top: 12px;
}

.diagnostic {
    margin-top: 14px;
    padding: 10px 12px;
    border: 1px solid #393234;
    border-radius: 8px;
    color: #91888a;
    font-size: 11px;
}

.footer {
    margin-top: 36px;
    padding-top: 18px;
    border-top: 1px solid #393234;
    color: #716a6c;
    font-size: 11px;
    line-height: 1.7;
}

@media (max-width: 800px) {

    body {
        padding: 18px;
    }

    .hero {
        grid-template-columns: 1fr;
    }

    .grid {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

    .pressure {
        grid-template-columns: 1fr;
    }

    .hero-temp {
        font-size: 52px;
    }
}

</style>

</head>


<body>

<div class="page">


<header class="header">

    <div class="title">
        奈良本 <span>｜</span> 標高 約500m
    </div>

    <div class="subtitle">
        自宅位置を基準にした天気・気圧情報
        ｜更新 {{ updated }}
    </div>

</header>


<!-- ======================================================
     自宅推定
======================================================= -->

<div class="section">

    <div class="section-title">
        自宅の現在推定
    </div>

    <div class="hero">

        <div class="panel">

            <div class="muted">
                MET Norway｜奈良本・標高500m
            </div>

            <div class="hero-temp">

                {{ home_temp }}

                {% if home_temp != "—" %}
                    <small>℃</small>
                {% endif %}

            </div>

            <div class="weather-main">

                {{ home_icon }}
                {{ home_weather }}

            </div>

            <div class="time">
                予報時刻：{{ home_time }}
            </div>

            <div class="observation-note">
                自宅に気温センサーを設置していないため、
                気温は自宅座標・標高500mにおける
                数値予報モデルの推定値です。
            </div>

        </div>


        <div class="panel">

            <div class="muted">
                現在の自宅推定気圧
            </div>

            <div class="pressure-value">

                {{ home_surface_pressure }}

                {% if home_surface_pressure != "—" %}
                    hPa
                {% endif %}

            </div>

            <div class="pressure-note">
                {{ pressure_level }}
            </div>

            <div class="time">
                気圧傾向：{{ pressure_trend }}
            </div>

            <div class="observation-note">
                海面更正気圧を標高約500mへ
                換算した推定値です。
            </div>

        </div>

    </div>

</div>


<!-- ======================================================
     周辺観測
======================================================= -->

<div class="section">

    <div class="section-title">
        周辺観測
    </div>


    <div class="grid">

        <div class="metric">

            <div class="metric-label">
                気温
            </div>

            <div class="metric-value">

                {{ amedas_temp }}

                {% if amedas_temp != "—" %}
                    <span class="metric-unit">℃</span>
                {% endif %}

            </div>

        </div>


        <div class="metric">

            <div class="metric-label">
                湿度
            </div>

            <div class="metric-value">

                {{ amedas_humidity }}

                {% if amedas_humidity != "—" %}
                    <span class="metric-unit">%</span>
                {% endif %}

            </div>

        </div>


        <div class="metric">

            <div class="metric-label">
                風速
            </div>

            <div class="metric-value">

                {{ amedas_wind }}

                {% if amedas_wind != "—" %}
                    <span class="metric-unit">m/s</span>
                {% endif %}

            </div>

        </div>


        <div class="metric">

            <div class="metric-label">
                風向
            </div>

            <div class="metric-value">
                {{ amedas_wind_direction }}
            </div>

        </div>

    </div>


    <div class="station">

        周辺観測：
        {{ amedas_four_station }}

        {% if amedas_four_distance != "—" %}
            （自宅から約{{ amedas_four_distance }}km）
        {% endif %}

        {% if amedas_time != "—" %}
            ｜{{ amedas_time }}
        {% endif %}

    </div>

</div>


<!-- ======================================================
     降水
======================================================= -->

<div class="section">

    <div class="section-title">
        降水観測
    </div>


    <div class="grid">

        <div class="metric">

            <div class="metric-label">
                直近10分
            </div>

            <div class="metric-value">

                {{ rain10 }}

                {% if rain10 != "—" %}
                    <span class="metric-unit">mm</span>
                {% endif %}

            </div>

        </div>


        <div class="metric">

            <div class="metric-label">
                直近1時間
            </div>

            <div class="metric-value">

                {{ rain1h }}

                {% if rain1h != "—" %}
                    <span class="metric-unit">mm</span>
                {% endif %}

            </div>

        </div>

    </div>


    <div class="station">

        降水観測：
        {{ rain_station }}

        {% if rain_distance != "—" %}
            （自宅から約{{ rain_distance }}km）
        {% endif %}

    </div>

</div>


<!-- ======================================================
     現在の状況
======================================================= -->

<div class="section">

    <div class="section-title">
        現在の状況
    </div>

    <div class="panel">

        <div style="font-size:20px;">
            {{ current_status }}
        </div>

        <div class="observation-note">
            {{ current_detail }}
        </div>

    </div>

</div>


<!-- ======================================================
     注意
======================================================= -->

{% if alerts %}

<div class="section">

    <div class="section-title">
        予報上の注意
    </div>

    {% for alert in alerts %}

        <div class="alert">
            {{ alert }}
        </div>

    {% endfor %}

</div>

{% endif %}


<!-- ======================================================
     24時間予報
======================================================= -->

<div class="section">

    <div class="section-title">
        24時間予報
    </div>


    {% if forecasts %}

    <div class="forecast-wrap">

        <div class="forecast">

        {% for item in forecasts %}

            <div class="forecast-item">

                <div class="forecast-time">
                    {{ item.time }}
                </div>

                <div class="forecast-icon">
                    {{ item.icon }}
                </div>

                <div class="forecast-temp">
                    {{ item.temperature }}℃
                </div>

                <div class="forecast-weather">
                    {{ item.weather }}
                </div>

                <div class="rain-prob">

                    {% if item.rain_probability != "—" %}

                        🌧️ {{ item.rain_probability }}%

                    {% else %}

                        🌧️ —

                    {% endif %}

                </div>

                <div class="rain-amount">

                    {% if item.precipitation != "—" %}

                        {{ item.precipitation }}mm

                    {% else %}

                        —

                    {% endif %}

                </div>

            </div>

        {% endfor %}

        </div>

    </div>

    {% else %}

        <div class="panel">
            24時間予報を取得できませんでした。
        </div>

    {% endif %}

</div>


<!-- ======================================================
     グラフ
======================================================= -->

<div class="section">

    <div class="section-title">
        気温
    </div>

    <div class="chart-box">

        <canvas id="temperatureChart"></canvas>

    </div>

</div>


<div class="section">

    <div class="section-title">
        気圧
    </div>

    <div class="chart-box">

        <canvas id="pressureChart"></canvas>

    </div>

</div>


<!-- ======================================================
     診断
======================================================= -->

{% if met_error %}

<div class="diagnostic">

    MET Norway：
    {{ met_error }}

</div>

{% endif %}


{% if amedas_error %}

<div class="diagnostic">

    AMeDAS：
    {{ amedas_error }}

</div>

{% endif %}


<footer class="footer">

    気温・湿度・風・降水：
    気象庁 AMeDAS

    <br>

    自宅推定気温・予報・気圧：
    MET Norway

    <br>

    ※自宅の実測センサーではありません。

</footer>


</div>


<script>

const chartLabels =
    {{ chart_labels | safe }};

const temperatureData =
    {{ temperature_data | safe }};

const pressureData =
    {{ pressure_data | safe }};


const chartOptions = {

    responsive: true,

    maintainAspectRatio: false,

    plugins: {

        legend: {
            display: false
        }

    },

    scales: {

        x: {
            ticks: {
                color: "#91888a"
            },

            grid: {
                color: "#302c2d"
            }
        },

        y: {
            ticks: {
                color: "#91888a"
            },

            grid: {
                color: "#302c2d"
            }
        }

    }

};


new Chart(
    document.getElementById(
        "temperatureChart"
    ),
    {

        type: "line",

        data: {

            labels: chartLabels,

            datasets: [
                {

                    data: temperatureData,

                    tension: 0.3,

                    pointRadius: 2,

                    borderWidth: 2

                }
            ]

        },

        options: chartOptions

    }
);


new Chart(
    document.getElementById(
        "pressureChart"
    ),
    {

        type: "line",

        data: {

            labels: chartLabels,

            datasets: [
                {

                    data: pressureData,

                    tension: 0.3,

                    pointRadius: 2,

                    borderWidth: 2

                }
            ]

        },

        options: chartOptions

    }
);

</script>


</body>

</html>
"""


# ============================================================
# Web
# ============================================================

@app.route("/")
def index():

    # --------------------------------------------------------
    # AMeDAS
    # --------------------------------------------------------

    amedas = get_amedas()

    # --------------------------------------------------------
    # MET
    # --------------------------------------------------------

    met_result = get_met_forecast()

    met_json = (
        met_result.get("data")
        if met_result
        else None
    )

    met_error = None

    if not met_result.get("ok"):

        met_error = (
            "データを取得できませんでした"
        )

    forecasts = build_forecasts(
        met_json
    )

    current_forecast = nearest_forecast(
        forecasts
    )

    # --------------------------------------------------------
    # 自宅現在値
    # --------------------------------------------------------

    if current_forecast:

        home_temp = format_number(
            current_forecast.get(
                "temperature"
            ),
            1
        )

        home_weather = (
            current_forecast.get(
                "weather"
            )
            or "—"
        )

        home_icon = (
            current_forecast.get(
                "icon"
            )
            or "🌤️"
        )

        home_surface_pressure = (
            format_number(
                current_forecast.get(
                    "surface_pressure"
                ),
                1
            )
        )

        home_time = (
            current_forecast["dt"]
            .strftime("%m/%d %H:%M")
        )

    else:

        home_temp = "—"
        home_weather = "—"
        home_icon = "🌤️"
        home_surface_pressure = "—"
        home_time = "—"

    # --------------------------------------------------------
    # 気圧
    # --------------------------------------------------------

    trend = pressure_trend(
        forecasts
    )

    level = pressure_level(
        current_forecast.get(
            "surface_pressure"
        )
        if current_forecast
        else None
    )

    # --------------------------------------------------------
    # 現在天気
    # --------------------------------------------------------

    current_status, current_detail = (
        current_weather_status(
            amedas
        )
    )

    alerts = build_alerts(
        forecasts
    )

    # --------------------------------------------------------
    # 24時間表示
    # --------------------------------------------------------

    forecast_view = []

    for item in forecasts:

        temperature = item.get(
            "temperature"
        )

        precipitation = item.get(
            "precipitation"
        )

        probability = item.get(
            "rain_probability"
        )

        forecast_view.append({

            "time": item["dt"].strftime(
                "%H:%M"
            ),

            "temperature": (
                f"{temperature:.1f}"
                if temperature is not None
                else "—"
            ),

            "weather": item.get(
                "weather",
                "—"
            ),

            "icon": item.get(
                "icon",
                "🌤️"
            ),

            "precipitation": (
                f"{precipitation:.1f}"
                if precipitation is not None
                else "—"
            ),

            "rain_probability": (
                f"{probability:.0f}"
                if probability is not None
                else "—"
            ),
        })

    # --------------------------------------------------------
    # グラフ
    # --------------------------------------------------------

    chart_labels = [
        item["dt"].strftime(
            "%H:%M"
        )
        for item in forecasts
    ]

    temperature_data = [
        item.get(
            "temperature"
        )
        for item in forecasts
    ]

    pressure_data = [
        item.get(
            "surface_pressure"
        )
        for item in forecasts
    ]

    # --------------------------------------------------------
    # AMeDAS表示
    # --------------------------------------------------------

    amedas_temp = format_number(
        amedas.get("temp"),
        1
    )

    amedas_humidity = format_number(
        amedas.get("humidity"),
        0
    )

    amedas_wind = format_number(
        amedas.get("wind"),
        1
    )

    amedas_wind_direction = (
        amedas.get(
            "wind_direction"
        )
        or "—"
    )

    rain10 = format_number(
        amedas.get("rain10"),
        1
    )

    rain1h = format_number(
        amedas.get("rain1h"),
        1
    )

    amedas_four_station = (
        amedas.get(
            "four_station"
        )
        or "—"
    )

    if amedas.get(
        "four_distance"
    ) is not None:

        amedas_four_distance = (
            f'{amedas["four_distance"]:.1f}'
        )

    else:

        amedas_four_distance = "—"

    if amedas.get(
        "rain_distance"
    ) is not None:

        rain_distance = (
            f'{amedas["rain_distance"]:.1f}'
        )

    else:

        rain_distance = "—"

    if amedas.get(
        "observed_at"
    ):

        amedas_time = (
            amedas["observed_at"]
            .strftime(
                "%H:%M"
            )
        )

    else:

        amedas_time = "—"

    amedas_error = None

    if not amedas.get("ok"):

        amedas_error = (
            amedas.get(
                "error"
            )
            or "取得できませんでした"
        )

    # --------------------------------------------------------
    # 更新時刻
    # --------------------------------------------------------

    updated = jst_now().strftime(
        "%Y/%m/%d %H:%M"
    )

    # --------------------------------------------------------
    # JSON化
    # --------------------------------------------------------

    chart_labels_json = json.dumps(
        chart_labels,
        ensure_ascii=False
    )

    temperature_json = json.dumps(
        temperature_data,
        ensure_ascii=False
    )

    pressure_json = json.dumps(
        pressure_data,
        ensure_ascii=False
    )

    # --------------------------------------------------------
    # Render
    # --------------------------------------------------------

    return render_template_string(
        HTML,

        updated=updated,

        home_temp=home_temp,
        home_weather=home_weather,
        home_icon=home_icon,
        home_surface_pressure=(
            home_surface_pressure
        ),
        home_time=home_time,

        pressure_trend=trend,
        pressure_level=level,

        amedas_temp=amedas_temp,
        amedas_humidity=amedas_humidity,
        amedas_wind=amedas_wind,
        amedas_wind_direction=(
            amedas_wind_direction
        ),

        amedas_four_station=(
            amedas_four_station
        ),

        amedas_four_distance=(
            amedas_four_distance
        ),

        amedas_time=amedas_time,

        rain10=rain10,
        rain1h=rain1h,

        rain_station=(
            amedas.get(
                "rain_station",
                "—"
            )
        ),

        rain_distance=rain_distance,

        current_status=current_status,
        current_detail=current_detail,

        alerts=alerts,

        forecasts=forecast_view,

        chart_labels=chart_labels_json,
        temperature_data=temperature_json,
        pressure_data=pressure_json,

        met_error=met_error,
        amedas_error=amedas_error,
    )


# ============================================================
# 起動
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )