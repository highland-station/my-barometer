from flask import Flask
import pandas as pd
import requests

app = Flask(__name__)

# =========================
# 場所
# =========================

COAST_LAT = 34.8156
COAST_LON = 139.0684

HIGHLAND_LAT = 34.8346
HIGHLAND_LON = 139.0481
HIGHLAND_ELEVATION = 500


# =========================
# 天気コード
# =========================

WEATHER_CODES = {
    0: "☀️ 快晴",
    1: "🌤️ 晴れ",
    2: "⛅ 晴れ時々くもり",
    3: "☁️ くもり",
    45: "🌫️ 霧",
    48: "🌫️ 霧",
    51: "☔ 小雨",
    53: "☔ 小雨",
    55: "☔ 小雨",
    56: "☔ 小雨",
    57: "☔ 小雨",
    61: "☔ 雨",
    63: "☔ 雨",
    65: "☔ 強い雨",
    66: "☔ 雨",
    67: "☔ 強い雨",
    71: "❄️ 雪",
    73: "❄️ 雪",
    75: "❄️ 大雪",
    77: "❄️ 雪",
    80: "☔ にわか雨",
    81: "☔ にわか雨",
    82: "☔ 強いにわか雨",
    85: "❄️ 雪",
    86: "❄️ 雪",
    95: "⚡ 雷雨",
    96: "⚡ 雷雨",
    99: "⚡ 雷雨",
}


def weather_text(code):
    return WEATHER_CODES.get(int(code), "☁️ くもり")


# =========================
# 気圧状態
# =========================

def pressure_status(pressure):

    pressure = float(pressure)

    if pressure <= 1005:
        return "⚠️ 注意", "danger"

    if pressure <= 1010:
        return "⚠️ やや低め", "warning"

    return "✓ 安定", "normal"


# =========================
# Open-Meteo
# =========================

def get_weather(latitude, longitude):

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
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

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    hourly = data["hourly"]

    df = pd.DataFrame({
        "Time": hourly["time"],
        "PressMSL": hourly["pressure_msl"],
        "SurfacePress": hourly["surface_pressure"],
        "WeatherCode": hourly["weather_code"],
        "Temp": hourly["temperature_2m"],
        "Humidity": hourly["relative_humidity_2m"],
        "Precip": hourly["precipitation"],
    })

    df["Time"] = pd.to_datetime(df["Time"])

    return df


# =========================
# 24時間取得
# =========================

def get_24_hours():

    highland = get_weather(
        HIGHLAND_LAT,
        HIGHLAND_LON
    )

    coast = get_weather(
        COAST_LAT,
        COAST_LON
    )

    now = pd.Timestamp.now(
        tz="Asia/Tokyo"
    ).tz_localize(None)

    highland = highland[
        highland["Time"] >= now
    ].head(24)

    coast = coast[
        coast["Time"] >= now
    ].head(24)

    return highland, coast


# =========================
# メイン
# =========================

@app.route("/")
def index():

    try:

        highland, coast = get_24_hours()

        if len(highland) == 0:
            raise Exception(
                "予報データがありません"
            )

        # =====================
        # 現在値
        # =====================

        current = highland.iloc[0]

        current_press = float(
            current["SurfacePress"]
        )

        current_msl_press = float(
            current["PressMSL"]
        )

        current_temp = float(
            current["Temp"]
        )

        current_humidity = float(
            current["Humidity"]
        )

        current_precip = float(
            current["Precip"]
        )

        current_weather = weather_text(
            current["WeatherCode"]
        )

        status_text, status_class = pressure_status(
            current_msl_press
        )


        # =====================
        # 24時間カード
        # =====================

        forecast_cards = ""

        for i in range(
            min(24, len(highland))
        ):

            row = highland.iloc[i]

            if i < len(coast):
                coast_row = coast.iloc[i]
            else:
                coast_row = coast.iloc[-1]

            time_text = row[
                "Time"
            ].strftime("%m/%d %H:%M")

            weather = weather_text(
                row["WeatherCode"]
            )

            surface_press = float(
                row["SurfacePress"]
            )

            msl_press = float(
                row["PressMSL"]
            )

            temp = float(
                row["Temp"]
            )

            humidity = float(
                row["Humidity"]
            )

            precip = float(
                row["Precip"]
            )

            coast_temp = float(
                coast_row["Temp"]
            )

            status, status_cls = pressure_status(
                msl_press
            )


            forecast_cards += f"""

            <div class="forecast-card">

                <div class="forecast-time">
                    {time_text}
                </div>

                <div class="forecast-weather">
                    {weather}
                </div>

                <div class="forecast-row">
                    <span>🌡️ 気温</span>
                    <strong>
                        {temp:.1f}℃
                    </strong>
                </div>

                <div class="forecast-row small-row">
                    <span>麓</span>
                    <span>
                        {coast_temp:.1f}℃
                    </span>
                </div>

                <div class="forecast-row">
                    <span>💧 湿度</span>
                    <strong>
                        {humidity:.0f}%
                    </strong>
                </div>

                <div class="forecast-pressure">

                    <div>
                        気圧
                    </div>

                    <strong>
                        {surface_press:.1f} hPa
                    </strong>

                    <span>
                        {msl_press:.1f} hPa
                    </span>

                </div>

                <div class="forecast-row">

                    <span>🌧️ 降水</span>

                    <strong>
                        {precip:.1f} mm
                    </strong>

                </div>

                <div class="forecast-status {status_cls}">
                    {status}
                </div>

            </div>

            """


        # =========================
        # HTML
        # =========================

        html = f"""

<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>伊豆熱川 気圧・天気</title>


<style>

/* =========================
   基本
   ========================= */

* {{
    box-sizing: border-box;
}}

html,
body {{
    margin: 0;
    padding: 0;
    width: 100%;
}}

body {{

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        "Noto Sans JP",
        sans-serif;

    background: #F8F6F5;

    color: #343034;

    overflow-x: hidden;
}}


/* =========================
   全体
   ========================= */

.container {{

    width: 100%;

    max-width: 1600px;

    margin: 0 auto;

    padding:
        24px
        30px
        40px;
}}


/* =========================
   現在状況
   ========================= */

.current-box {{

    background: #B86B7D;

    border-radius: 20px;

    padding: 28px;

    box-shadow:
        0 5px 18px rgba(
            184,
            107,
            125,
            0.22
        );

    margin-bottom: 30px;
}}


.current-grid {{

    display: grid;

    grid-template-columns:
        1.5fr
        1fr
        1fr
        1fr
        1fr;

    gap: 16px;
}}


.current-item {{

    background: rgba(
        255,
        255,
        255,
        0.94
    );

    border-radius: 14px;

    padding: 18px;

    text-align: center;

    min-height: 125px;

    display: flex;

    flex-direction: column;

    justify-content: center;
}}


.current-item.main-pressure {{

    background: #FFFFFF;
}}


.label {{

    font-size: 15px;

    color: #7D4655;

    margin-bottom: 8px;
}}


.current-val {{

    font-size: 28px;

    font-weight: 700;

    line-height: 1.35;

    color: #343034;
}}


.small-current {{

    font-size: 17px;

    color: #81777A;

    font-weight: 500;
}}


.weather-current {{

    font-size: 23px;

    font-weight: 700;

    color: #343034;
}}


/* =========================
   アラート
   ========================= */

.alert {{

    margin-top: 18px;

    padding: 12px 16px;

    border-radius: 10px;

    text-align: center;

    font-weight: 700;
}}

.alert.normal {{

    background: #FFFFFF;

    color: #7D4655;
}}

.alert.warning {{

    background: #F4E9C8;

    color: #79651A;
}}

.alert.danger {{

    background: #F4DEDF;

    color: #8E3038;
}}


/* =========================
   24時間エリア
   ========================= */

.section-title {{

    font-size: 22px;

    font-weight: 700;

    color: #7D4655;

    margin:
        0
        0
        14px
        4px;
}}


.forecast-grid {{

    background: #F0EEED;

    border-radius: 20px;

    padding: 18px;

    display: grid;

    grid-template-columns:
        repeat(
            6,
            minmax(0, 1fr)
        );

    gap: 12px;
}}


/* =========================
   予報カード
   ========================= */

.forecast-card {{

    background: #FFFFFF;

    border-radius: 14px;

    padding:
        15px
        13px;

    box-shadow:
        0 2px 8px rgba(
            52,
            48,
            52,
            0.07
        );

    min-width: 0;

    border:
        1px solid #E4DFDD;
}}


.forecast-time {{

    font-size: 15px;

    font-weight: 700;

    text-align: center;

    color: #7D4655;

    margin-bottom: 10px;
}}


.forecast-weather {{

    text-align: center;

    font-size: 17px;

    font-weight: 700;

    min-height: 45px;

    display: flex;

    align-items: center;

    justify-content: center;

    margin-bottom: 8px;
}}


.forecast-row {{

    display: flex;

    justify-content: space-between;

    align-items: center;

    gap: 5px;

    font-size: 13px;

    padding: 5px 0;

    border-top:
        1px solid #E5E1E0;
}}


.forecast-row strong {{

    font-size: 14px;

    color: #343034;
}}


.small-row {{

    color: #81777A;

    font-size: 12px;
}}


.forecast-pressure {{

    border-top:
        1px solid #E5E1E0;

    margin-top: 3px;

    padding-top: 7px;

    text-align: center;

    font-size: 12px;

    color: #81777A;
}}


.forecast-pressure strong {{

    display: block;

    font-size: 16px;

    color: #343034;

    margin-top: 2px;
}}


.forecast-pressure span {{

    display: block;

    font-size: 12px;

    color: #81777A;

    margin-top: 2px;
}}


/* =========================
   ステータス
   ========================= */

.forecast-status {{

    margin-top: 8px;

    padding: 5px;

    border-radius: 7px;

    text-align: center;

    font-size: 11px;

    font-weight: 700;
}}


.forecast-status.normal {{

    background: #F3E4E8;

    color: #7D4655;
}}


.forecast-status.warning {{

    background: #F4E9C8;

    color: #79651A;
}}


.forecast-status.danger {{

    background: #F4DEDF;

    color: #8E3038;
}}


/* =========================
   タブレット
   ========================= */

@media (max-width: 1100px) {{

    .forecast-grid {{

        grid-template-columns:
            repeat(
                4,
                minmax(0, 1fr)
            );
    }}

    .current-grid {{

        grid-template-columns:
            repeat(3, 1fr);
    }}

}}


/* =========================
   スマホ
   ========================= */

@media (max-width: 700px) {{

    .container {{

        padding:
            10px
            10px
            25px;
    }}


    .current-box {{

        padding: 12px;

        border-radius: 15px;

        margin-bottom: 18px;
    }}


    .current-grid {{

        grid-template-columns:
            repeat(2, 1fr);

        gap: 8px;
    }}


    .current-item {{

        min-height: 88px;

        padding:
            10px
            6px;

        border-radius: 11px;
    }}


    .current-item.main-pressure {{

        grid-column:
            span 2;
    }}


    .label {{

        font-size: 12px;

        margin-bottom: 4px;
    }}


    .current-val {{

        font-size: 21px;
    }}


    .small-current {{

        font-size: 13px;
    }}


    .weather-current {{

        font-size: 17px;
    }}


    .alert {{

        margin-top: 10px;

        padding: 9px;

        font-size: 13px;
    }}


    /* 24時間 */

    .section-title {{

        font-size: 18px;

        margin:
            0
            0
            10px
            2px;
    }}


    .forecast-grid {{

        padding: 10px;

        border-radius: 15px;

        display: grid;

        grid-template-columns: 1fr;

        gap: 8px;
    }}


    .forecast-card {{

        padding: 12px;

        border-radius: 12px;

        display: grid;

        grid-template-columns:
            90px
            1fr
            1.2fr;

        column-gap: 10px;

        align-items: center;
    }}


    .forecast-time {{

        grid-row:
            span 4;

        font-size: 15px;

        margin: 0;

        text-align: center;
    }}


    .forecast-weather {{

        grid-column:
            2 / 4;

        min-height: auto;

        justify-content: flex-start;

        text-align: left;

        font-size: 15px;

        margin-bottom: 3px;
    }}


    .forecast-row {{

        padding: 3px 0;

        border-top: none;

        font-size: 12px;
    }}


    .forecast-row strong {{

        font-size: 13px;
    }}


    .small-row {{

        display: none;
    }}


    .forecast-pressure {{

        grid-column:
            2 / 4;

        text-align: left;

        border-top:
            1px solid #E5E1E0;

        margin-top: 3px;

        padding-top: 5px;
    }}


    .forecast-pressure strong {{

        display: inline;

        font-size: 14px;

        margin-right: 5px;
    }}


    .forecast-pressure span {{

        display: inline;

        font-size: 11px;
    }}


    .forecast-status {{

        grid-column:
            2 / 4;

        margin-top: 3px;

        padding: 4px;

        font-size: 10px;
    }}

}}


/* =========================
   小さいスマホ
   ========================= */

@media (max-width: 380px) {{

    .container {{

        padding-left: 7px;

        padding-right: 7px;
    }}


    .current-box {{

        padding: 8px;
    }}


    .current-val {{

        font-size: 19px;
    }}


    .forecast-card {{

        grid-template-columns:
            72px
            1fr
            1fr;

        column-gap: 7px;

        padding: 10px;
    }}


    .forecast-time {{

        font-size: 13px;
    }}

}}

</style>

</head>


<body>


<div class="container">


    <!-- 現在の状況 -->

    <div class="current-box">

        <div class="current-grid">


            <div class="current-item main-pressure">

                <div class="label">
                    気圧
                </div>

                <div class="current-val">

                    {current_press:.1f} hPa

                    <br>

                    <span class="small-current">

                        {current_msl_press:.1f} hPa

                    </span>

                </div>

            </div>


            <div class="current-item">

                <div class="label">
                    天気
                </div>

                <div class="weather-current">
                    {current_weather}
                </div>

            </div>


            <div class="current-item">

                <div class="label">
                    気温
                </div>

                <div class="current-val">
                    {current_temp:.1f}℃
                </div>

            </div>


            <div class="current-item">

                <div class="label">
                    湿度
                </div>

                <div class="current-val">
                    {current_humidity:.0f}%
                </div>

            </div>


            <div class="current-item">

                <div class="label">
                    降水量
                </div>

                <div class="current-val">
                    {current_precip:.1f} mm
                </div>

            </div>


        </div>


        <div class="alert {status_class}">

            {status_text}

        </div>


    </div>


    <!-- 24時間予報 -->

    <div class="section-title">

        今後24時間の予報

    </div>


    <div class="forecast-grid">

        {forecast_cards}

    </div>


</div>


</body>

</html>

"""

        return html


    except Exception as e:

        return f"""

        <h2>データ取得エラー</h2>

        <p>{str(e)}</p>

        """


# =========================
# Render
# =========================

if __name__ == "__main__":

    import os

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
