from flask import Flask
import os

import pandas as pd
import requests

app = Flask(__name__)

# 東伊豆町奈良本
LAT = 34.8156
LON = 139.0684
ELEVATION_M = 500


def get_real_weather_data():
    """標高500m地点の、現在以降24時間分の予報を取得する。"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "elevation": ELEVATION_M,
        "hourly": (
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
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()

        hourly = res.json().get("hourly")
        if not hourly:
            return None

        df = pd.DataFrame(
            {
                "Time": pd.to_datetime(hourly["time"]),
                # APIに elevation=500 を渡しているので、標高補正は不要
                "Press": hourly["surface_pressure"],
                "Code": hourly["weather_code"],
                "Temp": hourly["temperature_2m"],
                "Humi": hourly["relative_humidity_2m"],
                "Rain": hourly["precipitation"],
            }
        )

        df["Press"] = df["Press"].round(1)
        df["Temp"] = df["Temp"].round(1)
        df["Humi"] = df["Humi"].round(0).astype(int)
        df["Rain"] = df["Rain"].round(1)

        now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")
        future_df = df[df["Time"] >= now]

        return (future_df if not future_df.empty else df).head(24)

    except (requests.RequestException, ValueError, KeyError) as error:
        app.logger.warning("Open-Meteo API error: %s", error)
        return None


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
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "☔ 雨"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "❄️ 雪"
    if code in (95, 96, 99):
        return "⚡ 雷雨"

    return "☁️ くもり"


@app.route("/")
def index():
    df = get_real_weather_data()

    # API障害時の表示用データ
    if df is None or df.empty:
        now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")
        df = pd.DataFrame(
            [
                {
                    "Time": now + pd.Timedelta(hours=i),
                    "Press": 947.9,
                    "Code": 2,
                    "Temp": 25.1,
                    "Humi": 70,
                    "Rain": 0.0,
                }
                for i in range(24)
            ]
        )

    current = df.iloc[0]
    current_press = current["Press"]
    current_weather = get_weather_string(current["Code"])
    current_temp = current["Temp"]
    current_humi = current["Humi"]
    current_rain = current["Rain"]

    # 標高500mの地表気圧を前提にした目安
    if current_press <= 943.0:
        alert_bg = "#fdf2f2"
        alert_border = "#fde8e8"
        alert_text = "#9b1c1c"
        message = (
            f"<b>🔴 【気圧警戒】現在 {current_press:.1f} hPa まで気圧が低下しています！</b>"
            "<br>頭痛のリスクが高い時間帯です。お部屋を暗くして、"
            "ワンちゃんと一緒にのんびり過ごしてください。"
        )
    elif current_press <= 948.0:
        alert_bg = "#fdfaea"
        alert_border = "#fdf6b2"
        alert_text = "#723b13"
        message = (
            f"<b>⚠️ 【気圧注意】気圧が {current_press:.1f} hPa まで下がっています</b>"
            "<br>自律神経に負担がかかっています。外出時は安全運転を心がけましょう。"
        )
    else:
        alert_bg = "#f3f8fc"
        alert_border = "#e1effa"
        alert_text = "#1e429f"
        message = (
            "<b>🍏 【環境安定】現在の高原の気圧は比較的穏やかです</b>"
            "<br>温かい水分を補給してリラックスしておきましょう。"
        )

    rows_html = ""

    for _, row in df.iterrows():
        pressure = float(row["Press"])

        if pressure <= 943.0:
            bg = "background:#fffdfd;"
            status = "🔴 警戒"
            status_color = "#e02424"
        elif pressure <= 948.0:
            bg = "background:#fffdf6;"
            status = "⚠️ 注意"
            status_color = "#b45309"
        else:
            bg = ""
            status = "正常"
            status_color = "#057a55"

        rows_html += f"""
        <tr style="{bg}">
            <td>{row["Time"].strftime("%H:%M")}</td>
            <td><b>{pressure:.1f}</b> <small>hPa</small></td>
            <td>{get_weather_string(row["Code"])}</td>
            <td>{float(row["Temp"]):.1f}℃</td>
            <td>{int(row["Humi"])}%</td>
            <td>{float(row["Rain"]):.1f} <small>mm</small></td>
            <td style="color:{status_color};"><b>{status}</b></td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Angel Forest Live Dashboard</title>
        <style>
            body {{
                font-family: sans-serif;
                background: #f9fafb;
                margin: 0;
                padding: 12px;
                color: #111827;
            }}
            .container {{
                max-width: 520px;
                margin: 10px auto;
                background: #fff;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
            }}
            .header {{
                text-align: center;
                border-bottom: 1px solid #f3f4f6;
                padding-bottom: 14px;
            }}
            .header h1 {{
                font-size: 19px;
                margin: 0;
            }}
            .current-box {{
                display: flex;
                justify-content: space-around;
                background: #1f2937;
                color: white;
                padding: 16px 10px;
                border-radius: 12px;
                margin: 18px 0;
                text-align: center;
            }}
            .current-item {{
                flex: 1;
            }}
            .current-val {{
                font-size: 16px;
                font-weight: bold;
                margin-top: 5px;
            }}
            .current-label {{
                font-size: 10px;
                color: #9ca3af;
            }}
            .alert-banner {{
                background: {alert_bg};
                border: 1px solid {alert_border};
                color: {alert_text};
                padding: 14px;
                border-radius: 10px;
                font-size: 13px;
                line-height: 1.6;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 24px;
                font-size: 13px;
            }}
            th, td {{
                padding: 12px 8px;
                border-bottom: 1px solid #f3f4f6;
                text-align: center;
            }}
            th {{
                background: #f9fafb;
                color: #4b5563;
                font-size: 12px;
            }}
            small {{
                color: #6b7280;
                font-weight: normal;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>エンジェルフォレスト伊豆熱川（標高500m）</h1>
            </div>

            <div class="current-box">
                <div class="current-item">
                    <div class="current-label">現在の地表気圧</div>
                    <div class="current-val" style="color:#fbbf24;">
                        {current_press:.1f} hPa
                    </div>
                </div>
                <div class="current-item">
                    <div class="current-label">天気</div>
                    <div class="current-val">{current_weather}</div>
                </div>
                <div class="current-item">
                    <div class="current-label">気温</div>
                    <div class="current-val" style="color:#f87171;">
                        {current_temp:.1f}℃
                    </div>
                </div>
                <div class="current-item">
                    <div class="current-label">湿度</div>
                    <div class="current-val" style="color:#60a5fa;">
                        {current_humi}%
                    </div>
                </div>
                <div class="current-item">
                    <div class="current-label">降水量</div>
                    <div class="current-val" style="color:#34d399;">
                        {current_rain:.1f}mm
                    </div>
                </div>
            </div>

            <div class="alert-banner">{message}</div>

            <table>
                <thead>
                    <tr>
                        <th>時間</th>
                        <th>気圧</th>
                        <th>天気</th>
                        <th>気温</th>
                        <th>湿度</th>
                        <th>雨量</th>
                        <th>状況</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """


port = int(os.environ.get("PORT", 5000))
wsgi_app = app.wsgi_app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)