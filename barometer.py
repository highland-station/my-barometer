from flask import Flask, render_template_string
import requests
import math
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# =========================================================
# 自宅
# =========================================================

HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

JST = timezone(timedelta(hours=9))

# =========================================================
# API
# =========================================================

JMA_LATEST_URL = (
    "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
)

JMA_STATION_URL = (
    "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
)

MET_URL = (
    "https://api.met.no/weatherapi/locationforecast/2.0/complete"
)

# ★ここは自分のメールアドレスに変更
MET_HEADERS = {
    "User-Agent": "NarabotoWeather/1.0 your-email@example.com"
}

# =========================================================
# 共通関数
# =========================================================

def to_float(value):
    if value is None:
        return None

    if isinstance(value, list):
        if len(value) == 0:
            return None
        value = value[0]

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def amedas_value(obs, key):
    """
    AMeDASの値は基本的に
    [値, 品質情報, ...]
    の形なので、値だけ取り出す。
    """

    if not isinstance(obs, dict):
        return None

    return to_float(obs.get(key))


# =========================================================
# AMeDAS 座標
# =========================================================

def coord_to_decimal(value):
    """
    JMA AMeDASのlat/lonは
    [度, 分]
    の形式なので10進数に変換。
    """

    if isinstance(value, list) and len(value) >= 2:
        degree = to_float(value[0])
        minute = to_float(value[1])

        if degree is None or minute is None:
            return None

        return degree + minute / 60.0

    return to_float(value)


# =========================================================
# 最寄りAMeDAS
# =========================================================

def find_nearest_station(stations):

    nearest = None
    best_distance = float("inf")

    cos_lat = math.cos(
        math.radians(HOME_LAT)
    )

    for station_id, station in stations.items():

        lat = coord_to_decimal(
            station.get("lat")
        )

        lon = coord_to_decimal(
            station.get("lon")
        )

        if lat is None or lon is None:
            continue

        dlat = lat - HOME_LAT
        dlon = (
            lon - HOME_LON
        ) * cos_lat

        distance2 = (
            dlat * dlat +
            dlon * dlon
        )

        if distance2 < best_distance:

            best_distance = distance2

            nearest = {
                "id": str(station_id),
                "name": (
                    station.get("kjName")
                    or station.get("kjName2")
                    or "AMeDAS"
                ),
                "lat": lat,
                "lon": lon,
                "distance_km": math.sqrt(
                    distance2
                ) * 111.0,
                "altitude": station.get("alt")
            }

    return nearest


# =========================================================
# AMeDAS 現在観測
# =========================================================

def get_amedas():

    try:

        # -------------------------------------------------
        # 最新時刻
        # -------------------------------------------------

        r = requests.get(
            JMA_LATEST_URL,
            timeout=20
        )

        r.raise_for_status()

        latest_text = r.text.strip()

        if not latest_text:
            raise Exception(
                "latest_time.txt が空です"
            )

        # ISO形式
        try:
            dt = datetime.fromisoformat(
                latest_text.replace(
                    "Z",
                    "+00:00"
                )
            )

        except ValueError:

            dt = datetime.strptime(
                latest_text[:14],
                "%Y%m%d%H%M%S"
            ).replace(
                tzinfo=JST
            )

        dt = dt.astimezone(JST)

        timestamp = dt.strftime(
            "%Y%m%d%H%M%S"
        )

        # -------------------------------------------------
        # 観測所一覧
        # -------------------------------------------------

        r = requests.get(
            JMA_STATION_URL,
            timeout=20
        )

        r.raise_for_status()

        stations = r.json()

        station = find_nearest_station(
            stations
        )

        if station is None:
            raise Exception(
                "最寄りAMeDASが見つかりません"
            )

        station_id = station["id"]

        # -------------------------------------------------
        # 最新観測データ
        # -------------------------------------------------

        map_url = (
            "https://www.jma.go.jp/"
            "bosai/amedas/data/map/"
            f"{timestamp}.json"
        )

        r = requests.get(
            map_url,
            timeout=20
        )

        r.raise_for_status()

        data = r.json()

        # IDを文字列として取得
        obs = data.get(
            station_id
        )

        if obs is None:

            # 念のため数値キーも試す
            try:
                obs = data.get(
                    int(station_id)
                )
            except Exception:
                obs = None

        if obs is None:
            raise Exception(
                f"観測データなし station={station_id}"
            )

        # -------------------------------------------------
        # 観測値
        # -------------------------------------------------

        temperature = amedas_value(
            obs,
            "temp"
        )

        humidity = amedas_value(
            obs,
            "humidity"
        )

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

        wind_direction = amedas_value(
            obs,
            "windDirection"
        )

        pressure = amedas_value(
            obs,
            "pressure"
        )

        normal_pressure = amedas_value(
            obs,
            "normalPressure"
        )

        visibility = amedas_value(
            obs,
            "visibility"
        )

        return {
            "ok": True,

            "station_id": station_id,
            "station_name": station["name"],

            "distance_km":
                station["distance_km"],

            "observed_at":
                dt.strftime(
                    "%Y/%m/%d %H:%M"
                ),

            "temperature":
                temperature,

            "humidity":
                humidity,

            "rain10":
                rain10,

            "rain1h":
                rain1h,

            "wind":
                wind,

            "wind_direction":
                wind_direction,

            "pressure":
                pressure,

            "normal_pressure":
                normal_pressure,

            "visibility":
                visibility,
        }

    except Exception as e:

        print(
            "AMeDAS ERROR:",
            repr(e)
        )

        return {
            "ok": False,
            "error": str(e)
        }


# =========================================================
# JMA 風向
# =========================================================

JMA_WIND_DIRECTIONS = [
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

        i = int(round(value))

        if 0 <= i < len(
            JMA_WIND_DIRECTIONS
        ):
            return JMA_WIND_DIRECTIONS[i]

    except Exception:
        pass

    return "—"


# =========================================================
# MET Norway
# =========================================================

def get_met_forecast():

    try:

        # 4桁程度にしてAPIキャッシュ効率も確保
        lat = round(
            HOME_LAT,
            4
        )

        lon = round(
            HOME_LON,
            4
        )

        params = {
            "lat": lat,
            "lon": lon,
            "altitude": HOME_ALTITUDE
        }

        r = requests.get(
            MET_URL,
            params=params,
            headers=MET_HEADERS,
            timeout=30
        )

        print(
            "MET STATUS:",
            r.status_code
        )

        print(
            "MET URL:",
            r.url
        )

        if r.status_code != 200:

            print(
                "MET RESPONSE:",
                r.text[:1000]
            )

        r.raise_for_status()

        return r.json()

    except Exception as e:

        print(
            "MET ERROR:",
            repr(e)
        )

        return None


# =========================================================
# 気圧計算
# =========================================================

def surface_pressure(
    sea_level_pressure,
    temperature
):

    if (
        sea_level_pressure is None
        or temperature is None
    ):
        return None

    return (
        sea_level_pressure
        * math.exp(
            -9.80665
            * HOME_ALTITUDE
            /
            (
                287.05
                *
                (
                    temperature
                    + 273.15
                )
            )
        )
    )


# =========================================================
# MET 天気
# =========================================================

def weather_icon(symbol):

    if not symbol:
        return "☁️"

    s = symbol.lower()

    if "thunder" in s:
        return "⛈️"

    if "heavyrain" in s:
        return "🌧️"

    if "rain" in s:
        return "🌦️"

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

    return "☁️"


def weather_name(symbol):

    if not symbol:
        return "曇り"

    s = symbol.lower()

    if "thunder" in s:
        return "雷雨"

    if "heavyrain" in s:
        return "強い雨"

    if "rain" in s:
        return "雨"

    if "sleet" in s:
        return "みぞれ"

    if "snow" in s:
        return "雪"

    if "fog" in s:
        return "霧"

    if "clearsky" in s:
        return "晴れ"

    if "fair" in s:
        return "晴れ"

    if "partlycloudy" in s:
        return "晴れ時々曇り"

    if "cloudy" in s:
        return "曇り"

    return "曇り"


# =========================================================
# MET 予報を24時間作成
# =========================================================

def build_forecasts(data):

    if not data:
        return []

    timeseries = (
        data
        .get("properties", {})
        .get("timeseries", [])
    )

    if not timeseries:
        return []

    now = datetime.now(
        timezone.utc
    )

    result = []

    for item in timeseries:

        try:

            valid = datetime.fromisoformat(
                item["time"].replace(
                    "Z",
                    "+00:00"
                )
            )

        except Exception:
            continue

        # 現在から24時間
        hours = (
            valid - now
        ).total_seconds() / 3600

        if hours < -0.5:
            continue

        if hours > 24.5:
            break

        data_block = item.get(
            "data",
            {}
        )

        instant = (
            data_block
            .get("instant", {})
            .get("details", {})
        )

        # -------------------------------------------------
        # 期間データ
        # -------------------------------------------------

        period = data_block.get(
            "next_1_hours"
        )

        if period is None:
            period = data_block.get(
                "next_6_hours"
            )

        if period is None:
            period = data_block.get(
                "next_12_hours"
            )

        period_details = (
            period.get("details", {})
            if period
            else {}
        )

        summary = (
            period.get("summary", {})
            if period
            else {}
        )

        # -------------------------------------------------
        # instant
        # -------------------------------------------------

        temperature = to_float(
            instant.get(
                "air_temperature"
            )
        )

        sea_pressure = to_float(
            instant.get(
                "air_pressure_at_sea_level"
            )
        )

        humidity = to_float(
            instant.get(
                "relative_humidity"
            )
        )

        wind = to_float(
            instant.get(
                "wind_speed"
            )
        )

        wind_direction = to_float(
            instant.get(
                "wind_from_direction"
            )
        )

        gust = to_float(
            instant.get(
                "wind_speed_of_gust"
            )
        )

        # -------------------------------------------------
        # period
        # -------------------------------------------------

        precipitation = to_float(
            period_details.get(
                "precipitation_amount"
            )
        )

        rain_probability = to_float(
            period_details.get(
                "probability_of_precipitation"
            )
        )

        thunder_probability = to_float(
            period_details.get(
                "probability_of_thunder"
            )
        )

        symbol = summary.get(
            "symbol_code"
        )

        local = valid.astimezone(
            JST
        )

        result.append({

            "datetime":
                local.strftime(
                    "%Y-%m-%d %H:%M"
                ),

            "time":
                local.strftime(
                    "%H:%M"
                ),

            "temperature":
                temperature,

            "humidity":
                humidity,

            "sea_pressure":
                sea_pressure,

            "surface_pressure":
                surface_pressure(
                    sea_pressure,
                    temperature
                ),

            "wind":
                wind,

            "gust":
                gust,

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

            "icon":
                weather_icon(symbol),

            "weather":
                weather_name(symbol),
        })

    # 時刻重複を除去
    unique = {}

    for item in result:
        unique[
            item["datetime"]
        ] = item

    return list(
        unique.values()
    )[:25]


# =========================================================
# MET 風向
# =========================================================

MET_DIRECTIONS = [
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


def met_wind_direction(
    degree
):

    if degree is None:
        return "—"

    index = int(
        (
            degree + 11.25
        ) / 22.5
    ) % 16

    return MET_DIRECTIONS[index]


# =========================================================
# 気圧傾向
# =========================================================

def pressure_trend(
    forecasts
):

    if len(forecasts) < 4:

        return {
            "icon": "—",
            "title":
                "気圧の傾向を判定できません",
            "text": ""
        }

    p1 = forecasts[0].get(
        "sea_pressure"
    )

    p2 = forecasts[3].get(
        "sea_pressure"
    )

    if p1 is None or p2 is None:

        return {
            "icon": "—",
            "title":
                "気圧の傾向を判定できません",
            "text": ""
        }

    diff = p2 - p1

    if diff <= -2:

        return {
            "icon": "↓",
            "title":
                "気圧は下降傾向",
            "text":
                "天候が崩れる方向への変化に注意。"
        }

    if diff >= 2:

        return {
            "icon": "↑",
            "title":
                "気圧は上昇傾向",
            "text":
                "天候が回復する方向への変化です。"
        }

    return {
        "icon": "→",
        "title":
            "気圧は比較的安定",
        "text":
            "大きな気圧変化は予想されていません。"
    }


# =========================================================
# 気象状況
# =========================================================

def build_alerts(
    forecasts
):

    if not forecasts:
        return []

    next_hours = forecasts[:7]

    alerts = []

    # 強い雨
    heavy = None

    for x in next_hours:

        rain = x.get(
            "precipitation"
        )

        if rain is not None and rain >= 5:

            heavy = x
            break

    if heavy:

        alerts.append({
            "icon": "🌧️",
            "title":
                "強い雨に注意",
            "text":
                f"{heavy['time']}頃に"
                f" {heavy['precipitation']:.1f} mm"
                "前後の降水が予想されています。"
        })

    # 雷
    thunder = None

    for x in next_hours:

        symbol = x.get(
            "symbol"
        )

        probability = x.get(
            "thunder_probability"
        )

        if (
            symbol
            and "thunder"
            in symbol.lower()
        ):
            thunder = x
            break

        if (
            probability is not None
            and probability >= 30
        ):
            thunder = x
            break

    if thunder:

        alerts.append({
            "icon": "⛈️",
            "title":
                "雷雨に注意",
            "text":
                f"{thunder['time']}頃に"
                "雷雨の可能性があります。"
        })

    # 強風
    strong = None

    for x in next_hours:

        wind = x.get(
            "wind"
        )

        if (
            wind is not None
            and wind >= 10
        ):
            strong = x
            break

    if strong:

        alerts.append({
            "icon": "🌬️",
            "title":
                "強風に注意",
            "text":
                f"{strong['time']}頃に"
                f"風速 {strong['wind']:.1f} m/s"
                "前後が予想されています。"
        })

    if not alerts:

        alerts.append({
            "icon": "✓",
            "title":
                "大きな荒天の兆候はありません",
            "text":
                "今後数時間の予報では大きな荒天は予想されていません。"
        })

    return alerts


# =========================================================
# 現在の観測状況
# =========================================================

def current_status(
    amedas
):

    if not amedas.get(
        "ok"
    ):

        return {
            "icon": "—",
            "title":
                "現在の観測を取得できません",
            "text":
                "気象庁AMeDASのデータを取得できませんでした。"
        }

    rain = amedas.get(
        "rain10"
    )

    visibility = amedas.get(
        "visibility"
    )

    # 霧
    if (
        visibility is not None
        and visibility <= 1000
    ):

        return {
            "icon": "🌫️",
            "title":
                "霧・視程低下",
            "text":
                f"観測視程 約{visibility:.0f}m"
        }

    # 雨
    if (
        rain is not None
        and rain >= 0.5
    ):

        return {
            "icon": "🌧️",
            "title":
                "雨を観測",
            "text":
                f"直近10分 {rain:.1f} mm"
        }

    if (
        rain is not None
        and rain > 0
    ):

        return {
            "icon": "🌦️",
            "title":
                "降水を観測",
            "text":
                f"直近10分 {rain:.1f} mm"
        }

    return {
        "icon": "✓",
        "title":
            "現在、降水は観測されていません",
        "text":
            "周辺AMeDASでは直近10分の降水はありません。"
    }


# =========================================================
# HTML
# =========================================================

HTML = r"""
<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>奈良本 天気・気圧</title>

<script
src="https://cdn.jsdelivr.net/npm/chart.js">
</script>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    color: #eee7e8;

    background:
        radial-gradient(
            circle at top right,
            #35282d,
            #1a1819 48%,
            #111112
        );

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

    justify-content:
        space-between;

    align-items: end;

    margin-bottom: 24px;
}

.location {

    font-size: 18px;

    letter-spacing:
        .08em;
}

.location strong {

    color: #f0c1cd;

    font-size: 27px;
}

.updated {

    color: #9e9699;

    font-size: 13px;
}

.panel {

    background:
        rgba(30,27,29,.94);

    border:
        1px solid #3b3437;

    border-radius: 16px;

    padding: 22px;

    margin-bottom: 20px;
}

.panel-title {

    color: #d8a9b6;

    font-size: 14px;

    letter-spacing:
        .08em;

    margin-bottom: 16px;
}

.observation-name {

    color: #aaa1a4;

    font-size: 12px;

    margin-bottom: 18px;
}

.grid {

    display: grid;

    grid-template-columns:
        repeat(4,1fr);

    gap: 14px;
}

.metric {

    border-top:
        1px solid #40383b;

    padding-top: 13px;
}

.metric-label {

    color: #9e9699;

    font-size: 12px;

    margin-bottom: 7px;
}

.metric-value {

    font-family: Georgia,serif;

    font-size: 26px;
}

.unit {

    color: #aaa1a4;

    font-family:
        sans-serif;

    font-size: 12px;
}

.note {

    color: #90898b;

    font-size: 11px;

    line-height: 1.7;

    margin-top: 18px;
}

.pressure {

    display: flex;

    gap: 45px;

    flex-wrap: wrap;
}

.pressure-value {

    font-family: Georgia,serif;

    font-size: 40px;
}

.pressure-label {

    color: #999194;

    font-size: 11px;

    margin-top: 4px;
}

.trend {

    border-top:
        1px solid #40383b;

    margin-top: 18px;

    padding-top: 15px;
}

.trend-title {

    color: #f0c1cd;

    font-size: 16px;
}

.trend-text {

    color: #a9a1a4;

    font-size: 12px;

    margin-top: 5px;
}

.alerts {

    display: grid;

    grid-template-columns:
        repeat(auto-fit,minmax(260px,1fr));

    gap: 12px;
}

.alert {

    background: #252123;

    border-left:
        3px solid #c993a3;

    border-radius: 9px;

    padding: 15px;
}

.alert-title {

    color: #f0c1cd;

    font-size: 14px;
}

.alert-text {

    color: #aaa2a5;

    font-size: 12px;

    line-height: 1.6;

    margin-top: 6px;
}

.forecast-scroll {

    overflow-x: auto;

    padding-bottom: 8px;
}

.forecast {

    display: flex;

    gap: 10px;

    width: max-content;
}

.card {

    width: 145px;

    min-height: 205px;

    background: #242022;

    border:
        1px solid #393337;

    border-radius: 12px;

    padding: 14px;
}

.time {

    color: #aaa1a4;

    font-size: 12px;
}

.temp {

    font-family: Georgia,serif;

    font-size: 28px;

    margin: 8px 0;
}

.weather {

    font-size: 13px;

    min-height: 40px;

    line-height: 1.5;
}

.rain {

    color: #b7afb1;

    font-size: 11px;

    margin-top: 10px;
}

.wind {

    color: #c0b8ba;

    font-size: 11px;

    margin-top: 8px;
}

.chart {

    height: 320px;
}

.error {

    color: #d39eac;

    font-size: 13px;

    line-height: 1.7;
}

.footer {

    color: #716a6d;

    text-align: center;

    font-size: 10px;

    margin: 30px 0 10px;
}

@media(max-width:800px) {

    .wrapper {
        padding: 16px;
    }

    .header {
        align-items: flex-start;
        flex-direction: column;
    }

    .grid {
        grid-template-columns:
            repeat(2,1fr);
    }

    .chart {
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


<!-- =====================================================
     現在観測
===================================================== -->

<div class="panel">

<div class="panel-title">
現在の周辺観測
</div>

{% if amedas.ok %}

<div class="observation-name">

{{ amedas.station_name }}

｜
観測時刻 {{ amedas.observed_at }}

｜
自宅から約{{ "%.1f"|format(amedas.distance_km) }}km

</div>

<div class="grid">

<div class="metric">

<div class="metric-label">
気温
</div>

<div class="metric-value">

{% if amedas.temperature is not none %}
{{ "%.1f"|format(amedas.temperature) }}
<span class="unit">℃</span>
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
{{ "%.0f"|format(amedas.humidity) }}
<span class="unit">%</span>
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
{{ "%.1f"|format(amedas.rain10) }}
<span class="unit">mm</span>
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

{{ "%.1f"|format(amedas.wind) }}

<span class="unit">m/s</span>

{% else %}

—

{% endif %}

</div>

<div class="metric-label">

{{ jma_wind_direction(amedas.wind_direction) }}

</div>

</div>

</div>

<div class="note">

※現在値は気象庁AMeDASによる周辺観測です。<br>

※自宅周辺と観測地点では、
特に風・雨・霧などに差が出る場合があります。

</div>

{% else %}

<div class="error">

現在の観測データを取得できませんでした。<br>

AMeDAS:
{{ amedas.error }}

</div>

{% endif %}

</div>


<!-- =====================================================
     自宅気圧
===================================================== -->

<div class="panel">

<div class="panel-title">
自宅地点の気圧
</div>

<div class="pressure">

<div>

<div class="pressure-value">

{% if current_pressure is not none %}

{{ "%.1f"|format(current_pressure) }}

<span class="unit">hPa</span>

{% else %}

— <span class="unit">hPa</span>

{% endif %}

</div>

<div class="pressure-label">
標高約500mの自宅地点
</div>

</div>


<div>

<div class="pressure-value"
style="font-size:30px;">

{% if current_sea_pressure is not none %}

{{ "%.1f"|format(current_sea_pressure) }}

<span class="unit">hPa</span>

{% else %}

— <span class="unit">hPa</span>

{% endif %}

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


<!-- =====================================================
     現在の気象状況
===================================================== -->

<div class="panel">

<div class="panel-title">
現在の気象状況
</div>

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

</div>


<!-- =====================================================
     24時間予報
===================================================== -->

<div class="panel">

<div class="panel-title">
これから24時間
</div>

<div style="
color:#aaa1a4;
font-size:12px;
margin-bottom:15px;
">

奈良本・標高約500m地点の予報

</div>


{% if forecasts %}

<div class="forecast-scroll">

<div class="forecast">

{% for item in forecasts %}

<div class="card">

<div class="time">
{{ item.time }}
</div>

<div class="temp">

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

{{ met_wind_direction(item.wind_direction) }}

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

{% else %}

<div class="error">

自宅地点の予報データを取得できませんでした。

</div>

{% endif %}

</div>


<!-- =====================================================
     気温
===================================================== -->

<div class="panel">

<div class="panel-title">
24時間の気温
</div>

<div class="chart">

<canvas id="temperatureChart"></canvas>

</div>

</div>


<!-- =====================================================
     気圧
===================================================== -->

<div class="panel">

<div class="panel-title">
24時間の気圧
</div>

<div class="chart">

<canvas id="pressureChart"></canvas>

</div>

</div>


<div class="footer">

奈良本｜標高 約500m
｜
24時間予報：MET Norway

</div>

</div>


<script>

const labels =
{{ chart_labels | safe }};

const temperatures =
{{ chart_temperatures | safe }};

const pressures =
{{ chart_pressures | safe }};


new Chart(

document.getElementById(
    "temperatureChart"
),

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

document.getElementById(
    "pressureChart"
),

{

type: "line",

data: {

labels: labels,

datasets: [{

label:
"自宅地点の推定気圧 hPa",

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


# =========================================================
# Flask
# =========================================================

@app.route("/")
def index():

    now = datetime.now(
        JST
    ).strftime(
        "%Y/%m/%d %H:%M"
    )

    # 現在の実測
    amedas = get_amedas()

    # 自宅予報
    met_data = get_met_forecast()

    forecasts = build_forecasts(
        met_data
    )

    # 現在の自宅地点気圧
    current_pressure = None
    current_sea_pressure = None

    if forecasts:

        current_pressure = forecasts[0].get(
            "surface_pressure"
        )

        current_sea_pressure = forecasts[0].get(
            "sea_pressure"
        )

    trend = pressure_trend(
        forecasts
    )

    alerts = build_alerts(
        forecasts
    )

    status = current_status(
        amedas
    )

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

        current_pressure=
            current_pressure,

        current_sea_pressure=
            current_sea_pressure,

        trend=trend,

        alerts=alerts,

        current_status=status,

        forecasts=forecasts,

        chart_labels=
            chart_labels,

        chart_temperatures=
            chart_temperatures,

        chart_pressures=
            chart_pressures,

        jma_wind_direction=
            jma_wind_direction,

        met_wind_direction=
            met_wind_direction,
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )