from flask import Flask
import pandas as pd
import math

app = Flask(__name__)

def get_complete_data():
    start_time = pd.Timestamp.now().floor('h')
    times = pd.date_range(start=start_time, periods=24, freq='h')
    
    data = []
    for t in times:
        # 気圧の自動計算 (夕方17時に933hPaの底)
        p_wave = 5 * math.cos((t.hour - 17) * 2 * math.pi / 24)
        press = round(938 + p_wave, 1)
        
        # 気温・湿度の自動計算
        temp = round(20 + 3 * math.sin((t.hour - 9) * 2 * math.pi / 24), 1)
        humi = int(82 - 10 * math.sin((t.hour - 13) * 2 * math.pi / 24))
        
        # 天気とステータス判定
        if 14 <= t.hour <= 19:
            weather = "☔ 雨"
            humi = max(humi, 88)
            status = "🔴 警戒（気圧の底）"
        elif press < 935:
            weather = "☁️ 曇"
            status = "⚠️ 注意"
        else:
            weather = "☁️ 曇"
            status = "正常"
            
        data.append({
            'Time': t.strftime('%H:%M'),
            'Press': press,
            'Weather': weather,
            'Temp': temp,
            'Humi': humi,
            'Status': status
        })
    return data

@app.route('/')
def index():
    data = get_complete_data()
    current = data[0] # 今現在のデータ
    
    # アラートバナーのメッセージ（スマートな表現に修正）
    if "警戒" in current['Status']:
        alert_bg = "#fdf2f2"
        alert_border = "#fde8e8"
        alert_text = "#9b1c1c"
        message = "<b>【気圧警戒】脳の血管が拡張しやすい時間帯です</b><br>内耳への負担が強まっています。お部屋の明かりを落とし、愛犬とともにリラックスしてお過ごしください。"
    elif "注意" in current['Status']:
        alert_bg = "#fdfaea"
        alert_border = "#fdf6b2"
        alert_text = "#723b13"
        message = "<b>【気圧注意】緩やかな低下傾向にあります</b><br>坂道を下りる際は、自律神経の急激な変化を防ぐため、引き続き「時速20〜30km」の減速運転を心がけてください。"
    else:
        alert_bg = "#f3f8fc"
        alert_border = "#e1effa"
        alert_text = "#1e429f"
        message = "<b>【環境安定】現在の気圧は比較的穏やかです</b><br>夕方（15:00〜19:00頃）に予定されている次の気圧低下の波に備え、今のうちに水分を補給しておきましょう。"

    # 時間別の表を組み立て
    rows_html = ""
    for row in data:
        bg = "background:#fffdfd;" if "警戒" in row['Status'] else ("background:#fffdf6;" if "注意" in row['Status'] else "")
        status_color = "#e02424" if "警戒" in row['Status'] else ("#b45309" if "注意" in row['Status'] else "#057a55")
        
        rows_html += f'''
        <tr style="{bg}">
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold;">{row['Time']}</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; font-weight:bold; color:#1f2937;">{row['Press']} <span style="font-size:10px;font-weight:normal;color:#6b7280;">hPa</span></td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#374151;">{row['Weather']}</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#9b1c1c; font-weight:bold;">{row['Temp']}℃</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:#1e429f; font-weight:bold;">{row['Humi']}%</td>
            <td style="padding:14px 8px; border-bottom:1px solid #f3f4f6; color:{status_color}; font-weight:bold; font-size:12px;">{row['Status'].split('（')[0]}</td>
        </tr>
        '''

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Angel Forest Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#f9fafb; margin:0; padding:12px; color:#111827; }}
            .container {{ max-width: 480px; margin: 10px auto; background: white; padding: 20px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }}
            .header {{ text-align: center; border-bottom: 1px solid #f3f4f6; padding-bottom: 14px; }}
            .header h1 {{ font-size: 19px; margin: 0; color: #111827; font-weight: 700; letter-spacing: -0.5px; }}
            .header p {{ font-size: 11px; margin: 6px 0 0 0; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; font-weight: 500; }}
            .current-box {{ display: flex; justify-content: space-around; background: #1f2937; color: white; padding: 16px 10px; border-radius: 12px; margin: 18px 0; text-align: center; }}
            .current-item {{ flex: 1; }}
            .current-val {{ font-size: 19px; font-weight: bold; margin-top: 5px; }}
            .current-label {{ font-size: 10px; color: #9ca3af; font-weight: 500; }}
            .alert-banner {{ background: {alert_bg}; border: 1px solid {alert_border}; color: {alert_text}; padding: 14px; border-radius: 10px; font-size: 13px; text-align: left; line-height: 1.6; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 13px; text-align: left; }}
            th {{ background: #f9fafb; color: #4b5563; padding: 12px 8px; font-weight: 600; border-bottom: 2px solid #e5e7eb; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>エンジェルフォレスト伊豆熱川 (500m)</h1>
                <p>Highland Weather & Pressure Monitor</p>
            </div>
            
            <div class="current-box">
                <div class="current-item" style="border-right: 1px solid #374151;">
                    <div class="current-label">気圧</div>
                    <div class="current-val" style="color:#fbbf24;">{current['Press']} <span style="font-size:11px;">hPa</span></div>
                </div>
                <div class="current-item" style="border-right: 1px solid #374151;">
                    <div class="current-label">天気</div>
                    <div class="current-val">{current['Weather']}</div>
                </div>
                <div class="current-item" style="border-right: 1px solid #374151;">
                    <div class="current-label">気温</div>
                    <div class="current-val" style="color:#f87171;">{current['Temp']}℃</div>
                </div>
                <div class="current-item">
                    <div class="current-label">湿度</div>
                    <div class="current-val" style="color:#60a5fa;">{current['Humi']}%</div>
                </div>
            </div>
            
            <div class="alert-banner">
                {message}
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>時間</th>
                        <th>気圧</th>
                        <th>天気</th>
                        <th>気温</th>
                        <th>湿度</th>
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)