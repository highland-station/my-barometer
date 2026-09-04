from flask import Flask
import pandas as pd
import requests
import time

app = Flask(__name__)

# =========================
# 場所
# =========================

COAST_LAT = 34.8156
COAST_LON = 139.0684

HIGHLAND_LAT = 34.8346
HIGHLAND_LON = 139.0481

# =========================
# キャッシュ
# =========================

CACHE_SECONDS = 600  # 10分
weather_cache = {
    "data": None,
    "time": 0
}


# =========================
# 天気の表示
# =========================

def weather_text(code):
    code = int(code)

    if code == 0:
        return "☀️ 快晴"
    elif code == 1:
        return "🌤️ 晴れ"
    elif code == 2:
        return "⛅ 晴れ時々くもり"
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
    else:
        return "☁️ くもり"


# =========================
# 気圧の状態
# =========================

def pressure_status(pressure):
    pressure = float(pressure)

    if pressure <= 1005:
        return "danger", "気圧低下"
    elif pressure <= 1010:
        return "warning", "やや低め"
    else:
        return "normal", "安定"


# =========================
# API取得
# =========================

def get_weather():

    now = time.time()

    # 10分以内ならキャッシュを使用
    if (
        weather_cache["data"] is not None
        and now - weather_cache["time"] < CACHE_SECONDS
    ):
        return weather_cache["data"]

    url = "https://api.open-meteo.com/v1/forecast"

    headers = {
        "User-Agent": "IzuAtagawaWeather/1.0"
    }

    # まず高地
    highland_params = {
        "latitude": HIGHLAND_LAT,
        "longitude": HIGHLAND_LON,
        "hourly": (
            "pressure_msl,"
            "surface_pressure,"
            "weather_code,"
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation"
        ),
        "timezone": "Asia/Tokyo",
        "forecast_days": 2,
    }

    # 海側
    coast_params = {
        "latitude": COAST_LAT,
        "longitude": COAST_LON,
        "hourly": (
            "pressure_msl,"
            "surface_pressure,"
            "weather_code,"
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation"
        ),
        "timezone": "Asia/Tokyo",
        "forecast_days": 2,
    }

    try:

        # 高地
        response_high = requests.get(
            url,
            params=highland_params,
            headers=headers,
            timeout=10
        )

        # 429ならキャッシュがあれば使用
        if response_high.status_code == 429:

            if weather_cache["data"] is not None:
                return weather_cache["data"]

            raise Exception(
                "Open-Meteoのアクセス制限中です。"
                "少し時間を置いて再度お試しください。"
            )

        response_high.raise_for_status()

        highland = response_high.json()

        # 少しだけ間隔を空ける
        time.sleep(1)

        # 海側
        response_coast = requests.get(
            url,
            params=coast_params,
            headers=headers,
            timeout=10
        )

        if response_coast.status_code == 429:

            # 高地だけでも表示できるようにする
            coast = highland

        else:

            response_coast.raise_for_status()
            coast = response_coast.json()

        result = {
            "highland": highland,
            "coast": coast
        }

        # キャッシュ保存
        weather_cache["data"] = result
        weather_cache["time"] = time.time()

        return result

    except requests.RequestException as e:

        # 過去データがあればそれを表示
        if weather_cache["data"] is not None:
            return weather_cache["data"]

        raise Exception(f"天気データを取得できませんでした: {e}")


# =========================
# DataFrame化
# =========================

def make_dataframe(data):

    df = pd.DataFrame({
        "time": pd.to_datetime(
            data["hourly"]["time"]
        ),
        "pressure_msl": data["hourly"]["pressure_msl"],
        "surface_pressure": data["hourly"]["surface_pressure"],
        "weather_code": data["hourly"]["weather_code"],
        "temperature": data["hourly"]["temperature_2m"],
        "humidity": data["hourly"]["relative_humidity_2m"],
        "precipitation": data["hourly"]["precipitation"],
    })

    return df


# =========================
# 今後24時間
# =========================

def get_24_hours(df):

    now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None)

    future = df[df["time"] >= now].copy()

    if len(future) == 0:
        future = df.copy()

    return future.head(24)


# =========================
# メイン画面
# =========================

@app.route("/")
def index():

    try:

        data = get_weather()

        highland_df = make_dataframe(data["highland"])
        coast_df = make_dataframe(data["coast"])

        highland_24 = get_24_hours(highland_df)
        coast_24 = get_24_hours(coast_df)

        current = highland_24.iloc[0]
        coast_current = coast_24.iloc[0]

        temperature_difference = (
            current["temperature"]
            - coast_current["temperature"]
        )

        status_class, status_text = pressure_status(
            current["pressure_msl"]
        )

        cards = ""

        for i in range(min(24, len(highland_24))):

            row = highland_24.iloc[i]

            if i < len(coast_24):
                coast_row = coast_24.iloc[i]
                temp_difference = (
                    row["temperature"]
                    - coast_row["temperature"]
                )
            else:
                temp_difference = 0

            card_status_class, card_status_text = pressure_status(
                row["pressure_msl"]
            )

            cards += f"""
            <div class="hour-card">

                <div class="hour-time">
                    {row["time"].strftime("%-m/%-d %H:%M")}
                </div>

                <div class="hour-status {card_status_class}">
                    {card_status_text}
                </div>

                <div class="hour-weather">
                    {weather_text(row["weather_code"])}
                </div>

                <div class="hour-temp">
                    {row["temperature"]:.1f}°
                </div>

                <div class="hour-diff">
                    海側との差
                    <strong>
                        {temp_difference:+.1f}°
                    </strong>
                </div>

                <div class="hour-info">
                    湿度 {row["humidity"]:.0f}%
                </div>

                <div class="hour-info">
                    降水 {row["precipitation"]:.1f} mm
                </div>

                <div class="hour-pressure">
                    <span>気圧</span>
                    <strong>
                        {row["surface_pressure"]:.1f}
                    </strong>
                    <strong>
                        {row["pressure_msl"]:.1f}
                    </strong>
                    <small>hPa</small>
                </div>

            </div>
            """

        html = """
<!DOCTYPE html>
<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>伊豆熱川 天気・気圧</title>

<style>

* {
    box-sizing: border-box;
}

body {
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
}

.container {
    width: min(96%, 1550px);
    margin: 0 auto;
    padding: 30px 0 50px;
}

/* =========================
   現在
   ========================= */

.current {
    background: #A85D72;
    color: white;
    border-radius: 28px;
    padding: 34px;
    box-shadow: 0 14px 35px rgba(70, 45, 52, 0.16);
}

.current-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 25px;
}

.location {
    font-size: 17px;
    letter-spacing: 0.08em;
    opacity: 0.9;
}

.weather-main {
    display: flex;
    align-items: center;
    gap: 25px;
    margin-top: 20px;
}

.weather-icon {
    font-size: 64px;
}

.temperature {
    font-size: 64px;
    line-height: 1;
    font-weight: 700;
    letter-spacing: -0.04em;
}

.weather-name {
    margin-top: 10px;
    font-size: 18px;
}

.current-pressure {
    min-width: 220px;
    background: rgba(255,255,255,0.14);
    border-radius: 20px;
    padding: 22px;
}

.pressure-label {
    font-size: 14px;
    opacity: 0.8;
    margin-bottom: 8px;
}

.pressure-number {
    font-size: 29px;
    font-weight: 700;
    line-height: 1.25;
}

.pressure-number + .pressure-number {
    margin-top: 4px;
}

.pressure-unit {
    font-size: 13px;
    opacity: 0.75;
    margin-left: 4px;
}

.current-info {
    display: grid;
    grid-template-columns:
        repeat(3, 1fr);
    gap: 14px;
    margin-top: 30px;
}

.info-box {
    background: rgba(255,255,255,0.12);
    border-radius: 17px;
    padding: 16px 18px;
}

.info-label {
    font-size: 12px;
    opacity: 0.75;
}

.info-value {
    font-size: 22px;
    font-weight: 600;
    margin-top: 5px;
}

.difference {
    background: rgba(255,255,255,0.18);
}

/* =========================
   24時間
   ========================= */

.forecast {
    margin-top: 30px;
    background: #E7E3E2;
    border-radius: 28px;
    padding: 30px;
}

.forecast-title {
    font-size: 22px;
    font-weight: 700;
    color: #704252;
    margin-bottom: 22px;
}

.hour-grid {
    display: grid;
    grid-template-columns:
        repeat(6, minmax(0, 1fr));
    gap: 12px;
}

.hour-card {
    background: #FAFAF9;
    border-radius: 17px;
    padding: 15px;
    min-width: 0;
    box-shadow: 0 4px 12px rgba(60, 50, 50, 0.05);
}

.hour-time {
    font-size: 12px;
    color: #81777A;
    white-space: nowrap;
}

.hour-status {
    display: inline-block;
    margin-top: 8px;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 10px;
}

.normal {
    background: #F5E8EC;
    color: #704252;
}

.warning {
    background: #F4E9C8;
    color: #80691C;
}

.danger {
    background: #F4DEDF;
    color: #983C48;
}

.hour-weather {
    margin-top: 13px;
    font-size: 13px;
    line-height: 1.4;
}

.hour-temp {
    margin-top: 8px;
    font-size: 27px;
    font-weight: 700;
    color: #704252;
}

.hour-diff {
    margin-top: 6px;
    font-size: 11px;
    color: #81777A;
}

.hour-diff strong {
    color: #A85D72;
}

.hour-info {
    margin-top: 7px;
    font-size: 11px;
    color: #81777A;
}

.hour-pressure {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid #E5DFE0;
    color: #704252;
}

.hour-pressure span {
    display: block;
    font-size: 10px;
    color: #81777A;
    margin-bottom: 3px;
}

.hour-pressure strong {
    display: block;
    font-size: 14px;
    line-height: 1.25;
}

.hour-pressure small {
    font-size: 9px;
    color: #81777A;
}

/* =========================
   スマホ
   ========================= */

@media (max-width: 1000px) {

    .hour-grid {
        grid-template-columns:
            repeat(4, minmax(0, 1fr));
    }

}

@media (max-width: 700px) {

    .container {
        width: 94%;
        padding-top: 15px;
    }

    .current {
        padding: 24px;
        border-radius: 22px;
    }

    .current-top {
        display: block;
    }

    .weather-main {
        gap: 15px;
    }

    .weather-icon {
        font-size: 48px;
    }

    .temperature {
        font-size: 48px;
    }

    .current-pressure {
        margin-top: 22px;
        min-width: 0;
    }

    .current-info {
        grid-template-columns:
            repeat(2, 1fr);
    }

    .forecast {
        padding: 20px;
        border-radius: 22px;
    }

    .hour-grid {
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

}

@media (max-width: 420px) {

    .current-info {
        grid-template-columns: 1fr;
    }

    .hour-grid {
        grid-template-columns:
            1fr;
    }

}

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
                        CURRENT_ICON
                    </div>

                    <div>

                        <div class="temperature">
                            CURRENT_TEMP℃
                        </div>

                        <div class="weather-name">
                            CURRENT_WEATHER
                        </div>

                    </div>

                </div>

            </div>

            <div class="current-pressure">

                <div class="pressure-label">
                    気圧
                </div>

                <div class="pressure-number">
                    CURRENT_SURFACE
                    <span class="pressure-unit">hPa</span>
                </div>

                <div class="pressure-number">
                    CURRENT_MSL
                    <span class="pressure-unit">hPa</span>
                </div>

            </div>

        </div>

        <div class="current-info">

            <div class="info-box">

                <div class="info-label">
                    湿度
                </div>

                <div class="info-value">
                    CURRENT_HUMIDITY%
                </div>

            </div>

            <div class="info-box">

                <div class="info-label">
                    降水量
                </div>

                <div class="info-value">
                    CURRENT_RAIN mm
                </div>

            </div>

            <div class="info-box difference">

                <div class="info-label">
                    海側との気温差
                </div>

                <div class="info-value">
                    CURRENT_DIFF℃
                </div>

            </div>

        </div>

    </section>


    <section class="forecast">

        <div class="forecast-title">
            これから24時間
        </div>

        <div class="hour-grid">
            FORECAST_CARDS
        </div>

    </section>

</div>

</body>

</html>
"""

        icon = weather_text(current["weather_code"]).split(" ")[0]

        html = html.replace(
            "CURRENT_ICON",
            icon
        )

        html = html.replace(
            "CURRENT_TEMP",
            f"{current['temperature']:.1f}"
        )

        html = html.replace(
            "CURRENT_WEATHER",
            weather_text(current["weather_code"])
        )

        html = html.replace(
            "CURRENT_SURFACE",
            f"{current['surface_pressure']:.1f}"
        )

        html = html.replace(
            "CURRENT_MSL",
            f"{current['pressure_msl']:.1f}"
        )

        html = html.replace(
            "CURRENT_HUMIDITY",
            f"{current['humidity']:.0f}"
        )

        html = html.replace(
            "CURRENT_RAIN",
            f"{current['precipitation']:.1f}"
        )

        html = html.replace(
            "CURRENT_DIFF",
            f"{temperature_difference:+.1f}"
        )

        html = html.replace(
            "FORECAST_CARDS",
            cards
        )

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
    color: #40393B;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Helvetica Neue",
        "Yu Gothic",
        "Meiryo",
        sans-serif;
}}

.error {{
    max-width: 700px;
    margin: 80px auto;
    padding: 30px;
    background: white;
    border-radius: 20px;
}}

h1 {{
    color: #A85D72;
    font-size: 22px;
}}

</style>

</head>

<body>

<div class="error">

<h1>データ取得エラー</h1>

<p>{str(e)}</p>

<p>
少し時間を置いて、もう一度ページを開いてください。
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