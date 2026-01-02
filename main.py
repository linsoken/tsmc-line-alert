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
        {"id": "F-D0047-063", "name": "北投區"},
        {"id": "F-D0047-063", "name": "萬華區"},
        {"id": "F-D0047-063", "name": "信義區"},
        {"id": "F-D0047-071", "name": "淡水區"},
        {"id": "F-D0047-003", "name": "礁溪鄉"}
    ]
    results = []
    
    for item in dist_configs:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{item['id']}?Authorization={CWA_KEY}&format=JSON&locationName={item['name']}&elementName=Wx,MinT,MaxT,PoP12h"
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                results.append(f"📍 {item['name']} 連線異常")
                continue

            data = r.json()
            
            # --- 核心邏輯：暴力搜尋 location 節點 ---
            # 直接從 records 開始往下找任何層級的 location 列表
            records = data.get('records', {})
            
            # 這是鄉鎮預報最穩定的路徑提取方式
            all_locations = []
            if 'locations' in records:
                all_locations = records['locations'][0].get('location', [])
            elif 'location' in records:
                all_locations = records['location']
            
            # 鎖定該行政區
            target_loc = None
            for loc in all_locations:
                if loc.get('locationName') == item['name']:
                    target_loc = loc
                    break
            
            if not target_loc:
                results.append(f"📍 {item['name']} 讀取不到")
                continue

            # 抓取天氣元素
            e_map = {}
            for elem in target_loc.get('weatherElement', []):
                e_name = elem.get('elementName')
                # 遍歷時段直到找到第一個有值的值
                for t in elem.get('time', []):
                    # 部分數值存在於 elementValue 的第一項
                    vals = t.get('elementValue', [])
                    if vals and vals[0].get('value'):
                        e_map[e_name] = vals[0]['value']
                        break
            
            wx = e_map.get('Wx', '未知')
            mint = e_map.get('MinT', '--')
            maxt = e_map.get('MaxT', '--')
            pop = e_map.get('PoP12h', '0')
            
            results.append(f"📍 {item['name']} {mint}~{maxt}° {wx} (降雨{pop}%)")
            
        except Exception as e:
            print(f"Error fetching {item['name']}: {e}")
            results.append(f"📍 {item['name']} 更新中")
            
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

    # 4. 發送
    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
