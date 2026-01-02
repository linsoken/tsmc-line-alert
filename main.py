import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def get_precise_weather():
    # 定義目標區域及其對應的縣市 API ID
    # 063: 台北市, 071: 新北市, 003: 宜蘭縣
    dist_configs = [
        {"id": "F-D0047-063", "name": "北投"},
        {"id": "F-D0047-063", "name": "萬華"},
        {"id": "F-D0047-063", "name": "信義"},
        {"id": "F-D0047-071", "name": "淡水"},
        {"id": "F-D0047-003", "name": "礁溪"}
    ]
    
    # 預抓取快取，避免重複請求同一個縣市 API
    city_cache = {}
    results = []
    
    for item in dist_configs:
        api_id = item["id"]
        dist_name = item["name"]
        
        try:
            # 如果快取沒有該縣市資料，則請求 API
            if api_id not in city_cache:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&elementName=Wx,MinT,MaxT,PoP12h"
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    # 找到 location 列表所在位置
                    records = r.json().get('records', {})
                    locations = records.get('locations', [{}])[0].get('location', [])
                    city_cache[api_id] = locations
                else:
                    city_cache[api_id] = []

            # 在該縣市資料中尋找匹配的行政區
            target_loc = next((l for l in city_cache[api_id] if dist_name in l.get('locationName', '')), None)
            
            if target_loc:
                e_map = {}
                for elem in target_loc.get('weatherElement', []):
                    name = elem.get('elementName')
                    # 抓取第一個有值且非空的時段
                    for t in elem.get('time', []):
                        val = t.get('elementValue', [{}])[0].get('value')
                        if val is not None and str(val).strip():
                            e_map[name] = val
                            break
                
                wx = e_map.get('Wx', '未知')
                mint = e_map.get('MinT', '--')
                maxt = e_map.get('MaxT', '--')
                pop = e_map.get('PoP12h', '0')
                results.append(f"📍 {dist_name}區 {mint}~{maxt}° {wx} (降雨{pop}%)")
            else:
                results.append(f"📍 {dist_name}區 找無資料")
                
        except Exception as e:
            results.append(f"📍 {dist_name}區 讀取中")
            
    return "\n".join(results)

def main():
    # 1. 取得用戶
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except: return

    # 2. 抓取股價
    price_info = ""
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: price_info = "📈 股價更新中"

    # 3. 組合與發送
    now = datetime.utcnow() + timedelta(hours=8)
    weather_report = get_precise_weather()
    final_msg = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n{weather_report}\n\n{price_info}\n\n天氣變化多留意，祝吉祥如意，平安幸福。"

    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
