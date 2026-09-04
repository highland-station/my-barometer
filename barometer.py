from flask import Flask, render_template_string
import requests
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# =========================================================
# 自宅地点
# =========================================================
HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

# MET Norway API
API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"

# MET NorwayはUser-Agentを必須としている
HEADERS = {
    "User-Agent": "IzuHomeWeather/1.0 https://github.com/highland-station/my-barometer"
}

JST = timezone(timedelta(hours=9))


# =========================================================
# 天気表示
# =========================================================
WEATHER = {
    "clearsky": "快晴",
    "fair": "晴れ",
    "partlycloudy": "晴れ時々くもり",
    "cloudy": "くもり",
    "lightrain": "小雨",
    "rain": "雨",
    "heavyrain": "強い雨",
    "lightsleet": "みぞれ",
    "sleet": "みぞれ",
    "heavysleet": "強いみぞれ",
    "lightsnow": "小雪",
    "snow": "雪",
    "heavysnow": "大雪",
    "rainshowers": "にわか雨",
    "heavyrainshowers": "強いにわか雨",
    "lightsleetshowers": "にわかみぞれ",
    "sleetshowers": "にわかみぞれ",
    "heavysleetshowers": "強いにわかみぞれ",
    "snowshowers": "にわか雪",
    "heavysnowshowers": "強いにわか雪",
    "fog": "霧",
    "lightsleetshowersandthunder": "雷雨",
    "rainshowersandthunder": "雷雨",
    "heavyrainshowersandthunder": "激しい雷雨",
    "rainandthunder": "雷雨",
    "heavyrainandthunder": "激しい雷雨",
    "snowandthunder": "雷雪",
    "sleetandthunder": "雷雨",
}


def weather_name(symbol):
    if not symbol:
        return "—"

    # day / night / polarday を取り除く
    base = symbol.split("_")[0]
    return WEATHER.get(base, "—")


def wind_direction(degrees):
    if degrees is None:
        return "—"

    directions = [
        "北", "北北東", "北東", "東北東",
        "東", "東南東", "南東", "南南東",
        "南", "南南西", "南西", "西南西",
        "西", "西北西", "北西", "北北西"
    ]

    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]


def get_value(data, key, default=None):
    try:
        value = data.get(key)
        if value is None:
            return default
        return value
    except Exception:
        return default


# =========================================================
# MET Norwayから取得
# =========================================================
def get_weather():

    params = {
        "lat": round(HOME_LAT, 4),
        "lon": round(HOME_LON, 4),
        "altitude": HOME_ALTITUDE,
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# データ整形
# =========================================================
def build_weather():

    data = get_weather()

    timeseries = data["properties"]["timeseries"]

    now = datetime.now(JST)

    records = []

    for item in timeseries:

        dt = datetime.fromisoformat(
            item["time"].replace("Z", "+00:00")
        ).astimezone(JST)

        instant = item["data"].get("instant", {}).get("details", {})

        next1 = item["data"].get("next_1_hours", {})
        next6 = item["data"].get("next_6_hours", {})

        details1 = next1.get("details", {})
        details6 = next6.get("details", {})

        symbol = None

        if "summary" in next1:
            symbol = next1["summary"].get("symbol_code")

        if not symbol and "summary" in next6:
            symbol = next6["summary"].get("symbol_code")

        record = {
            "time": dt,
            "temp": get_value(instant, "air_temperature"),
            "humidity": get_value(instant, "relative_humidity"),
            "pressure": get_value(
                instant,
                "air_pressure_at_sea_level"
            ),
            "surface_pressure": get_value(
                instant,
                "surface_air_pressure"
            ),
            "wind": get_value(instant, "wind_speed"),
            "wind_dir": get_value(instant, "wind_from_direction"),
            "precip": get_value(
                details1,
                "precipitation_amount",
                get_value(details6, "precipitation_amount")
            ),
            "pop": get_value(
                details1,
                "probability_of_precipitation",
                get_value(details6, "probability_of_precipitation")
            ),
            "symbol": symbol,
        }

        records.append(record)

    # 現在に一番近い時刻
    current = min(
        records,
        key=lambda x: abs((x["time"] - now).total_seconds())
    )

    # 現在から24時間
    future = [
        x for x in records
        if x["time"] >= now - timedelta(hours=1)
    ]

    future = future[:25]

    return current, future


# =========================================================
# HTML
# =========================================================
HTML = r"""
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>奈良本の空</title>

<style>

@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500&family=Playfair+Display:wght@400;500&display=swap');

:root {
    --bg: #171517;
    --panel: #211e21;
    --panel2: #252124;
    --text: #eee8e8;
    --muted: #a89ea2;
    --rose: #c59aa6;
    --rose2: #8f6875;
    --line: rgba(197,154,166,.20);
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background:
        radial-gradient(
            circle at 75% 5%,
            rgba(151,91,111,.15),
            transparent 32%
        ),
        linear-gradient(
            135deg,
            #151315 0%,
            #1a1719 50%,
            #121113 100%
        );
    color: var(--text);
    font-family:
        "Noto Sans JP",
        sans-serif;
    font-weight: 300;
    min-height: 100vh;
}

.wrapper {
    max-width: 1220px;
    margin: 0 auto;
    padding: 44px 34px 60px;
}


/* -----------------------------------------
   Header
----------------------------------------- */

.header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-bottom: 1px solid var(--line);
    padding-bottom: 20px;
    margin-bottom: 30px;
}

.location {
    font-size: 13px;
    letter-spacing: .18em;
    color: var(--muted);
}

.location strong {
    display: block;
    color: var(--text);
    font-size: 20px;
    font-weight: 400;
    letter-spacing: .08em;
    margin-top: 6px;
}

.updated {
    font-size: 11px;
    color: var(--muted);
    letter-spacing: .08em;
}


/* -----------------------------------------
   Main atmosphere
----------------------------------------- */

.hero {
    display: grid;
    grid-template-columns: 1.3fr .7fr;
    gap: 1px;
    background: var(--line);
    border: 1px solid var(--line);
}

.hero-main {
    background:
        radial-gradient(
            circle at 70% 40%,
            rgba(197,154,166,.11),
            transparent 38%
        ),
        var(--panel);
    padding: 48px;
    min-height: 300px;
}

.hero-side {
    background: var(--panel);
    padding: 42px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.current-label {
    color: var(--muted);
    font-size: 12px;
    letter-spacing: .18em;
    margin-bottom: 18px;
}

.temperature {
    font-family: "Playfair Display", serif;
    font-size: clamp(76px, 10vw, 132px);
    line-height: .9;
    letter-spacing: -.04em;
    font-weight: 400;
}

.temperature span {
    font-family: "Noto Sans JP", sans-serif;
    font-size: 24px;
    color: var(--muted);
    margin-left: 7px;
}

.weather {
    font-size: 22px;
    margin-top: 20px;
    letter-spacing: .08em;
}

.feels {
    color: var(--muted);
    font-size: 12px;
    margin-top: 10px;
}

.metric-list {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px 32px;
}

.metric {
    border-bottom: 1px solid var(--line);
    padding-bottom: 15px;
}

.metric-label {
    color: var(--muted);
    font-size: 11px;
    letter-spacing: .12em;
    margin-bottom: 7px;
}

.metric-value {
    font-family: "Playfair Display", serif;
    font-size: 28px;
}

.metric-unit {
    font-family: "Noto Sans JP", sans-serif;
    color: var(--muted);
    font-size: 11px;
    margin-left: 3px;
}


/* -----------------------------------------
   Pressure
----------------------------------------- */

.pressure-section {
    margin-top: 1px;
    border: 1px solid var(--line);
    background: var(--panel);
    padding: 30px 42px;
}

.pressure-title {
    font-size: 11px;
    color: var(--muted);
    letter-spacing: .18em;
    margin-bottom: 18px;
}

.pressures {
    display: flex;
    align-items: baseline;
    gap: 34px;
}

.pressure-main {
    font-family: "Playfair Display", serif;
    font-size: 42px;
}

.pressure-secondary {
    font-family: "Playfair Display", serif;
    font-size: 27px;
    color: var(--rose);
}


/* -----------------------------------------
   24 hour
----------------------------------------- */

.section {
    margin-top: 36px;
}

.section-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid var(--line);
    padding-bottom: 14px;
    margin-bottom: 1px;
}

.section-title {
    font-family: "Playfair Display", serif;
    font-size: 25px;
}

.section-sub {
    color: var(--muted);
    font-size: 11px;
}

.timeline-wrap {
    border: 1px solid var(--line);
    border-top: none;
    overflow-x: auto;
    background: var(--panel);
}

.timeline {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 108px;
    min-width: max-content;
}

.hour {
    padding: 20px 14px 23px;
    border-right: 1px solid var(--line);
    text-align: center;
}

.hour.now {
    background: rgba(197,154,166,.08);
}

.hour-time {
    color: var(--muted);
    font-size: 11px;
    margin-bottom: 15px;
}

.hour-temp {
    font-family: "Playfair Display", serif;
    font-size: 25px;
}

.hour-weather {
    height: 37px;
    margin-top: 10px;
    font-size: 12px;
    color: var(--rose);
    display: flex;
    align-items: center;
    justify-content: center;
}

.hour-rain {
    font-size: 11px;
    color: var(--muted);
    margin-top: 9px;
}

.hour-wind {
    font-size: 10px;
    color: var(--muted);
    margin-top: 13px;
}


/* -----------------------------------------
   Graph
----------------------------------------- */

.graph {
    border: 1px solid var(--line);
    background: var(--panel);
    padding: 25px;
}

canvas {
    width: 100%;
    height: 250px;
}


/* -----------------------------------------
   Footer
----------------------------------------- */

.footer {
    margin-top: 35px;
    padding-top: 18px;
    border-top: 1px solid var(--line);
    color: #746c70;
    font-size: 10px;
    line-height: 1.8;
}


/* -----------------------------------------
   Mobile
----------------------------------------- */

@media (max-width: 760px) {

    .wrapper {
        padding: 25px 16px 40px;
    }

    .header {
        align-items: flex-start;
    }

    .hero {
        grid-template-columns: 1fr;
    }

    .hero-main {
        padding: 35px 27px;
    }

    .hero-side {
        padding: 30px 27px;
    }

    .pressure-section {
        padding: 25px 27px;
    }

    .pressures {
        gap: 20px;
    }

    .pressure-main {
        font-size: 34px;
    }

    .pressure-secondary {
        font-size: 23px;
    }

    .temperature {
        font-size: 88px;
    }
}

</style>
</head>


<body>

<div class="wrapper">

    <header class="header">

        <div class="location">
            IZU / SHIZUOKA
            <strong>奈良本の空</strong>
        </div>

        <div class="updated">
            {{ updated }}
        </div>

    </header>


    <!-- 現在 -->
    <section class="hero">

        <div class="hero-main">

            <div class="current-label">
                自宅地点の予報
            </div>

            <div class="temperature">
                {{ current_temp }}
                <span>℃</span>
            </div>

            <div class="weather">
                {{ current_weather }}
            </div>

            <div class="feels">
                気温は標高 {{ altitude }}m を考慮
            </div>

        </div>


        <div class="hero-side">

            <div class="metric-list">

                <div class="metric">
                    <div class="metric-label">湿度</div>
                    <div class="metric-value">
                        {{ humidity }}
                        <span class="metric-unit">%</span>
                    </div>
                </div>

                <div class="metric">
                    <div class="metric-label">降水量</div>
                    <div class="metric-value">
                        {{ precip }}
                        <span class="metric-unit">mm</span>
                    </div>
                </div>

                <div class="metric">
                    <div class="metric-label">降水確率</div>
                    <div class="metric-value">
                        {{ pop }}
                        <span class="metric-unit">%</span>
                    </div>
                </div>

                <div class="metric">
                    <div class="metric-label">風</div>
                    <div class="metric-value">
                        {{ wind }}
                        <span class="metric-unit">m/s</span>
                    </div>
                </div>

                <div class="metric">
                    <div class="metric-label">風向</div>
                    <div class="metric-value">
                        {{ wind_dir }}
                    </div>
                </div>

                <div class="metric">
                    <div class="metric-label">海面更正気圧</div>
                    <div class="metric-value">
                        {{ pressure }}
                        <span class="metric-unit">hPa</span>
                    </div>
                </div>

            </div>

        </div>

    </section>


    <!-- 気圧 -->
    <section class="pressure-section">

        <div class="pressure-title">
            気圧
        </div>

        <div class="pressures">

            <div class="pressure-main">
                {{ surface_pressure }}
                <span class="metric-unit">hPa</span>
            </div>

            <div class="pressure-secondary">
                {{ pressure }}
                <span class="metric-unit">hPa</span>
            </div>

        </div>

    </section>


    <!-- 24時間 -->
    <section class="section">

        <div class="section-head">

            <div class="section-title">
                これから24時間
            </div>

            <div class="section-sub">
                1時間ごとの予報
            </div>

        </div>


        <div class="timeline-wrap">

            <div class="timeline">

                {% for item in forecast %}

                <div class="hour {% if loop.first %}now{% endif %}">

                    <div class="hour-time">
                        {{ item.time }}
                    </div>

                    <div class="hour-temp">
                        {{ item.temp }}°
                    </div>

                    <div class="hour-weather">
                        {{ item.weather }}
                    </div>

                    <div class="hour-rain">
                        {% if item.pop is not none %}
                            雨 {{ item.pop }}%
                        {% else %}
                            —
                        {% endif %}
                    </div>

                    <div class="hour-rain">
                        {% if item.precip is not none %}
                            {{ item.precip }} mm
                        {% else %}
                            —
                        {% endif %}
                    </div>

                    <div class="hour-wind">
                        {{ item.wind_dir }} {{ item.wind }}m/s
                    </div>

                </div>

                {% endfor %}

            </div>

        </div>

    </section>


    <!-- グラフ -->
    <section class="section">

        <div class="section-head">

            <div class="section-title">
                気温の推移
            </div>

            <div class="section-sub">
                自宅地点
            </div>

        </div>

        <div class="graph">
            <canvas id="temperatureChart"></canvas>
        </div>

    </section>


    <footer class="footer">

        予報地点：静岡県東伊豆町 奈良本付近<br>
        標高：{{ altitude }}m（設定値）<br>
        気象予報データ：MET Norway Locationforecast

    </footer>

</div>


<script>

const forecast = {{ chart_data | safe }};

const canvas = document.getElementById("temperatureChart");
const ctx = canvas.getContext("2d");

function drawChart() {

    const ratio = window.devicePixelRatio || 1;

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    canvas.width = width * ratio;
    canvas.height = height * ratio;

    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    const padding = {
        left: 10,
        right: 10,
        top: 20,
        bottom: 35
    };

    const w = width - padding.left - padding.right;
    const h = height - padding.top - padding.bottom;

    const temps = forecast.map(x => x.temp);

    const minTemp = Math.floor(Math.min(...temps) - 1);
    const maxTemp = Math.ceil(Math.max(...temps) + 1);

    const range = maxTemp - minTemp;

    ctx.clearRect(0, 0, width, height);

    /* 横線 */

    ctx.strokeStyle = "rgba(197,154,166,.12)";
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {

        const y =
            padding.top +
            h * (i / 4);

        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        const value =
            maxTemp -
            range * (i / 4);

        ctx.fillStyle = "#8d8388";
        ctx.font = "10px sans-serif";

        ctx.fillText(
            value.toFixed(0) + "°",
            padding.left,
            y - 5
        );
    }


    /* 折れ線 */

    ctx.beginPath();

    forecast.forEach((item, index) => {

        const x =
            padding.left +
            (index / (forecast.length - 1)) * w;

        const y =
            padding.top +
            (1 - (item.temp - minTemp) / range) * h;

        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });

    ctx.strokeStyle = "#c59aa6";
    ctx.lineWidth = 2;
    ctx.stroke();


    /* 点 */

    forecast.forEach((item, index) => {

        const x =
            padding.left +
            (index / (forecast.length - 1)) * w;

        const y =
            padding.top +
            (1 - (item.temp - minTemp) / range) * h;

        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);

        ctx.fillStyle = "#211e21";
        ctx.fill();

        ctx.strokeStyle = "#c59aa6";
        ctx.lineWidth = 1.5;
        ctx.stroke();


        /* 3時間ごとに時刻表示 */

        if (index % 3 === 0) {

            ctx.fillStyle = "#8d8388";
            ctx.font = "10px sans-serif";

            ctx.textAlign = "center";

            ctx.fillText(
                item.time,
                x,
                height - 10
            );
        }
    });

}

drawChart();

window.addEventListener("resize", drawChart);

</script>

</body>
</html>
"""


# =========================================================
# Route
# =========================================================
@app.route("/")
def index():

    try:

        current, future = build_weather()

        def fmt(value, digits=1):
            if value is None:
                return "—"

            return f"{value:.{digits}f}"

        forecast = []

        for item in future:

            forecast.append({
                "time": item["time"].strftime("%H:%M"),
                "temp": fmt(item["temp"], 1),
                "weather": weather_name(item["symbol"]),
                "pop": (
                    round(item["pop"])
                    if item["pop"] is not None
                    else None
                ),
                "precip": fmt(item["precip"], 1)
                    if item["precip"] is not None
                    else None,
                "wind": fmt(item["wind"], 1),
                "wind_dir": wind_direction(item["wind_dir"]),
            })


        chart_data = []

        for item in future:

            chart_data.append({
                "time": item["time"].strftime("%H:%M"),
                "temp": round(
                    item["temp"], 1
                ) if item["temp"] is not None else 0
            })


        return render_template_string(
            HTML,

            current_temp=fmt(
                current["temp"], 1
            ),

            current_weather=weather_name(
                current["symbol"]
            ),

            humidity=(
                round(current["humidity"])
                if current["humidity"] is not None
                else "—"
            ),

            precip=fmt(
                current["precip"], 1
            ),

            pop=(
                round(current["pop"])
                if current["pop"] is not None
                else "—"
            ),

            wind=fmt(
                current["wind"], 1
            ),

            wind_dir=wind_direction(
                current["wind_dir"]
            ),

            pressure=fmt(
                current["pressure"], 1
            ),

            surface_pressure=fmt(
                current["surface_pressure"], 1
            ),

            altitude=HOME_ALTITUDE,

            updated=datetime.now(JST).strftime(
                "%Y.%m.%d  %H:%M"
            ),

            forecast=forecast,

            chart_data=chart_data,
        )


    except Exception as e:

        return f"""
        <html>
        <body style="
            background:#171517;
            color:#eee;
            font-family:sans-serif;
            padding:40px;
        ">
        <h2>気象データを取得できませんでした</h2>
        <p>{str(e)}</p>
        </body>
        </html>
        """, 500


# =========================================================
# 起動
# =========================================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )