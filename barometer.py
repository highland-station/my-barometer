from flask import Flask, render_template_string
import requests
import math
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# =========================================================
# 奈良本・自宅
# =========================================================
HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"

HEADERS = {
    "User-Agent": "my-barometer/1.0 github.com/highland-station/my-barometer"
}

JST = timezone(timedelta(hours=9))


# =========================================================
# 天気アイコン
# =========================================================
def weather_icon(symbol):
    if not symbol:
        return "🌤️"

    s = symbol.lower()

    if "thunder" in s:
        return "⛈️"
    if "sleet" in s:
        return "🌨️"
    if "snow" in s:
        return "❄️"
    if "fog" in s:
        return "🌫️"
    if "heavyrain" in s:
        return "🌧️"
    if "rain" in s:
        return "🌧️"
    if "heavysleet" in s:
        return "🌨️"
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


# =========================================================
# 天気名
# =========================================================
def weather_name(symbol):
    if not symbol:
        return "天気不明"

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

    return "天気不明"


# =========================================================
# 風向
# =========================================================
def wind_direction(deg):
    if deg is None:
        return "—"

    directions = [
        "北", "北北東", "北東", "東北東",
        "東", "東南東", "南東", "南南東",
        "南", "南南西", "南西", "西南西",
        "西", "西北西", "北西", "北北西"
    ]

    index = int((deg + 11.25) / 22.5) % 16
    return directions[index]


# =========================================================
# 自宅標高から地上気圧を計算
# =========================================================
def calculate_surface_pressure(sea_level_pressure, temperature):
    if sea_level_pressure is None or temperature is None:
        return None

    kelvin = temperature + 273.15

    pressure = sea_level_pressure * math.exp(
        -9.80665 * HOME_ALTITUDE /
        (287.05 * kelvin)
    )

    return pressure


# =========================================================
# 気圧の状態
# =========================================================
def pressure_status(current_pressure, previous_pressure):
    if current_pressure is None:
        return "気圧データなし", "—"

    if previous_pressure is None:
        return "気圧は安定しています", "→"

    diff = current_pressure - previous_pressure

    if diff <= -3:
        return "気圧が大きく下降しています", "↓↓"
    elif diff <= -1:
        return "気圧が下降しています", "↓"
    elif diff >= 3:
        return "気圧が大きく上昇しています", "↑↑"
    elif diff >= 1:
        return "気圧が上昇しています", "↑"
    else:
        return "気圧はほぼ安定しています", "→"


# =========================================================
# 気象状況を自動判定
# =========================================================
def analyze_weather(current, forecast):
    messages = []

    temp = current.get("temperature")
    humidity = current.get("humidity")
    pressure = current.get("pressure")
    pressure_previous = current.get("pressure_previous")
    wind = current.get("wind")
    symbol = current.get("symbol", "")

    # 気圧
    p_text, p_arrow = pressure_status(
        pressure,
        pressure_previous
    )

    messages.append({
        "icon": "◉",
        "title": p_text,
        "text": "気圧の変化から、今後の天候変化に注意してください。"
        if "下降" in p_text
        else "大きな気圧変化はありません。"
    })

    # 霧
    if humidity is not None and humidity >= 90:
        messages.append({
            "icon": "🌫️",
            "title": "霧が発生しやすい状況",
            "text": f"湿度が{humidity:.0f}%と高く、視界が悪くなる可能性があります。"
        })

    # 強風
    if wind is not None and wind >= 10:
        messages.append({
            "icon": "🌬️",
            "title": "強風に注意",
            "text": f"風速が{wind:.1f}m/sに達する予想です。"
        })
    elif wind is not None and wind >= 7:
        messages.append({
            "icon": "🌬️",
            "title": "風が強めです",
            "text": f"風速は{wind:.1f}m/s前後です。"
        })

    # 雨・雷
    if "thunder" in symbol.lower():
        messages.append({
            "icon": "⛈️",
            "title": "雷雨に注意",
            "text": "雷を伴う雨が予想されています。"
        })
    elif "heavyrain" in symbol.lower():
        messages.append({
            "icon": "🌧️",
            "title": "強い雨に注意",
            "text": "強い雨が予想されています。"
        })
    elif "rain" in symbol.lower():
        messages.append({
            "icon": "🌧️",
            "title": "雨の予想",
            "text": "今後数時間は雨に注意してください。"
        })

    # 24時間以内の大きな変化
    pressures = [
        x["pressure"]
        for x in forecast
        if x.get("pressure") is not None
    ]

    if len(pressures) >= 3:
        pressure_change = pressures[-1] - pressures[0]

        if pressure_change <= -5:
            messages.append({
                "icon": "⚠️",
                "title": "今後24時間で気圧が大きく低下",
                "text": "天候が大きく変化する可能性があります。"
            })

    # 何も特別なことがない場合
    if len(messages) == 1:
        messages.append({
            "icon": "✓",
            "title": "大きな荒天の兆候はありません",
            "text": "現在のところ比較的安定した気象状況です。"
        })

    return messages, p_arrow


# =========================================================
# MET Norwayから取得
# =========================================================
def get_weather():
    params = {
        "lat": HOME_LAT,
        "lon": HOME_LON,
        "altitude": HOME_ALTITUDE
    }

    response = requests.get(
        MET_URL,
        params=params,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    timeseries = data["properties"]["timeseries"]

    now = datetime.now(timezone.utc)

    records = []

    for item in timeseries:
        time_string = item["time"]

        dt = datetime.fromisoformat(
            time_string.replace("Z", "+00:00")
        )

        instant = item.get("data", {}).get("instant", {})
        details = instant.get("details", {})

        next_hour = (
            item.get("data", {})
            .get("next_1_hours", {})
            .get("details", {})
        )

        next_six = (
            item.get("data", {})
            .get("next_6_hours", {})
            .get("details", {})
        )

        temperature = details.get("air_temperature")
        humidity = details.get("relative_humidity")
        sea_pressure = details.get("air_pressure_at_sea_level")
        wind = details.get("wind_speed")
        wind_deg = details.get("wind_from_direction")

        # 降水確率
        rain_probability = next_hour.get(
            "probability_of_precipitation"
        )

        if rain_probability is None:
            rain_probability = next_six.get(
                "probability_of_precipitation"
            )

        # 降水量
        precipitation = next_hour.get(
            "precipitation_amount"
        )

        if precipitation is None:
            precipitation = next_six.get(
                "precipitation_amount"
            )

        # 天気
        symbol = (
            item.get("data", {})
            .get("next_1_hours", {})
            .get("summary", {})
            .get("symbol_code")
        )

        if symbol is None:
            symbol = (
                item.get("data", {})
                .get("next_6_hours", {})
                .get("summary", {})
                .get("symbol_code")
            )

        surface_pressure = calculate_surface_pressure(
            sea_pressure,
            temperature
        )

        records.append({
            "dt": dt,
            "temperature": temperature,
            "humidity": humidity,
            "sea_pressure": sea_pressure,
            "pressure": surface_pressure,
            "wind": wind,
            "wind_deg": wind_deg,
            "rain_probability": rain_probability,
            "precipitation": precipitation,
            "symbol": symbol
        })

    future = [
        x for x in records
        if x["dt"] >= now
    ]

    if not future:
        future = records

    current = future[0]

    # 現在の降水確率が取れない場合、
    # 次に取得できる降水確率を使う
    if current["rain_probability"] is None:
        for item in future:
            if item["rain_probability"] is not None:
                current["rain_probability"] = item["rain_probability"]
                break

    # 前の気圧
    previous_pressure = None

    if len(future) > 1:
        previous_pressure = future[1]["pressure"]

    current["pressure_previous"] = previous_pressure

    # 24時間分
    forecast = future[:25]

    for item in forecast:
        item["time_jst"] = item["dt"].astimezone(JST).strftime("%H:%M")

        if item["rain_probability"] is not None:
            item["rain_probability"] = round(
                item["rain_probability"]
            )

        if item["precipitation"] is not None:
            item["precipitation"] = round(
                item["precipitation"], 1
            )

        if item["temperature"] is not None:
            item["temperature"] = round(
                item["temperature"], 1
            )

        if item["wind"] is not None:
            item["wind"] = round(
                item["wind"], 1
            )

        if item["pressure"] is not None:
            item["pressure"] = round(
                item["pressure"], 1
            )

        item["icon"] = weather_icon(item["symbol"])
        item["weather_name"] = weather_name(item["symbol"])
        item["wind_direction"] = wind_direction(
            item["wind_deg"]
        )

    # 現在値
    current_temp = current["temperature"]
    current_pressure = current["pressure"]

    if current_temp is not None:
        current_temp = round(current_temp, 1)

    if current_pressure is not None:
        current_pressure = round(current_pressure, 1)

    if current["sea_pressure"] is not None:
        sea_pressure_display = round(
            current["sea_pressure"], 1
        )
    else:
        sea_pressure_display = "—"

    if current["humidity"] is not None:
        humidity_display = round(current["humidity"])
    else:
        humidity_display = "—"

    if current["wind"] is not None:
        wind_display = round(current["wind"], 1)
    else:
        wind_display = "—"

    if current["rain_probability"] is not None:
        rain_probability_display = round(
            current["rain_probability"]
        )
    else:
        rain_probability_display = "—"

    if current["precipitation"] is not None:
        precipitation_display = round(
            current["precipitation"], 1
        )
    else:
        precipitation_display = "—"

    current_data = {
        "temperature": current_temp,
        "humidity": humidity_display,
        "pressure": current_pressure,
        "sea_pressure": sea_pressure_display,
        "wind": wind_display,
        "wind_direction": wind_direction(
            current["wind_deg"]
        ),
        "rain_probability": rain_probability_display,
        "precipitation": precipitation_display,
        "symbol": current["symbol"],
        "weather": weather_name(current["symbol"]),
        "icon": weather_icon(current["symbol"]),
        "pressure_previous": previous_pressure
    }

    messages, pressure_arrow = analyze_weather(
        current_data,
        forecast
    )

    return {
        "current": current_data,
        "forecast": forecast,
        "messages": messages,
        "pressure_arrow": pressure_arrow,
        "updated": datetime.now(JST).strftime(
            "%Y/%m/%d %H:%M"
        )
    }


# =========================================================
# HTML
# =========================================================
HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>奈良本 気象ダッシュボード</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background:
        radial-gradient(circle at top right, #30272c 0%, #181617 38%, #111011 100%);
    color: #eee8e9;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Noto Sans JP",
        sans-serif;
}

.container {
    max-width: 1180px;
    margin: 0 auto;
    padding: 28px 24px 50px;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: end;
    border-bottom: 1px solid #393235;
    padding-bottom: 18px;
    margin-bottom: 28px;
}

.location {
    font-size: 14px;
    letter-spacing: 1.5px;
    color: #c8b8bd;
}

.location strong {
    color: #e3a6b6;
    font-weight: 500;
}

.updated {
    color: #81777b;
    font-size: 12px;
}

.hero {
    display: grid;
    grid-template-columns: 1.2fr .8fr;
    gap: 22px;
}

.panel {
    background: rgba(31, 28, 29, .88);
    border: 1px solid #3b3437;
    border-radius: 18px;
    padding: 28px;
    box-shadow: 0 18px 45px rgba(0,0,0,.22);
}

.current {
    min-height: 330px;
}

.current-top {
    display: flex;
    align-items: center;
    gap: 24px;
}

.weather-icon {
    font-size: 72px;
}

.temp {
    font-family: Georgia, serif;
    font-size: 74px;
    line-height: 1;
    color: #f1dfe4;
}

.temp span {
    font-size: 28px;
    color: #a99da1;
}

.weather-name {
    margin-top: 10px;
    color: #cbbec2;
    font-size: 18px;
}

.metrics {
    margin-top: 30px;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px 30px;
}

.metric {
    border-top: 1px solid #393336;
    padding-top: 10px;
}

.metric-label {
    color: #8f8589;
    font-size: 12px;
}

.metric-value {
    margin-top: 4px;
    font-size: 17px;
}

.pressure-main {
    text-align: center;
}

.pressure-label {
    color: #958a8e;
    letter-spacing: 2px;
    font-size: 12px;
}

.pressure-value {
    font-family: Georgia, serif;
    font-size: 56px;
    margin-top: 20px;
    color: #e8b0bf;
}

.pressure-sea {
    font-size: 18px;
    color: #aaa0a4;
    margin-top: 4px;
}

.pressure-status {
    margin-top: 22px;
    padding: 15px;
    background: #282325;
    border-radius: 12px;
    color: #d9cbd0;
}

.pressure-arrow {
    color: #e3a6b6;
    font-size: 24px;
}

.section {
    margin-top: 24px;
}

.section-title {
    font-size: 15px;
    letter-spacing: 1.5px;
    color: #d7c6ca;
    margin-bottom: 12px;
}

.alerts {
    display: grid;
    gap: 10px;
}

.alert {
    background: #252123;
    border-left: 3px solid #b8788b;
    border-radius: 10px;
    padding: 14px 17px;
}

.alert-title {
    font-size: 14px;
    color: #e3c3ca;
}

.alert-text {
    margin-top: 4px;
    color: #9e9498;
    font-size: 12px;
}

.forecast {
    overflow-x: auto;
    display: flex;
    gap: 10px;
    padding-bottom: 10px;
}

.hour {
    min-width: 125px;
    background: #211e20;
    border: 1px solid #393235;
    border-radius: 14px;
    padding: 14px;
}

.hour-time {
    color: #d5b5bd;
    font-size: 13px;
}

.hour-temp {
    font-family: Georgia, serif;
    font-size: 25px;
    margin-top: 8px;
}

.hour-weather {
    margin-top: 7px;
    min-height: 42px;
    font-size: 13px;
}

.hour-rain {
    margin-top: 9px;
    color: #d9aeba;
    font-size: 13px;
}

.hour-wind {
    margin-top: 7px;
    color: #9d9397;
    font-size: 12px;
}

footer {
    margin-top: 28px;
    color: #70686b;
    font-size: 11px;
    text-align: center;
}

@media (max-width: 800px) {

    .container {
        padding: 18px 14px 40px;
    }

    header {
        align-items: start;
        gap: 10px;
    }

    .hero {
        grid-template-columns: 1fr;
    }

    .metrics {
        grid-template-columns: 1fr 1fr;
    }

    .temp {
        font-size: 58px;
    }

    .weather-icon {
        font-size: 58px;
    }

    .pressure-value {
        font-size: 48px;
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
        {{ weather.updated }}
    </div>
</header>


<div class="hero">

    <!-- 現在 -->
    <div class="panel current">

        <div class="current-top">

            <div class="weather-icon">
                {{ weather.current.icon }}
            </div>

            <div>
                <div class="temp">
                    {{ weather.current.temperature }}<span>°</span>
                </div>

                <div class="weather-name">
                    {{ weather.current.weather }}
                </div>
            </div>

        </div>


        <div class="metrics">

            <div class="metric">
                <div class="metric-label">湿度</div>
                <div class="metric-value">
                    {{ weather.current.humidity }}%
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">降水量</div>
                <div class="metric-value">
                    {{ weather.current.precipitation }} mm
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">降水確率</div>
                <div class="metric-value">
                    ☔ {{ weather.current.rain_probability }}%
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">風</div>
                <div class="metric-value">
                    {{ weather.current.wind_direction }}
                    {{ weather.current.wind }} m/s
                </div>
            </div>

        </div>

    </div>


    <!-- 気圧 -->
    <div class="panel pressure-main">

        <div class="pressure-label">
            自宅の気圧
        </div>

        <div class="pressure-value">
            {{ weather.current.pressure }}
            <small style="font-size:20px;">hPa</small>
        </div>

        <div class="pressure-sea">
            海面更正 {{ weather.current.sea_pressure }} hPa
        </div>

        <div class="pressure-status">
            <div class="pressure-arrow">
                {{ weather.pressure_arrow }}
            </div>

            {% if weather.pressure_arrow == "↓↓" %}
                気圧が大きく下降しています
            {% elif weather.pressure_arrow == "↓" %}
                気圧が下降しています
            {% elif weather.pressure_arrow == "↑↑" %}
                気圧が大きく上昇しています
            {% elif weather.pressure_arrow == "↑" %}
                気圧が上昇しています
            {% else %}
                気圧は安定しています
            {% endif %}

        </div>

    </div>

</div>


<!-- 気象状況 -->
<div class="section">

    <div class="section-title">
        現在の気象状況
    </div>

    <div class="alerts">

        {% for alert in weather.messages %}

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


<!-- 24時間 -->
<div class="section">

    <div class="section-title">
        これから24時間
    </div>

    <div class="forecast">

        {% for item in weather.forecast %}

        <div class="hour">

            <div class="hour-time">
                {{ item.time_jst }}
            </div>

            <div class="hour-temp">
                {{ item.temperature }}°
            </div>

            <div class="hour-weather">
                {{ item.icon }}
                {{ item.weather_name }}
            </div>

            <div class="hour-rain">

                {% if item["rain_probability"] is not none %}
                    ☔ {{ item["rain_probability"] }}%
                {% else %}
                    ☔ —
                {% endif %}

                {% if item["precipitation"] is not none %}
                    {{ item["precipitation"] }} mm
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


<footer>
    奈良本・自宅地点の予報 ｜ 標高 約500m ｜ MET Norway
</footer>

</div>

</body>
</html>
"""


# =========================================================
# Flask
# =========================================================
@app.route("/")
def index():

    try:
        weather = get_weather()

        return render_template_string(
            HTML,
            weather=weather
        )

    except Exception as e:

        return f"""
        <html>
        <body style="
            background:#151314;
            color:#eee;
            font-family:sans-serif;
            padding:40px;
        ">
        <h2>気象データを取得できませんでした</h2>
        <p>{str(e)}</p>
        </body>
        </html>
        """, 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )