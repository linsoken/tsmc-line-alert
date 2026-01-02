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
    # 重新校準行政區 ID 與 關鍵字 (去除所有"區/鄉"以增加匹配成功率)
    dist_configs = [
        {"id": "F-D0047-063", "name": "北投", "label": "北投"},
        {"id": "F-D0047-063", "name": "萬華", "label": "萬華"},
        {"id": "F-D0047-063", "name": "信義", "label": "信義"},
        {"id": "F-D0047-071", "name": "淡水", "label": "淡水"},
        {"id": "F-D0047-003", "name": "礁溪", "label": "礁溪"}
    ]
    
    city_cache = {}
    results = []
    
    for item in dist_configs:
        api_id = item["id"]
        search_key = item["name"]
        
        try:
            # 快取縣市資料，避免重複請求
            if api_id not in city_cache:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&elementName=Wx,MinT,MaxT,PoP12h"
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    # 遍歷尋找 location 列表 (這版路徑最穩健)
                    recs = data.get('records', {})
                    locs_node = recs.get('locations', [{}])[0]
                    city_cache[api_id] = locs_node.get('location', [])
                else:
                    city_cache[api_id] = []

            # 模糊匹配：只要行政區名稱包含 "北投" 就能抓到 "北投區"
            target_loc = next((l for l in city_cache[api_id] if search_key in l.get('locationName', '')), None)
            
            if target_loc:
                e_map = {}
                for elem in target_loc.get('weatherElement', []):
                    name = elem.get('elementName')
                    for t in elem.get('time', []):
                        val = t.get('elementValue', [{}])[0].get('value')
                        if val is not None and str(val).strip():
                            e_map[name] = val
                            break
                
                wx = e_map.get('Wx', '未知')
                mint = e_map.get('MinT', '--')
                maxt = e_map.get('MaxT', '--')
                pop = e_map.get('PoP12h', '0')
                results.append(f"📍 {item['label']}區 {mint}~{maxt}° {wx} (降雨{pop}%)")
            else:
                results.append(f"📍 {item['label']}區 更新中")
                
        except:
            results.append(f"📍 {item['label']}區 讀取中")
            
    return "\n".join(results)

def main():
    # 1. 取得用戶 (Cloudflare KV)
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except: return

    # 2. 抓取股價 (台積電)
    price_info = ""
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
        if price >= 1600:
            price_info += "\n🚨 【目標達成】台積電已達 1600 元！"
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
