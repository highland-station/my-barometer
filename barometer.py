from flask import Flask
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)

INATORI_ID = "50506"
JST = ZoneInfo("Asia/Tokyo")

CACHE_SECONDS = 600

cache = {
    "time": 0,
    "data": None
}


def get_value(point, key):
    value = point.get(key)

    if value is None:
        return None

    if isinstance(value, list):
        if len(value) == 0:
            return None
        value = value[0]

    try:
        return float(value)
    except:
        return None


def get_jma_observation():

    # 最新観測時刻を取得
    latest_url = (
        "https://www.jma.go.jp/bosai/amedas/data/"
        "latest_time.txt"
    )

    response = requests.get(
        latest_url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    if response.status_code != 200:
        raise Exception(
            f"気象庁の時刻取得に失敗しました "
            f"(HTTP {response.status_code})"
        )

    latest_text = response.text.strip()

    print("JMA latest:", latest_text)

    try:
        latest_dt = datetime.fromisoformat(
            latest_text
        )
    except Exception as e:
        raise Exception(
            f"気象庁の時刻データを読み込めませんでした: {e}"
        )

    # 最新観測データのURL
    timestamp = latest_dt.strftime(
        "%Y%m%d%H%M%S"
    )

    data_url = (
        "https://www.jma.go.jp/bosai/amedas/data/map/"
        f"{timestamp}.json"
    )

    print("JMA URL:", data_url)

    response = requests.get(
        data_url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    if response.status_code != 200:
        raise Exception(
            f"気象庁アメダスデータ取得失敗 "
            f"(HTTP {response.status_code})"
        )

    try:
        data = response.json()
    except Exception as e:
        raise Exception(
            f"気象庁データをJSONとして読み込めませんでした: {e}"
        )

    print(
        "JMA station count:",
        len(data)
    )

    # 稲取
    if INATORI_ID not in data:
        raise Exception(
            "稲取アメダス（50506）が "
            "気象庁データにありません。"
        )

    point = data[INATORI_ID]

    print(
        "INATORI:",
        point
    )

    return {
        "time": latest_dt,

        "temperature":
            get_value(point, "temp"),

        "humidity":
            get_value(point, "humidity"),

        "precipitation":
            get_value(
                point,
                "precipitation10m"
            ),

        "pressure":
            get_value(
                point,
                "pressure"
            ),

        "normal_pressure":
            get_value(
                point,
                "normalPressure"
            )
    }


def get_weather():

    now = datetime.now(JST).timestamp()

    # キャッシュ
    if (
        cache["data"] is not None
        and now - cache["time"] < CACHE_SECONDS
    ):
        return cache["data"]

    observation = get_jma_observation()

    result = {
        "observation": observation
    }

    cache["data"] = result
    cache["time"] = now

    return result


@app.route("/")
def index():

    try:

        weather = get_weather()
        obs = weather["observation"]

        temperature = obs["temperature"]
        humidity = obs["humidity"]
        precipitation = obs["precipitation"]
        pressure = obs["pressure"]
        normal_pressure = obs["normal_pressure"]

        if temperature is not None:
            temperature_text = (
                f"{temperature:.1f} ℃"
            )
        else:
            temperature_text = "--.- ℃"

        if humidity is not None:
            humidity_text = (
                f"{humidity:.0f} %"
            )
        else:
            humidity_text = "-- %"

        if precipitation is not None:
            precipitation_text = (
                f"{precipitation:.1f} mm"
            )
        else:
            precipitation_text = "0.0 mm"

        if pressure is not None:
            pressure_text = (
                f"{pressure:.1f} hPa"
            )
        else:
            pressure_text = "--.- hPa"

        if normal_pressure is not None:
            normal_pressure_text = (
                f"{normal_pressure:.1f} hPa"
            )
        else:
            normal_pressure_text = "--.- hPa"

        observation_time = (
            obs["time"]
            .astimezone(JST)
        )

        time_text = observation_time.strftime(
            "%Y/%m/%d %H:%M"
        )

        error_message = ""

    except Exception as e:

        temperature_text = "--.- ℃"
        humidity_text = "-- %"
        precipitation_text = "--.- mm"
        pressure_text = "--.- hPa"
        normal_pressure_text = "--.- hPa"
        time_text = "--"

        error_message = (
            f"{type(e).__name__}: {e}"
        )


    # HTML
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
        sans-serif;
}}

.container {{
    width: 100%;
    max-width: 1100px;
    margin: auto;
    padding: 24px;
}}

.location {{
    color: #704252;
    font-size: 14px;
    letter-spacing: .08em;
    margin-bottom: 10px;
}}

.current {{
    background: #A85D72;
    color: white;
    border-radius: 20px;
    padding: 28px;
}}

.current-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

.current-label {{
    font-size: 14px;
    opacity: .85;
}}

.temperature {{
    font-size: 64px;
    font-weight: 300;
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
    margin-top: 20px;
}}

.card {{
    background: #FAFAF9;
    border-radius: 16px;
    padding: 20px;
}}

.card-label {{
    color: #81777A;
    font-size: 13px;
    margin-bottom: 8px;
}}

.card-value {{
    color: #704252;
    font-size: 24px;
}}

.pressure {{
    background: #FAFAF9;
    border-radius: 18px;
    padding: 24px;
    margin-top: 20px;
}}

.pressure-title {{
    color: #81777A;
    font-size: 14px;
    margin-bottom: 10px;
}}

.pressure-value {{
    color: #704252;
    font-size: 30px;
    line-height: 1.6;
}}

.forecast {{
    background: #E7E3E2;
    border-radius: 18px;
    padding: 24px;
    margin-top: 20px;
}}

.section-title {{
    color: #704252;
    font-size: 18px;
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
    color: #81777A;
    font-size: 12px;
}}

.hour-icon {{
    font-size: 25px;
    margin: 8px 0;
}}

.hour-temp {{
    color: #704252;
    font-size: 16px;
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
    word-break: break-word;
}}

@media (max-width: 700px) {{

    .container {{
        padding: 14px;
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
{pressure_text}<br>
{normal_pressure_text}
</div>

</section>


<section class="forecast">

<div class="section-title">
24時間
</div>

<div class="forecast-grid">
"""


    # 24時間表示
    # 現段階では現在観測値を仮表示

    now_japan = datetime.now(JST)

    for i in range(24):

        hour = now_japan.replace(
            minute=0,
            second=0,
            microsecond=0
        )

        from datetime import timedelta

        hour = hour + timedelta(
            hours=i
        )

        hour_text = hour.strftime(
            "%H:%M"
        )

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


    html += f"""
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
