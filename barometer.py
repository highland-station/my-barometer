from flask import Flask, render_template_string
import requests
import math
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# ============================================================
# 基本設定
# ============================================================

HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

JST = timezone(timedelta(hours=9))

JMA_LATEST_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
JMA_STATION_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"

HEADERS = {
    "User-Agent": "Naraboto-Weather-Dashboard/1.0 contact@example.com"
}

# ============================================================
# 共通
# ============================================================

def safe_float(value):
    """数値を安全にfloatへ"""
    if value is None:
        return None

    if isinstance(value, list):
        if not value:
            return None
        value = value[0]

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def jma_value(obs, key):
    """AMeDASの [値, 品質情報, ...] 形式を安全に取り出す"""
    if not obs:
        return None

    value = obs.get(key)

    if value is None:
        return None

    if isinstance(value, list):
        if len(value) == 0:
            return None
        return safe_float(value[0])

    return safe_float(value)


# ============================================================
# AMeDAS地点座標
# ============================================================

def coord_to_decimal(value):
    """
    JMA AMeDASの座標は
    [度, 分] 形式なので10進数へ変換する。
    """
    if isinstance(value, list) and len(value) >= 2:
        degree = safe_float(value[0])
        minute = safe_float(value[1])

        if degree is None or minute is None:
            return None

        return degree + minute / 60.0

    return safe_float(value)


def find_nearest_station(stations):
    """自宅から最も近いAMeDAS地点を探す"""

    best = None
    best_distance = float("inf")

    cos_lat = math.cos(math.radians(HOME_LAT))

    for station_id, station in stations.items():

        lat = coord_to_decimal(station.get("lat"))
        lon = coord_to_decimal(station.get("lon"))

        if lat is None or lon is None:
            continue

        # 緯度経度の簡易距離
        dlat = lat - HOME_LAT
        dlon = (lon - HOME_LON) * cos_lat

        distance = dlat * dlat + dlon * dlon

        if distance < best_distance:
            best_distance = distance

            best = {
                "id": str(station_id),
                "name": station.get("kjName") or station.get("kjName2") or "AMeDAS",
                "lat": lat,
                "lon": lon,
                "alt": station.get("alt"),
                "distance_km": math.sqrt(
                    dlat * dlat + dlon * dlon
                ) * 111.0
            }

    return best


# ============================================================
# 現在のAMeDAS観測
# ============================================================

def get_current_amedas():
    try:
        # --------------------------------------------
        # 最新観測時刻
        # --------------------------------------------
        r = requests.get(
            JMA_LATEST_URL,
            timeout=15
        )
        r.raise_for_status()

        latest_text = r.text.strip()

        if not latest_text:
            raise Exception("latest_time.txt が空です")

        # ISO形式
        try:
            latest_dt = datetime.fromisoformat(
                latest_text.replace("Z", "+00:00")
            )
        except ValueError:
            # 念のため YYYYMMDDHHMMSS にも対応
            latest_dt = datetime.strptime(
                latest_text[:14],
                "%Y%m%d%H%M%S"
            ).replace(tzinfo=JST)

        latest_jst = latest_dt.astimezone(JST)

        timestamp = latest_jst.strftime("%Y%m%d%H%M%S")

        # --------------------------------------------
        # 観測地点一覧
        # --------------------------------------------
        r = requests.get(
            JMA_STATION_URL,
            timeout=15
        )
        r.raise_for_status()

        stations = r.json()

        station = find_nearest_station(stations)

        if not station:
            raise Exception("最寄りAMeDAS地点を見つけられませんでした")

        station_id = station["id"]

        # --------------------------------------------
        # 最新AMeDASマップ
        # --------------------------------------------
        map_url = (
            f"https://www.jma.go.jp/bosai/amedas/data/map/"
            f"{timestamp}.json"
        )

        r = requests.get(
            map_url,
            timeout=15
        )
        r.raise_for_status()

        data = r.json()

        obs = data.get(station_id)

        if obs is None:
            # IDの文字列/数値違い対策
            obs = data.get(str(station_id))

        if obs is None:
            raise Exception(
                f"AMeDAS観測値がありません: {station_id}"
            )

        # --------------------------------------------
        # 観測値
        # --------------------------------------------

        temperature = jma_value(obs, "temp")
        humidity = jma_value(obs, "humidity")
        rain10 = jma_value(obs, "precipitation10m")
        rain1h = jma_value(obs, "precipitation1h")
        wind = jma_value(obs, "wind")
        wind_direction = jma_value(obs, "windDirection")
        pressure = jma_value(obs, "pressure")
        normal_pressure = jma_value(obs, "normalPressure")
        visibility = jma_value(obs, "visibility")

        return {
            "ok": True,
            "station_name": station["name"],
            "station_id": station_id,
            "station_distance": station["distance_km"],
            "observed_at": latest_jst.strftime("%Y/%m/%d %H:%M"),

            "temperature": temperature,
            "humidity": humidity,
            "rain10": rain10,
            "rain1h": rain1h,
            "wind": wind,
            "wind_direction": wind_direction,
            "pressure": pressure,
            "normal_pressure": normal_pressure,
            "visibility": visibility,
        }

    except Exception as e:
        print("AMeDAS ERROR:", repr(e))

        return {
            "ok": False,
            "error": str(e)
        }


# ============================================================
# JMA風向
# ============================================================

WIND_DIRECTIONS = [
    "静穏",
    "北",
    "北北東",
    "北東",
    "東北東",
    "東",
    "東南東",
    "南東",
    "南南東",
    "南",
    "南南西",
    "南西",
    "西南西",
    "西",
    "西北西",
    "北西",
    "北北西",
]


def jma_wind_direction(value):
    if value is None:
        return "—"

    try:
        index = int(round(value))

        if 0 <= index < len(WIND_DIRECTIONS):
            return WIND_DIRECTIONS[index]

    except Exception:
        pass

    return "—"


# ============================================================
# 自宅地点の気圧
# ============================================================

def calculate_surface_pressure(sea_level_pressure, temperature):
    """
    海面更正気圧から標高500mの自宅地点の気圧を推定
    """

    if sea_level_pressure is None or temperature is None:
        return None

    return sea_level_pressure * math.exp(
        -9.80665 * HOME_ALTITUDE /
        (287.05 * (temperature + 273.15))
    )


# ============================================================
# MET Norway
# ============================================================

def get_met_forecast():
    try:
        params = {
            "lat": HOME_LAT,
            "lon": HOME_LON,
            "altitude": HOME_ALTITUDE
        }

        r = requests.get(
            MET_URL,
            params=params,
            headers=HEADERS,
            timeout=20
        )

        r.raise_for_status()

        return r.json()

    except Exception as e:
        print("MET ERROR:", repr(e))
        return None


# ============================================================
# MET天気アイコン
# ============================================================

def weather_icon(symbol):
    if not symbol:
        return "☁️"

    symbol = symbol.lower()

    if "thunder" in symbol:
        return "⛈️"

    if "heavyrain" in symbol:
        return "🌧️"

    if "rain" in symbol:
        return "🌦️"

    if "snow" in symbol:
        return "❄️"

    if "sleet" in symbol:
        return "🌨️"

    if "fog" in symbol:
        return "🌫️"

    if "clearsky" in symbol:
        return "☀️"

    if "fair" in symbol:
        return "🌤️"

    if "partlycloudy" in symbol:
        return "⛅"

    if "cloudy" in symbol:
        return "☁️"

    return "☁️"


def weather_name(symbol):
    if not symbol:
        return "曇り"

    symbol = symbol.lower()

    if "thunder" in symbol:
        return "雷雨"

    if "heavyrain" in symbol:
        return "強い雨"

    if "rain" in symbol:
        return "雨"

    if "snow" in symbol:
        return "雪"

    if "sleet" in symbol:
        return "みぞれ"

    if "fog" in symbol:
        return "霧"

    if "clearsky" in symbol:
        return "晴れ"

    if "fair" in symbol:
        return "晴れ"

    if "partlycloudy" in symbol:
        return "晴れ時々曇り"

    if "cloudy" in symbol:
        return "曇り"

    return "曇り"


# ============================================================
# MET予報を24時間分取り出す
# ============================================================

def build_forecast_items(met_data):

    if not met_data:
        return []

    timeseries = (
        met_data
        .get("properties", {})
        .get("timeseries", [])
    )

    items = []

    now = datetime.now(JST)

    for item in timeseries:

        try:
            valid_time = datetime.fromisoformat(
                item["time"].replace("Z", "+00:00")
            ).astimezone(JST)
        except Exception:
            continue

        # 現在から24時間
        diff_hours = (
            valid_time - now
        ).total_seconds() / 3600

        if diff_hours < -0.5:
            continue

        if diff_hours > 24.5:
            break

        instant = (
            item
            .get("data", {})
            .get("instant", {})
            .get("details", {})
        )

        next_hour = (
            item
            .get("data", {})
            .get("next_1_hours", {})
        )

        next_hour_details = (
            next_hour.get("details", {})
        )

        summary = (
            next_hour.get("summary", {})
        )

        temperature = safe_float(
            instant.get("air_temperature")
        )

        humidity = safe_float(
            instant.get("relative_humidity")
        )

        sea_pressure = safe_float(
            instant.get("air_pressure_at_sea_level")
        )

        wind = safe_float(
            instant.get("wind_speed")
        )

        wind_direction = safe_float(
            instant.get("wind_from_direction")
        )

        precipitation = safe_float(
            next_hour_details.get(
                "precipitation_amount"
            )
        )

        rain_probability = safe_float(
            next_hour_details.get(
                "probability_of_precipitation"
            )
        )

        symbol = summary.get(
            "symbol_code"
        )

        surface_pressure = calculate_surface_pressure(
            sea_pressure,
            temperature
        )

        items.append({
            "time": valid_time.strftime("%H:%M"),
            "datetime": valid_time.strftime(
                "%Y-%m-%d %H:%M"
            ),

            "temperature": temperature,
            "humidity": humidity,

            "sea_pressure": sea_pressure,
            "surface_pressure": surface_pressure,

            "wind": wind,
            "wind_direction": wind_direction,

            "precipitation": precipitation,
            "rain_probability": rain_probability,

            "symbol": symbol,
            "icon": weather_icon(symbol),
            "weather": weather_name(symbol),
        })

    # 同じ時刻を除去
    unique = {}

    for item in items:
        unique[item["datetime"]] = item

    return list(unique.values())[:25]


# ============================================================
# 風向
# ============================================================

def met_wind_direction(degree):
    if degree is None:
        return "—"

    directions = [
        "北",
        "北北東",
        "北東",
        "東北東",
        "東",
        "東南東",
        "南東",
        "南南東",
        "南",
        "南南西",
        "南西",
        "西南西",
        "西",
        "西北西",
        "北西",
        "北北西",
    ]

    index = int(
        (degree + 11.25) / 22.5
    ) % 16

    return directions[index]


# ============================================================
# 気圧の傾向
# ============================================================

def pressure_trend(forecasts):

    if len(forecasts) < 4:
        return {
            "icon": "—",
            "title": "気圧の傾向を判定できません",
            "text": ""
        }

    p1 = forecasts[0].get("sea_pressure")
    p2 = forecasts[min(3, len(forecasts) - 1)].get(
        "sea_pressure"
    )

    if p1 is None or p2 is None:
        return {
            "icon": "—",
            "title": "気圧の傾向を判定できません",
            "text": ""
        }

    diff = p2 - p1

    if diff <= -2.0:
        return {
            "icon": "↓",
            "title": "気圧は下降傾向",
            "text": "天候が崩れる方向への変化に注意。"
        }

    if diff >= 2.0:
        return {
            "icon": "↑",
            "title": "気圧は上昇傾向",
            "text": "天候が回復する方向への変化です。"
        }

    return {
        "icon": "→",
        "title": "気圧は比較的安定",
        "text": "大きな気圧変化は予想されていません。"
    }


# ============================================================
# 気象状況
# ============================================================

def build_weather_alerts(forecasts):

    alerts = []

    if not forecasts:
        return alerts

    next_6 = forecasts[:7]

    # 強い雨
    max_rain = max(
        [
            x["precipitation"]
            for x in next_6
            if x["precipitation"] is not None
        ],
        default=0
    )

    if max_rain >= 5:
        heavy = next(
            (
                x for x in next_6
                if x["precipitation"] is not None
                and x["precipitation"] >= 5
            ),
            None
        )

        if heavy:
            alerts.append({
                "icon": "🌧️",
                "title": "強い雨に注意",
                "text": (
                    f"{heavy['time']}頃に"
                    f"1時間で {heavy['precipitation']:.1f} mm"
                    f" 前後の降水が予想されています。"
                )
            })

    # 雷
    thunder = next(
        (
            x for x in next_6
            if x["symbol"]
            and "thunder" in x["symbol"].lower()
        ),
        None
    )

    if thunder:
        alerts.append({
            "icon": "⛈️",
            "title": "雷雨に注意",
            "text": f"{thunder['time']}頃に雷雨が予想されています。"
        })

    # 強風
    strong_wind = max(
        [
            x["wind"]
            for x in next_6
            if x["wind"] is not None
        ],
        default=0
    )

    if strong_wind >= 10:
        strong = next(
            (
                x for x in next_6
                if x["wind"] is not None
                and x["wind"] >= 10
            ),
            None
        )

        if strong:
            alerts.append({
                "icon": "🌬️",
                "title": "強風に注意",
                "text": (
                    f"{strong['time']}頃に"
                    f"風速 {strong['wind']:.1f} m/s"
                    f" 前後が予想されています。"
                )
            })

    if not alerts:
        alerts.append({
            "icon": "✓",
            "title": "大きな荒天の兆候はありません",
            "text": "今後数時間の予報では大きな荒天は予想されていません。"
        })

    return alerts


# ============================================================
# 現在観測の天気判定
# ============================================================

def current_weather_status(amedas):

    if not amedas or not amedas.get("ok"):
        return {
            "icon": "—",
            "title": "現在の観測を取得できません",
            "text": ""
        }

    rain = amedas.get("rain10")
    visibility = amedas.get("visibility")

    # 霧
    if visibility is not None and visibility <= 1000:
        return {
            "icon": "🌫️",
            "title": "霧・視程低下",
            "text": f"現在の視程は約{visibility:.0f}mです。"
        }

    # 雨
    if rain is not None and rain >= 0.5:
        return {
            "icon": "🌧️",
            "title": "雨を観測",
            "text": f"直近10分の降水量は {rain:.1f} mm です。"
        }

    if rain is not None and rain > 0:
        return {
            "icon": "🌦️",
            "title": "降水を観測",
            "text": f"直近10分の降水量は {rain:.1f} mm です。"
        }

    return {
        "icon": "✓",
        "title": "現在、降水は観測されていません",
        "text": "周辺AMeDASでは直近10分の降水はありません。"
    }


# ============================================================
# HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>奈良本 天気・気圧</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background:
        radial-gradient(
            circle at top right,
            #34282d 0%,
            #1a1819 45%,
            #111112 100%
        );
    color: #eee7e8;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

.wrapper {
    max-width: 1450px;
    margin: auto;
    padding: 28px;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 20px;
    margin-bottom: 25px;
}

.location {
    font-size: 18px;
    letter-spacing: 0.08em;
}

.location strong {
    font-size: 27px;
    color: #f0c1cd;
}

.updated {
    color: #a89fa2;
    font-size: 13px;
}

.panel {
    background: rgba(30, 27, 29, 0.92);
    border: 1px solid #3a3437;
    border-radius: 16px;
    padding: 22px;
    margin-bottom: 20px;
    box-shadow: 0 12px 35px rgba(0,0,0,.18);
}

.panel-title {
    color: #d8a9b6;
    font-size: 14px;
    letter-spacing: .08em;
    margin-bottom: 17px;
}

.current-grid {
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));
    gap: 14px;
}

.metric {
    border-top: 1px solid #40383b;
    padding-top: 14px;
}

.metric-label {
    color: #9f9699;
    font-size: 12px;
    margin-bottom: 7px;
}

.metric-value {
    font-size: 26px;
    font-family: Georgia, serif;
}

.metric-unit {
    font-size: 13px;
    color: #aaa2a5;
}

.observation-note {
    margin-top: 18px;
    color: #9f9699;
    font-size: 12px;
    line-height: 1.7;
}

.pressure-main {
    display: flex;
    gap: 45px;
    align-items: end;
    flex-wrap: wrap;
}

.pressure-number {
    font-family: Georgia, serif;
    font-size: 42px;
}

.pressure-label {
    color: #aaa2a5;
    font-size: 12px;
}

.trend {
    margin-top: 17px;
    padding-top: 17px;
    border-top: 1px solid #40383b;
}

.trend-title {
    font-size: 17px;
    color: #f0c1cd;
}

.trend-text {
    color: #aaa2a5;
    font-size: 13px;
    margin-top: 5px;
}

.alerts {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px;
}

.alert {
    border-left: 3px solid #c993a3;
    background: #252123;
    padding: 15px 17px;
    border-radius: 10px;
}

.alert-title {
    font-size: 15px;
    color: #f0c1cd;
}

.alert-text {
    margin-top: 7px;
    color: #b5adaf;
    font-size: 13px;
    line-height: 1.6;
}

.forecast-wrap {
    overflow-x: auto;
    padding-bottom: 5px;
}

.forecast {
    display: flex;
    gap: 10px;
    min-width: max-content;
}

.forecast-card {
    width: 145px;
    min-height: 205px;
    background: #242022;
    border: 1px solid #393337;
    border-radius: 12px;
    padding: 14px;
}

.forecast-time {
    color: #b8aeb1;
    font-size: 13px;
}

.forecast-temp {
    font-family: Georgia, serif;
    font-size: 28px;
    margin: 8px 0;
}

.weather {
    font-size: 13px;
    line-height: 1.5;
    min-height: 40px;
}

.rain {
    margin-top: 10px;
    font-size: 12px;
    color: #b9aeb1;
}

.wind {
    margin-top: 9px;
    font-size: 12px;
    color: #c6bdc0;
}

.chart-box {
    height: 330px;
}

.small-error {
    color: #c99ca9;
    font-size: 13px;
    line-height: 1.7;
}

.footer {
    color: #777073;
    text-align: center;
    font-size: 11px;
    margin: 30px 0 10px;
}

@media (max-width: 800px) {

    .wrapper {
        padding: 16px;
    }

    .header {
        align-items: start;
        flex-direction: column;
    }

    .current-grid {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

    .pressure-number {
        font-size: 34px;
    }

    .chart-box {
        height: 260px;
    }
}

</style>
</head>

<body>

<div class="wrapper">

    <div class="header">

        <div class="location">
            <strong>奈良本</strong>
            ｜標高 約500m
        </div>

        <div class="updated">
            {{ now }}
        </div>

    </div>


    <!-- 現在のAMeDAS -->

    <div class="panel">

        <div class="panel-title">
            現在の周辺観測
        </div>

        {% if amedas.ok %}

        <div style="margin-bottom:18px;color:#aaa2a5;font-size:12px;">
            {{ amedas.station_name }}
            ｜観測時刻 {{ amedas.observed_at }}
            {% if amedas.station_distance %}
            ｜自宅から約{{ "%.1f"|format(amedas.station_distance) }}km
            {% endif %}
        </div>

        <div class="current-grid">

            <div class="metric">
                <div class="metric-label">気温</div>
                <div class="metric-value">
                    {% if amedas.temperature is not none %}
                        {{ "%.1f"|format(amedas.temperature) }}
                        <span class="metric-unit">℃</span>
                    {% else %}
                        —
                    {% endif %}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">湿度</div>
                <div class="metric-value">
                    {% if amedas.humidity is not none %}
                        {{ "%.0f"|format(amedas.humidity) }}
                        <span class="metric-unit">%</span>
                    {% else %}
                        —
                    {% endif %}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">降水量（10分）</div>
                <div class="metric-value">
                    {% if amedas.rain10 is not none %}
                        {{ "%.1f"|format(amedas.rain10) }}
                        <span class="metric-unit">mm</span>
                    {% else %}
                        —
                    {% endif %}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">風</div>
                <div class="metric-value">
                    {% if amedas.wind is not none %}
                        {{ "%.1f"|format(amedas.wind) }}
                        <span class="metric-unit">m/s</span>
                    {% else %}
                        —
                    {% endif %}
                </div>

                {% if amedas.wind_direction is not none %}
                <div class="metric-label">
                    {{ jma_wind_direction(amedas.wind_direction) }}
                </div>
                {% endif %}
            </div>

        </div>

        <div class="observation-note">
            ※現在値は気象庁AMeDASによる周辺観測です。<br>
            ※自宅周辺と観測地点では、特に風・雨・霧などに差が出る場合があります。
        </div>

        {% else %}

        <div class="small-error">
            現在の観測データを取得できませんでした。<br>
            AMeDASの最新データが一時的に取得できない可能性があります。
        </div>

        {% endif %}

    </div>


    <!-- 自宅地点の気圧 -->

    <div class="panel">

        <div class="panel-title">
            自宅地点の気圧
        </div>

        <div class="pressure-main">

            <div>
                <div class="pressure-number">
                    {% if current_pressure %}
                        {{ "%.1f"|format(current_pressure) }}
                    {% else %}
                        —
                    {% endif %}
                    <span class="metric-unit">hPa</span>
                </div>

                <div class="pressure-label">
                    標高約500mの自宅地点
                </div>
            </div>

            <div>
                <div class="pressure-number" style="font-size:30px;">
                    {% if current_sea_pressure %}
                        {{ "%.1f"|format(current_sea_pressure) }}
                    {% else %}
                        —
                    {% endif %}
                    <span class="metric-unit">hPa</span>
                </div>

                <div class="pressure-label">
                    海面更正気圧
                </div>
            </div>

        </div>

        <div class="trend">

            <div class="trend-title">
                {{ trend.icon }}
                {{ trend.title }}
            </div>

            <div class="trend-text">
                {{ trend.text }}
            </div>

        </div>

    </div>


    <!-- 現在の気象状況 -->

    <div class="panel">

        <div class="panel-title">
            現在の気象状況
        </div>

        {% if current_status %}

        <div class="alerts">

            <div class="alert">

                <div class="alert-title">
                    {{ current_status.icon }}
                    {{ current_status.title }}
                </div>

                <div class="alert-text">
                    {{ current_status.text }}
                </div>

            </div>

            {% for alert in alerts %}

            <div class="alert">

                <div class="alert-title">
                    {{ alert.icon }}
                    {{ alert.title }}
                </div>

                <div class="alert-text">
                    {{ alert.text }}
                </div>

            </div>

            {% endfor %}

        </div>

        {% endif %}

    </div>


    <!-- 24時間予報 -->

    <div class="panel">

        <div class="panel-title">
            これから24時間
        </div>

        <div style="color:#aaa2a5;font-size:12px;margin-bottom:15px;">
            奈良本・標高約500m地点の予報
        </div>

        <div class="forecast-wrap">

            <div class="forecast">

                {% for item in forecasts %}

                <div class="forecast-card">

                    <div class="forecast-time">
                        {{ item.time }}
                    </div>

                    <div class="forecast-temp">
                        {% if item.temperature is not none %}
                            {{ "%.1f"|format(item.temperature) }}°
                        {% else %}
                            —
                        {% endif %}
                    </div>

                    <div class="weather">
                        {{ item.icon }}
                        {{ item.weather }}
                    </div>

                    <div class="rain">
                        ☔
                        {% if item.rain_probability is not none %}
                            {{ "%.0f"|format(item.rain_probability) }}%
                        {% else %}
                            —
                        {% endif %}

                        ｜
                        {% if item.precipitation is not none %}
                            {{ "%.1f"|format(item.precipitation) }} mm
                        {% else %}
                            — mm
                        {% endif %}
                    </div>

                    <div class="wind">

                        {% if item.wind_direction is not none %}
                            {{ met_wind_direction(item.wind_direction) }}
                        {% endif %}

                        {% if item.wind is not none %}
                            {{ "%.1f"|format(item.wind) }}m/s
                        {% else %}
                            —
                        {% endif %}

                    </div>

                </div>

                {% endfor %}

            </div>

        </div>

    </div>


    <!-- 気温グラフ -->

    <div class="panel">

        <div class="panel-title">
            24時間の気温
        </div>

        <div class="chart-box">
            <canvas id="temperatureChart"></canvas>
        </div>

    </div>


    <!-- 気圧グラフ -->

    <div class="panel">

        <div class="panel-title">
            24時間の気圧
        </div>

        <div class="chart-box">
            <canvas id="pressureChart"></canvas>
        </div>

    </div>


    <div class="footer">
        奈良本｜標高 約500m ｜ 24時間予報：MET Norway
    </div>

</div>


<script>

const labels = {{ chart_labels | safe }};
const temperatures = {{ chart_temperatures | safe }};
const pressures = {{ chart_pressures | safe }};


new Chart(
    document.getElementById("temperatureChart"),
    {
        type: "line",

        data: {
            labels: labels,

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
                    labels: {
                        color: "#bdb4b7"
                    }
                }
            },

            scales: {
                x: {
                    ticks: {
                        color: "#8f888b"
                    },
                    grid: {
                        color: "#302b2d"
                    }
                },

                y: {
                    ticks: {
                        color: "#8f888b"
                    },
                    grid: {
                        color: "#302b2d"
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
            labels: labels,

            datasets: [{
                label: "自宅地点の推定気圧 hPa",
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
                    labels: {
                        color: "#bdb4b7"
                    }
                }
            },

            scales: {
                x: {
                    ticks: {
                        color: "#8f888b"
                    },
                    grid: {
                        color: "#302b2d"
                    }
                },

                y: {
                    ticks: {
                        color: "#8f888b"
                    },
                    grid: {
                        color: "#302b2d"
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
# Flask
# ============================================================

@app.route("/")
def index():

    now = datetime.now(JST).strftime(
        "%Y/%m/%d %H:%M"
    )

    # 現在のAMeDAS
    amedas = get_current_amedas()

    # MET予報
    met_data = get_met_forecast()

    forecasts = build_forecast_items(
        met_data
    )

    # 現在の自宅気圧
    current_pressure = None
    current_sea_pressure = None

    if forecasts:
        current_pressure = forecasts[0].get(
            "surface_pressure"
        )

        current_sea_pressure = forecasts[0].get(
            "sea_pressure"
        )

    # 気圧傾向
    trend = pressure_trend(
        forecasts
    )

    # 気象状況
    alerts = build_weather_alerts(
        forecasts
    )

    # 現在の観測状況
    current_status = current_weather_status(
        amedas
    )

    # グラフ
    chart_labels = [
        x["time"]
        for x in forecasts
    ]

    chart_temperatures = [
        x["temperature"]
        for x in forecasts
    ]

    chart_pressures = [
        x["surface_pressure"]
        for x in forecasts
    ]

    return render_template_string(
        HTML,

        now=now,

        amedas=amedas,

        current_pressure=current_pressure,
        current_sea_pressure=current_sea_pressure,

        trend=trend,

        current_status=current_status,
        alerts=alerts,

        forecasts=forecasts,

        chart_labels=chart_labels,
        chart_temperatures=chart_temperatures,
        chart_pressures=chart_pressures,

        jma_wind_direction=jma_wind_direction,
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )