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
    dist_configs = [
        {"id": "063", "name": "北投區"},
        {"id": "063", "name": "萬華區"},
        {"id": "063", "name": "信義區"},
        {"id": "071", "name": "淡水區"},
        {"id": "003", "name": "礁溪鄉"}
    ]
    
    city_cache = {}
    results = []
    
    for item in dist_configs:
        api_id = f"F-D0047-{item['id']}"
        try:
            if api_id not in city_cache:
                url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&elementName=Wx,MinT,MaxT,PoP12h"
                r = requests.get(url, timeout=20)
                data = r.json()
                # 取得該縣市所有的區資料清單
                city_cache[api_id] = data['records']['locations'][0]['location']
            
            # 從清單中找出名稱完全符合的行政區
            target = next(loc for loc in city_cache[api_id] if loc['locationName'] == item['name'])
            
            e_map = {}
            for elem in target['weatherElement']:
                # 遍歷時間段，找到第一個有值的 elementValue
                for t in elem['time']:
                    val = t['elementValue'][0]['value']
                    if val and val.strip():
                        e_map[elem['elementName']] = val
                        break
            
            wx = e_map.get('Wx', '未知')
            mint = e_map.get('MinT', '--')
            maxt = e_map.get('MaxT', '--')
            pop = e_map.get('PoP12h', '0')
            results.append(f"📍 {item['name']} {mint}~{maxt}° {wx} (降雨{pop}%)")
            
        except Exception as e:
            print(f"DEBUG: {item['name']} 發生錯誤: {e}")
            results.append(f"📍 {item['name']} 讀取失敗")
            
    return "\n".join(results)

def main():
    # 1. 取得 LINE 用戶 ID
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [k['name'] for k in r.json().get('result', [])]
    except: return

    # 2. 抓取台積電股價
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: price_info = "📈 股價資訊更新中"

    # 3. 組合訊息
    now = datetime.utcnow() + timedelta(hours=8)
    weather_report = get_precise_weather()
    final_msg = (
        f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n"
        f"{weather_report}\n\n"
        f"{price_info}\n\n"
        f"天氣變化多留意，祝吉祥如意，平安幸福。"
    )

    # 4. LINE 推播
    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
