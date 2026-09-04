from flask import Flask
import requests
import time
from datetime import datetime, timedelta

app = Flask(__name__)

# =========================================================
# 設定
# =========================================================

# エンジェルフォレスト周辺・約500m
HIGHLAND_LAT = 34.8346
HIGHLAND_LON = 139.0481
HIGHLAND_ELEVATION = 500

# 気象庁アメダス 稲取
INATORI_ID = "50506"

CACHE_SECONDS = 600

cache = {
    "time": 0,
    "data": None
}


# =========================================================
# 天気表示
# =========================================================

def weather_text(code):
    code = int(code)

    if code == 0:
        return "☀️ 快晴"
    if code == 1:
        return "🌤️ 晴れ"
    if code == 2:
        return "⛅ 晴れ時々くもり"
    if code == 3:
        return "☁️ くもり"
    if code in [45, 48]:
        return "🌫️ 霧"
    if 51 <= code <= 67:
        return "☔ 雨"
    if 71 <= code <= 77:
        return "❄️ 雪"
    if 80 <= code <= 82:
        return "☔ 雨"
    if code in [85, 86]:
        return "❄️ 雪"
    if code in [95, 96, 99]:
        return "⚡ 雷雨"

    return "☁️ くもり"


def pressure_status(pressure):
    if pressure <= 1005:
        return "danger", "気圧低下"
    elif pressure <= 1010:
        return "warning", "やや低め"
    else:
        return "normal", "安定"


# =========================================================
# 気象庁アメダス実測
# =========================================================

def get_jma_observation():

    now = datetime.now()

    # 10分刻み
    minute = (now.minute // 10) * 10

    # 最新データがまだ更新されていない可能性があるので
    # 最大30分前まで探す
    for back in range(0, 40, 10):

        target = now - timedelta(minutes=back)

        target_minute = (target.minute // 10) * 10

        timestamp = target.strftime("%Y%m%d") + f"{target.hour:02d}{target_minute:02d}"

        url = (
            "https://www.jma.go.jp/bosai/amedas/data/map/"
            + timestamp
            + ".json"
        )

        try:

            response = requests.get(
                url,
                timeout=8,
                headers={
                    "User-Agent": "IzuAtagawaWeather/1.0"
                }
            )

            if response.status_code != 200:
                continue

            data = response.json()

            if INATORI_ID not in data:
                continue

            point = data[INATORI_ID]

            return {
                "time": timestamp,
                "temperature": point.get("temp"),
                "humidity": point.get("humidity"),
                "precipitation": point.get("precipitation10m"),
                "pressure": point.get("pressure"),
            }

        except Exception:
            continue

    return None


# =========================================================
# Open-Meteo JMAモデル
# =========================================================

def get_jma_model():

    url = "https://api.open-meteo.com/v1/jma"

    params = {
        "latitude": HIGHLAND_LAT,
        "longitude": HIGHLAND_LON,

        "hourly": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "pressure_msl,"
            "surface_pressure,"
            "precipitation,"
            "weather_code"
        ),

        "timezone": "Asia/Tokyo",
        "forecast_days": 2,

        # 約500m地点
        "elevation": HIGHLAND_ELEVATION
    }

    response = requests.get(
        url,
        params=params,
        timeout=12,
        headers={
            "User-Agent": "IzuAtagawaWeather/1.0"
        }
    )

    if response.status_code == 429:
        raise Exception(
            "Open-Meteoが一時的にアクセスを制限しています。"
        )

    response.raise_for_status()

    return response.json()


# =========================================================
# データ取得
# =========================================================

def get_weather():

    now = time.time()

    # キャッシュ
    if (
        cache["data"] is not None
        and now - cache["time"] < CACHE_SECONDS
    ):
        return cache["data"]

    jma_observation = get_jma_observation()

    jma_model = get_jma_model()

    data = {
        "observation": jma_observation,
        "model": jma_model
    }

    cache["data"] = data
    cache["time"] = time.time()

    return data


# =========================================================
# HTML
# =========================================================

@app.route("/")
def index():

    try:

        data = get_weather()

        observation = data["observation"]
        model = data["model"]

        hourly = model["hourly"]

        times = hourly["time"]
        temps = hourly["temperature_2m"]
        humidity = hourly["relative_humidity_2m"]
        pressure_msl = hourly["pressure_msl"]
        surface_pressure = hourly["surface_pressure"]
        rain = hourly["precipitation"]
        weather_codes = hourly["weather_code"]

        # 現在
        current_temp = observation["temperature"]

        if current_temp is None:
            current_temp = temps[0]

        current_humidity = observation["humidity"]

        if current_humidity is None:
            current_humidity = humidity[0]

        current_rain = observation["precipitation"]

        if current_rain is None:
            current_rain = 0

        current_pressure = observation["pressure"]

        # 気象庁実測に気圧がない場合は
        # JMAモデルの地上気圧を使用
        if current_pressure is None:
            current_pressure = surface_pressure[0]

        current_msl = pressure_msl[0]

        # 高地モデル温度
        highland_temp = temps[0]

        # 海側実測との差
        temperature_difference = (
            highland_temp - current_temp
        )

        status_class, status_text = pressure_status(
            current_msl
        )

        # -------------------------------------------------
        # 24時間カード
        # -------------------------------------------------

        cards = ""

        for i in range(min(24, len(times))):

            temp = temps[i]
            hum = humidity[i]
            pmsl = pressure_msl[i]
            psurface = surface_pressure[i]
            precipitation = rain[i]
            code = weather_codes[i]

            card_status, card_text = pressure_status(pmsl)

            cards += f"""
            <div class="hour-card">

                <div class="hour-time">
                    {times[i][5:10].replace("-", "/")}
                    {times[i][11:16]}
                </div>

                <div class="hour-status {card_status}">
                    {card_text}
                </div>

                <div class="hour-weather">
                    {weather_text(code)}
                </div>

                <div class="hour-temp">
                    {temp:.1f}°
                </div>

                <div class="hour-info">
                    湿度 {hum:.0f}%
                </div>

                <div class="hour-info">
                    降水 {precipitation:.1f} mm
                </div>

                <div class="hour-pressure">

                    <span>気圧</span>

                    <strong>
                        {psurface:.1f}
                    </strong>

                    <strong>
                        {pmsl:.1f}
                    </strong>

                    <small>hPa</small>

                </div>

            </div>
            """

        current_code = weather_codes[0]

        html = f"""
<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>伊豆熱川 天気・気圧</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #F3F1F0;
    color: #40393B;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Helvetica Neue",
        "Yu Gothic",
        "Meiryo",
        sans-serif;
}}

.container {{
    width: min(96%, 1550px);
    margin: auto;
    padding: 30px 0 50px;
}}


/* =====================================
   現在
===================================== */

.current {{
    background: #A85D72;
    color: white;
    border-radius: 28px;
    padding: 34px;
    box-shadow:
        0 14px 35px rgba(70,45,52,0.16);
}}

.current-top {{
    display: flex;
    justify-content: space-between;
    gap: 30px;
}}

.location {{
    font-size: 17px;
    letter-spacing: .08em;
    opacity: .9;
}}

.weather-main {{
    display: flex;
    align-items: center;
    gap: 22px;
    margin-top: 20px;
}}

.weather-icon {{
    font-size: 62px;
}}

.temperature {{
    font-size: 64px;
    font-weight: 700;
    line-height: 1;
}}

.weather-name {{
    margin-top: 10px;
    font-size: 18px;
}}

.current-pressure {{
    min-width: 220px;
    background: rgba(255,255,255,.14);
    border-radius: 20px;
    padding: 22px;
}}

.pressure-label {{
    font-size: 14px;
    opacity: .8;
    margin-bottom: 8px;
}}

.pressure-number {{
    font-size: 29px;
    font-weight: 700;
    line-height: 1.3;
}}

.pressure-unit {{
    font-size: 13px;
    opacity: .75;
}}

.current-info {{
    display: grid;
    grid-template-columns: repeat(3,1fr);
    gap: 14px;
    margin-top: 30px;
}}

.info-box {{
    background: rgba(255,255,255,.12);
    border-radius: 17px;
    padding: 16px 18px;
}}

.info-label {{
    font-size: 12px;
    opacity: .75;
}}

.info-value {{
    font-size: 22px;
    font-weight: 600;
    margin-top: 5px;
}}


/* =====================================
   24時間
===================================== */

.forecast {{
    margin-top: 30px;
    background: #E7E3E2;
    border-radius: 28px;
    padding: 30px;
}}

.forecast-title {{
    font-size: 22px;
    font-weight: 700;
    color: #704252;
    margin-bottom: 22px;
}}

.hour-grid {{
    display: grid;
    grid-template-columns:
        repeat(6,minmax(0,1fr));
    gap: 12px;
}}

.hour-card {{
    background: #FAFAF9;
    border-radius: 17px;
    padding: 15px;
    min-width: 0;
    box-shadow:
        0 4px 12px rgba(60,50,50,.05);
}}

.hour-time {{
    font-size: 12px;
    color: #81777A;
}}

.hour-status {{
    display: inline-block;
    margin-top: 8px;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 10px;
}}

.normal {{
    background: #F5E8EC;
    color: #704252;
}}

.warning {{
    background: #F4E9C8;
    color: #80691C;
}}

.danger {{
    background: #F4DEDF;
    color: #983C48;
}}

.hour-weather {{
    margin-top: 13px;
    font-size: 13px;
}}

.hour-temp {{
    margin-top: 8px;
    font-size: 27px;
    font-weight: 700;
    color: #704252;
}}

.hour-info {{
    margin-top: 7px;
    font-size: 11px;
    color: #81777A;
}}

.hour-pressure {{
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid #E5DFE0;
    color: #704252;
}}

.hour-pressure span {{
    display: block;
    font-size: 10px;
    color: #81777A;
}}

.hour-pressure strong {{
    display: block;
    font-size: 14px;
}}

.hour-pressure small {{
    font-size: 9px;
    color: #81777A;
}}


/* =====================================
   タブレット
===================================== */

@media (max-width: 1000px) {{

    .hour-grid {{
        grid-template-columns:
            repeat(4,minmax(0,1fr));
    }}

}}


/* =====================================
   スマホ
===================================== */

@media (max-width: 700px) {{

    .container {{
        width: 94%;
        padding-top: 15px;
    }}

    .current {{
        padding: 24px;
        border-radius: 22px;
    }}

    .current-top {{
        display: block;
    }}

    .weather-icon {{
        font-size: 48px;
    }}

    .temperature {{
        font-size: 48px;
    }}

    .current-pressure {{
        margin-top: 22px;
    }}

    .current-info {{
        grid-template-columns:
            repeat(2,1fr);
    }}

    .forecast {{
        padding: 20px;
        border-radius: 22px;
    }}

    .hour-grid {{
        grid-template-columns:
            repeat(2,minmax(0,1fr));
    }}

}}


/* =====================================
   小さいスマホ
===================================== */

@media (max-width: 420px) {{

    .current-info {{
        grid-template-columns: 1fr;
    }}

    .hour-grid {{
        grid-template-columns: 1fr;
    }}

}}

</style>

</head>


<body>

<div class="container">


<section class="current">

    <div class="current-top">

        <div>

            <div class="location">
                伊豆熱川
            </div>

            <div class="weather-main">

                <div class="weather-icon">
                    {weather_text(current_code).split(" ")[0]}
                </div>

                <div>

                    <div class="temperature">
                        {current_temp:.1f}℃
                    </div>

                    <div class="weather-name">
                        {weather_text(current_code)}
                    </div>

                </div>

            </div>

        </div>


        <div class="current-pressure">

            <div class="pressure-label">
                気圧
            </div>

            <div class="pressure-number">
                {current_pressure:.1f}
                <span class="pressure-unit">
                    hPa
                </span>
            </div>

            <div class="pressure-number">
                {current_msl:.1f}
                <span class="pressure-unit">
                    hPa
                </span>
            </div>

        </div>

    </div>


    <div class="current-info">

        <div class="info-box">

            <div class="info-label">
                湿度
            </div>

            <div class="info-value">
                {current_humidity:.0f}%
            </div>

        </div>


        <div class="info-box">

            <div class="info-label">
                降水量
            </div>

            <div class="info-value">
                {current_rain:.1f} mm
            </div>

        </div>


        <div class="info-box">

            <div class="info-label">
                海側との気温差
            </div>

            <div class="info-value">
                {temperature_difference:+.1f}℃
            </div>

        </div>

    </div>

</section>


<section class="forecast">

    <div class="forecast-title">
        これから24時間
    </div>

    <div class="hour-grid">

        {cards}

    </div>

</section>


</div>

</body>

</html>
"""

        return html

    except Exception as e:

        return f"""
<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>伊豆熱川 天気・気圧</title>

<style>

body {{
    margin: 0;
    background: #F3F1F0;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Yu Gothic",
        sans-serif;
}}

.error {{
    max-width: 700px;
    margin: 70px auto;
    padding: 30px;
    background: white;
    border-radius: 20px;
}}

h1 {{
    color: #A85D72;
}}

</style>

</head>

<body>

<div class="error">

<h1>データ取得エラー</h1>

<p>{str(e)}</p>

<p>
少し時間を置いて、もう一度お試しください。
</p>

</div>

</body>

</html>
"""


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )