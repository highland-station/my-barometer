from flask import Flask
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# =========================================================
# 設定
# =========================================================

# 気象庁アメダス 稲取
INATORI_ID = "50506"

# キャッシュ
CACHE_SECONDS = 600

cache = {
    "time": 0,
    "data": None
}


# =========================================================
# 天気コード
# =========================================================

def weather_text_from_jma(code):

    if code is None:
        return "☁️ くもり"

    code = int(code)

    if code == 0:
        return "☀️ 快晴"
    elif code == 1:
        return "🌤️ 晴れ"
    elif code == 2:
        return "⛅ 晴れ"
    elif code == 3:
        return "☁️ くもり"
    elif code in [45, 48]:
        return "🌫️ 霧"
    elif 51 <= code <= 67:
        return "☔ 雨"
    elif 71 <= code <= 77:
        return "❄️ 雪"
    elif 80 <= code <= 82:
        return "☔ 雨"
    elif code in [85, 86]:
        return "❄️ 雪"
    elif code in [95, 96, 99]:
        return "⚡ 雷雨"

    return "☁️ くもり"


def pressure_status(pressure):

    if pressure is None:
        return "normal", "観測中"

    if pressure <= 1005:
        return "danger", "気圧低下"

    if pressure <= 1010:
        return "warning", "やや低め"

    return "normal", "安定"


# =========================================================
# 気象庁アメダス
# =========================================================

def get_jma_observation():

    now = datetime.now()

    # 最新の10分刻みデータを探す
    for back in range(0, 61, 10):

        target = now - timedelta(minutes=back)

        minute = (target.minute // 10) * 10

        timestamp = (
            target.strftime("%Y%m%d")
            + f"{target.hour:02d}{minute:02d}"
        )

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
# データ取得
# =========================================================

def get_weather():

    now = datetime.now().timestamp()

    # キャッシュ
    if (
        cache["data"] is not None
        and now - cache["time"] < CACHE_SECONDS
    ):
        return cache["data"]

    observation = get_jma_observation()

    if observation is None:
        raise Exception(
            "気象庁アメダスの観測データを取得できませんでした。"
        )

    result = {
        "observation": observation
    }

    cache["data"] = result
    cache["time"] = now

    return result


# =========================================================
# HTML
# =========================================================

@app.route("/")
def index():

    try:

        data = get_weather()

        obs = data["observation"]

        temperature = obs["temperature"]
        humidity = obs["humidity"]
        precipitation = obs["precipitation"]
        pressure = obs["pressure"]

        if temperature is None:
            temperature_text = "--"
        else:
            temperature_text = f"{temperature:.1f}"

        if humidity is None:
            humidity_text = "--"
        else:
            humidity_text = f"{humidity:.0f}"

        if precipitation is None:
            precipitation_text = "--"
        else:
            precipitation_text = f"{precipitation:.1f}"

        if pressure is None:
            pressure_text = "--"
            msl_pressure_text = "--"
        else:
            pressure_text = f"{pressure:.1f}"
            msl_pressure_text = f"{pressure:.1f}"

        status_class, status_text = pressure_status(
            pressure
        )

        # =================================================
        # 24時間表示
        # =================================================

        cards = ""

        current_time = datetime.now()

        for i in range(24):

            card_time = current_time + timedelta(hours=i)

            cards += f"""
            <div class="hour-card">

                <div class="hour-time">
                    {card_time.strftime("%-m/%-d %H:%M")}
                </div>

                <div class="hour-status {status_class}">
                    {status_text}
                </div>

                <div class="hour-weather">
                    気象庁観測
                </div>

                <div class="hour-temp">
                    {temperature_text}°
                </div>

                <div class="hour-info">
                    湿度 {humidity_text}%
                </div>

                <div class="hour-info">
                    降水 {precipitation_text} mm
                </div>

                <div class="hour-pressure">

                    <span>気圧</span>

                    <strong>
                        {pressure_text}
                    </strong>

                    <strong>
                        {msl_pressure_text}
                    </strong>

                    <small>
                        hPa
                    </small>

                </div>

            </div>
            """

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


/* ===============================
   現在
================================ */

.current {{
    background: #A85D72;
    color: white;
    border-radius: 28px;
    padding: 34px;
    box-shadow:
        0 14px 35px rgba(70,45,52,.16);
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

.current-top {{
    display: flex;
    justify-content: space-between;
    gap: 30px;
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
    grid-template-columns:
        repeat(3,1fr);
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


/* ===============================
   24時間
================================ */

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


/* ===============================
   タブレット
================================ */

@media (max-width: 1000px) {{

    .hour-grid {{
        grid-template-columns:
            repeat(4,minmax(0,1fr));
    }}

}}


/* ===============================
   スマホ
================================ */

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


/* ===============================
   小さいスマホ
================================ */

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
                    🌤️
                </div>

                <div>

                    <div class="temperature">
                        {temperature_text}℃
                    </div>

                    <div class="weather-name">
                        気象庁アメダス実測
                    </div>

                </div>

            </div>

        </div>


        <div class="current-pressure">

            <div class="pressure-label">
                気圧
            </div>

            <div class="pressure-number">
                {pressure_text}
                <span class="pressure-unit">
                    hPa
                </span>
            </div>

            <div class="pressure-number">
                {msl_pressure_text}
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
                {humidity_text}%
            </div>

        </div>


        <div class="info-box">

            <div class="info-label">
                降水量
            </div>

            <div class="info-value">
                {precipitation_text} mm
            </div>

        </div>


        <div class="info-box">

            <div class="info-label">
                観測地点
            </div>

            <div class="info-value">
                稲取
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

</div>

</body>

</html>
"""


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )