import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def get_weather_data():
    # 定義區域與對應的 API 代碼
    targets = {
        "F-D0047-063": ["北投區", "萬華區", "信義區"],
        "F-D0047-071": ["淡水區"],
        "F-D0047-003": ["礁溪鄉"]
    }
    weather_results = []
    
    for api_id, districts in targets.items():
        try:
            # 增加 timeout 到 10 秒給氣象局 API
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&locationName={','.join(districts)}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                locations = r.json()['records']['locations'][0]['location']
                for loc in locations:
                    name = loc['locationName']
                    # 提取天氣現象、最高溫、最低溫、降雨機率
                    elems = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in loc['weatherElement']}
                    weather_results.append(f"📍 {name} {elems.get('MinT')}~{elems.get('MaxT')}° {elems.get('Wx')} (降雨{elems.get('PoP12h')}%)")
        except:
            for d in districts:
                weather_results.append(f"📍 {d} 連線稍慢，更新中")
    
    return "\n".join(weather_results) if weather_results else "🌦 氣象資料暫時無法取得"

def main():
    # 1. 取得用戶 ID
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except:
        print("❌ 用戶讀取失敗")
        return

    # 2. 抓取股價 (Yahoo Finance)
    price_info = "📈 TSMC 股價資訊更新中"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 取得氣象資料
    weather_report = get_weather_data()

    # 4. 組合最終訊息
    now = datetime.utcnow() + timedelta(hours=8)
    date_header = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤"
    
    final_msg = f"{date_header}\n\n{weather_report}\n\n{price_info}\n\n天氣變化多留意，祝福吉祥如意，平安幸福。"

    # 5. 發送 LINE
    if users:
        url = "https://api.line.me/v2/bot/message/multicast"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"🚀 發送結果: {res.status_code}")

if __name__ == "__main__":
    main()
