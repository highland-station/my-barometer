from flask import Flask, render_template_string
import requests
from datetime import datetime
from functools import lru_cache

app = Flask(__name__)

# ============================================================
# 伊豆熱川・自宅付近
# 1489番地の公開地図座標を基準に設定
# ============================================================
HOME_LAT = 34.8345956
HOME_LON = 139.0481289

# Open-Meteo
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

HEADERS = {
    "User-Agent": "IzuAtagawaWeather/1.0"
}


# ============================================================
# 天気コード → 日本語
# ============================================================
def weather_text(code):
    codes = {
        0: "快晴",
        1: "晴れ",
        2: "晴れ時々くもり",
        3: "くもり",
        45: "霧",
        48: "霧",
        51: "弱い霧雨",
        53: "霧雨",
        55: "強い霧雨",
        56: "凍る霧雨",
        57: "強い凍る霧雨",
        61: "弱い雨",
        63: "雨",
        65: "強い雨",
        66: "凍る雨",
        67: "強い凍る雨",
        71: "弱い雪",
        73: "雪",
        75: "強い雪",
        77: "雪あられ",
        80: "にわか雨",
        81: "にわか雨",
        82: "強いにわか雨",
        85: "にわか雪",
        86: "強いにわか雪",
        95: "雷雨",
        96: "雷雨・ひょう",
        99: "強い雷雨・ひょう",
    }
    return codes.get(code, "—")


def weather_icon(code, is_day=True):
    if code == 0:
        return "☀"
    if code == 1:
        return "☀"
    if code == 2:
        return "◐"
    if code == 3:
        return "☁"
    if code in [45, 48]:
        return "≋"
    if code in [51, 53, 55, 56, 57]:
        return "☂"
    if code in [61, 63, 65, 66, 67, 80, 81, 82]:
        return "☂"
    if code in [71, 73, 75, 77, 85, 86]:
        return "❄"
    if code in [95, 96, 99]:
        return "⚡"

    return "☁"


# ============================================================
# Open-Meteo取得
# ============================================================
@lru_cache(maxsize=1)
def get_weather():

    params = {
        "latitude": HOME_LAT,
        "longitude": HOME_LON,

        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "rain",
            "weather_code",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
            "pressure_msl",
        ]),

        "hourly": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation_probability",
            "precipitation",
            "rain",
            "weather_code",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
            "pressure_msl",
        ]),

        "forecast_days": 2,
        "timezone": "Asia/Tokyo",

        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
    }

    response = requests.get(
        WEATHER_URL,
        params=params,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# 時刻フォーマット
# ============================================================
def hour_label(value):
    try:
        dt = datetime.fromisoformat(value)
        return f"{dt.hour}時"
    except Exception:
        return value


# ============================================================
# 風向
# ============================================================
def wind_direction(degree):

    if degree is None:
        return "—"

    directions = [
        "北", "北北東", "北東", "東北東",
        "東", "東南東", "南東", "南南東",
        "南", "南南西", "南西", "西南西",
        "西", "西北西", "北西", "北北西"
    ]

    index = int((degree + 11.25) / 22.5) % 16

    return directions[index]


# ============================================================
# メイン画面
# ============================================================
@app.route("/")
def index():

    try:
        data = get_weather()

        current = data["current"]
        hourly = data["hourly"]

        current_time = current["time"]

        # --------------------------------------------
        # 現在値
        # --------------------------------------------
        temperature = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        apparent = current.get("apparent_temperature")
        precipitation = current.get("precipitation")
        weather_code = current.get("weather_code")

        wind_speed = current.get("wind_speed_10m")
        wind_degree = current.get("wind_direction_10m")

        surface_pressure = current.get("surface_pressure")
        pressure_msl = current.get("pressure_msl")

        # --------------------------------------------
        # 24時間予報
        # --------------------------------------------
        times = hourly["time"]

        # 現在時刻に一番近いインデックス
        current_index = 0

        for i, t in enumerate(times):
            if t >= current_time:
                current_index = i
                break

        forecast = []

        for i in range(
            current_index,
            min(current_index + 24, len(times))
        ):

            code = hourly["weather_code"][i]

            forecast.append({
                "time": hour_label(times[i]),
                "temperature": hourly["temperature_2m"][i],
                "humidity": hourly["relative_humidity_2m"][i],
                "rain_probability": hourly["precipitation_probability"][i],
                "precipitation": hourly["precipitation"][i],
                "weather": weather_text(code),
                "icon": weather_icon(code),
                "wind": hourly["wind_speed_10m"][i],
                "pressure": hourly["surface_pressure"][i],
            })

        # --------------------------------------------
        # グラフ用
        # --------------------------------------------
        chart_labels = [
            item["time"] for item in forecast
        ]

        chart_temperature = [
            item["temperature"] for item in forecast
        ]

        chart_rain = [
            item["rain_probability"] for item in forecast
        ]

        return render_template_string(
            HTML,
            temperature=temperature,
            humidity=humidity,
            apparent=apparent,
            precipitation=precipitation,
            weather=weather_text(weather_code),
            icon=weather_icon(weather_code),
            wind_speed=wind_speed,
            wind_direction=wind_direction(wind_degree),
            surface_pressure=surface_pressure,
            pressure_msl=pressure_msl,
            forecast=forecast,
            chart_labels=chart_labels,
            chart_temperature=chart_temperature,
            chart_rain=chart_rain,
            current_time=current_time
        )

    except Exception as e:

        return render_template_string(
            ERROR_HTML,
            error=str(e)
        )


# ============================================================
# HTML
# ============================================================
HTML = r"""
<!DOCTYPE html>
<html lang="ja">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>伊豆熱川 Weather</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background:
        radial-gradient(
            circle at 15% 0%,
            #38262e 0%,
            #171416 42%,
            #101011 100%
        );

    color: #eee8e9;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        "Hiragino Kaku Gothic ProN",
        "Yu Gothic",
        sans-serif;

    min-height: 100vh;
}

.container {
    max-width: 1180px;
    margin: auto;
    padding: 38px 28px 60px;
}


/* ------------------------------------------------
   LOCATION
------------------------------------------------ */

.location {
    color: #cfa7b1;
    font-size: 13px;
    letter-spacing: 0.18em;
    margin-bottom: 22px;
}


/* ------------------------------------------------
   CURRENT
------------------------------------------------ */

.current {
    position: relative;

    padding: 38px;

    border-radius: 28px;

    background:
        linear-gradient(
            135deg,
            rgba(111, 58, 72, 0.45),
            rgba(29, 25, 27, 0.82)
        );

    border: 1px solid rgba(219, 160, 176, 0.18);

    box-shadow:
        0 30px 80px rgba(0,0,0,.35);

    overflow: hidden;
}

.current::after {
    content: "";

    position: absolute;

    width: 260px;
    height: 260px;

    right: -90px;
    top: -90px;

    border-radius: 50%;

    background:
        radial-gradient(
            circle,
            rgba(192, 112, 135, .28),
            transparent 70%
        );
}

.current-grid {
    display: grid;

    grid-template-columns:
        1.25fr
        1fr;

    gap: 35px;

    position: relative;
    z-index: 1;
}

.current-main {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.weather-icon {
    font-size: 54px;
    color: #d8a5b2;
    margin-bottom: 10px;
}

.temperature {
    font-size: 76px;
    line-height: 1;

    font-weight: 300;

    letter-spacing: -0.05em;
}

.temperature span {
    font-size: 27px;
    margin-left: 5px;

    color: #b9afb2;
}

.weather-name {
    margin-top: 14px;

    font-size: 20px;

    color: #e4cdd2;
}

.feels {
    margin-top: 8px;

    color: #938b8d;

    font-size: 13px;
}


/* ------------------------------------------------
   METRICS
------------------------------------------------ */

.metrics {

    display: grid;

    grid-template-columns:
        1fr
        1fr;

    gap: 12px;
}

.metric {

    padding: 20px 21px;

    border-radius: 18px;

    background: rgba(255,255,255,.045);

    border:
        1px solid
        rgba(255,255,255,.07);
}

.metric-label {

    font-size: 11px;

    color: #948c8f;

    letter-spacing: .13em;

    margin-bottom: 7px;
}

.metric-value {

    font-size: 19px;

    color: #eee6e8;
}

.pressure-box {

    grid-column: 1 / -1;

    padding: 22px;

    border-radius: 18px;

    background:
        linear-gradient(
            135deg,
            rgba(143, 76, 94, .25),
            rgba(255,255,255,.035)
        );

    border:
        1px solid
        rgba(211,151,168,.15);
}

.pressure-values {

    display: flex;

    gap: 28px;

    align-items: baseline;
}

.pressure-number {

    font-size: 29px;

    font-weight: 300;
}

.pressure-number span {

    font-size: 12px;

    color: #a69b9e;
}


/* ------------------------------------------------
   SECTION
------------------------------------------------ */

.section {

    margin-top: 28px;

    padding: 27px;

    border-radius: 24px;

    background:
        rgba(24,21,23,.78);

    border:
        1px solid
        rgba(255,255,255,.065);
}

.section-title {

    display: flex;

    align-items: center;

    justify-content: space-between;

    margin-bottom: 22px;
}

.section-title h2 {

    margin: 0;

    font-size: 16px;

    font-weight: 400;

    letter-spacing: .12em;
}

.section-title span {

    font-size: 11px;

    color: #80777a;
}


/* ------------------------------------------------
   FORECAST
------------------------------------------------ */

.forecast {

    display: flex;

    gap: 9px;

    overflow-x: auto;

    padding-bottom: 7px;

    scrollbar-width: thin;
}

.forecast-card {

    min-width: 92px;

    padding: 17px 10px;

    text-align: center;

    border-radius: 17px;

    background:
        linear-gradient(
            180deg,
            rgba(255,255,255,.055),
            rgba(255,255,255,.025)
        );

    border:
        1px solid
        rgba(255,255,255,.055);
}

.forecast-card:first-child {

    background:
        linear-gradient(
            180deg,
            rgba(139,76,94,.38),
            rgba(255,255,255,.035)
        );

    border-color:
        rgba(211,151,168,.25);
}

.forecast-time {

    color: #aaa1a4;

    font-size: 11px;

    margin-bottom: 13px;
}

.forecast-icon {

    font-size: 25px;

    height: 34px;

    color: #d3a2af;
}

.forecast-temp {

    font-size: 20px;

    margin-top: 8px;
}

.forecast-rain {

    margin-top: 8px;

    font-size: 11px;

    color: #b98493;
}

.forecast-mm {

    margin-top: 4px;

    font-size: 10px;

    color: #746d70;
}


/* ------------------------------------------------
   CHART
------------------------------------------------ */

.chart-wrap {

    height: 270px;

    position: relative;
}


/* ------------------------------------------------
   FOOTER
------------------------------------------------ */

.footer {

    text-align: center;

    margin-top: 26px;

    color: #615b5d;

    font-size: 10px;

    letter-spacing: .08em;
}


/* ------------------------------------------------
   MOBILE
------------------------------------------------ */

@media (max-width: 760px) {

    .container {
        padding: 20px 14px 40px;
    }

    .current {
        padding: 25px 20px;
        border-radius: 23px;
    }

    .current-grid {
        grid-template-columns: 1fr;
        gap: 25px;
    }

    .temperature {
        font-size: 65px;
    }

    .metrics {
        grid-template-columns: 1fr 1fr;
    }

    .section {
        padding: 20px 15px;
    }

    .chart-wrap {
        height: 230px;
    }

}

</style>

</head>


<body>

<div class="container">


    <div class="location">
        IZU · ATAGAWA
    </div>


    <!-- ================= CURRENT ================= -->

    <section class="current">

        <div class="current-grid">


            <div class="current-main">

                <div class="weather-icon">
                    {{ icon }}
                </div>

                <div class="temperature">
                    {{ "%.1f"|format(temperature) }}
                    <span>°C</span>
                </div>

                <div class="weather-name">
                    {{ weather }}
                </div>

                <div class="feels">
                    体感 {{ "%.1f"|format(apparent) }}°C
                </div>

            </div>


            <div class="metrics">


                <div class="metric">

                    <div class="metric-label">
                        湿度
                    </div>

                    <div class="metric-value">
                        {{ humidity }}%
                    </div>

                </div>


                <div class="metric">

                    <div class="metric-label">
                        降水量
                    </div>

                    <div class="metric-value">
                        {{ "%.1f"|format(precipitation) }} mm
                    </div>

                </div>


                <div class="metric">

                    <div class="metric-label">
                        風
                    </div>

                    <div class="metric-value">
                        {{ "%.1f"|format(wind_speed) }} m/s
                    </div>

                </div>


                <div class="metric">

                    <div class="metric-label">
                        風向
                    </div>

                    <div class="metric-value">
                        {{ wind_direction }}
                    </div>

                </div>


                <div class="pressure-box">

                    <div class="metric-label">
                        気圧
                    </div>

                    <div class="pressure-values">

                        <div class="pressure-number">
                            {{ "%.1f"|format(surface_pressure) }}
                            <span>hPa</span>
                        </div>

                        <div class="pressure-number">
                            {{ "%.1f"|format(pressure_msl) }}
                            <span>hPa</span>
                        </div>

                    </div>

                </div>


            </div>

        </div>

    </section>


    <!-- ================= 24H ================= -->

    <section class="section">

        <div class="section-title">

            <h2>24時間予報</h2>

            <span>自宅地点</span>

        </div>


        <div class="forecast">

            {% for item in forecast %}

            <div class="forecast-card">

                <div class="forecast-time">
                    {{ item.time }}
                </div>

                <div class="forecast-icon">
                    {{ item.icon }}
                </div>

                <div class="forecast-temp">
                    {{ "%.0f"|format(item.temperature) }}°
                </div>

                <div class="forecast-rain">
                    {{ item.rain_probability }}%
                </div>

                <div class="forecast-mm">
                    {{ "%.1f"|format(item.precipitation) }} mm
                </div>

            </div>

            {% endfor %}

        </div>

    </section>


    <!-- ================= CHART ================= -->

    <section class="section">

        <div class="section-title">

            <h2>気温の推移</h2>

            <span>これから24時間</span>

        </div>

        <div class="chart-wrap">

            <canvas id="temperatureChart"></canvas>

        </div>

    </section>


    <div class="footer">
        IZU ATAGAWA · WEATHER
    </div>


</div>


<script>

const labels =
    {{ chart_labels | tojson }};

const temperatures =
    {{ chart_temperature | tojson }};

const rain =
    {{ chart_rain | tojson }};


const ctx =
    document
        .getElementById("temperatureChart")
        .getContext("2d");


new Chart(ctx, {

    type: "line",

    data: {

        labels: labels,

        datasets: [{

            data: temperatures,

            borderColor: "#c990a0",

            backgroundColor:
                "rgba(201,144,160,.10)",

            borderWidth: 2,

            pointRadius: 2,

            pointHoverRadius: 5,

            tension: .38,

            fill: true

        }]

    },

    options: {

        responsive: true,

        maintainAspectRatio: false,

        plugins: {

            legend: {
                display: false
            },

            tooltip: {

                callbacks: {

                    label: function(context) {

                        return (
                            context.parsed.y.toFixed(1)
                            + " °C"
                        );

                    }

                }

            }

        },

        scales: {

            x: {

                grid: {
                    display: false
                },

                ticks: {

                    color: "#777073",

                    maxTicksLimit: 8,

                    font: {
                        size: 10
                    }

                }

            },

            y: {

                grid: {

                    color:
                        "rgba(255,255,255,.055)"

                },

                ticks: {

                    color: "#777073",

                    font: {
                        size: 10
                    },

                    callback: function(value) {

                        return value + "°";

                    }

                }

            }

        }

    }

});

</script>


</body>

</html>
"""


# ============================================================
# エラー画面
# ============================================================
ERROR_HTML = r"""
<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<title>Weather Error</title>

<style>

body {
    background: #151315;
    color: #eee;
    font-family: sans-serif;
    padding: 40px;
}

.box {
    max-width: 800px;
    margin: auto;
    padding: 30px;
    background: #241e21;
    border-radius: 20px;
}

h2 {
    color: #d49aaa;
}

pre {
    white-space: pre-wrap;
    color: #c9b9bd;
}

</style>

</head>

<body>

<div class="box">

<h2>気象データを取得できませんでした</h2>

<p>
自宅地点の気象データ取得時にエラーが発生しました。
</p>

<pre>{{ error }}</pre>

</div>

</body>

</html>
"""


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )