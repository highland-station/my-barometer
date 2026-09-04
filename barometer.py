from flask import Flask, render_template_string
import requests
import math
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# ============================================================
# 自宅
# ============================================================
HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

JST = timezone(timedelta(hours=9))

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"

HEADERS = {
    "User-Agent": "my-barometer/1.0 github.com/highland-station/my-barometer"
}


# ============================================================
# 共通
# ============================================================
def get_json(url, params=None):
    r = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=20
    )
    r.raise_for_status()
    return r.json()


# ============================================================
# 風向
# ============================================================
def wind_direction(deg):
    if deg is None:
        return "—"

    directions = [
        "北", "北北東", "北東", "東北東",
        "東", "東南東", "南東", "南南東",
        "南", "南南西", "南西", "西南西",
        "西", "西北西", "北西", "北北西"
    ]

    return directions[int((deg + 11.25) / 22.5) % 16]


# ============================================================
# 天気アイコン
# ============================================================
def weather_icon(symbol):
    if not symbol:
        return "🌤️"

    s = symbol.lower()

    if "thunder" in s:
        return "⛈️"
    if "heavyrain" in s:
        return "🌧️"
    if "rain" in s:
        return "🌦️"
    if "fog" in s:
        return "🌫️"
    if "snow" in s:
        return "❄️"
    if "sleet" in s:
        return "🌨️"
    if "partlycloudy" in s:
        return "🌤️"
    if "cloudy" in s:
        return "☁️"
    if "fair" in s:
        return "🌤️"
    if "clearsky" in s:
        return "☀️"

    return "🌤️"


def weather_name(symbol):
    if not symbol:
        return "予報データなし"

    s = symbol.lower()

    if "thunder" in s:
        return "雷雨"
    if "heavyrain" in s:
        return "強い雨"
    if "rain" in s:
        return "雨"
    if "fog" in s:
        return "霧"
    if "snow" in s:
        return "雪"
    if "sleet" in s:
        return "みぞれ"
    if "partlycloudy" in s:
        return "晴れ時々曇り"
    if "cloudy" in s:
        return "曇り"
    if "fair" in s:
        return "晴れ"
    if "clearsky" in s:
        return "快晴"

    return "予報"


# ============================================================
# 標高から自宅の気圧を計算
# ============================================================
def surface_pressure(sea_pressure, temperature):
    if sea_pressure is None or temperature is None:
        return None

    kelvin = temperature + 273.15

    return sea_pressure * math.exp(
        -9.80665 * HOME_ALTITUDE /
        (287.05 * kelvin)
    )


# ============================================================
# MET Norway
# 奈良本の24時間予報
# ============================================================
def get_forecast():

    params = {
        "lat": HOME_LAT,
        "lon": HOME_LON,
        "altitude": HOME_ALTITUDE
    }

    data = get_json(
        MET_URL,
        params=params
    )

    timeseries = data["properties"]["timeseries"]

    now = datetime.now(timezone.utc)

    rows = []

    for item in timeseries:

        dt = datetime.fromisoformat(
            item["time"].replace("Z", "+00:00")
        )

        if dt < now - timedelta(hours=1):
            continue

        data_block = item.get("data", {})

        instant = data_block.get(
            "instant", {}
        ).get("details", {})

        next1 = data_block.get(
            "next_1_hours", {}
        )

        next6 = data_block.get(
            "next_6_hours", {}
        )

        details1 = next1.get("details", {})
        details6 = next6.get("details", {})

        summary1 = next1.get("summary", {})
        summary6 = next6.get("summary", {})

        symbol = (
            summary1.get("symbol_code")
            or summary6.get("symbol_code")
        )

        rain_probability = details1.get(
            "probability_of_precipitation"
        )

        if rain_probability is None:
            rain_probability = details6.get(
                "probability_of_precipitation"
            )

        precipitation = details1.get(
            "precipitation_amount"
        )

        if precipitation is None:
            precipitation = details6.get(
                "precipitation_amount"
            )

        temperature = instant.get(
            "air_temperature"
        )

        sea_pressure = instant.get(
            "air_pressure_at_sea_level"
        )

        pressure = surface_pressure(
            sea_pressure,
            temperature
        )

        rows.append({
            "dt": dt,
            "time": dt.astimezone(JST).strftime("%H:%M"),
            "temperature": temperature,
            "humidity": instant.get("relative_humidity"),
            "pressure": pressure,
            "sea_pressure": sea_pressure,
            "wind": instant.get("wind_speed"),
            "wind_deg": instant.get("wind_from_direction"),
            "rain_probability": rain_probability,
            "precipitation": precipitation,
            "symbol": symbol,
            "icon": weather_icon(symbol),
            "weather": weather_name(symbol)
        })

        if len(rows) >= 25:
            break

    return rows


# ============================================================
# AMeDAS
# 「現在」の実測値
# ============================================================
def get_amedas():

    # 気象庁の観測所一覧
    stations = get_json(
        "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
    )

    nearest = None
    nearest_distance = None

    for station_id, station in stations.items():

        lat_data = station.get("lat")
        lon_data = station.get("lon")

        if not lat_data or not lon_data:
            continue

        lat = lat_data[0]
        lon = lon_data[0]

        # 簡易距離
        distance = (
            (lat - HOME_LAT) ** 2 +
            ((lon - HOME_LON) * math.cos(
                math.radians(HOME_LAT)
            )) ** 2
        )

        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest = {
                "id": station_id,
                "name": station.get("kjName", "近隣AMeDAS"),
                "lat": lat,
                "lon": lon
            }

    if nearest is None:
        return None

    now = datetime.now(JST)

    # 直近10分程度の観測ファイルを順に探す
    observations = None
    observed_time = None

    for minutes_back in range(0, 61, 10):

        target = now - timedelta(minutes=minutes_back)

        target = target.replace(
            minute=(target.minute // 10) * 10,
            second=0,
            microsecond=0
        )

        date_str = target.strftime("%Y%m%d")
        hour = target.strftime("%H")
        minute = target.strftime("%M")

        url = (
            f"https://www.jma.go.jp/bosai/amedas/data/"
            f"map/{date_str}/{hour}{minute}0000.json"
        )

        try:
            data = get_json(url)

            if nearest["id"] in data:
                observations = data[nearest["id"]]
                observed_time = target
                break

        except Exception:
            continue

    if observations is None:
        return None

    def value(key):
        v = observations.get(key)
        if isinstance(v, list) and v:
            return v[0]
        return v

    temperature = value("temp")
    humidity = value("humidity")
    wind_speed = value("wind")
    wind_deg = value("windDirection")

    rain10 = value("precipitation10m")

    if rain10 is None:
        rain10 = 0

    return {
        "station": nearest["name"],
        "observed_time": observed_time.strftime("%H:%M"),
        "temperature": temperature,
        "humidity": humidity,
        "wind": wind_speed,
        "wind_direction": wind_direction(wind_deg),
        "rain10": rain10
    }


# ============================================================
# 気象状況
# ============================================================
def analyze(current, forecast):

    messages = []

    # 現在の雨
    if current:

        rain = current.get("rain10")

        if rain is not None and rain >= 1:
            messages.append({
                "icon": "🌧️",
                "title": "現在、雨が観測されています",
                "text": f"直近10分の降水量は {rain:.1f} mm です。"
            })

        elif rain is not None and rain > 0:
            messages.append({
                "icon": "🌦️",
                "title": "弱い降水を観測",
                "text": f"直近10分の降水量は {rain:.1f} mm です。"
            })

    # 予報
    for item in forecast[:6]:

        symbol = item.get("symbol", "")

        if not symbol:
            continue

        s = symbol.lower()

        if "thunder" in s:
            messages.append({
                "icon": "⛈️",
                "title": "雷雨に注意",
                "text": "今後数時間に雷を伴う雨が予想されています。"
            })
            break

        if "heavyrain" in s:
            messages.append({
                "icon": "🌧️",
                "title": "強い雨に注意",
                "text": "今後数時間に強い雨が予想されています。"
            })
            break

    # 霧
    if current:

        humidity = current.get("humidity")

        if humidity is not None and humidity >= 95:
            messages.append({
                "icon": "🌫️",
                "title": "霧が発生しやすい状況",
                "text": f"周辺の湿度が {humidity:.0f}% と非常に高くなっています。"
            })

    # 強風
    for item in forecast[:12]:

        wind = item.get("wind")

        if wind is not None and wind >= 10:
            messages.append({
                "icon": "🌬️",
                "title": "強風に注意",
                "text": f"{item['time']}頃に風速 {wind:.1f} m/s 前後が予想されています。"
            })
            break

    if not messages:
        messages.append({
            "icon": "✓",
            "title": "大きな荒天の兆候はありません",
            "text": "現在のところ、目立った荒天は予想されていません。"
        })

    return messages


# ============================================================
# HTML
# ============================================================
HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>奈良本 気象ダッシュボード</title>

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
            #181516 40%,
            #101011 100%
        );
    color: #eee8e9;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Noto Sans JP",
        sans-serif;
}

.container {
    max-width: 1180px;
    margin: auto;
    padding: 28px 24px 60px;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: end;
    border-bottom: 1px solid #393235;
    padding-bottom: 18px;
    margin-bottom: 24px;
}

.location {
    color: #c9b9be;
    font-size: 14px;
    letter-spacing: 1.5px;
}

.location strong {
    color: #e2a7b7;
    font-weight: 500;
}

.updated {
    color: #81777b;
    font-size: 12px;
}

.grid {
    display: grid;
    grid-template-columns: 1.2fr .8fr;
    gap: 20px;
}

.panel {
    background: rgba(31,28,29,.9);
    border: 1px solid #3b3437;
    border-radius: 18px;
    padding: 26px;
    box-shadow: 0 18px 45px rgba(0,0,0,.22);
}

.current {
    min-height: 340px;
}

.current-title {
    color: #857b7f;
    font-size: 11px;
    letter-spacing: 1.5px;
    margin-bottom: 18px;
}

.current-note {
    color: #7e7478;
    font-size: 11px;
    margin-top: 16px;
}

.current-main {
    display: flex;
    align-items: center;
    gap: 22px;
}

.current-temp {
    font-family: Georgia, serif;
    font-size: 68px;
    color: #f0dfe4;
}

.current-temp small {
    font-size: 27px;
    color: #a99da1;
}

.current-icon {
    font-size: 64px;
}

.current-details {
    color: #cbbdc1;
}

.metrics {
    margin-top: 30px;
    display: grid;
    grid-template-columns: repeat(2,1fr);
    gap: 12px 28px;
}

.metric {
    border-top: 1px solid #393336;
    padding-top: 10px;
}

.metric-label {
    color: #8f8589;
    font-size: 11px;
}

.metric-value {
    margin-top: 5px;
    font-size: 16px;
}

.pressure-title {
    color: #857b7f;
    font-size: 11px;
    letter-spacing: 2px;
}

.pressure-value {
    font-family: Georgia, serif;
    color: #e5aabb;
    font-size: 54px;
    margin-top: 22px;
}

.pressure-sea {
    color: #9e9498;
    font-size: 14px;
}

.pressure-explain {
    margin-top: 22px;
    padding: 16px;
    background: #272224;
    border-radius: 12px;
    color: #d5c7cb;
    line-height: 1.7;
}

.section {
    margin-top: 22px;
}

.section-title {
    color: #d6c6ca;
    font-size: 14px;
    letter-spacing: 1.5px;
    margin-bottom: 12px;
}

.alerts {
    display: grid;
    gap: 9px;
}

.alert {
    background: #242021;
    border-left: 3px solid #b9798d;
    border-radius: 10px;
    padding: 13px 16px;
}

.alert-title {
    color: #e4c4cb;
    font-size: 14px;
}

.alert-text {
    color: #9d9397;
    font-size: 12px;
    margin-top: 4px;
}

.forecast {
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding-bottom: 8px;
}

.hour {
    min-width: 125px;
    background: #211e20;
    border: 1px solid #393235;
    border-radius: 14px;
    padding: 14px;
}

.hour-time {
    color: #d4b3bc;
    font-size: 13px;
}

.hour-temp {
    font-family: Georgia, serif;
    font-size: 25px;
    margin-top: 7px;
}

.hour-weather {
    margin-top: 7px;
    min-height: 45px;
    font-size: 13px;
    line-height: 1.5;
}

.hour-rain {
    margin-top: 8px;
    color: #d9aeba;
    font-size: 12px;
}

.hour-wind {
    margin-top: 7px;
    color: #9c9296;
    font-size: 12px;
}

.chart-panel {
    margin-top: 22px;
}

.chart-wrap {
    position: relative;
    height: 270px;
}

footer {
    text-align: center;
    color: #70686b;
    font-size: 11px;
    margin-top: 28px;
}

@media(max-width:800px) {

    .container {
        padding: 18px 14px 45px;
    }

    header {
        align-items: flex-start;
    }

    .grid {
        grid-template-columns: 1fr;
    }

    .current-temp {
        font-size: 55px;
    }

    .current-icon {
        font-size: 52px;
    }

    .metrics {
        grid-template-columns: 1fr 1fr;
    }
}

</style>

</head>

<body>

<div class="container">

<header>

    <div class="location">
        <strong>奈良本</strong>｜標高 約500m
    </div>

    <div class="updated">
        {{ updated }}
    </div>

</header>


<!-- =====================================================
     現在
===================================================== -->

<div class="grid">

<div class="panel">

    <div class="current-title">
        現在の周辺観測
    </div>

    {% if current %}

    <div class="current-main">

        <div class="current-icon">
            🌤️
        </div>

        <div>

            {% if current.temperature is not none %}
            <div class="current-temp">
                {{ current.temperature }}<small>°</small>
            </div>
            {% else %}
            <div class="current-temp">—</div>
            {% endif %}

            <div class="current-details">
                {{ current.station }}
                ｜ {{ current.observed_time }}
            </div>

        </div>

    </div>

    <div class="metrics">

        <div class="metric">
            <div class="metric-label">湿度</div>
            <div class="metric-value">
                {% if current.humidity is not none %}
                    {{ current.humidity }}%
                {% else %}
                    —
                {% endif %}
            </div>
        </div>

        <div class="metric">
            <div class="metric-label">直近10分の降水量</div>
            <div class="metric-value">
                {{ current.rain10 }} mm
            </div>
        </div>

        <div class="metric">
            <div class="metric-label">風</div>
            <div class="metric-value">
                {{ current.wind_direction }}
                {% if current.wind is not none %}
                    {{ current.wind }} m/s
                {% endif %}
            </div>
        </div>

        <div class="metric">
            <div class="metric-label">観測地点</div>
            <div class="metric-value">
                {{ current.station }}
            </div>
        </div>

    </div>

    <div class="current-note">
        ※現在値は最寄りの気象庁AMeDASによる周辺観測です。
        自宅地点の24時間予報とは分けて表示しています。
    </div>

    {% else %}

    <div style="color:#999;">
        現在の観測データを取得できませんでした。
    </div>

    {% endif %}

</div>


<!-- =====================================================
     気圧
===================================================== -->

<div class="panel">

    <div class="pressure-title">
        自宅地点の気圧
    </div>

    <div class="pressure-value">
        {{ current_pressure }}
        <span style="font-size:18px;">hPa</span>
    </div>

    <div class="pressure-sea">
        海面更正 {{ sea_pressure }} hPa
    </div>

    <div class="pressure-explain">

        {% if pressure_change <= -3 %}
            ↓↓ <strong>気圧が大きく下降中</strong><br>
            天候が変化しやすい状態です。

        {% elif pressure_change < -1 %}
            ↓ <strong>気圧は下降傾向</strong><br>
            天候が崩れる方向への変化に注意。

        {% elif pressure_change >= 3 %}
            ↑↑ <strong>気圧が大きく上昇中</strong><br>
            天候は回復方向へ向かう可能性があります。

        {% elif pressure_change > 1 %}
            ↑ <strong>気圧は上昇傾向</strong><br>
            天候は回復方向の傾向です。

        {% else %}
            → <strong>気圧は比較的安定</strong><br>
            大きな気圧変化はありません。
        {% endif %}

    </div>

</div>

</div>


<!-- =====================================================
     気象状況
===================================================== -->

<div class="section">

<div class="section-title">
    現在の気象状況
</div>

<div class="alerts">

{% for alert in alerts %}

<div class="alert">

    <div class="alert-title">
        {{ alert.icon }} {{ alert.title }}
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

<div class="section">

<div class="section-title">
    これから24時間
</div>

<div style="color:#7e7478;font-size:11px;margin-bottom:12px;">
    奈良本・標高約500m地点の予報
</div>

<div class="forecast">

{% for item in forecast %}

<div class="hour">

    <div class="hour-time">
        {{ item.time }}
    </div>

    <div class="hour-temp">
        {{ item.temperature }}°
    </div>

    <div class="hour-weather">
        {{ item.icon }}
        {{ item.weather }}
    </div>

    <div class="hour-rain">

        {% if item.rain_probability is not none %}
            ☔ {{ item.rain_probability }}%
        {% else %}
            ☔ —
        {% endif %}

        {% if item.precipitation is not none %}
            ｜ {{ item.precipitation }} mm
        {% endif %}

    </div>

    <div class="hour-wind">
        {{ item.wind_direction }}
        {{ item.wind }}m/s
    </div>

</div>

{% endfor %}

</div>

</div>


<!-- =====================================================
     気温グラフ
===================================================== -->

<div class="panel chart-panel">

<div class="section-title">
    24時間の気温
</div>

<div class="chart-wrap">
    <canvas id="temperatureChart"></canvas>
</div>

</div>


<!-- =====================================================
     気圧グラフ
===================================================== -->

<div class="panel chart-panel">

<div class="section-title">
    24時間の気圧
</div>

<div class="chart-wrap">
    <canvas id="pressureChart"></canvas>
</div>

</div>


<footer>
    奈良本｜標高 約500m ｜ 24時間予報：MET Norway
</footer>

</div>


<script>

const labels = {{ labels | safe }};
const temperatures = {{ temperatures | safe }};
const pressures = {{ pressures | safe }};


new Chart(
    document.getElementById("temperatureChart"),
    {
        type: "line",

        data: {
            labels: labels,

            datasets: [{
                label: "気温",
                data: temperatures,

                tension: 0.35,

                borderWidth: 2,

                pointRadius: 2,

                fill: false
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
                        color: "#8f8589"
                    },

                    grid: {
                        color: "rgba(255,255,255,.05)"
                    }
                },

                y: {
                    ticks: {
                        color: "#8f8589",
                        callback: function(value) {
                            return value + "°";
                        }
                    },

                    grid: {
                        color: "rgba(255,255,255,.05)"
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
                label: "気圧",
                data: pressures,

                tension: 0.35,

                borderWidth: 2,

                pointRadius: 2,

                fill: false
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
                        color: "#8f8589"
                    },

                    grid: {
                        color: "rgba(255,255,255,.05)"
                    }
                },

                y: {
                    ticks: {
                        color: "#8f8589",
                        callback: function(value) {
                            return value + " hPa";
                        }
                    },

                    grid: {
                        color: "rgba(255,255,255,.05)"
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

    forecast = []
    amedas = None

    try:
        forecast = get_forecast()
    except Exception as e:
        print("forecast error:", e)

    try:
        amedas = get_amedas()
    except Exception as e:
        print("amedas error:", e)

    # -----------------------------------------
    # 自宅の気圧
    # -----------------------------------------
    if forecast:

        first = forecast[0]

        current_pressure = first["pressure"]
        sea_pressure = first["sea_pressure"]

        if current_pressure is not None:
            current_pressure = round(
                current_pressure, 1
            )

        if sea_pressure is not None:
            sea_pressure = round(
                sea_pressure, 1
            )

    else:

        current_pressure = "—"
        sea_pressure = "—"

    # -----------------------------------------
    # 気圧変化
    # -----------------------------------------
    pressure_change = 0

    if len(forecast) >= 4:

        p0 = forecast[0]["pressure"]
        p3 = forecast[3]["pressure"]

        if p0 is not None and p3 is not None:
            pressure_change = p3 - p0

    # -----------------------------------------
    # 現在観測
    # -----------------------------------------
    if amedas:

        if amedas["temperature"] is not None:
            amedas["temperature"] = round(
                amedas["temperature"], 1
            )

        if amedas["humidity"] is not None:
            amedas["humidity"] = round(
                amedas["humidity"]
            )

        if amedas["wind"] is not None:
            amedas["wind"] = round(
                amedas["wind"], 1
            )

        if amedas["rain10"] is None:
            amedas["rain10"] = 0
        else:
            amedas["rain10"] = round(
                amedas["rain10"], 1
            )

    # -----------------------------------------
    # 気象状況
    # -----------------------------------------
    alerts = analyze(
        amedas,
        forecast
    )

    # -----------------------------------------
    # グラフ
    # -----------------------------------------
    labels = [
        x["time"]
        for x in forecast
    ]

    temperatures = [
        round(x["temperature"], 1)
        if x["temperature"] is not None
        else None
        for x in forecast
    ]

    pressures = [
        round(x["pressure"], 1)
        if x["pressure"] is not None
        else None
        for x in forecast
    ]

    return render_template_string(
        HTML,

        current=amedas,

        current_pressure=current_pressure,
        sea_pressure=sea_pressure,

        pressure_change=pressure_change,

        forecast=forecast,

        alerts=alerts,

        labels=labels,
        temperatures=temperatures,
        pressures=pressures,

        updated=datetime.now(JST).strftime(
            "%Y/%m/%d %H:%M"
        )
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )