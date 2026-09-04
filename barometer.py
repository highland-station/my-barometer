from flask import Flaskimport osimport pandas as pdimport requests
app = Flask(__name__)
# 麓：海岸・国道135号周辺（伊豆熱川駅付近）COAST_LAT = 34.8156COAST_LON = 139.0684
# 現地：奈良本1489-23付近（エンジェルフォレスト伊豆熱川など）HIGHLAND_LAT = 34.8346HIGHLAND_LON = 139.0481HIGHLAND_ELEVATION = 500

def get_weather_data(latitude, longitude, elevation=None):
    url = "https://open-meteo.com"
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
        response = requests.get(url, params=params, timeout=15)
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
                "Humi": hourly['relative_humidity_2m'],
                "Rain": hourly["precipitation"],
            }
        )

        df["PressMSL"] = df["PressMSL"].round(1)
        df["SurfacePress"] = df["SurfacePress"].round(1)
        df["Temp"] = df["Temp"].round(1)
        df["Humi"] = df["Humi"].round().astype(int)
        df["Rain"] = df["Rain"].round(1)

        now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")
        future_df = df[df["Time"] >= now]

        return (future_df if not future_df.empty else df).head(24)

    except (requests.RequestException, ValueError, KeyError) as error:
        app.logger.warning("Weather API error: %s", error)
        return None

def create_fallback_data(is_highland):
    now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")

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
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "☔ 雨"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "❄️ 雪"
    if code in (95, 96, 99):
        return "⚡ 雷雨"

    return "☁️ くもり"


@app.route("/")def index():
    highland_df = get_weather_data(
        HIGHLAND_LAT,
        HIGHLAND_LON,
        HIGHLAND_ELEVATION,
    )
    coast_df = get_weather_data(COAST_LAT, COAST_LON)

    highland_fallback = highland_df is None or highland_df.empty
    coast_fallback = coast_df is None or coast_df.empty

    if highland_fallback:
        highland_df = create_fallback_data(is_highland=True)

    if coast_fallback:
        coast_df = create_fallback_data(is_highland=False)

    data_error = highland_fallback or coast_fallback

    # 安全なマージ処理
    coast_temp = coast_df[["Time", "Temp"]].rename(
        columns={"Temp": "CoastTemp"}
    )
    df = highland_df.merge(coast_temp, on="Time", how="left")
    df["CoastTemp"] = df["CoastTemp"].fillna(df["Temp"])

    # 🌟 バグ修正：iloc の後ろに [0] を正確に追加
    current = df.iloc[0]

    current_press = current["SurfacePress"]
    current_forecast_press = current["PressMSL"]
    current_weather = get_weather_string(current["Code"])
    current_temp = current["Temp"]
    current_coast_temp = current["CoastTemp"]
    current_humi = current["Humi"]
    current_rain = current["Rain"]

    if data_error:
        alert_bg = "#fffaf0"
        alert_border = "#ffe4b5"
        alert_text = "#92400e"
        message = (
            "<b>⚠️ データ取得に失敗しています。</b>"
            "<br>一部または全部の数値は仮の参考値です。"
        )
    elif current_forecast_press <= 1005.0:
        alert_bg = "#fdf2f2"
        alert_border = "#fde8e8"
        alert_text = "#9b1c1c"
        message = (
            f"<b>🔴 気圧警戒：{current_forecast_press:.1f} hPa</b>"
            "<br>気圧変化に敏感な方は、無理をせずゆっくり過ごしましょう。"
        )
    elif current_forecast_press <= 1010.0:
        alert_bg = "#fdfaea"
        alert_border = "#fdf6b2"
        alert_text = "#78350f"
        message = (
            f"<b>⚠️ 気圧注意：{current_forecast_press:.1f} hPa</b>"
            "<br>体調の変化に気をつけて過ごしましょう。"
        )
    else:
        alert_bg = "#f3f8fc"
        alert_border = "#e1effa"
        alert_text = "#1e429f"
        message = (
            "<b>🍏 気圧は比較的穏やかです。</b>"
            "<br>水分補給をして、ゆったり過ごしましょう。"
        )

    rows_html = ""

    for _, row in df.iterrows():
        forecast_press = float(row["PressMSL"])

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
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb;">{row["Time"].strftime("%H:%M")}</td>
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb;">
                <b style="color:#1f2937; display:block;">{row["SurfacePress"]:.1f} hPa</b>
                <span style="color:#6b7280; font-size:11px;">(海面: {row["PressMSL"]:.1f})</span>
            </td>
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb;">{get_weather_string(row["Code"])}</td>
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb;">
                <b style="color:#1f2937; display:block;">{row["Temp"]:.1f}℃</b>
                <span style="color:#6b7280; font-size:11px;">(麓: {row["CoastTemp"]:.1f}℃)</span>
            </td>
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb;">{int(row["Humi"])}%</td>
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb;">{row["Rain"]:.1f} mm</td>
            <td style="padding:12px 8px; border-bottom:1px solid #e5e7eb; color:{status_color};"><b>{status}</b></td>
        </tr>
        """

    # 🌟 HTMLテンプレートの波括弧をすべてエスケープし、デザインを最適化
    return f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>伊豆熱川・奈良本ライブ画面</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
                background: #f5f7fa; color: #1f2937; margin: 0; padding: 12px;
            }}
            .container {{
                max-width: 620px; margin: 12px auto; background: #ffffff; padding: 20px; border-radius: 18px;
                box-shadow: 0 6px 18px rgba(31, 41, 55, 0.08);
            }}
            .header-title {{ text-align: center; font-size: 18px; margin: 0 0 16px 0; color: #374151; }}
            .current-box {{ background: #1f2937; color: #ffffff; border-radius: 14px; padding: 18px 14px; margin-bottom: 18px; }}
            .grid-container {{ display: flex; justify-content: space-around; text-align: center; }}
            .grid-item {{ flex: 1; padding: 0 4px; }}
            .grid-item:not(:last-child) {{ border-right: 1px solid #374151; }}
            .label {{ color: #cbd5e1; font-size: 11px; font-weight: bold; margin-bottom: 4px; }}
            .current-val {{ font-size: 15px; font-weight: 700; margin-top: 4px; }}
            .alert-banner {{ background: {alert_bg}; border: 1px solid {alert_border}; color: {alert_text}; padding: 14px; border-radius: 10px; font-size: 13px; line-height: 1.6; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 12px; text-align: left; }}
            th {{ background: #f9fafb; color: #4b5563; padding: 12px 8px; border-bottom: 2px solid #e5e7eb; font-size: 11px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="header-title">エンジェルフォレスト伊豆熱川(500m) & 麓比較</h1>
            
            <div class="current-box">
                <div class="grid-container">
                    <div class="grid-item">
                        <div class="label">現地気圧 (予報基準)</div>
                        <div class="current-val" style="color:#fbbf24;">{current_press:.1f} hPa<br><span style="font-size:10px;color:#9ca3af;font-weight:normal;">({current_forecast_press:.1f} hPa)</span></div>
                    </div>
                    <div class="grid-item">
                        <div class="label">現在の天気</div>
                        <div class="current-val">{current_weather}</div>
                    </div>
                    <div class="grid-item">
                        <div class="label">気温 (現地/麓)</div>

{current_temp:.1f}℃
麓: {current_coast_temp:.1f}℃


現在の湿度
{current_humi}%


現在の降水
{current_rain:.1f}mm


{message}
"""
port = int(os.environ.get("PORT", 5000))
wsgi_app = app.wsgi_app
if name == "main":
app.run(host="0.0.0.0", port=port)