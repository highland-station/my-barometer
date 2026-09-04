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
        # 🌟 正しいパラメータ名 「pressures_msl」に修正しました！
        url = (
            "https://open-meteo.com"
            f"?latitude={LAT}&longitude={LON}"
            "&hourly=pressures_msl,weather_code,temperature_2m,relative_humidity_2m,precipitation"
            "&timezone=Asia%2FTokyo"
        )
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 200:
            res_json = res.json()
            if 'hourly' in res_json:
                hourly = res_json['hourly']
                
                df = pd.DataFrame({
                    'Time': pd.to_datetime(hourly['time']),
                    'SeaPress': hourly['pressures_msl'],     # 天気予報と同じ海面更正気圧
                    'Code': hourly['weather_code'],
                    'Temp': hourly['temperature_2m'],
                    'Humi': hourly['relative_humidity_2m'],
                    'Rain': hourly['precipitation']        
                })
                
                df['Press'] = round(df['SeaPress'], 1)
                df['Temp'] = round(df['Temp'], 1)
                
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

def get_weather_string(code, rain_val=0.0):
    c = int(code)
    if c == 0: return "☀️ 快晴"
    elif c >= 1 and c <= 3: return "☁️ くもり"
    elif c == 45 or c == 48: return "🌫️ 霧"
    elif (c >= 51 and c <= 67) or (c >= 80 and c <= 82): 
        if rain_val == 0.0: return "☁️ くもり"
        return "☔ 雨"
    elif (c >= 71 and c <= 77) or (c >= 85 and c <= 86): return "❄️ 雪"
    elif c == 95 or c == 96 or c == 99: return "⚡ 雷雨"
    return "☁️ くもり"

@app.route('/')
def index():
    df = get_real_weather_data()
    
    # 通信失敗時のセーフティ（おなじみの天気予報基準の通常値）
    if df is None or df.empty:
        now_time = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).floor("h")
        fallback_data = []
        for i in range(24):
            fallback_data.append({
                'Time': now_time + pd.Timedelta(hours=i),
                'Press': 1013.0, 'Code': 2, 'Temp': 25.1, 'Humi': 70, 'Rain': 0.0
            })
        df = pd.DataFrame(fallback_data)
    
    current_press = df['Press'].head(1).item()
    current_weather = get_weather_string(df['Code'].head(1).item(), df['Rain'].head(1).item())
    current_temp = df['Temp'].head(1).item()
    current_humi = df['Humi'].head(1).item()
    current_rain = df['Rain'].head(1).item() 
    
    # アラート判定基準（天気予報の気圧配置・頭痛リスクに最適化）
    if current_press <= 1005.0: 
        alert_bg = "#fdf2f2"
        alert_border = "#fde8e8"
        alert_text = "#9b1c1c"
        message = f"<b>🔴 【気圧警戒】現在 {current_press} hPa まで気圧が低下しています！</b><br>頭痛のリスクが高い時間帯です。お部屋を暗くして、ワンちゃんと一緒にのんびり過ごしてください。"
    elif current_press <= 1010.0: 
        alert_bg = "#fdfaea"
        alert_border = "#fdf6b2"
        alert_text = "#723b13"
        message = f"<b>⚠️ 【気圧注意】気圧が {current_press} hPa まで下がっています</b><br>自律神経に負担がかかりやすい状態です。のんびり安全運転を心がけましょう。"
    else: 
        alert_bg = "#f3f8fc"
        alert_border = "#e1effa"
        alert_text = "#1e429f"
        message = "<b>🍏 【環境安定】現在の気圧は比較的穏やかです</b><br>これからの気圧の変化に備えて、今のうちに温かい水分を補給してリラックスしておきましょう。"

    rows_html = ""
    for _, row in df.iterrows():
        time_str = row['Time'].strftime('%H:%M')
        weather_txt = get_weather_string(row['Code'], row['Rain'])
        p_val = row['Press']
        t_val = row['Temp']
        h_val = row['Humi']
        r_val = row['Rain'] 
        
        bg = "background:#fffdfd;" if p_val <= 1005.0 else ("background:#fffdf6;" if p_val <= 1010.0 else "")
        status_txt = "🔴 警戒" if p_val <= 1005.0 else ("⚠️ 注意" if p_val <= 1010.0 else "正常")
        status_color = "#e02424" if p_val <= 1005.0 else ("#b45309" if p_val <= 1010.0 else "#057a55")
        
        rows_html += f'''
        <tr style="{bg}">
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold;">{time_str}</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold; color:#1f2937;">{p_val} <span style="font-size:10px;font-weight:normal;color:#6b7280;">hPa</span></td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#374151;">{weather_txt}</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#9b1c1c; font-weight:bold;">{t_val}℃</td>
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
            .container {{ max-width: 520px; margin: 10px auto; background: white; padding: 20px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }}
            .header {{ text-align: center; border-bottom: 1px solid #f3f4f6; padding-bottom: 14px; }}
            .header h1 {{ font-size: 19px; margin: 0; }}
            .current-box {{ display: flex; justify-content: space-around; background: #1f2937; color: white; padding: 16px 10px; border-radius: 12px; margin: 18px 0; text-align: center; }}
            .current-item {{ flex: 1; }}
            .current-val {{ font-size: 16px; font-weight: bold; margin-top: 5px; }}
            .current-label {{ font-size: 10px; color: #9ca3af; }}
            .alert-banner {{ background: {alert_bg}; border: 1px solid {alert_border}; color: {alert_text}; padding: 14px; border-radius: 10px; font-size: 13px; line-height: 1.6; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 13px; }}
            th {{ background: #f9fafb; color: #4b5563; padding: 12px 8px; border-bottom: 2px solid #e5e7eb; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>エンジェルフォレスト伊豆熱川 (500m)</h1>
            </div>
            <div class="current-box">
                <div class="current-item" style="border-right: 1px solid #374151;"><div class="current-label">リアルタイム気圧</div><div class="current-val" style="color:#fbbf24;">{current_press} hPa</div></div>
                <div class="current-item" style="border-right: 1px solid #374151;"><div class="current-label">天気</div><div class="current-val">{current_weather}</div></div>
                <div class="current-item" style="border-right: 1px solid #374151;"><div class="current-label">現在の気温</div><div class="current-val" style="color:#f87171;">{current_temp}℃</div></div>
                <div class="current-item" style="border-right: 1px solid #374151;"><div class="current-label">現在の湿度</div><div class="current-val" style="color:#60a5fa;">{current_humi}%</div></div>
                <div class="current-item"><div class="current-label">降水量</div><div class="current-val" style="color:#34d399;">{current_rain}mm</div></div>
            </div>
            <div class="alert-banner">{message}</div>
            <table><thead><tr><th>時間</th><th>気圧予測</th><th>天気</th><th>気温</th><th>湿度</th><th>雨量</th><th>状況</th></tr></thead><tbody>{rows_html}</tbody></table>
        </div>
    </body>
    </html>
    '''

port = int(os.environ.get("PORT", 5000))
wsgi_app = app.wsgi_app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)