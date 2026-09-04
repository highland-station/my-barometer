import json
import math
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, render_template_string


app = Flask(__name__)


# =========================================================
# 基本設定
# =========================================================

HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

JST = timezone(timedelta(hours=9))

JMA_LATEST_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
JMA_STATION_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
JMA_MAP_URL = "https://www.jma.go.jp/bosai/amedas/data/map/{}.json"

MET_URL = (
    "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    f"?lat={HOME_LAT}&lon={HOME_LON}"
)

MET_CONTACT_EMAIL = os.environ.get(
    "MET_CONTACT_EMAIL",
    "contact@example.com"
)

HEADERS = {
    "User-Agent": f"NarimotoWeatherDashboard/1.0 {MET_CONTACT_EMAIL}"
}


# =========================================================
# 共通関数
# =========================================================

def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def jst_now():
    return datetime.now(JST)


def fetch_json(url, headers=None, timeout=15):
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print("JSON取得エラー:", url, e)
        return None


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dlon / 2) ** 2
    )

    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =========================================================
# JMA AMeDAS
# =========================================================

def get_amedas_stations():
    data = fetch_json(JMA_STATION_URL)

    if not data:
        return []

    stations = []

    for station_id, station in data.items():
        try:
            lat_data = station.get("lat")
            lon_data = station.get("lon")

            if not lat_data or not lon_data:
                continue

            lat = safe_float(lat_data[0])
            lon = safe_float(lon_data[0])

            if lat is None or lon is None:
                continue

            distance = haversine_km(
                HOME_LAT,
                HOME_LON,
                lat,
                lon
            )

            stations.append({
                "id": station_id,
                "name": station.get("kjName", station_id),
                "lat": lat,
                "lon": lon,
                "altitude": station.get("alt"),
                "distance": distance
            })

        except Exception:
            continue

    stations.sort(key=lambda x: x["distance"])

    return stations


def get_amedas_latest():
    latest = fetch_json(JMA_LATEST_URL)

    if not latest:
        return None

    try:
        text = latest if isinstance(latest, str) else str(latest)
        text = text.strip()

        dt = datetime.strptime(
            text,
            "%Y%m%d%H%M%S"
        )

        return dt.replace(tzinfo=JST)

    except Exception:
        return None


def get_amedas_map():
    latest = get_amedas_latest()

    if latest is None:
        latest = jst_now()

    timestamp = latest.strftime("%Y%m%d%H%M%S")

    return fetch_json(
        JMA_MAP_URL.format(timestamp)
    )


def find_nearest_rain_station():
    stations = get_amedas_stations()

    if not stations:
        return None

    amedas = get_amedas_map()

    if not amedas:
        return None

    for station in stations:
        sid = station["id"]

        if sid not in amedas:
            continue

        data = amedas[sid]

        rain = data.get("precipitation10m")

        rain = safe_float(rain)

        if rain is not None:
            station = station.copy()
            station["rain"] = rain
            return station

    return None


def get_nearest_observation():
    stations = get_amedas_stations()

    if not stations:
        return None

    amedas = get_amedas_map()

    if not amedas:
        return None

    for station in stations:
        sid = station["id"]

        if sid not in amedas:
            continue

        data = amedas[sid]

        temp = safe_float(data.get("temp"))
        humidity = safe_float(data.get("humidity"))
        wind = safe_float(data.get("wind"))
        wind_direction = data.get("windDirection")

        observation = station.copy()

        observation["temp"] = temp
        observation["humidity"] = humidity
        observation["wind"] = wind
        observation["wind_direction"] = wind_direction

        observation["rain_10m"] = safe_float(
            data.get("precipitation10m")
        )

        observation["visibility"] = safe_float(
            data.get("visibility")
        )

        return observation

    return None


# =========================================================
# 風向
# =========================================================

WIND_DIRECTIONS = {
    0: "静穏",
    1: "北北東",
    2: "北東",
    3: "東北東",
    4: "東",
    5: "東南東",
    6: "南東",
    7: "南南東",
    8: "南",
    9: "南南西",
    10: "南西",
    11: "西南西",
    12: "西",
    13: "西北西",
    14: "北西",
    15: "北北西",
    16: "北",
}


def wind_direction_text(value):
    try:
        value = int(value)
        return WIND_DIRECTIONS.get(value, "—")
    except Exception:
        return "—"


# =========================================================
# MET Norway
# =========================================================

def get_met_forecast():
    data = fetch_json(
        MET_URL,
        headers=HEADERS
    )

    if not data:
        return []

    try:
        timeseries = data["properties"]["timeseries"]
    except Exception:
        return []

    forecasts = []

    for item in timeseries:
        try:
            time_text = item.get("time")

            if not time_text:
                continue

            dt = datetime.fromisoformat(
                time_text.replace("Z", "+00:00")
            ).astimezone(JST)

            details = (
                item
                .get("data", {})
                .get("instant", {})
                .get("details", {})
            )

            next_1h = (
                item
                .get("data", {})
                .get("next_1_hours", {})
            )

            next_6h = (
                item
                .get("data", {})
                .get("next_6_hours", {})
            )

            symbol = (
                next_1h.get("summary", {}).get("symbol_code")
                or next_6h.get("summary", {}).get("symbol_code")
                or ""
            )

            temperature = safe_float(
                details.get("air_temperature")
            )

            wind_speed = safe_float(
                details.get("wind_speed")
            )

            humidity = safe_float(
                details.get("relative_humidity")
            )

            pressure_sea = safe_float(
                details.get("air_pressure_at_sea_level")
            )

            precipitation = safe_float(
                next_1h
                .get("details", {})
                .get("precipitation_amount")
            )

            if precipitation is None:
                precipitation = safe_float(
                    next_6h
                    .get("details", {})
                    .get("precipitation_amount")
                )

            if precipitation is None:
                precipitation = 0.0

            thunder = safe_float(
                next_1h
                .get("details", {})
                .get("probability_of_thunder")
            )

            if thunder is None:
                thunder = safe_float(
                    next_6h
                    .get("details", {})
                    .get("probability_of_thunder")
                )

            if thunder is None:
                thunder = 0.0

            # 海面気圧から標高500m地点の気圧を推定
            pressure_home = None

            if pressure_sea is not None:
                pressure_home = (
                    pressure_sea
                    * math.exp(
                        -HOME_ALTITUDE / 8434.5
                    )
                )

            forecasts.append({
                "datetime": dt,
                "temperature": temperature,
                "wind_speed": wind_speed,
                "humidity": humidity,
                "pressure_sea": pressure_sea,
                "pressure_home": pressure_home,
                "precipitation": precipitation,
                "thunder": thunder,
                "symbol": symbol,
            })

        except Exception as e:
            print("予報解析エラー:", e)
            continue

    return forecasts


# =========================================================
# 天気表示
# =========================================================

def symbol_to_japanese(symbol):
    symbol = (symbol or "").lower()

    if "heavyrain" in symbol:
        return "大雨"

    if "lightrain" in symbol:
        return "弱い雨"

    if "rain" in symbol:
        return "雨"

    if "sleet" in symbol:
        return "みぞれ"

    if "snow" in symbol:
        return "雪"

    if "fog" in symbol:
        return "霧"

    if "thunderstorm" in symbol:
        return "雷雨"

    if "fair" in symbol:
        return "晴れ"

    if "clearsky" in symbol:
        return "晴れ"

    if "partlycloudy" in symbol:
        return "晴れ時々くもり"

    if "cloudy" in symbol:
        return "くもり"

    return "—"


def weather_display(item):
    symbol = item.get("symbol", "")
    rain = item.get("precipitation") or 0
    thunder = item.get("thunder") or 0

    if "thunder" in symbol or thunder >= 30:
        return "雷雨"

    if rain >= 5:
        return "強い雨"

    if rain > 0:
        return "雨"

    return symbol_to_japanese(symbol)


# =========================================================
# 気圧変化
# =========================================================

def calculate_pressure_changes(forecasts):
    for i, item in enumerate(forecasts):

        current = item.get("pressure_home")

        change = None

        # 約3時間前との比較
        if i >= 3:
            old = forecasts[i - 3].get("pressure_home")

            if current is not None and old is not None:
                change = current - old

        item["pressure_change"] = change

        if change is None:
            item["pressure_level"] = "normal"

        elif change <= -3.0:
            item["pressure_level"] = "strong-fall"

        elif change <= -1.5:
            item["pressure_level"] = "fall"

        elif change >= 3.0:
            item["pressure_level"] = "strong-rise"

        elif change >= 1.5:
            item["pressure_level"] = "rise"

        else:
            item["pressure_level"] = "normal"


# =========================================================
# 健康・移動注意
# =========================================================

def health_attention_text(forecasts):

    strong = [
        x for x in forecasts
        if x.get("pressure_level") == "strong-fall"
    ]

    fall = [
        x for x in forecasts
        if x.get("pressure_level") == "fall"
    ]

    if strong:
        return "気圧が大きく低下する時間があります。"

    if fall:
        return "気圧が低下する時間があります。"

    return "大きな気圧低下は予想されていません。"


def travel_level(item):

    rain = item.get("precipitation") or 0
    thunder = item.get("thunder") or 0
    wind = item.get("wind_speed") or 0
    symbol = item.get("symbol", "").lower()

    if (
        rain >= 5
        or thunder >= 30
        or "thunder" in symbol
        or wind >= 10
    ):
        return "danger"

    if (
        rain >= 1
        or "fog" in symbol
        or wind >= 7
    ):
        return "attention"

    return "good"


def travel_reason(item):

    rain = item.get("precipitation") or 0
    thunder = item.get("thunder") or 0
    wind = item.get("wind_speed") or 0
    symbol = item.get("symbol", "").lower()

    reasons = []

    if rain >= 5:
        reasons.append("雨が強い")

    elif rain >= 1:
        reasons.append("降雨")

    if thunder >= 30 or "thunder" in symbol:
        reasons.append("雷の可能性")

    if wind >= 10:
        reasons.append("風が強い")

    elif wind >= 7:
        reasons.append("風に注意")

    if "fog" in symbol:
        reasons.append("霧")

    if not reasons:
        return "比較的移動しやすい時間"

    return "・".join(reasons)


def best_travel_window(forecasts):

    for item in forecasts:
        if item.get("travel_level") == "good":
            return item

    return None


# =========================================================
# 現在の天気
# =========================================================

def current_weather_status(observation):

    if not observation:
        return "観測データ取得中"

    rain = observation.get("rain_10m") or 0
    visibility = observation.get("visibility")

    if rain >= 5:
        return "強い雨"

    if rain > 0:
        return "雨"

    if visibility is not None and visibility < 1:
        return "視界不良"

    return "大きな降水なし"


# =========================================================
# HTML
# =========================================================

HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>奈良本 500m 天気</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #17151a;
    color: #eee;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

.container {
    width: min(1200px, 94%);
    margin: 0 auto;
    padding: 20px 0 40px;
}

header {
    margin-bottom: 20px;
}

h1 {
    margin: 0;
    font-size: 28px;
}

.subtitle {
    margin-top: 6px;
    color: #aaa;
}

section {
    background: #211e24;
    border: 1px solid #38333c;
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 18px;
}

.section-title {
    font-size: 20px;
    font-weight: bold;
    margin-bottom: 14px;
}

.cards {
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));
    gap: 12px;
}

.card {
    background: #2a262d;
    border-radius: 12px;
    padding: 15px;
}

.card-label {
    color: #aaa;
    font-size: 13px;
    margin-bottom: 7px;
}

.card-value {
    font-size: 25px;
    font-weight: bold;
}

.card-small {
    color: #aaa;
    margin-top: 5px;
    font-size: 12px;
}

.notice {
    border-radius: 12px;
    padding: 14px;
    background: #2a262d;
    margin-top: 10px;
}

.notice strong {
    display: block;
    margin-bottom: 5px;
}

.hourly {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    min-width: 850px;
}

th {
    background: #2b2730;
    color: #bbb;
    font-size: 13px;
    padding: 11px 8px;
    text-align: center;
    white-space: nowrap;
}

td {
    border-top: 1px solid #38333c;
    padding: 11px 8px;
    text-align: center;
    white-space: nowrap;
}

.weather-name {
    font-weight: bold;
}

.pressure-fall {
    color: #ff9b9b;
}

.pressure-rise {
    color: #9ed0ff;
}

.good {
    color: #9be7ad;
}

.attention {
    color: #ffd58a;
}

.danger {
    color: #ff8e8e;
}

.chart-box {
    height: 330px;
    padding: 10px;
}

.pressure-chart-box {
    height: 350px;
}

.error {
    color: #ff9999;
    padding: 20px;
    text-align: center;
}

.footer {
    color: #777;
    text-align: center;
    font-size: 12px;
    margin-top: 20px;
}


@media (max-width: 800px) {

    .container {
        width: 96%;
        padding-top: 12px;
    }

    h1 {
        font-size: 23px;
    }

    .cards {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

    .card-value {
        font-size: 21px;
    }

    section {
        padding: 13px;
        border-radius: 13px;
    }

    .section-title {
        font-size: 18px;
    }

    .chart-box {
        height: 300px;
        padding: 5px;
    }

    .pressure-chart-box {
        height: 320px;
    }
}

</style>
</head>


<body>

<div class="container">

<header>
    <h1>奈良本｜標高 約500m</h1>
    <div class="subtitle">
        24時間 天気・気圧・麓への移動目安
    </div>
</header>


<!-- =====================================================
     現在の状況
===================================================== -->

<section>

    <div class="section-title">
        現在の自宅周辺
    </div>

    <div class="cards">

        <div class="card">
            <div class="card-label">
                気温
            </div>

            <div class="card-value">
                {% if current_temp is not none %}
                    {{ "%.1f"|format(current_temp) }}℃
                {% else %}
                    —
                {% endif %}
            </div>
        </div>


        <div class="card">
            <div class="card-label">
                自宅推定気圧
            </div>

            <div class="card-value">
                {% if current_pressure is not none %}
                    {{ "%.1f"|format(current_pressure) }}
                    hPa
                {% else %}
                    —
                {% endif %}
            </div>

            <div class="card-small">
                標高約500m地点
            </div>
        </div>


        <div class="card">
            <div class="card-label">
                周辺AMeDAS
            </div>

            <div class="card-value">
                {% if observation %}
                    {{ observation.name }}
                {% else %}
                    —
                {% endif %}
            </div>

            {% if observation %}
            <div class="card-small">
                自宅から約
                {{ "%.1f"|format(observation.distance) }}
                km
            </div>
            {% endif %}
        </div>


        <div class="card">
            <div class="card-label">
                現在の状況
            </div>

            <div class="card-value">
                {{ current_status }}
            </div>

            {% if observation %}
            <div class="card-small">
                {% if observation.wind is not none %}
                    風 {{ "%.1f"|format(observation.wind) }} m/s
                {% endif %}
            </div>
            {% endif %}
        </div>

    </div>


    {% if observation %}

    <div class="notice">

        <strong>
            周辺AMeDAS観測
        </strong>

        気温：
        {% if observation.temp is not none %}
            {{ "%.1f"|format(observation.temp) }}℃
        {% else %}
            —
        {% endif %}

        ／

        湿度：
        {% if observation.humidity is not none %}
            {{ "%.0f"|format(observation.humidity) }}%
        {% else %}
            —
        {% endif %}

        ／

        風：
        {% if observation.wind is not none %}
            {{ "%.1f"|format(observation.wind) }}m/s
        {% else %}
            —
        {% endif %}

        {{ wind_direction_text(observation.wind_direction) }}

    </div>

    {% endif %}

</section>


<!-- =====================================================
     注意情報
===================================================== -->

<section>

    <div class="section-title">
        今後の注意
    </div>

    <div class="notice">
        <strong>気圧</strong>
        {{ health_text }}
    </div>


    {% if best_window %}

    <div class="notice">

        <strong>
            麓への移動
        </strong>

        {{ best_window.datetime.strftime("%H:%M") }}
        頃は比較的移動しやすい予想です。

    </div>

    {% endif %}

</section>


<!-- =====================================================
     24時間の天気
===================================================== -->

<section>

    <div class="section-title">
        24時間の天気
    </div>

    {% if forecasts %}

    <div class="hourly">

        <table>

            <thead>
                <tr>
                    <th>時間</th>
                    <th>天気</th>
                    <th>状況</th>
                    <th>気温</th>
                    <th>降水量</th>
                    <th>気圧</th>
                    <th>麓への移動</th>
                </tr>
            </thead>


            <tbody>

            {% for item in forecasts %}

                <tr>

                    <td>
                        {{ item.datetime.strftime("%m/%d %H:%M") }}
                    </td>


                    <td class="weather-name">
                        {{ item.display_weather }}
                    </td>


                    <td>
                        {% if item.thunder >= 30 %}
                            雷 {{ "%.0f"|format(item.thunder) }}%
                        {% elif item.precipitation > 0 %}
                            雨
                        {% else %}
                            降水なし
                        {% endif %}
                    </td>


                    <td>
                        {% if item.temperature is not none %}
                            {{ "%.1f"|format(item.temperature) }}℃
                        {% else %}
                            —
                        {% endif %}
                    </td>


                    <td>
                        {{ "%.1f"|format(item.precipitation) }} mm
                    </td>


                    <td>

                        {% if item.pressure_home is not none %}

                            {{ "%.1f"|format(item.pressure_home) }}

                            {% if item.pressure_change is not none %}

                                <span
                                    class="
                                    {% if item.pressure_level == 'fall'
                                       or item.pressure_level == 'strong-fall' %}
                                       pressure-fall
                                    {% elif item.pressure_level == 'rise'
                                       or item.pressure_level == 'strong-rise' %}
                                       pressure-rise
                                    {% endif %}
                                    "
                                >

                                    {% if item.pressure_change > 0 %}
                                        ↑
                                    {% elif item.pressure_change < 0 %}
                                        ↓
                                    {% endif %}

                                    {{ "%.1f"|format(
                                        item.pressure_change
                                    ) }}

                                </span>

                            {% endif %}

                        {% else %}
                            —
                        {% endif %}

                    </td>


                    <td
                        class="
                        {{ item.travel_level }}
                        "
                    >

                        {% if item.travel_level == "good" %}

                            ◎

                        {% elif item.travel_level == "attention" %}

                            △

                        {% else %}

                            ⚠

                        {% endif %}

                        {{ item.travel_reason }}

                    </td>

                </tr>

            {% endfor %}

            </tbody>

        </table>

    </div>

    {% else %}

        <div class="error">
            24時間予報を取得できませんでした。
        </div>

    {% endif %}

</section>


<!-- =====================================================
     天気グラフ
===================================================== -->

<section>

    <div class="section-title">
        24時間 天気グラフ
    </div>

    <div class="chart-box">
        <canvas id="weatherChart"></canvas>
    </div>

</section>


<!-- =====================================================
     気圧グラフ
===================================================== -->

<section>

    <div class="section-title">
        24時間 気圧グラフ
    </div>

    <div class="chart-box pressure-chart-box">
        <canvas id="pressureChart"></canvas>
    </div>

</section>


<div class="footer">
    AMeDAS + MET Norway
</div>


</div>


<script>

const labels = {{ chart_labels | safe }};

const temperatures = {{ chart_temperatures | safe }};

const rainfall = {{ chart_rainfall | safe }};

const pressures = {{ chart_pressures | safe }};


new Chart(
    document.getElementById("weatherChart"),
    {
        type: "line",

        data: {
            labels: labels,

            datasets: [
                {
                    label: "気温 ℃",
                    data: temperatures,
                    tension: 0.3,
                    yAxisID: "temperature"
                },
                {
                    label: "降水量 mm",
                    data: rainfall,
                    type: "bar",
                    yAxisID: "rain"
                }
            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,

            interaction: {
                mode: "index",
                intersect: false
            },

            scales: {

                temperature: {
                    position: "left",
                    title: {
                        display: true,
                        text: "気温 ℃"
                    }
                },

                rain: {
                    position: "right",
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: "降水量 mm"
                    },
                    grid: {
                        drawOnChartArea: false
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

            datasets: [
                {
                    label: "自宅推定気圧 hPa",
                    data: pressures,
                    tension: 0.3,
                    spanGaps: true
                }
            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,

            interaction: {
                mode: "index",
                intersect: false
            },

            scales: {

                y: {
                    title: {
                        display: true,
                        text: "気圧 hPa"
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
# メイン
# =========================================================

@app.route("/")
def index():

    now = jst_now()

    observation = get_nearest_observation()

    forecasts = get_met_forecast()


    # -----------------------------------------------------
    # 今から30分前～24時間後
    # -----------------------------------------------------

    filtered = []

    start_time = now - timedelta(minutes=30)
    end_time = now + timedelta(hours=24)

    seen = set()

    for item in forecasts:

        dt = item["datetime"]

        if dt < start_time:
            continue

        if dt > end_time:
            continue

        key = dt.strftime("%Y%m%d%H")

        if key in seen:
            continue

        seen.add(key)

        filtered.append(item)


    filtered.sort(
        key=lambda x: x["datetime"]
    )

    forecasts = filtered[:24]


    # -----------------------------------------------------
    # 気圧変化
    # -----------------------------------------------------

    calculate_pressure_changes(
        forecasts
    )


    # -----------------------------------------------------
    # 旅行・移動判定
    # -----------------------------------------------------

    for item in forecasts:

        item["display_weather"] = weather_display(
            item
        )

        item["travel_level"] = travel_level(
            item
        )

        item["travel_reason"] = travel_reason(
            item
        )


    # -----------------------------------------------------
    # グラフデータ
    # -----------------------------------------------------

    chart_labels = []

    chart_temperatures = []

    chart_rainfall = []

    chart_pressures = []


    for item in forecasts:

        chart_labels.append(
            item["datetime"].strftime("%H:%M")
        )

        chart_temperatures.append(
            item.get("temperature")
        )

        chart_rainfall.append(
            item.get("precipitation", 0)
        )

        chart_pressures.append(
            item.get("pressure_home")
        )


    # -----------------------------------------------------
    # 現在値
    # -----------------------------------------------------

    current_temp = None
    current_pressure = None


    if forecasts:

        first = forecasts[0]

        current_temp = first.get(
            "temperature"
        )

        current_pressure = first.get(
            "pressure_home"
        )


    # -----------------------------------------------------
    # AMeDASが取得できた場合は観測気温を優先
    # -----------------------------------------------------

    if observation:

        if observation.get("temp") is not None:
            current_temp = observation["temp"]


    # -----------------------------------------------------
    # 現在の状態
    # -----------------------------------------------------

    current_status = current_weather_status(
        observation
    )


    # -----------------------------------------------------
    # 気圧注意
    # -----------------------------------------------------

    health_text = health_attention_text(
        forecasts
    )


    # -----------------------------------------------------
    # 移動しやすい時間
    # -----------------------------------------------------

    best_window = best_travel_window(
        forecasts
    )


    return render_template_string(

        HTML,

        observation=observation,

        current_temp=current_temp,

        current_pressure=current_pressure,

        current_status=current_status,

        health_text=health_text,

        best_window=best_window,

        forecasts=forecasts,

        chart_labels=json.dumps(
            chart_labels,
            ensure_ascii=False
        ),

        chart_temperatures=json.dumps(
            chart_temperatures,
            ensure_ascii=False
        ),

        chart_rainfall=json.dumps(
            chart_rainfall,
            ensure_ascii=False
        ),

        chart_pressures=json.dumps(
            chart_pressures,
            ensure_ascii=False
        ),

        wind_direction_text=wind_direction_text
    )


# =========================================================
# 起動
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )