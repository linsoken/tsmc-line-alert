import requests
import os
import json
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def get_district_weather():
    """精確抓取行政區資料，並具備縣市級備援"""
    # 定義行政區及其所屬縣市代碼 (F-D0047 系列)
    districts = {
        "北投區": "F-D0047-063",
        "萬華區": "F-D0047-063",
        "信義區": "F-D0047-063",
        "淡水區": "F-D0047-071",
        "礁溪鄉": "F-D0047-003"
    }
    
    weather_results = []
    # 建立一個暫存，避免重複請求同一個縣市 API
    api_cache = {}

    for dist_name, api_id in districts.items():
        try:
            # 檢查快取是否有該縣市資料
            if api_id not in api_cache:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON"
                r = requests.get(url, timeout=8)
                if r.status_code == 200:
                    api_cache[api_id] = r.json()['records']['locations'][0]['location']
            
            # 從資料中找出該行政區
            found = False
            if api_id in api_cache:
                for loc in api_cache[api_id]:
                    if loc['locationName'] == dist_name:
                        e = {elem['elementName']: elem['time'][0]['elementValue'][0]['value'] for elem in loc['weatherElement']}
                        weather_results.append(f"📍 {dist_name} {e.get('MinT')}~{e.get('MaxT')}° {e.get('Wx')} (降雨{e.get('PoP12h') or e.get('PoP') or '0'}%)")
                        found = True
                        break
            
            if not found:
                weather_results.append(f"📍 {dist_name} 讀取中...")
        except:
            weather_results.append(f"📍 {dist_name} 稍後更新")

    return "\n".join(weather_results)

def main():
    # 1. 取得用戶 ID
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except: return

    # 2. 抓取台積電股價
    price_info = "📈 TSMC 股價更新中"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 取得精確氣象
    weather_report = get_district_weather()
    now = datetime.utcnow() + timedelta(hours=8)
    date_str = now.strftime("%m/%d")

    # 4. 組合訊息
    final_msg = (
        f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        f"{weather_report}\n\n"
        f"{price_info}\n\n"
        f"天氣變化多留意，祝福吉祥如意，平安幸福。"
    )

    # 5. 發送
    if users:
        url = "https://api.line.me/v2/bot/message/multicast"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post(url, headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
