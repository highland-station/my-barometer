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

# Renderの環境変数 MET_CONTACT_EMAIL に自分のメールアドレスを
# 設定しておくと確実です。
#
# 未設定の場合は下の文字列が使われます。
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
    """数値へ安全に変換"""
    try:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def format_number(value, digits=1):
    """表示用数値"""
    if value is None:
        return "—"

    return f"{value:.{digits}f}"


def coord_to_decimal(value):
    """
    AMeDASの [度, 分] または [度, 分, 秒] を
    十進法へ変換。
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
    """簡易ハーサイン距離"""
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


def get_json(url, timeout=20, headers=None):
    """JSON取得"""
    response = requests.get(
        url,
        timeout=timeout,
        headers=headers
    )

    response.raise_for_status()

    return response.json()


def get_latest_amedas_time():
    """AMeDAS最新観測時刻取得"""

    response = requests.get(
        JMA_LATEST_URL,
        timeout=20
    )

    response.raise_for_status()

    text = response.text.strip()

    # 例:
    # 2026-09-04T11:10:00Z
    dt = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    )

    return dt.astimezone(JST)


def find_nearest_station(stations):
    """自宅に最も近いAMeDAS観測所を探す"""

    best = None
    best_distance = None

    for station_id, station in stations.items():

        lat = coord_to_decimal(station.get("lat"))
        lon = coord_to_decimal(station.get("lon"))

        if lat is None or lon is None:
            continue

        distance = distance_km(
            HOME_LAT,
            HOME_LON,
            lat,
            lon
        )

        if best_distance is None or distance < best_distance:

            best_distance = distance

            best = {
                "id": str(station_id),
                "name": station.get("kjName")
                or station.get("enName")
                or str(station_id),
                "lat": lat,
                "lon": lon,
                "distance": distance,
            }

    return best


def amedas_value(obs, key):
    """
    AMeDASの値を安全に取得。

    AMeDASでは
    [値, 品質情報, 品質情報...]
    のような配列になることがある。
    """

    if not obs:
        return None

    value = obs.get(key)

    if isinstance(value, list):

        if len(value) == 0:
            return None

        return safe_float(value[0])

    return safe_float(value)


def get_amedas():
    """周辺AMeDAS観測"""

    try:

        latest_dt = get_latest_amedas_time()

        timestamp = latest_dt.strftime(
            "%Y%m%d%H%M%S"
        )

        stations = get_json(
            JMA_STATION_URL
        )

        station = find_nearest_station(
            stations
        )

        if station is None:
            raise RuntimeError(
                "AMeDAS観測所が見つかりません"
            )

        data = get_json(
            JMA_MAP_URL.format(timestamp)
        )

        station_id = station["id"]

        obs = (
            data.get(station_id)
            or data.get(str(station_id))
        )

        if obs is None:

            # 念のため整数キーも確認
            try:
                obs = data.get(int(station_id))
            except Exception:
                pass

        if obs is None:
            raise RuntimeError(
                f"AMeDAS観測データなし: {station_id}"
            )

        temp = amedas_value(obs, "temp")
        humidity = amedas_value(obs, "humidity")
        rain10 = amedas_value(
            obs,
            "precipitation10m"
        )
        rain1h = amedas_value(
            obs,
            "precipitation1h"
        )
        wind = amedas_value(
            obs,
            "wind"
        )
        wind_direction_value = amedas_value(
            obs,
            "windDirection"
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

        # 視程
        visibility = amedas_value(
            obs,
            "visibility"
        )

        # デバッグ用。
        # 必要ならRenderのログで実際のAMeDAS構造を確認できます。
        print(
            "AMeDAS:",
            station["name"],
            "temp=", temp,
            "humidity=", humidity,
            "rain10=", rain10,
            "wind=", wind,
            "windDirection=", wind_direction_value
        )

        return {
            "ok": True,
            "station": station["name"],
            "station_id": station_id,
            "distance": station["distance"],
            "observed_at": latest_dt,
            "temp": temp,
            "humidity": humidity,
            "rain10": rain10,
            "rain1h": rain1h,
            "wind": wind,
            "wind_direction": wind_direction,
            "visibility": visibility,
            "raw": obs,
        }

    except Exception as e:

        print(
            "AMeDAS ERROR:",
            repr(e)
        )

        return {
            "ok": False,
            "error": str(e),
            "station": "—",
            "distance": None,
            "observed_at": None,
            "temp": None,
            "humidity": None,
            "rain10": None,
            "rain1h": None,
            "wind": None,
            "wind_direction": "—",
            "visibility": None,
            "raw": {},
        }


# ============================================================
# MET Norway
# ============================================================

def get_met_forecast():
    """奈良本・標高500mの予報"""

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

        return response.json()

    except Exception as e:

        print(
            "MET ERROR:",
            repr(e)
        )

        return None


def get_period_data(data):
    """
    next_1_hours → next_6_hours → next_12_hours
    の順で期間データを取得。
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
    """MET Norwayのsymbol_codeを日本語表示へ"""

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
    """天気アイコン"""

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
    """
    MET Norway JSONから24時間分を作る。
    """

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

            instant = (
                item
                .get("data", {})
                .get("instant", {})
                .get("details", {})
            )

            period = get_period_data(
                item.get("data", {})
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
                instant.get("air_temperature")
            )

            humidity = safe_float(
                instant.get("relative_humidity")
            )

            sea_pressure = safe_float(
                instant.get(
                    "air_pressure_at_sea_level"
                )
            )

            wind = safe_float(
                instant.get("wind_speed")
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

            # 自宅標高500mの推定地上気圧
            surface = None

            if (
                sea_pressure is not None
                and temperature is not None
            ):

                surface = (
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
                "surface_pressure": surface,
                "wind": wind,
                "wind_direction": wind_direction,
                "precipitation": precipitation,
                "rain_probability": rain_probability,
                "thunder_probability": thunder_probability,
                "symbol": symbol,
                "weather": symbol_to_japanese(
                    symbol
                ),
                "icon": symbol_icon(symbol),
            })

        except Exception as e:

            print(
                "FORECAST ITEM ERROR:",
                repr(e)
            )

    return forecasts


# ============================================================
# 自宅現在値
# ============================================================

def nearest_forecast(forecasts):
    """
    現在時刻に最も近いMET予報を取得。
    """

    if not forecasts:
        return None

    now = datetime.now(JST)

    return min(
        forecasts,
        key=lambda x: abs(
            (x["dt"] - now).total_seconds()
        )
    )


# ============================================================
# 気圧傾向
# ============================================================

def pressure_trend(forecasts):
    """
    現在付近から数時間の気圧変化を判定。
    """

    current = nearest_forecast(
        forecasts
    )

    if current is None:
        return "気圧の傾向を判定できません"

    now = datetime.now(JST)

    future = [
        x for x in forecasts
        if x["dt"] >= now
    ]

    if len(future) < 2:
        return "気圧の傾向を判定できません"

    current_pressure = (
        current["surface_pressure"]
    )

    if current_pressure is None:
        return "気圧の傾向を判定できません"

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
        return "気圧の傾向を判定できません"

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
    """気圧の大まかな表示"""

    if pressure is None:
        return "—"

    if pressure >= 1020:
        return "高め"

    if pressure <= 1000:
        return "低め"

    return "標準"


# ============================================================
# 天気状況
# ============================================================

def current_weather_status(amedas):
    """
    現在の状況はAMeDAS実測を優先。
    """

    rain = amedas.get("rain10")

    visibility = amedas.get(
        "visibility"
    )

    if (
        visibility is not None
        and visibility <= 1000
    ):
        return (
            "🌫️ 視程が低下しています",
            "周辺AMeDASで視程1000m以下が観測されています。"
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
            "周辺AMeDASでは直近10分の降水はありません。"
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

    future = forecasts[:]

    for item in future:

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

    # 重複削除
    result = []

    for alert in alerts:

        if alert not in result:
            result.append(alert)

    return result[:4]


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

.forecast-wrap {
    overflow-x: auto;
    padding-bottom: 10px;
}

.forecast {
    display: flex;
    gap: 10px;
    min-width: max-content;
}

.forecast-card {
    width: 112px;
    background: #211d1e;
    border: 1px solid #332d2f;
    border-radius: 10px;
    padding: 13px;
    text-align: center;
}

.forecast-time {
    color: #8d8587;
    font-size: 11px;
}

.forecast-icon {
    font-size: 28px;
    margin: 8px 0;
}

.forecast-temp {
    font-size: 21px;
}

.forecast-weather {
    margin-top: 4px;
    color: #aaa1a3;
    font-size: 11px;
}

.forecast-rain {
    margin-top: 10px;
    font-size: 11px;
    color: #b9b0b2;
}

.chart-box {
    background: #211d1e;
    border: 1px solid #332d2f;
    border-radius: 10px;
    padding: 16px;
    height: 310px;
}

.chart-box canvas {
    width: 100% !important;
    height: 100% !important;
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
}

</style>

</head>

<body>

<div class="page">

    <header class="header">

        <div class="title">
            <span>奈良本</span>
            ｜標高 約500m
        </div>

        <div class="updated">
            {{ updated }}
        </div>

    </header>


    <!-- 自宅の推定気温 -->

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
                    <span class="home-temp-unit">℃</span>
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
                ※気象モデル（MET Norway）による自宅地点の推定値です。
                自宅に温度計を設置した実測値ではありません。
            </div>

        </div>

    </section>


    <!-- 周辺観測 -->

    <section class="section">

        <div class="section-title">
            現在の周辺観測
        </div>

        <div class="observation">

            <div class="station">

                {% if amedas.ok %}

                    {{ amedas.station }}
                    ｜観測時刻
                    {{ amedas.observed_at.strftime("%Y/%m/%d %H:%M") }}

                    {% if amedas.distance is not none %}
                        ｜自宅から約
                        {{ "%.1f"|format(amedas.distance) }}km
                    {% endif %}

                {% else %}

                    天城山 ｜ AMeDASデータ取得エラー

                {% endif %}

            </div>


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
                        風
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


    <!-- 気圧 -->

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


    <!-- 現在の気象状況 -->

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


    <!-- 注意情報 -->

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


    <!-- 24時間予報 -->

    <section class="section">

        <div class="section-title">
            これから24時間
        </div>

        <div class="note">
            奈良本・標高約500m地点の予報
        </div>

        {% if forecasts %}

        <div class="forecast-wrap">

            <div class="forecast">

                {% for item in forecasts %}

                <div class="forecast-card">

                    <div class="forecast-time">
                        {{ item.dt.strftime("%H:%M") }}
                    </div>

                    <div class="forecast-icon">
                        {{ item.icon }}
                    </div>

                    <div class="forecast-temp">

                        {% if item.temperature is not none %}
                            {{ "%.1f"|format(item.temperature) }}℃
                        {% else %}
                            —
                        {% endif %}

                    </div>

                    <div class="forecast-weather">
                        {{ item.weather }}
                    </div>

                    <div class="forecast-rain">

                        ☔

                        {% if item.rain_probability is not none %}
                            {{ "%.0f"|format(item.rain_probability) }}%
                        {% else %}
                            —
                        {% endif %}

                        {% if item.precipitation is not none %}
                            ｜{{ "%.1f"|format(item.precipitation) }}mm
                        {% endif %}

                    </div>

                </div>

                {% endfor %}

            </div>

        </div>

        {% else %}

            <div class="error">
                自宅地点の予報データを取得できませんでした。
            </div>

        {% endif %}

    </section>


    <!-- 気温グラフ -->

    <section class="section">

        <div class="section-title">
            24時間の気温
        </div>

        <div class="chart-box">

            <canvas id="temperatureChart"></canvas>

        </div>

    </section>


    <!-- 気圧グラフ -->

    <section class="section">

        <div class="section-title">
            24時間の気圧
        </div>

        <div class="chart-box">

            <canvas id="pressureChart"></canvas>

        </div>

    </section>


    <footer class="footer">

        奈良本｜標高 約500m
        ｜24時間予報：MET Norway

    </footer>

</div>


<script>

const forecastLabels = {{ chart_labels | safe }};
const temperatures = {{ chart_temperatures | safe }};
const pressures = {{ chart_pressures | safe }};


new Chart(
    document.getElementById("temperatureChart"),
    {
        type: "line",

        data: {
            labels: forecastLabels,

            datasets: [{
                label: "気温 ℃",
                data: temperatures,
                tension: 0.35,
                pointRadius: 2,
                borderWidth: 2
            }]
        },

        options: {

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
                        color: "#8d8587",
                        maxTicksLimit: 12
                    },

                    grid: {
                        color: "#302a2c"
                    }
                },

                y: {
                    ticks: {
                        color: "#8d8587"
                    },

                    grid: {
                        color: "#302a2c"
                    }
                }

            }

        }

    }
);


new Chart(
    document.getElementById("pressureChart"),
    {
        type: "line",

        data: {
            labels: forecastLabels,

            datasets: [{
                label: "自宅地点の気圧 hPa",
                data: pressures,
                tension: 0.35,
                pointRadius: 2,
                borderWidth: 2
            }]
        },

        options: {

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
                        color: "#8d8587",
                        maxTicksLimit: 12
                    },

                    grid: {
                        color: "#302a2c"
                    }
                },

                y: {
                    ticks: {
                        color: "#8d8587"
                    },

                    grid: {
                        color: "#302a2c"
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


    # --------------------------------------------------------
    # 現在に最も近い自宅予報
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

        home_temp = current_forecast[
            "temperature"
        ]

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

        home_weather = current_forecast[
            "weather"
        ]

        home_icon = current_forecast[
            "icon"
        ]

        home_forecast_time = (
            current_forecast["dt"]
            .strftime("%Y/%m/%d %H:%M")
        )


    # --------------------------------------------------------
    # これから24時間
    # --------------------------------------------------------

    end_time = now + timedelta(
        hours=24
    )

    forecasts = [
        item
        for item in all_forecasts
        if now - timedelta(minutes=30)
        <= item["dt"]
        <= end_time
    ]


    # 同じ時間帯の重複を避ける
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

    pressure_trend_text = pressure_trend(
        all_forecasts
    )

    pressure_level_text = pressure_level(
        home_surface_pressure
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
    # グラフ
    # --------------------------------------------------------

    chart_labels = [
        item["dt"].strftime("%H:%M")
        for item in forecasts
    ]

    chart_temperatures = [
        item["temperature"]
        for item in forecasts
    ]

    chart_pressures = [
        item["surface_pressure"]
        for item in forecasts
    ]


    # --------------------------------------------------------
    # METエラーを小さく表示
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
            str(chart_labels)
            .replace("'", '"')
        ),

        chart_temperatures=(
            str(chart_temperatures)
            .replace("'", '"')
        ),

        chart_pressures=(
            str(chart_pressures)
            .replace("'", '"')
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