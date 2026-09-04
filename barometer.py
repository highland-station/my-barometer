from flask import Flask
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

# 稲取アメダス
INATORI_ID = "50506"

# キャッシュ時間（10分）
CACHE_SECONDS = 600

cache = {
    "time": 0,
    "data": None
}


def extract_value(value):
    """
    気象庁アメダスの
    [数値, 品質情報]
    形式から数値だけ取り出す
    """
    if value is None:
        return None

    if isinstance(value, list):
        if len(value) == 0:
            return None

        value = value[0]

    if isinstance(value, (int, float)):
        return float(value)

    return None


def get_jma_observation():

    # RenderはUTCなので日本時間に変換
    now = datetime.now(ZoneInfo("Asia/Tokyo"))

    # 最新データから最大2時間前まで探す
    for back in range(0, 121, 10):

        target = now - timedelta(minutes=back)

        # 気象庁の観測データは10分刻み
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
                timeout=10,
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

            temperature = extract_value(
                point.get("temp")
            )

            humidity = extract_value(
                point.get("humidity")
            )

            precipitation = extract_value(
                point.get("precipitation10m")
            )

            pressure = extract_value(
                point.get("pressure")
            )

            return {
                "time": timestamp,
                "temperature": temperature,
                "humidity": humidity,
                "precipitation": precipitation,
                "pressure": pressure
            }

        except Exception:
            continue

    return None


def get_weather():

    now = datetime.now().timestamp()

    # 10分以内ならキャッシュを使用
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


@app.route("/")
def index():

    error_message = ""

    try:

        weather = get_weather()
        obs = weather["observation"]

        temperature = obs.get("temperature")
        humidity = obs.get("humidity")
        precipitation = obs.get("precipitation")
        pressure = obs.get("pressure")

        # -------------------------
        # 表示用データ
        # -------------------------

        if temperature is not None:
            temperature_text = f"{temperature:.1f} ℃"
        else:
            temperature_text = "--.- ℃"

        if humidity is not None:
            humidity_text = f"{humidity:.0f} %"
        else:
            humidity_text = "-- %"

        if precipitation is not None:
            precipitation_text = f"{precipitation:.1f} mm"
        else:
            precipitation_text = "--.- mm"

        if pressure is not None:
            pressure_text = f"{pressure:.1f} hPa"
        else:
            pressure_text = "--.- hPa"

        # -------------------------
        # 観測時刻
        # -------------------------

        try:

            dt = datetime.strptime(
                obs["time"],
                "%Y%m%d%H%M"
            )

            dt = dt.replace(
                tzinfo=ZoneInfo("Asia/Tokyo")
            )

            time_text = dt.strftime(
                "%Y/%m/%d %H:%M"
            )

        except Exception:

            time_text = "--"

    except Exception as e:

        temperature_text = "--.- ℃"
        humidity_text = "-- %"
        precipitation_text = "--.- mm"
        pressure_text = "--.- hPa"
        time_text = "--"

        error_message = str(e)


    # -------------------------
    # HTML
    # -------------------------

    html = f"""
<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>伊豆熱川 気象観測</title>

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
        "Segoe UI",
        "Yu Gothic",
        "Hiragino Kaku Gothic ProN",
        sans-serif;
}}

.container {{
    width: 100%;
    max-width: 1100px;

    margin: 0 auto;

    padding: 24px;
}}

.location {{
    color: #704252;

    font-size: 14px;

    letter-spacing: 0.08em;

    margin-bottom: 8px;
}}

.current {{
    background: #A85D72;

    color: white;

    border-radius: 20px;

    padding: 28px;

    margin-bottom: 20px;
}}

.current-top {{
    display: flex;

    justify-content: space-between;

    align-items: center;

    gap: 20px;
}}

.current-label {{
    font-size: 14px;

    opacity: 0.85;
}}

.temperature {{
    font-size: 64px;

    font-weight: 300;

    line-height: 1.1;

    margin-top: 8px;
}}

.weather-icon {{
    font-size: 58px;
}}

.cards {{
    display: grid;

    grid-template-columns:
        repeat(4, minmax(0, 1fr));

    gap: 12px;

    margin-top: 24px;
}}

.card {{
    background: #FAFAF9;

    border-radius: 16px;

    padding: 20px;

    min-width: 0;
}}

.card-label {{
    color: #81777A;

    font-size: 13px;

    margin-bottom: 8px;
}}

.card-value {{
    font-size: 24px;

    color: #704252;

    font-weight: 500;
}}

.pressure {{
    background: #FAFAF9;

    border-radius: 18px;

    padding: 24px;

    margin-top: 20px;
}}

.pressure-title {{
    font-size: 14px;

    color: #81777A;

    margin-bottom: 12px;
}}

.pressure-value {{
    font-size: 30px;

    color: #704252;
}}

.forecast {{
    background: #E7E3E2;

    border-radius: 18px;

    padding: 24px;

    margin-top: 20px;
}}

.section-title {{
    font-size: 18px;

    color: #704252;

    margin-bottom: 18px;
}}

.forecast-grid {{
    display: grid;

    grid-template-columns:
        repeat(8, minmax(80px, 1fr));

    gap: 8px;

    overflow-x: auto;
}}

.hour {{
    background: #FAFAF9;

    border-radius: 12px;

    padding: 12px 8px;

    text-align: center;
}}

.hour-time {{
    font-size: 12px;

    color: #81777A;
}}

.hour-icon {{
    font-size: 25px;

    margin: 8px 0;
}}

.hour-temp {{
    font-size: 16px;

    color: #704252;
}}

.update {{
    text-align: right;

    color: #81777A;

    font-size: 12px;

    margin-top: 16px;
}}

.error {{
    background: #F4DEDF;

    color: #704252;

    border-radius: 14px;

    padding: 16px;

    margin-top: 20px;
}}

@media (max-width: 700px) {{

    .container {{
        padding: 14px;
    }}

    .current {{
        padding: 22px;
    }}

    .temperature {{
        font-size: 48px;
    }}

    .weather-icon {{
        font-size: 44px;
    }}

    .cards {{
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }}

    .forecast-grid {{
        grid-template-columns:
            repeat(8, 80px);

        overflow-x: auto;
    }}

}}

</style>

</head>


<body>

<div class="container">

    <div class="location">
        伊豆熱川
    </div>


    <section class="current">

        <div class="current-top">

            <div>

                <div class="current-label">
                    現在の観測
                </div>

                <div class="temperature">
                    {temperature_text}
                </div>

            </div>

            <div class="weather-icon">
                🌤️
            </div>

        </div>

    </section>


    <div class="cards">

        <div class="card">

            <div class="card-label">
                湿度
            </div>

            <div class="card-value">
                {humidity_text}
            </div>

        </div>


        <div class="card">

            <div class="card-label">
                降水量
            </div>

            <div class="card-value">
                {precipitation_text}
            </div>

        </div>


        <div class="card">

            <div class="card-label">
                観測地点
            </div>

            <div class="card-value">
                稲取
            </div>

        </div>


        <div class="card">

            <div class="card-label">
                観測時刻
            </div>

            <div class="card-value"
                 style="font-size:18px;">
                {time_text}
            </div>

        </div>

    </div>


    <section class="pressure">

        <div class="pressure-title">
            気圧
        </div>

        <div class="pressure-value">
            {pressure_text}
        </div>

    </section>


    <section class="forecast">

        <div class="section-title">
            24時間
        </div>

        <div class="forecast-grid">
"""


    # -------------------------
    # 24時間表示
    # -------------------------

    now_japan = datetime.now(
        ZoneInfo("Asia/Tokyo")
    )

    for i in range(24):

        hour = now_japan + timedelta(hours=i)

        hour_text = hour.strftime("%H:%M")

        html += f"""
            <div class="hour">

                <div class="hour-time">
                    {hour_text}
                </div>

                <div class="hour-icon">
                    🌤️
                </div>

                <div class="hour-temp">
                    {temperature_text}
                </div>

            </div>
"""


    html += """
        </div>

    </section>
"""


    if error_message:

        html += f"""
    <div class="error">

        データ取得エラー<br>

        {error_message}

    </div>
"""


    html += f"""

    <div class="update">

        気象庁アメダス 稲取<br>

        観測時刻：{time_text}

    </div>

</div>

</body>

</html>
"""


    return html


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )