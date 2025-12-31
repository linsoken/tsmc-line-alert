import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def main():
    # 1. 取得用戶 ID
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=5)
        users = [item['name'] for item in r.json().get('result', [])]
        print(f"✅ 成功讀取用戶數: {len(users)}")
    except:
        print("❌ KV 讀取失敗")
        return

    # 2. 抓取股價
    price_info = "📢 股價抓取暫時失效"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 抓取氣象 (極速版)
    weather_info = "🌦 氣象資料更新中..."
    try:
        # 只抓台北市作為代表，減少請求次數提高成功率
        api_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-063?Authorization={CWA_KEY}&format=JSON&locationName=北投區,萬華區,信義區"
        wr = requests.get(api_url, timeout=5)
        if wr.status_code == 200:
            data = wr.json()
            locs = data['records']['locations'][0]['location']
            weather_info = "🌤 一分鐘報天氣 🌤\n"
            for l in locs:
                name = l['locationName']
                elems = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in l['weatherElement']}
                weather_info += f"\n📍 {name} {elems.get('MinT')}~{elems.get('MaxT')}° {elems.get('Wx')}"
    except:
        weather_info = "🌦 氣象連線超時，請稍後再試"

    # 4. 合併內容並發送 (只發一次，保證內容不遺失)
    final_msg = f"{weather_info}\n\n{price_info}\n\n祝您吉祥如意，平安幸福。"
    
    if users:
        url = "https://api.line.me/v2/bot/message/multicast"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE 回應: {res.status_code}, {res.text}")

if __name__ == "__main__":
    main()
