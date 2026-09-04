from flask import Flask
import requests
import pandas as pd
import os
app = Flask(__name__)
# 🏡 東伊豆町奈良本
LAT = 34.8156
LON = 139.0684
def get_real_weather_data():
    try:
        # 🌟 チャットGPTのアドバイス通り、elevation=500を指定し、surface_pressureも同時に取得
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}&elevation=500"
            "&hourly=pressure_msl,surface_pressure,weather_code,temperature_2m,relative_humidity_2m,precipitation"
            "&timezone=Asia%2FTokyo"
        )
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 200:
            res_json = res.json()
            if 'hourly' in res_json:
                hourly = res_json['hourly']
                
                # 🌟 APIが算出した正確な海面更正気圧と、標高500mの地表気圧・気温をそのまま使用
                df = pd.DataFrame({
                    'Time': pd.to_datetime(hourly['time']),
                    'Press_MSL': hourly['pressure_msl'],         # 海面更正気圧（天気予報基準）
                    'Press_500m': hourly['surface_pressure'],     # 標高500mの実際の地表気圧
                    'Code': hourly['weather_code'],
                    'Temp_500m': hourly['temperature_2m'],        # 標高500mの実際の気温
                    'Humi': hourly['relative_humidity_2m'],
                    'Rain': hourly['precipitation'],
                    'IsFallback': False                           # 本物のデータであるフラグ
                })
                
                df['Press_MSL'] = round(df['Press_MSL'], 1)
                df['Press_500m'] = round(df['Press_500m'], 1)
                df['Temp_500m'] = round(df['Temp_500m'], 1)
                df["Humi"] = df["Humi"].round().astype(int)
                
                now = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")
                df_filtered = df[df['Time'] >= now]
                
                if not df_filtered.empty:
                    return df_filtered.head(24)
                return df.head(24)
        else:
            print(f"API Error Status Code: {res.status_code}")
    except Exception as e:
        print("API Access Error:", e)
    return None
def get_weather_string(code):
    # 🌟 指摘通り、降水量による上書きを廃止し、APIの天気コードを最優先に判定（霧雨や降り始めも正確に網羅）
    c = int(code)
    if c == 0: return "☀️ 快晴"
    elif c >= 1 and c <= 3: return "☁️ くもり"
    elif c == 45 or c == 48: return "🌫️ 霧"
    elif (c >= 51 and c <= 67) or (c >= 80 and c <= 82): return "☔ 雨"
    elif (c >= 71 and c <= 77) or (c >= 85 and c <= 86): return "❄️ 雪"
    elif c == 95 or c == 96 or c == 99: return "⚡ 雷雨"
    return "☁️ くもり"

@app.route("/")
def index():
    df = get_real_weather_data()
    
    is_fallback = False
    # 🌟 通信失敗時のセーフティ（IsFallbackをTrueにして、ユーザーに障害中であることを明示）
    if df is None or df.empty:
        is_fallback = True
        now_time = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")
        fallback_data = []
        for i in range(24):
            fallback_data.append({
                'Time': now_time + pd.Timedelta(hours=i),
                'Press_MSL': 1013.0, 'Press_500m': 955.0, 
                'Code': 2, 'Temp_500m': 20.0, 
                'Humi': 70, 'Rain': 0.0, 'IsFallback': True
            })
        df = pd.DataFrame(fallback_data)
    
    current_press_msl = df['Press_MSL'].head(1).item()
    current_press_500m = df['Press_500m'].head(1).item()
    current_weather = get_weather_string(df['Code'].head(1).item())
    current_temp_500m = df['Temp_500m'].head(1).item()
    current_humi = df['Humi'].head(1).item()
    current_rain = df['Rain'].head(1).item() 
    
    # 🌟 障害発生時は、上部に目立つ警告バナーを表示する
    if is_fallback:
        alert_bg = "#fffaf0"
        alert_border = "#ffe4b5"
        alert_text = "#b8860b"
        message = "<b>⚠️ 【データ取得失敗】現在、気象APIとの通信ができません。表示されている数値は「過去の平均参考値」です。</b>"
    # 頭痛リスク管理のため、天気予報基準（海面更正気圧）でアラート判定
    elif current_press_msl <= 1005.0: 
        alert_bg = "#fdf2f2"
        alert_border = "#fde8e8"
        alert_text = "#9b1c1c"
        message = f"<b>🔴 【気圧警戒】現在 海面更正気圧が {current_press_msl} hPa まで低下しています！</b><br>頭痛のリスクが高い時間帯です。お部屋を暗くして、ワンちゃんと一緒にのんびり過ごしてください。"
    elif current_press_msl <= 1010.0: 
        alert_bg = "#fdfaea"
        alert_border = "#fdf6b2"
        alert_text = "#723b13"
        message = f"<b>⚠️ 【気圧注意】海面更正気圧が {current_press_msl} hPa まで下がっています</b><br>自律神経に負担がかかりやすい状態です。のんびり安全運転を心がけましょう。"
    else: 
        alert_bg = "#f3f8fc"
        alert_border = "#e1effa"
        alert_text = "#1e429f"
        message = "<b>🍏 【環境安定】現在の気圧は比較的穏やかです</b><br>これからの気圧の変化に備えて、今のうちに温かい水分を補給してリラックスしておきましょう。"

    rows_html = ""
    for _, row in df.iterrows():
        time_str = row['Time'].strftime('%H:%M')
        weather_txt = get_weather_string(row['Code'])
        p_msl = row['Press_MSL']
        p_500m = row['Press_500m']
        t_500m = row['Temp_500m']
        h_val = row['Humi']
        r_val = row['Rain'] 
        
        bg = ""
        if not is_fallback:
            bg = "background:#fffdfd;" if p_msl <= 1005.0 else ("background:#fffdf6;" if p_msl <= 1010.0 else "")
            status_txt = "🔴 警戒" if p_msl <= 1005.0 else ("⚠️ 注意" if p_msl <= 1010.0 else "正常")
            status_color = "#e02424" if p_msl <= 1005.0 else ("#b45309" if p_msl <= 1010.0 else "#057a55")
        else:
            status_txt = "通信障害"
            status_color = "#6b7280"
        
        rows_html += f'''
        <tr style="{bg}">
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold;">{time_str}</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold; color:#1f2937; font-size:11px;">
                海面: {p_msl}<br><span style="color:#057a55;">現地: {p_500m}</span>
            </td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#374151;">{weather_txt}</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold; font-size:12px; color:#9b1c1c;">
                {t_500m}℃
            </td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#1e429f; font-weight:bold;">{h_val}%</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#4b5563;">{r_val} <span style="font-size:10px;color:#9ca3af;">mm</span></td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:{status_color}; font-weight:bold; font-size:12px;">{status_txt}</td>
        </tr>
        '''

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Angel Forest Live Dashboard</title>
        <style>
            body {{ font-family: sans-serif; background:#f9fafb; margin:0; padding:12px; color:#111827; }}
            .container {{ max-width: 540px; margin: 10px auto; background: white; padding: 20px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }}
            .header {{ text-align: center; border-bottom: 1px solid #f3f4f6; padding-bottom: 14px; }}
            .header h1 {{ font-size: 17px; margin: 0; color: #374151; }}
            .current-box {{ background: #1f2937; color: white; padding: 16px 12px; border-radius: 12px; margin: 18px 0; }}
            .grid-row {{ display: flex; justify-content: space-around; text-align: center; margin-bottom: 10px; }}
            .grid-row:last-child {{ margin-bottom: 0; padding-top: 10px; border-top: 1px solid #374151; }}
            .current-item {{ flex: 1; }}
            .current-val {{ font-size: 14px; font-weight: bold; margin-top: 4px; }}
            .current-label {{ font-size: 11px; color: #fbbf24; font-weight: bold; }}
            .sub-label {{ font-size: 10px; color: #9ca3af; }}
            .alert-banner {{ background: {alert_bg}; border: 1px solid {alert_border}; color: {alert_text}; padding: 14px; border-radius: 10px; font-size: 13px; line-height: 1.6; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 12px; }}
            th {{ background: #f9fafb; color: #4b5563; padding: 12px 6px; border-bottom: 2px solid #e5e7eb; font-size: 11px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>エンジェルフォレスト伊豆熱川 (標高500m)</h1>
            </div>
            
            <div class="current-box">
                <!-- 1段目: 広域基準（海面更正） -->
                <div class="grid-row">
                    <div class="current-item" style="color: #fca5a5;"><div class="current-label">海面更正（天気予報基準）</div></div>
                    <div class="current-item"><div class="sub-label">換算気圧</div><div class="current-val">{current_press_msl} hPa</div></div>
                    <div class="current-item" style="display:flex; flex-direction:column; justify-content:center; border-left:1px solid #374151;">
                        <div class="sub-label">天気</div><div class="current-val" style="font-size:15px;">{current_weather}</div>
                    </div>
                </div>
                <!-- 2段目: 現地（標高500m） -->
                <div class="grid-row">
                    <div class="current-item" style="color: #93c5fd;"><div class="current-label" style="color:#60a5fa;">現地（標高500m実態）</div></div>
                    <div class="current-item"><div class="sub-label">地表気圧</div><div class="current-val" style="color:#fbbf24;">{current_press_500m} hPa</div></div>
                    <div class="current-item"><div class="sub-label">気温</div><div class="current-val" style="color:#f87171;">{current_temp_500m}℃</div></div>
<div class="current-item">
    <div class="sub-label">湿度</div>
    <div class="current-val" style="color:#60a5fa;">
        {current_humi}%
    </div>
</div>
                    <div class="current-item" style="display:flex; flex-direction:column; justify-content:center; border-left:1px solid #374151;">
                        <div class="sub-label">降水量</div><div class="current-val" style="color:#34d399;">{current_rain}mm</div>
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
    '''
port = int(os.environ.get("PORT", 5000))
wsgi_app = app.wsgi_app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)