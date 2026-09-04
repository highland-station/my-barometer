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
    try:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def coord_to_decimal(value):
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


def amedas_value(obs, key):
    if not obs:
        return None

    value = obs.get(key)

    if isinstance(value, list):
        if not value:
            return None

        return safe_float(value[0])

    return safe_float(value)


def get_latest_amedas_time():
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


def station_distance(station):
    lat = coord_to_decimal(station.get("lat"))
    lon = coord_to_decimal(station.get("lon"))

    if lat is None or lon is None:
        return None

    return distance_km(
        HOME_LAT,
        HOME_LON,
        lat,
        lon
    )


def sorted_stations(stations):
    result = []

    for station_id, station in stations.items():
        distance = station_distance(station)

        if distance is None:
            continue

        result.append({
            "id": str(station_id),
            "name": (
                station.get("kjName")
                or station.get("enName")
                or str(station_id)
            ),
            "lat": coord_to_decimal(
                station.get("lat")
            ),
            "lon": coord_to_decimal(
                station.get("lon")
            ),
            "distance": distance,
            "type": station.get("type"),
            "elems": station.get("elems", []),
        })

    result.sort(
        key=lambda x: x["distance"]
    )

    return result


def get_obs(data, station_id):
    obs = (
        data.get(station_id)
        or data.get(str(station_id))
    )

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
    for station in stations:

        obs = get_obs(
            data,
            station["id"]
        )

        if obs is None:
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
    for station in stations:

        obs = get_obs(
            data,
            station["id"]
        )

        if obs is None:
            continue

        values = [
            amedas_value(obs, "temp"),
            amedas_value(obs, "humidity"),
            amedas_value(obs, "wind"),
            amedas_value(obs, "windDirection"),
        ]

        count = sum(
            value is not None
            for value in values
        )

        if count >= 2:
            return station, obs

    return None, None


def get_amedas():
    try:
        latest_dt = get_latest_amedas_time()

        timestamp = latest_dt.strftime(
            "%Y%m%d%H%M%S"
        )

        stations = get_json(
            JMA_STATION_URL
        )

        data = get_json(
            JMA_MAP_URL.format(timestamp)
        )

        station_list = sorted_stations(
            stations
        )

        rain_station, rain_obs = (
            find_nearest_rain_station(
                station_list,
                data
            )
        )

        four_station, four_obs = (
            find_nearest_four_element_station(
                station_list,
                data
            )
        )

        if rain_station is None:
            raise RuntimeError(
                "降水を観測できるAMeDASが見つかりません"
            )

        rain10 = amedas_value(
            rain_obs,
            "precipitation10m"
        )

        rain1h = amedas_value(
            rain_obs,
            "precipitation1h"
        )

        temp = None
        humidity = None
        wind = None
        wind_direction = "—"
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

            wind_direction_value = (
                amedas_value(
                    four_obs,
                    "windDirection"
                )
            )

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

            visibility = amedas_value(
                four_obs,
                "visibility"
            )

        print(
            "AMeDAS:",
            "rain=",
            rain_station["name"],
            "four=",
            (
                four_station["name"]
                if four_station
                else "—"
            ),
            "rain10=",
            rain10,
            "temp=",
            temp
        )

        return {
            "ok": True,

            "rain_station": (
                rain_station["name"]
            ),

            "rain_distance": (
                rain_station["distance"]
            ),

            "four_station": (
                four_station["name"]
                if four_station
                else "—"
            ),

            "four_distance": (
                four_station["distance"]
                if four_station
                else None
            ),

            "observed_at": latest_dt,

            "rain10": rain10,
            "rain1h": rain1h,

            "temp": temp,
            "humidity": humidity,
            "wind": wind,
            "wind_direction": wind_direction,
            "visibility": visibility,
        }

    except Exception as e:

        print(
            "AMeDAS ERROR:",
            repr(e)
        )

        return {
            "ok": False,

            "rain_station": "—",
            "rain_distance": None,

            "four_station": "—",
            "four_distance": None,

            "observed_at": None,

            "rain10": None,
            "rain1h": None,

            "temp": None,
            "humidity": None,
            "wind": None,
            "wind_direction": "—",
            "visibility": None,

            "error": str(e),
        }


# ============================================================
# MET Norway
# ============================================================

def get_met_forecast():
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

        response.raise_for_status()

        return response.json()

    except Exception as e:

        print(
            "MET ERROR:",
            repr(e)
        )

        return None


def get_period_data(data):
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
        ("fair", "晴れ"),
        ("clearsky", "快晴"),
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

                "temperature":
                    temperature,

                "humidity":
                    humidity,

                "sea_pressure":
                    sea_pressure,

                "surface_pressure":
                    surface_pressure,

                "wind":
                    wind,

                "wind_direction":
                    wind_direction,

                "precipitation":
                    precipitation,

                "rain_probability":
                    rain_probability,

                "thunder_probability":
                    thunder_probability,

                "symbol":
                    symbol,

                "weather":
                    symbol_to_japanese(
                        symbol
                    ),

                "icon":
                    symbol_icon(symbol),

            })

        except Exception as e:

            print(
                "FORECAST ITEM ERROR:",
                repr(e)
            )

    return forecasts


def nearest_forecast(forecasts):

    if not forecasts:
        return None

    now = jst_now()

    return min(
        forecasts,
        key=lambda x: abs(
            (
                x["dt"] - now
            ).total_seconds()
        )
    )


# ============================================================
# 気圧判定
# ============================================================

def pressure_level(pressure):

    if pressure is None:
        return "—"

    if pressure >= 1020:
        return "高め"

    if pressure <= 1000:
        return "低め"

    return "標準"


def pressure_trend(forecasts):

    current = nearest_forecast(
        forecasts
    )

    if current is None:
        return "判定できません"

    now = jst_now()

    future = [
        x for x in forecasts
        if x["dt"] >= now
    ]

    if len(future) < 2:
        return "判定できません"

    current_pressure = (
        current["surface_pressure"]
    )

    if current_pressure is None:
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
        target["surface_pressure"]
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


def add_pressure_change_info(
    forecasts
):
    """
    各時間について、3時間前との気圧差を計算。

    目安：
      ±1.5hPa以上 → 変化あり
      ±3.0hPa以上 → 大きな変化
    """

    result = []

    for index, item in enumerate(
        forecasts
    ):

        current = item.get(
            "surface_pressure"
        )

        previous = None

        for j in range(
            index - 1,
            -1,
            -1
        ):

            candidate = forecasts[j]

            if (
                item["dt"]
                - candidate["dt"]
                >= timedelta(hours=2.5)
            ):

                if (
                    item["dt"]
                    - candidate["dt"]
                    <= timedelta(hours=3.5)
                ):
                    previous = candidate
                    break

        change = None

        if (
            current is not None
            and previous is not None
            and previous.get(
                "surface_pressure"
            ) is not None
        ):

            change = (
                current
                - previous[
                    "surface_pressure"
                ]
            )

        if change is None:

            level = "normal"

            label = "安定"

        elif change <= -3.0:

            level = "strong-fall"

            label = "急低下"

        elif change <= -1.5:

            level = "fall"

            label = "低下"

        elif change >= 3.0:

            level = "strong-rise"

            label = "急上昇"

        elif change >= 1.5:

            level = "rise"

            label = "上昇"

        else:

            level = "normal"

            label = "安定"

        item = dict(item)

        item["pressure_change"] = change

        item["pressure_level"] = level

        item["pressure_label"] = label

        result.append(item)

    return result


# ============================================================
# 現在の気象状況
# ============================================================

def current_weather_status(amedas):

    rain = amedas.get(
        "rain10"
    )

    visibility = amedas.get(
        "visibility"
    )

    if (
        visibility is not None
        and visibility <= 1000
    ):

        return (
            "🌫️ 視程が低下しています",
            "周辺観測で視程1000m以下が観測されています。"
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
        "周辺観測の降水データを取得できませんでした。"
    )


# ============================================================
# 注意情報
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
                "💨 今後、風が強まる時間帯があります。"
            )

        if (
            thunder is not None
            and thunder >= 30
        ):

            alerts.append(
                "⛈️ 雷の可能性がある時間帯があります。"
            )

        if "雷" in weather:

            alerts.append(
                "⛈️ 雷雨の予報がある時間帯があります。"
            )

        pressure_level = item.get(
            "pressure_level"
        )

        if pressure_level == "strong-fall":

            alerts.append(
                "📉 気圧が大きく低下する時間帯があります。"
            )

        elif pressure_level == "strong-rise":

            alerts.append(
                "📈 気圧が大きく上昇する時間帯があります。"
            )

    result = []

    for alert in alerts:

        if alert not in result:
            result.append(alert)

    return result[:6]


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
    margin-bottom: 24px;
}

.title {
    font-size: 26px;
    font-weight: 500;
    letter-spacing: .08em;
}

.title span {
    color: #c98991;
}

.updated {
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

.home-weather {
    background: #211d1e;
    border: 1px solid #3a3335;
    border-radius: 12px;
    padding: 24px;
}

.home-label {
    color: #aaa1a3;
    font-size: 13px;
    margin-bottom: 8px;
}

.home-temp {
    font-size: 54px;
    font-weight: 300;
    letter-spacing: -.03em;
}

.home-temp-unit {
    font-size: 20px;
    color: #aaa1a3;
}

.home-meta {
    margin-top: 8px;
    color: #b7afb1;
    font-size: 13px;
}

.note {
    color: #81797b;
    font-size: 11px;
    margin-top: 12px;
    line-height: 1.7;
}

.observation {
    border-top: 1px solid #393234;
    border-bottom: 1px solid #393234;
    padding: 18px 0;
}

.station {
    color: #b9b0b2;
    font-size: 13px;
    margin-bottom: 18px;
}

.metrics {
    display: grid;
    grid-template-columns:
        repeat(5, minmax(0, 1fr));
    gap: 12px;
}

.metric {
    padding: 15px;
    background: #211d1e;
    border: 1px solid #332d2f;
    border-radius: 9px;
}

.metric-label {
    color: #81797b;
    font-size: 11px;
    margin-bottom: 8px;
}

.metric-value {
    font-size: 20px;
    font-weight: 400;
}

.pressure {
    display: grid;
    grid-template-columns:
        repeat(2, minmax(0, 1fr));
    gap: 14px;
}

.pressure-box {
    background: #211d1e;
    border: 1px solid #3a3335;
    border-radius: 10px;
    padding: 20px;
}

.pressure-label {
    color: #81797b;
    font-size: 12px;
}

.pressure-value {
    font-size: 30px;
    margin-top: 8px;
}

.trend {
    margin-top: 14px;
    color: #c98991;
}

.status {
    padding: 20px 0;
    border-bottom: 1px solid #393234;
}

.status-main {
    font-size: 19px;
}

.status-sub {
    margin-top: 7px;
    color: #92898b;
    font-size: 13px;
}

.alert {
    padding: 13px 0;
    border-bottom: 1px solid #302a2c;
    color: #d6a0a5;
    font-size: 13px;
}

.chart-box {
    background: #211d1e;
    border: 1px solid #332d2f;
    border-radius: 10px;
    padding: 16px;
    height: 360px;
}

.chart-box.pressure-chart-box {
    height: 390px;
}

.chart-box canvas {
    width: 100% !important;
    height: 100% !important;
}

.chart-explanation {
    margin-top: 10px;
    color: #81797b;
    font-size: 11px;
    line-height: 1.7;
}

.legend-note {
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    margin-top: 10px;
    color: #91888a;
    font-size: 11px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
}

.legend-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #8d6b70;
}

.legend-dot.strong {
    background: #b87880;
}

.legend-dot.rise {
    background: #706e86;
}

.error {
    color: #b8878d;
    font-size: 12px;
    padding: 10px 0;
}

.footer {
    margin-top: 35px;
    padding-top: 18px;
    border-top: 1px solid #393234;
    color: #70696b;
    font-size: 11px;
}

@media (max-width: 800px) {

    body {
        padding: 18px;
    }

    .metrics {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

    .pressure {
        grid-template-columns: 1fr;
    }

    .home-temp {
        font-size: 46px;
    }

    .chart-box {
        height: 330px;
        padding: 10px;
    }

    .chart-box.pressure-chart-box {
        height: 350px;
    }
}

</style>

</head>

<body>

<div class="page">

<header class="header">

    <div class="title">
        <span>奈良本</span>｜標高 約500m
    </div>

    <div class="updated">
        {{ updated }}
    </div>

</header>


<!-- ===================================================== -->
<!-- 自宅推定 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        自宅の現在推定
    </div>

    <div class="home-weather">

        <div class="home-label">
            奈良本・標高約500m地点
        </div>

        <div class="home-temp">

            {% if home_temp is not none %}

                {{ "%.1f"|format(home_temp) }}

                <span class="home-temp-unit">
                    ℃
                </span>

            {% else %}

                —

            {% endif %}

        </div>

        <div class="home-meta">

            {% if home_forecast_time %}
                推定時刻 {{ home_forecast_time }}
            {% endif %}

            {% if home_weather %}
                ｜{{ home_icon }} {{ home_weather }}
            {% endif %}

        </div>

        <div class="note">

            ※気象モデル（MET Norway）による自宅地点の推定値です。<br>
            ※自宅に温度計を設置した実測値ではありません。

        </div>

    </div>

</section>


<!-- ===================================================== -->
<!-- AMeDAS -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        現在の周辺観測
    </div>

    <div class="observation">

        {% if amedas.ok %}

        <div class="station">

            降水：
            {{ amedas.rain_station }}

            {% if amedas.rain_distance is not none %}
                ｜約{{ "%.1f"|format(amedas.rain_distance) }}km
            {% endif %}

            <br>

            気温・湿度・風：
            {{ amedas.four_station }}

            {% if amedas.four_distance is not none %}
                ｜約{{ "%.1f"|format(amedas.four_distance) }}km
            {% endif %}

            ｜観測時刻
            {{ amedas.observed_at.strftime("%Y/%m/%d %H:%M") }}

        </div>

        {% else %}

        <div class="station">
            AMeDASデータ取得エラー
        </div>

        {% endif %}


        <div class="metrics">

            <div class="metric">

                <div class="metric-label">
                    気温
                </div>

                <div class="metric-value">

                    {% if amedas.temp is not none %}
                        {{ "%.1f"|format(amedas.temp) }} ℃
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    湿度
                </div>

                <div class="metric-value">

                    {% if amedas.humidity is not none %}
                        {{ "%.0f"|format(amedas.humidity) }} %
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    降水量（10分）
                </div>

                <div class="metric-value">

                    {% if amedas.rain10 is not none %}
                        {{ "%.1f"|format(amedas.rain10) }} mm
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    風速
                </div>

                <div class="metric-value">

                    {% if amedas.wind is not none %}
                        {{ "%.1f"|format(amedas.wind) }} m/s
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    風向
                </div>

                <div class="metric-value">
                    {{ amedas.wind_direction }}
                </div>

            </div>

        </div>


        <div class="note">

            ※現在値は気象庁AMeDASによる周辺観測です。<br>
            ※自宅周辺と観測地点では、特に風・雨・霧などに差が出る場合があります。

        </div>

    </div>

</section>


<!-- ===================================================== -->
<!-- 気圧現在値 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        自宅地点の気圧
    </div>

    <div class="pressure">

        <div class="pressure-box">

            <div class="pressure-label">
                標高約500mの自宅地点
            </div>

            <div class="pressure-value">

                {% if home_surface_pressure is not none %}

                    {{ "%.1f"|format(home_surface_pressure) }}
                    hPa

                {% else %}

                    —

                {% endif %}

            </div>

        </div>


        <div class="pressure-box">

            <div class="pressure-label">
                海面更正気圧
            </div>

            <div class="pressure-value">

                {% if home_sea_pressure is not none %}

                    {{ "%.1f"|format(home_sea_pressure) }}
                    hPa

                {% else %}

                    —

                {% endif %}

            </div>

        </div>

    </div>


    <div class="trend">

        {% if home_surface_pressure is not none %}

            {{ pressure_level_text }}
            ｜{{ pressure_trend_text }}

        {% else %}

            気圧の傾向を判定できません

        {% endif %}

    </div>

</section>


<!-- ===================================================== -->
<!-- 現在の気象状況 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        現在の気象状況
    </div>

    <div class="status">

        <div class="status-main">
            {{ weather_status }}
        </div>

        <div class="status-sub">
            {{ weather_status_sub }}
        </div>

    </div>

</section>


<!-- ===================================================== -->
<!-- 注意情報 -->
<!-- ===================================================== -->

{% if alerts %}

<section class="section">

    <div class="section-title">
        今後の注意情報
    </div>

    {% for alert in alerts %}

        <div class="alert">
            {{ alert }}
        </div>

    {% endfor %}

</section>

{% endif %}


<!-- ===================================================== -->
<!-- 24時間予報 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        これから24時間
    </div>

    <div class="note">
        奈良本・標高約500m地点の予報
    </div>


    {% if forecasts %}

    <div class="chart-box">

        <canvas id="weatherChart"></canvas>

    </div>

    <div class="chart-explanation">

        気温は折れ線、降水量は棒グラフです。<br>
        天気アイコンと降水確率を時間ごとに表示しています。

    </div>

    {% else %}

    <div class="error">
        自宅地点の予報データを取得できませんでした。
    </div>

    {% endif %}

</section>


<!-- ===================================================== -->
<!-- 気圧グラフ -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        24時間の気圧
    </div>

    <div class="chart-box pressure-chart-box">

        <canvas id="pressureChart"></canvas>

    </div>


    <div class="legend-note">

        <div class="legend-item">
            <span class="legend-dot"></span>
            気圧変化あり
        </div>

        <div class="legend-item">
            <span class="legend-dot strong"></span>
            大きな気圧変化
        </div>

        <div class="legend-item">
            <span class="legend-dot rise"></span>
            上昇方向
        </div>

    </div>


    <div class="chart-explanation">

        3時間程度の気圧変化を目安に、
        変化が大きい時間帯を背景で表示しています。<br>
        「注意」は気圧そのものの高低ではなく、
        短時間の変化が大きい時間帯を示します。

    </div>

</section>


<footer class="footer">

    奈良本｜標高 約500m
    ｜24時間予報：MET Norway

</footer>


</div>


<script>

const forecastLabels =
    {{ chart_labels | safe }};

const temperatures =
    {{ chart_temperatures | safe }};

const precipitation =
    {{ chart_precipitation | safe }};

const rainProbability =
    {{ chart_rain_probability | safe }};

const forecastIcons =
    {{ chart_icons | safe }};

const pressures =
    {{ chart_pressures | safe }};

const pressureLevels =
    {{ pressure_levels | safe }};

const pressureChanges =
    {{ pressure_changes | safe }};


/* =========================================================
   共通設定
   ========================================================= */

const gridColor = "#302a2c";
const textColor = "#8d8587";


/* =========================================================
   24時間 天気＋気温
   ========================================================= */

const weatherPlugin = {

    id: "weatherPlugin",

    afterDatasetsDraw(chart) {

        const ctx = chart.ctx;

        const meta =
            chart.getDatasetMeta(0);

        ctx.save();

        meta.data.forEach(
            (point, index) => {

                const x = point.x;

                const y = point.y;

                const icon =
                    forecastIcons[index];

                const probability =
                    rainProbability[index];

                if (icon) {

                    ctx.font =
                        "18px sans-serif";

                    ctx.textAlign =
                        "center";

                    ctx.textBaseline =
                        "middle";

                    ctx.fillText(
                        icon,
                        x,
                        y - 28
                    );

                }

                if (
                    probability !== null
                    &&
                    probability !== undefined
                ) {

                    ctx.font =
                        "10px sans-serif";

                    ctx.fillStyle =
                        "#aaa1a3";

                    ctx.textAlign =
                        "center";

                    ctx.fillText(
                        "☔ " +
                        Math.round(
                            probability
                        ) +
                        "%",
                        x,
                        y - 48
                    );

                }

            }
        );

        ctx.restore();

    }

};


new Chart(

    document.getElementById(
        "weatherChart"
    ),

    {

        type: "line",

        plugins: [
            weatherPlugin
        ],

        data: {

            labels:
                forecastLabels,

            datasets: [

                {

                    label:
                        "気温",

                    data:
                        temperatures,

                    yAxisID:
                        "temperature",

                    tension:
                        0.35,

                    pointRadius:
                        3,

                    pointHoverRadius:
                        5,

                    borderWidth:
                        2,

                },

                {

                    type:
                        "bar",

                    label:
                        "降水量",

                    data:
                        precipitation,

                    yAxisID:
                        "rain",

                    borderWidth:
                        0,

                    barPercentage:
                        0.65,

                    categoryPercentage:
                        0.9,

                }

            ]

        },

        options: {

            responsive:
                true,

            maintainAspectRatio:
                false,

            interaction: {

                mode:
                    "index",

                intersect:
                    false

            },

            plugins: {

                legend: {

                    display:
                        true,

                    labels: {

                        color:
                            textColor

                    }

                },

                tooltip: {

                    callbacks: {

                        label(context) {

                            const index =
                                context.dataIndex;

                            if (
                                context.datasetIndex
                                === 0
                            ) {

                                const temp =
                                    temperatures[index];

                                return (
                                    "気温 "
                                    +
                                    (
                                        temp !== null
                                            ? temp.toFixed(1)
                                            : "—"
                                    )
                                    +
                                    "℃"
                                );

                            }

                            const rain =
                                precipitation[index];

                            const probability =
                                rainProbability[index];

                            return (
                                "降水 "
                                +
                                (
                                    rain !== null
                                        ? rain.toFixed(1)
                                        : "—"
                                )
                                +
                                "mm"
                                +
                                "｜降水確率 "
                                +
                                (
                                    probability !== null
                                        ? Math.round(
                                            probability
                                        )
                                        : "—"
                                )
                                +
                                "%"
                            );

                        }

                    }

                }

            },

            scales: {

                x: {

                    ticks: {

                        color:
                            textColor,

                        maxTicksLimit:
                            12

                    },

                    grid: {

                        color:
                            gridColor

                    }

                },

                temperature: {

                    type:
                        "linear",

                    position:
                        "left",

                    ticks: {

                        color:
                            textColor,

                        callback(value) {

                            return value + "℃";

                        }

                    },

                    grid: {

                        color:
                            gridColor

                    }

                },

                rain: {

                    type:
                        "linear",

                    position:
                        "right",

                    beginAtZero:
                        true,

                    grid: {

                        drawOnChartArea:
                            false

                    },

                    ticks: {

                        color:
                            textColor,

                        callback(value) {

                            return value + "mm";

                        }

                    }

                }

            }

        }

    }

);


/* =========================================================
   気圧グラフ
   ========================================================= */

const pressureBackgroundPlugin = {

    id:
        "pressureBackgroundPlugin",

    beforeDatasetsDraw(chart) {

        const ctx =
            chart.ctx;

        const xScale =
            chart.scales.x;

        const chartArea =
            chart.chartArea;

        if (!xScale) {
            return;
        }

        ctx.save();

        for (
            let i = 0;
            i < pressureLevels.length;
            i++
        ) {

            const level =
                pressureLevels[i];

            if (
                level === "normal"
                || level === null
            ) {
                continue;
            }

            const x1 =
                xScale.getPixelForValue(
                    i
                );

            const x2 =
                i <
                pressureLevels.length - 1
                    ? xScale.getPixelForValue(
                        i + 1
                    )
                    : x1 + 30;

            let fill =
                "rgba(150,110,120,0.08)";

            if (
                level === "strong-fall"
                ||
                level === "strong-rise"
            ) {

                fill =
                    "rgba(190,110,120,0.18)";

            }

            if (
                level === "rise"
                ||
                level === "strong-rise"
            ) {

                fill =
                    "rgba(105,105,140,0.12)";

            }

            ctx.fillStyle =
                fill;

            ctx.fillRect(

                x1,

                chartArea.top,

                x2 - x1,

                chartArea.bottom
                - chartArea.top

            );

        }

        ctx.restore();

    },


    afterDatasetsDraw(chart) {

        const ctx =
            chart.ctx;

        const xScale =
            chart.scales.x;

        const yScale =
            chart.scales.y;

        if (!xScale || !yScale) {
            return;
        }

        ctx.save();

        for (
            let i = 0;
            i < pressureLevels.length;
            i++
        ) {

            const level =
                pressureLevels[i];

            if (
                level === "normal"
                || level === null
            ) {
                continue;
            }

            const change =
                pressureChanges[i];

            if (change === null) {
                continue;
            }

            const x =
                xScale.getPixelForValue(i);

            const y =
                yScale.getPixelForValue(
                    pressures[i]
                );

            let label = "";

            if (
                level === "strong-fall"
            ) {

                label =
                    "⚠ 急低下";

            } else if (
                level === "fall"
            ) {

                label =
                    "低下";

            } else if (
                level === "strong-rise"
            ) {

                label =
                    "⚠ 急上昇";

            } else if (
                level === "rise"
            ) {

                label =
                    "上昇";

            }

            ctx.font =
                "10px sans-serif";

            ctx.textAlign =
                "center";

            ctx.textBaseline =
                "bottom";

            ctx.fillStyle =
                (
                    level === "strong-fall"
                    ||
                    level === "strong-rise"
                )
                    ? "#d6a0a5"
                    : "#a89599";

            ctx.fillText(
                label,
                x,
                y - 8
            );

        }

        ctx.restore();

    }

};


new Chart(

    document.getElementById(
        "pressureChart"
    ),

    {

        type:
            "line",

        plugins: [
            pressureBackgroundPlugin
        ],

        data: {

            labels:
                forecastLabels,

            datasets: [

                {

                    label:
                        "自宅地点の気圧",

                    data:
                        pressures,

                    tension:
                        0.35,

                    pointRadius:
                        3,

                    pointHoverRadius:
                        5,

                    borderWidth:
                        2,

                }

            ]

        },

        options: {

            responsive:
                true,

            maintainAspectRatio:
                false,

            interaction: {

                mode:
                    "index",

                intersect:
                    false

            },

            plugins: {

                legend: {

                    display:
                        false

                },

                tooltip: {

                    callbacks: {

                        label(context) {

                            const index =
                                context.dataIndex;

                            const pressure =
                                pressures[index];

                            const change =
                                pressureChanges[index];

                            let text =
                                "気圧 "
                                +
                                (
                                    pressure !== null
                                        ? pressure.toFixed(1)
                                        : "—"
                                )
                                +
                                " hPa";

                            if (
                                change !== null
                            ) {

                                text +=
                                    "｜3時間変化 "
                                    +
                                    (
                                        change >= 0
                                            ? "+"
                                            : ""
                                    )
                                    +
                                    change.toFixed(1)
                                    +
                                    " hPa";

                            }

                            return text;

                        }

                    }

                }

            },

            scales: {

                x: {

                    ticks: {

                        color:
                            textColor,

                        maxTicksLimit:
                            12

                    },

                    grid: {

                        color:
                            gridColor

                    }

                },

                y: {

                    ticks: {

                        color:
                            textColor,

                        callback(value) {

                            return value
                                + " hPa";

                        }

                    },

                    grid: {

                        color:
                            gridColor

                    }

                }

            }

        }

    }

);

</script>

</body>
</html>
"""


# ============================================================
# メイン
# ============================================================

@app.route("/")
def index():

    now = jst_now()

    amedas = get_amedas()

    met_json = get_met_forecast()

    all_forecasts = build_forecasts(
        met_json
    )

    all_forecasts = add_pressure_change_info(
        all_forecasts
    )


    # --------------------------------------------------------
    # 現在の自宅推定
    # --------------------------------------------------------

    current_forecast = nearest_forecast(
        all_forecasts
    )

    home_temp = None
    home_surface_pressure = None
    home_sea_pressure = None
    home_weather = None
    home_icon = "🌤️"
    home_forecast_time = None

    if current_forecast:

        home_temp = (
            current_forecast[
                "temperature"
            ]
        )

        home_surface_pressure = (
            current_forecast[
                "surface_pressure"
            ]
        )

        home_sea_pressure = (
            current_forecast[
                "sea_pressure"
            ]
        )

        home_weather = (
            current_forecast[
                "weather"
            ]
        )

        home_icon = (
            current_forecast[
                "icon"
            ]
        )

        home_forecast_time = (
            current_forecast["dt"]
            .strftime(
                "%Y/%m/%d %H:%M"
            )
        )


    # --------------------------------------------------------
    # これから24時間
    # --------------------------------------------------------

    end_time = (
        now + timedelta(hours=24)
    )

    forecasts = [

        item

        for item in all_forecasts

        if (
            now
            - timedelta(minutes=30)
            <= item["dt"]
            <= end_time
        )

    ]


    # 同じ時間帯の重複を削除

    unique = []

    seen = set()

    for item in forecasts:

        key = item["dt"].strftime(
            "%Y%m%d%H"
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(item)

    forecasts = unique[:24]


    # --------------------------------------------------------
    # 気圧
    # --------------------------------------------------------

    pressure_trend_text = (
        pressure_trend(
            all_forecasts
        )
    )

    pressure_level_text = (
        pressure_level(
            home_surface_pressure
        )
    )


    # --------------------------------------------------------
    # 現在の気象状況
    # --------------------------------------------------------

    (
        weather_status,
        weather_status_sub
    ) = current_weather_status(
        amedas
    )


    # --------------------------------------------------------
    # 注意情報
    # --------------------------------------------------------

    alerts = build_alerts(
        forecasts
    )


    # --------------------------------------------------------
    # グラフ用データ
    # --------------------------------------------------------

    chart_labels = [

        item["dt"].strftime("%H:%M")

        for item in forecasts

    ]

    chart_temperatures = [

        item["temperature"]

        for item in forecasts

    ]

    chart_precipitation = [

        item["precipitation"]

        for item in forecasts

    ]

    chart_rain_probability = [

        item["rain_probability"]

        for item in forecasts

    ]

    chart_icons = [

        item["icon"]

        for item in forecasts

    ]

    chart_pressures = [

        item["surface_pressure"]

        for item in forecasts

    ]

    pressure_levels = [

        item["pressure_level"]

        for item in forecasts

    ]

    pressure_changes = [

        item["pressure_change"]

        for item in forecasts

    ]


    # --------------------------------------------------------
    # JSON化
    # --------------------------------------------------------

    chart_labels_json = json.dumps(
        chart_labels,
        ensure_ascii=False
    )

    chart_temperatures_json = json.dumps(
        chart_temperatures,
        ensure_ascii=False
    )

    chart_precipitation_json = json.dumps(
        chart_precipitation,
        ensure_ascii=False
    )

    chart_rain_probability_json = json.dumps(
        chart_rain_probability,
        ensure_ascii=False
    )

    chart_icons_json = json.dumps(
        chart_icons,
        ensure_ascii=False
    )

    chart_pressures_json = json.dumps(
        chart_pressures,
        ensure_ascii=False
    )

    pressure_levels_json = json.dumps(
        pressure_levels,
        ensure_ascii=False
    )

    pressure_changes_json = json.dumps(
        pressure_changes,
        ensure_ascii=False
    )


    # --------------------------------------------------------
    # METエラー
    # --------------------------------------------------------

    met_error = None

    if met_json is None:

        met_error = (
            "自宅地点の予報データを取得できませんでした。"
        )


    return render_template_string(

        HTML,

        updated=now.strftime(
            "%Y/%m/%d %H:%M"
        ),

        amedas=amedas,

        home_temp=home_temp,

        home_surface_pressure=(
            home_surface_pressure
        ),

        home_sea_pressure=(
            home_sea_pressure
        ),

        home_weather=home_weather,

        home_icon=home_icon,

        home_forecast_time=(
            home_forecast_time
        ),

        pressure_trend_text=(
            pressure_trend_text
        ),

        pressure_level_text=(
            pressure_level_text
        ),

        weather_status=(
            weather_status
        ),

        weather_status_sub=(
            weather_status_sub
        ),

        alerts=alerts,

        forecasts=forecasts,

        chart_labels=(
            chart_labels_json
        ),

        chart_temperatures=(
            chart_temperatures_json
        ),

        chart_precipitation=(
            chart_precipitation_json
        ),

        chart_rain_probability=(
            chart_rain_probability_json
        ),

        chart_icons=(
            chart_icons_json
        ),

        chart_pressures=(
            chart_pressures_json
        ),

        pressure_levels=(
            pressure_levels_json
        ),

        pressure_changes=(
            pressure_changes_json
        ),

        met_error=met_error,

    )


# ============================================================
# Render / Gunicorn
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