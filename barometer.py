from flask import Flask
import pandas as pd
import requests
import os

app = Flask(__name__)

COAST_LAT = 34.8156
COAST_LON = 139.0684

HIGHLAND_LAT = 34.8346
HIGHLAND_LON = 139.0481


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


def pressure_status(pressure):
    pressure = float(pressure)

    if pressure <= 1005:
        return "注意", "danger"

    if pressure <= 1010:
        return "やや低め", "warning"

    return "安定", "normal"


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


@app.route("/")
def index():

    try:

        highland, coast = get_24_hours()

        if len(highland) == 0:
            raise Exception("予報データがありません")

        current = highland.iloc[0]

        current_surface = float(
            current["SurfacePress"]
        )

        current_msl = float(
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
            current_msl
        )

        coast_current_temp = float(
            coast.iloc[0]["Temp"]
        )

        temp_difference = (
            current_temp - coast_current_temp
        )


        # ---------------------------------
        # 24時間カード
        # ---------------------------------

        forecast_cards = ""

        for i in range(
            min(24, len(highland))
        ):

            row = highland.iloc[i]

            if i < len(coast):
                coast_row = coast.iloc[i]
            else:
                coast_row = coast.iloc[-1]

            time_text = row["Time"].strftime(
                "%m/%d %H:%M"
            )

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

            forecast_cards += """
            <article class="forecast-card">

                <div class="forecast-top">

                    <span class="forecast-time">
                        {time}
                    </span>

                    <span class="forecast-status {status_cls}">
                        {status}
                    </span>

                </div>

                <div class="forecast-weather">
                    {weather}
                </div>

                <div class="temperature">
                    {temp:.1f}<small>℃</small>
                </div>

                <div class="details">

                    <div>
                        <span>麓</span>
                        <strong>{coast_temp:.1f}℃</strong>
                    </div>

                    <div>
                        <span>湿度</span>
                        <strong>{humidity:.0f}%</strong>
                    </div>

                    <div>
                        <span>降水</span>
                        <strong>{precip:.1f}mm</strong>
                    </div>

                </div>

                <div class="pressure">

                    <span>気圧</span>

                    <strong>
                        {surface:.1f}
                        <small>hPa</small>
                    </strong>

                    <em>
                        {msl:.1f} hPa
                    </em>

                </div>

            </article>
            """.format(
                time=time_text,
                status_cls=status_cls,
                status=status,
                weather=weather,
                temp=temp,
                coast_temp=coast_temp,
                humidity=humidity,
                precip=precip,
                surface=surface_press,
                msl=msl_press
            )


        # ---------------------------------
        # HTML
        # ---------------------------------

        html = """
<!DOCTYPE html>

<html lang="ja">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>伊豆熱川 Weather</title>


<style>


* {
    box-sizing: border-box;
}


html {
    overflow-x: hidden;
}


body {

    margin: 0;

    background: #F3F1F0;

    color: #303033;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Helvetica Neue",
        "Yu Gothic",
        sans-serif;

    overflow-x: hidden;
}


/* =========================
   MAIN
========================= */


.container {

    width: min(
        1500px,
        calc(100% - 48px)
    );

    margin: 0 auto;

    padding: 34px 0 60px;
}


/* =========================
   CURRENT
========================= */


.current {

    display: grid;

    grid-template-columns:
        1.35fr
        1fr
        1fr
        1fr;

    gap: 1px;

    background: #704252;

    border-radius: 24px;

    overflow: hidden;

    box-shadow:
        0 18px 45px
        rgba(48,48,51,.12);

    margin-bottom: 42px;
}


.current-main {

    background: #A85D72;

    color: white;

    padding: 34px 38px;

    display: flex;

    flex-direction: column;

    justify-content: center;
}


.current-label {

    font-size: 14px;

    letter-spacing: .12em;

    opacity: .8;

    margin-bottom: 10px;
}


.current-weather {

    font-size: 28px;

    font-weight: 600;

    margin-bottom: 16px;
}


.current-temp {

    font-size: 68px;

    line-height: 1;

    font-weight: 300;

    letter-spacing: -.04em;
}


.current-temp small {

    font-size: 24px;

    margin-left: 4px;
}


.current-place {

    margin-top: 18px;

    font-size: 13px;

    opacity: .72;
}


/* =========================
   CURRENT DATA
========================= */


.current-data {

    background: #FAFAF9;

    padding: 28px;

    display: flex;

    flex-direction: column;

    justify-content: center;
}


.data-label {

    color: #81777A;

    font-size: 13px;

    margin-bottom: 7px;
}


.pressure-main {

    font-size: 42px;

    font-weight: 500;

    color: #303033;

    line-height: 1;
}


.pressure-main small {

    font-size: 14px;

    font-weight: 400;
}


.pressure-second {

    color: #81777A;

    font-size: 15px;

    margin-top: 8px;
}


.data-divider {

    height: 1px;

    background: #E2DEDC;

    margin: 20px 0;
}


.data-value {

    font-size: 26px;

    font-weight: 500;
}


.data-value small {

    font-size: 14px;

    color: #81777A;
}


.current-status {

    margin-top: 18px;

    padding: 8px 13px;

    border-radius: 999px;

    width: fit-content;

    font-size: 13px;
}


.current-status.normal {

    background: #F5E8EC;

    color: #704252;
}


.current-status.warning {

    background: #F4E9C8;

    color: #79651A;
}


.current-status.danger {

    background: #F4DEDF;

    color: #8E3038;
}


/* =========================
   24 HOURS
========================= */


.forecast-section {

    background: #E7E3E2;

    border-radius: 26px;

    padding: 30px;
}


.section-header {

    display: flex;

    align-items: baseline;

    justify-content: space-between;

    margin-bottom: 24px;
}


.section-title {

    margin: 0;

    font-size: 21px;

    font-weight: 600;

    color: #704252;

    letter-spacing: .03em;
}


.section-sub {

    color: #81777A;

    font-size: 12px;
}


/* =========================
   GRID
========================= */


.forecast-grid {

    display: grid;

    grid-template-columns:
        repeat(6, minmax(0, 1fr));

    gap: 14px;
}


/* =========================
   CARD
========================= */


.forecast-card {

    background: #FAFAF9;

    border-radius: 18px;

    padding: 18px;

    min-width: 0;

    border: 1px solid #DDD8D6;

    transition:
        transform .2s ease,
        box-shadow .2s ease;
}


.forecast-card:hover {

    transform: translateY(-2px);

    box-shadow:
        0 10px 25px
        rgba(48,48,51,.08);
}


.forecast-top {

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 8px;

    margin-bottom: 15px;
}


.forecast-time {

    color: #704252;

    font-size: 12px;

    font-weight: 600;
}


.forecast-status {

    font-size: 10px;

    padding: 4px 7px;

    border-radius: 999px;

    white-space: nowrap;
}


.forecast-status.normal {

    background: #F5E8EC;

    color: #704252;
}


.forecast-status.warning {

    background: #F4E9C8;

    color: #79651A;
}


.forecast-status.danger {

    background: #F4DEDF;

    color: #8E3038;
}


.forecast-weather {

    font-size: 15px;

    min-height: 23px;

    margin-bottom: 4px;
}


.temperature {

    font-size: 34px;

    font-weight: 400;

    letter-spacing: -.03em;

    margin-bottom: 15px;
}


.temperature small {

    font-size: 14px;

    color: #81777A;
}


.details {

    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 5px;

    border-top: 1px solid #E2DEDC;

    border-bottom: 1px solid #E2DEDC;

    padding: 12px 0;
}


.details div {

    min-width: 0;
}


.details span {

    display: block;

    font-size: 10px;

    color: #81777A;

    margin-bottom: 4px;
}


.details strong {

    display: block;

    font-size: 13px;

    font-weight: 500;
}


.pressure {

    padding-top: 13px;

    display: flex;

    flex-direction: column;

    gap: 3px;
}


.pressure span {

    font-size: 10px;

    color: #81777A;
}


.pressure strong {

    font-size: 19px;

    font-weight: 500;
}


.pressure strong small {

    font-size: 10px;

    font-weight: 400;
}


.pressure em {

    font-size: 12px;

    font-style: normal;

    color: #81777A;
}


/* =========================
   TABLET
========================= */


@media (max-width: 1100px) {

    .current {

        grid-template-columns:
            repeat(2, 1fr);
    }


    .current-main {

        grid-row: span 2;
    }


    .forecast-grid {

        grid-template-columns:
            repeat(4, minmax(0, 1fr));
    }

}


/* =========================
   MOBILE
========================= */


@media (max-width: 700px) {

    .container {

        width: calc(100% - 24px);

        padding-top: 12px;
    }


    .current {

        grid-template-columns: 1fr;

        border-radius: 20px;

        margin-bottom: 24px;
    }


    .current-main {

        padding: 28px 24px;
    }


    .current-temp {

        font-size: 58px;
    }


    .current-data {

        padding: 23px 24px;
    }


    .forecast-section {

        padding: 18px;

        border-radius: 20px;
    }


    .section-header {

        margin-bottom: 18px;

        display: block;
    }


    .section-sub {

        display: block;

        margin-top: 5px;
    }


    .forecast-grid {

        grid-template-columns: 1fr;

        gap: 10px;
    }


    .forecast-card {

        padding: 16px;
    }


    .forecast-top {

        margin-bottom: 10px;
    }


    .temperature {

        font-size: 30px;

        margin-bottom: 10px;
    }


    .details {

        padding: 9px 0;
    }


    .pressure {

        padding-top: 10px;
    }

}


/* =========================
   SMALL MOBILE
========================= */


@media (max-width: 380px) {

    .container {

        width: calc(100% - 16px);
    }


    .current-main {

        padding: 24px 20px;
    }


    .current-data {

        padding: 20px;
    }


    .forecast-section {

        padding: 14px;
    }

}


</style>

</head>


<body>


<main class="container">


    <!-- 現在 -->


    <section class="current">


        <div class="current-main">

            <div class="current-label">
                伊豆熱川
            </div>

            <div class="current-weather">
                {current_weather}
            </div>

            <div class="current-temp">
                {current_temp:.1f}
                <small>℃</small>
            </div>

            <div class="current-place">
                標高約500m
            </div>

        </div>


        <div class="current-data">

            <div class="data-label">
                気圧
            </div>

            <div class="pressure-main">
                {current_surface:.1f}
                <small>hPa</small>
            </div>

            <div class="pressure-second">
                {current_msl:.1f} hPa
            </div>

            <div class="current-status {status_class}">
                {status_text}
            </div>

        </div>


        <div class="current-data">

            <div class="data-label">
                湿度
            </div>

            <div class="data-value">
                {current_humidity:.0f}
                <small>%</small>
            </div>

            <div class="data-divider"></div>

            <div class="data-label">
                降水
            </div>

            <div class="data-value">
                {current_precip:.1f}
                <small>mm</small>
            </div>

        </div>


        <div class="current-data">

            <div class="data-label">
                麓との気温差
            </div>

            <div class="data-value">
                {temp_difference:+.1f}
                <small>℃</small>
            </div>

            <div class="data-divider"></div>

            <div class="data-label">
                空模様
            </div>

            <div class="data-value">
                {current_weather.split(" ", 1)[0]}
            </div>

        </div>


    </section>


    <!-- 24時間 -->


    <section class="forecast-section">


        <div class="section-header">

            <h2 class="section-title">
                今後24時間
            </h2>

            <span class="section-sub">
                標高約500mの予報
            </span>

        </div>


        <div class="forecast-grid">

            {forecast_cards}

        </div>


    </section>


</main>


</body>

</html>
"""

        # HTML側のデータを安全に差し込む
        html = html.format(
            current_weather=current_weather,
            current_temp=current_temp,
            current_surface=current_surface,
            current_msl=current_msl,
            current_humidity=current_humidity,
            current_precip=current_precip,
            temp_difference=temp_difference,
            status_class=status_class,
            status_text=status_text,
            forecast_cards=forecast_cards
        )

        return html


    except Exception as e:

        return f"""
        <h2>データ取得エラー</h2>
        <p>{str(e)}</p>
        """


if __name__ == "__main__":

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