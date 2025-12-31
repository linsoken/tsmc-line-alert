import requests
import os
import json
from datetime import datetime, timedelta

# --- 環境變數直接讀取 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def send_to_line(user_ids, text):
    if not user_ids or not text: return
    print(f"📡 準備發送 LINE 訊息給 {len(user_ids)} 人...")
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": user_ids, "messages": [{"type": "text", "text": str(text)}]}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE 回應: {r.status_code}, {r.text}")
    except Exception as e:
        print(f"❌ LINE 發送崩潰: {e}")

def get_weather():
    print("☁️ 正在抓取氣象資料...")
    districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    api_ids = {"F-D0047-063": districts, "F-D0047-071": districts, "F-D0047-003": districts}
    results = {}
    
    try:
        for aid in api_ids.keys():
            # 這裡縮短 timeout 到 5 秒，避免卡死
            api_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{aid}?Authorization={CWA_KEY}&format=JSON"
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                locs = data.get('records', {}).get('locations', [{}])[0].get('location', [])
                for l in locs:
                    name = l.get('locationName')
                    if name in districts:
                        info = {e.get('elementName'): e.get('time', [{}])[0].get('elementValue', [{}])[0].get('value') 
                                for e in l.get('weatherElement', [])}
                        results[name] = info
    except Exception as e:
        print(f"⚠️ 氣象抓取中斷: {e}")

    now = datetime.utcnow() + timedelta(hours=8)
    msg = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n"
    for d in districts:
        w = results.get(d)
        if w and w.get('Wx'):
            msg += f"📍 {d} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {d} 資料獲取失敗\n"
    msg += "\n天氣變化多留意，祝福吉祥如意。"
    return msg

def main():
    # 1. 取得用戶 (最優先)
    print("🔍 正在讀取 Cloudflare KV...")
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
        print(f"✅ 成功讀取用戶數: {len(users)}")
    except Exception as e:
        print(f"❌ KV 讀取失敗: {e}")
        return

    # 2. 股價 (次優先)
    print("📈 正在抓取股價...")
    price_msg = "📢 股價抓取失敗"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", 
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_msg = f"📢 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 發送 (分開兩則訊息發送，確保至少收到一則)
    tw_hour = (datetime.utcnow() + timedelta(hours=8)).hour
    
    if tw_hour == 7:
        send_to_line(users, get_weather())
    elif 13 <= tw_hour <= 15:
        send_to_line(users, price_msg)
    else:
        # 測試模式：先發股價，再發天氣
        print("🛠 執行測試發送...")
        send_to_line(users, price_msg)
        send_to_line(users, get_weather())

if __name__ == "__main__":
    main()
