import requests
import os
import time
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def get_weather_with_retry(api_id, districts):
    """帶有重試機制的氣象抓取"""
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&locationName={','.join(districts)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 嘗試 2 次
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                return data['records']['locations'][0]['location']
            print(f"⚠️ {api_id} 嘗試第 {attempt+1} 次失敗: 狀態碼 {r.status_code}")
        except Exception as e:
            print(f"⚠️ {api_id} 嘗試第 {attempt+1} 次錯誤: {e}")
        
        if attempt == 0:
            time.sleep(2)  # 失敗後休息 2 秒再試
    return None

def get_weather_data():
    targets = {
        "F-D0047-063": ["北投區", "萬華區", "信義區"],
        "F-D0047-071": ["淡水區"],
        "F-D0047-003": ["礁溪鄉"]
    }
    weather_results = []
    
    for api_id, districts in targets.items():
        locations = get_weather_with_retry(api_id, districts)
        
        if locations:
            for loc in locations:
                name = loc['locationName']
                # 提取天氣現象、最高溫、最低溫、降雨機率
                try:
                    elems = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in loc['weatherElement']}
                    weather_results.append(f"📍 {name} {elems.get('MinT')}~{elems.get('MaxT')}° {elems.get('Wx')} (降雨{elems.get('PoP12h')}%)")
                except:
                    weather_results.append(f"📍 {name} 資料格式解析異常")
        else:
            for d in districts:
                weather_results.append(f"📍 {d} 氣象署伺服器繁忙")
        
        time.sleep(1) # 不同 API 間隔 1 秒，避免被封鎖
    
    return "\n".join(weather_results)

def main():
    # 1. 取得用戶 ID
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except:
        return

    # 2. 抓取股價 (Yahoo Finance)
    price_info = "📈 TSMC 股價資訊更新中"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 取得氣象資料 (強化版)
    weather_report = get_weather_data()

    # 4. 組合訊息
    now = datetime.utcnow() + timedelta(hours=8)
    date_header = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤"
    final_msg = f"{date_header}\n\n{weather_report}\n\n{price_info}\n\n天氣變化多留意，祝福吉祥如意，平安幸福。"

    # 5. 發送 LINE
    if users:
        url = "https://api.line.me/v2/bot/message/multicast"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post(url, headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
