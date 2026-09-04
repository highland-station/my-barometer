from flask import Flask
import os
import pandas as pd
import requests

app = Flask(__name__)


# 麓：海岸・国道135号周辺（伊豆熱川駅付近）
COAST_LAT = 34.8156
COAST_LON = 139.0684

# 現地：奈良本・エンジェルフォレスト伊豆熱川付近
HIGHLAND_LAT = 34.8346
HIGHLAND_LON = 139.0481
HIGHLAND_ELEVATION = 500


def get_weather_data(latitude, longitude, elevation=None):

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

    if elevation is not None:
        params["elevation"] = elevation

    try:
        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        hourly = response.json().get("hourly")

        if not hourly:
            return None

        df = pd.DataFrame(
            {
                "Time": pd.to_datetime(hourly["time"]),
                "PressMSL": hourly["pressure_msl"],
                "SurfacePress": hourly["surface_pressure"],
                "Code": hourly["weather_code"],
                "Temp": hourly["temperature_2m"],
                "Humi": hourly["relative_humidity_2m"],
                "Rain": hourly["precipitation"],
            }
        )

        df["PressMSL"] = df["PressMSL"].round(1)
        df["SurfacePress"] = df["SurfacePress"].round(1)
        df["Temp"] = df["Temp"].round(1)
        df["Humi"] = df["Humi"].round().astype(int)
        df["Rain"] = df["Rain"].round(1)

        now = (
            pd.Timestamp.now(tz="Asia/Tokyo")
            .tz_localize(None)
            .floor("h")
        )

        future_df = df[df["Time"] >= now]

        if future_df.empty:
            return df.head(24)

        return future_df.head(24)

    except Exception as error:

        app.logger.warning(
            "Weather API error: %s",
            error
        )

        return None


def create_fallback_data(is_highland):

    now = (
        pd.Timestamp.now(tz="Asia/Tokyo")
        .tz_localize(None)
        .floor("h")
    )

    if is_highland:

        press_msl = 1013.0
        surface_press = 955.0
        temp = 20.0
        humi = 70

    else:

        press_msl = 1013.0
        surface_press = 1010.0
        temp = 23.0
        humi = 68

    return pd.DataFrame(
        [
            {
                "Time": now + pd.Timedelta(hours=i),
                "PressMSL": press_msl,
                "SurfacePress": surface_press,
                "Code": 2,
                "Temp": temp,
                "Humi": humi,
                "Rain": 0.0,
            }
            for i in range(24)
        ]
    )


def get_weather_string(code):

    code = int(code)

    if code == 0:
        return "☀️ 快晴"

    if code == 1:
        return "🌤️ 晴れ"

    if code == 2:
        return "⛅ 晴れ時々くもり"

    if code == 3:
        return "☁️ くもり"

    if code in (45, 48):
        return "🌫️ 霧"

    if 51 <= code <= 67:
        return "☔ 雨"

    if 71 <= code <= 77:
        return "❄️ 雪"

    if 80 <= code <= 82:
        return "☔ 雨"

    if 85 <= code <= 86:
        return "❄️ 雪"

    if code in (95, 96, 99):
        return "⚡ 雷雨"

    return "☁️ くもり"


@app.route("/")
def index():

    # 500m地点
    highland_df = get_weather_data(
        HIGHLAND_LAT,
        HIGHLAND_LON,
        HIGHLAND_ELEVATION
    )

    # 麓
    coast_df = get_weather_data(
        COAST_LAT,
        COAST_LON
    )

    highland_fallback = (
        highland_df is None
        or highland_df.empty
    )

    coast_fallback = (
        coast_df is None
        or coast_df.empty
    )

    if highland_fallback:

        highland_df = create_fallback_data(
            is_highland=True
        )

    if coast_fallback:

        coast_df = create_fallback_data(
            is_highland=False
        )

    data_error = (
        highland_fallback
        or coast_fallback
    )


    # 麓の気温を500m地点の時間に合わせる
    coast_temp = coast_df[
        ["Time", "Temp"]
    ].rename(
        columns={
            "Temp": "CoastTemp"
        }
    )

    df = highland_df.merge(
        coast_temp,
        on="Time",
        how="outer"
    )

    df = df.sort_values("Time")

    df = df.ffill().bfill()


    # 現在値
    if not df.empty:

        current = df.iloc[0]

        # 標高500m地点の実際の気圧
        current_press = float(
            current["SurfacePress"]
        )

        # 海面更正気圧
        current_msl_press = float(
            current["PressMSL"]
        )

        current_weather = get_weather_string(
            current["Code"]
        )

        current_temp = float(
            current["Temp"]
        )

        current_coast_temp = float(
            current["CoastTemp"]
        )

        current_humi = int(
            current["Humi"]
        )

        current_rain = float(
            current["Rain"]
        )

    else:

        current_press = 955.0
        current_msl_press = 1013.0
        current_weather = "☁️ くもり"
        current_temp = 20.0
        current_coast_temp = 23.0
        current_humi = 70
        current_rain = 0.0


    # 気圧による表示
    if data_error:

        alert_bg = "#fffaf0"
        alert_border = "#ffe4b5"
        alert_text = "#92400e"

        message = (
            "<b>⚠️ データ取得に失敗しています。</b>"
            "<br>"
            "一部の数値は参考値です。"
        )

    elif current_msl_press <= 1005.0:

        alert_bg = "#fdf2f2"
        alert_border = "#fde8e8"
        alert_text = "#9b1c1c"

        message = (
            f"<b>🔴 気圧警戒："
            f"{current_msl_press:.1f} hPa</b>"
            "<br>"
            "気圧変化に敏感な方は、"
            "無理をせずゆっくり過ごしましょう。"
        )

    elif current_msl_press <= 1010.0:

        alert_bg = "#fdfaea"
        alert_border = "#fdf6b2"
        alert_text = "#78350f"

        message = (
            f"<b>⚠️ 気圧注意："
            f"{current_msl_press:.1f} hPa</b>"
            "<br>"
            "気圧変化に敏感な方は、"
            "体調の変化に気をつけて過ごしましょう。"
        )

    else:

        alert_bg = "#f3f8fc"
        alert_border = "#e1effa"
        alert_text = "#1e429f"

        message = (
            "<b>🍏 気圧は比較的穏やかです。</b>"
            "<br>"
            "水分補給をして、ゆったり過ごしましょう。"
        )


    # 24時間予報の表
    rows_html = ""

    for _, row in df.iterrows():

        forecast_press = float(
            row["PressMSL"]
        )

        if data_error:

            status = "参考値"
            status_color = "#6b7280"
            row_bg = ""

        elif forecast_press <= 1005.0:

            status = "🔴 警戒"
            status_color = "#e02424"
            row_bg = "background:#fff7f7;"

        elif forecast_press <= 1010.0:

            status = "⚠️ 注意"
            status_color = "#b45309"
            row_bg = "background:#fffdf6;"

        else:

            status = "正常"
            status_color = "#057a55"
            row_bg = ""


        rows_html += f"""
        <tr style="{row_bg}">

            <td>
                {row["Time"].strftime("%H:%M")}
            </td>

            <td>
                <b>
                    {float(row["SurfacePress"]):.1f} hPa
                </b>

                <br>

                <span class="small-value">
                    {float(row["PressMSL"]):.1f} hPa
                </span>
            </td>

            <td>
                {get_weather_string(row["Code"])}
            </td>

            <td>
                <b>
                    {float(row["Temp"]):.1f}℃
                </b>

                <br>

                <span class="small-value">
                    {float(row["CoastTemp"]):.1f}℃
                </span>
            </td>

            <td>
                {int(row["Humi"])}%
            </td>

            <td>
                {float(row["Rain"]):.1f} mm
            </td>

            <td style="color:{status_color};">
                <b>{status}</b>
            </td>

        </tr>
        """


    return f"""
    <!DOCTYPE html>

    <html lang="ja">

    <head>

        <meta charset="utf-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <meta
            http-equiv="refresh"
            content="600"
        >

        <title>
            伊豆熱川・奈良本ライブ画面
        </title>


        <style>

            * {{
                box-sizing: border-box;
            }}


            body {{

                font-family:
                    -apple-system,
                    BlinkMacSystemFont,
                    "Segoe UI",
                    "Hiragino Kaku Gothic ProN",
                    Meiryo,
                    sans-serif;

                background: #f5f7fa;

                color: #1f2937;

                margin: 0;

                padding: 20px;
            }}


            .container {{

                max-width: 1400px;

                margin: 0 auto;

                background: #ffffff;

                padding: 30px;

                border-radius: 18px;

                box-shadow:
                    0 6px 18px
                    rgba(31,41,55,0.08);
            }}


            .current-box {{

                background: #1f2937;

                color: #ffffff;

                border-radius: 14px;

                padding: 25px 18px;

                margin-bottom: 22px;
            }}


            .grid-container {{

                display: flex;

                justify-content: space-around;

                text-align: center;
            }}


            .grid-item {{

                flex: 1;

                padding: 0 10px;
            }}


            .grid-item:not(:last-child) {{

                border-right:
                    1px solid #374151;
            }}


            .label {{

                color: #cbd5e1;

                font-size: 14px;

                font-weight: bold;

                margin-bottom: 7px;
            }}


            .current-val {{

                font-size: 21px;

                font-weight: 700;

                margin-top: 5px;
            }}


            .small-current {{

                font-size: 13px;

                color: #9ca3af;

                font-weight: normal;
            }}


            .alert-banner {{

                background: {alert_bg};

                border:
                    1px solid
                    {alert_border};

                color: {alert_text};

                padding: 16px;

                border-radius: 10px;

                font-size: 14px;

                line-height: 1.7;

                margin-bottom: 24px;
            }}


            .section-title {{

                font-size: 18px;

                font-weight: bold;

                margin-top: 20px;

                margin-bottom: 10px;

                color: #374151;
            }}


            .table-wrapper {{

                overflow-x: auto;

                -webkit-overflow-scrolling: touch;
            }}


            table {{

                width: 100%;

                min-width: 900px;

                border-collapse: collapse;

                margin-top: 8px;

                font-size: 14px;

                text-align: left;
            }}


            th {{

                background: #f9fafb;

                color: #4b5563;

                padding: 14px 10px;

                border-bottom:
                    2px solid #e5e7eb;

                font-size: 13px;

                white-space: nowrap;
            }}


            td {{

                padding: 14px 10px;

                border-bottom:
                    1px solid #e5e7eb;

                white-space: nowrap;
            }}


            .small-value {{

                color: #6b7280;

                font-size: 12px;
            }}


            .note {{

                color: #6b7280;

                font-size: 12px;

                line-height: 1.7;

                margin-top: 18px;
            }}


            @media (max-width: 700px) {{

                body {{
                    padding: 8px;
                }}

                .container {{
                    padding: 14px;
                }}

                .current-box {{
                    padding: 18px 8px;
                }}

                .grid-container {{
                    flex-wrap: wrap;
                }}

                .grid-item {{
                    flex-basis: 33.333%;

                    margin-bottom: 15px;
                }}

                .grid-item:not(:last-child) {{
                    border-right: none;
                }}

                .current-val {{
                    font-size: 16px;
                }}

                .label {{
                    font-size: 11px;
                }}

            }}

        </style>

    </head>


    <body>

        <div class="container">


            <!-- 現在の状況 -->

            <div class="current-box">

                <div class="grid-container">


                    <div class="grid-item">

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


                    <div class="grid-item">

                        <div class="label">
                            現在の天気
                        </div>

                        <div class="current-val">
                            {current_weather}
                        </div>

                    </div>


                    <div class="grid-item">

                        <div class="label">
                            気温
                        </div>

                        <div class="current-val">

                            {current_temp:.1f}℃

                            <br>

                            <span class="small-current">
                                麓 {current_coast_temp:.1f}℃
                            </span>

                        </div>

                    </div>


                    <div class="grid-item">

                        <div class="label">
                            湿度
                        </div>

                        <div class="current-val">
                            {current_humi}%
                        </div>

                    </div>


                    <div class="grid-item">

                        <div class="label">
                            降水
                        </div>

                        <div class="current-val">
                            {current_rain:.1f} mm
                        </div>

                    </div>


                </div>

            </div>


            <!-- 気圧メッセージ -->

            <div class="alert-banner">

                {message}

            </div>


            <!-- 24時間予報 -->

            <div class="section-title">

                今後24時間の予報

            </div>


            <div class="table-wrapper">

                <table>

                    <thead>

                        <tr>

                            <th>
                                時刻
                            </th>

                            <th>
                                気圧
                            </th>

                            <th>
                                天気
                            </th>

                            <th>
                                気温
                            </th>

                            <th>
                                湿度
                            </th>

                            <th>
                                降水
                            </th>

                            <th>
                                判定
                            </th>

                        </tr>

                    </thead>


                    <tbody>

                        {rows_html}

                    </tbody>

                </table>

            </div>


            <div class="note">

                ※ 上段の気圧は標高約500m地点の気圧です。<br>

                ※ 下段の数値は海面更正気圧です。<br>

                ※ 気温の下段は麓（伊豆熱川駅付近）の気温です。<br>

                ※ 画面は10分ごとに自動更新します。

            </div>


        </div>

    </body>

    </html>
    """


# Render用ポート設定
port = int(
    os.environ.get(
        "PORT",
        5000
    )
)


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=port
    )