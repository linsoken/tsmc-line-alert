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
    # 重新定義目標區域與對應縣市
    dist_configs = [
        {"id": "F-D0047-063", "name": "北投", "label": "北投區"},
        {"id": "F-D0047-063", "name": "萬華", "label": "萬華區"},
        {"id": "F-D0047-063", "name": "信義", "label": "信義區"},
        {"id": "F-D0047-071", "name": "淡水", "label": "淡水區"},
        {"id": "F-D0047-003", "name": "礁溪", "label": "礁溪鄉"}
    ]
    
    city_cache = {}
    results = []
    
    for item in dist_configs:
        api_id = item["id"]
        search_name = item["name"]
        
        try:
            # 1. 快取機制：避免重複請求同一個縣市
            if api_id not in city_cache:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&elementName=Wx,MinT,MaxT,PoP12h"
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    # 遍歷尋找 location 節點
                    locations = []
                    records = data.get('records', {})
                    locs_groups = records.get('locations', [])
                    if locs_groups:
                        locations = locs_groups[0].get('location', [])
                    city_cache[api_id] = locations
                else:
                    city_cache[api_id] = []

            # 2. 強化比對邏輯：只要 API 回傳的地名包含「北投」即可
            target_loc = None
            for loc in city_cache[api_id]:
                api_loc_name = loc.get('locationName', '')
                if search_name in api_loc_name:
                    target_loc = loc
                    break
            
            if target_loc:
                e_map = {}
                for elem in target_loc.get('weatherElement', []):
                    e_name = elem.get('elementName')
                    # 抓取第一筆有效時間段
                    for t_block in elem.get('time', []):
                        val = t_block.get('elementValue', [{}])[0].get('value')
                        if val is not None and str(val).strip():
                            e_map[e_name] = val
                            break
                
                wx = e_map.get('Wx', '未知')
                mint = e_map.get('MinT', '--')
                maxt = e_map.get('MaxT', '--')
                pop = e_map.get('PoP12h', '0')
                results.append(f"📍 {item['label']} {mint}~{maxt}° {wx} (降雨{pop}%)")
            else:
                results.append(f"📍 {item['label']} 資料讀取中")
                
        except Exception as e:
            print(f"Error on {item['label']}: {e}")
            results.append(f"📍 {item['label']} 連線中")
            
    return "\n".join(results)

def main():
    # 1. 取得用戶
    users = []
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

    # 3. 組合訊息
    now = datetime.utcnow() + timedelta(hours=8)
    weather_report = get_precise_weather()
    final_msg = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n{weather_report}\n\n{price_info}\n\n天氣變化多留意，祝吉祥如意，平安幸福。"

    # 4. 發送推播
    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
