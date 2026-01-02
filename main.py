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
            # 鄉鎮預報 API 篩選路徑
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{item['id']}?Authorization={CWA_KEY}&format=JSON&locationName={item['name']}&elementName=Wx,MinT,MaxT,PoP12h"
            r = requests.get(url, timeout=12)
            
            if r.status_code == 200:
                data = r.json()
                # 自動尋找 location 節點，適應篩選後的結構
                records = data.get('records', {})
                # 在篩選模式下，location 可能直接存在於 records 下，或在 locations[0] 裡
                locations_node = records.get('locations', [{}])[0]
                loc_list = locations_node.get('location', records.get('location', []))
                
                if loc_list:
                    loc_data = loc_list[0]
                    elements = loc_data.get('weatherElement', [])
                    e_map = {}
                    for elem in elements:
                        e_name = elem.get('elementName')
                        # 遍歷時間段尋找有效值
                        for t_block in elem.get('time', []):
                            val = t_block.get('elementValue', [{}])[0].get('value')
                            if val and val.strip() and val != " ":
                                e_map[e_name] = val
                                break
                    
                    wx = e_map.get('Wx', '未知')
                    mint = e_map.get('MinT', '--')
                    maxt = e_map.get('MaxT', '--')
                    pop = e_map.get('PoP12h', '0')
                    results.append(f"📍 {item['name']} {mint}~{maxt}° {wx} (降雨{pop}%)")
                else:
                    results.append(f"📍 {item['name']} 找不到區域資料")
            else:
                results.append(f"📍 {item['name']} 服務忙碌")
        except Exception as e:
            print(f"Error fetching {item['name']}: {e}")
            results.append(f"📍 {item['name']} 讀取超時")
            
    return "\n".join(results)

def main():
    # 1. 取得用戶 (Cloudflare KV)
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
        print(f"✅ 成功讀取用戶數: {len(users)}")
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
    final_msg = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n{weather_report}\n\n{price_info}\n\n天氣變化多留意，祝吉祥如意，平安幸福。"

    # 4. LINE 發送
    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        res = requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE 回應: {res.status_code}, {res.text}")

if __name__ == "__main__":
    main()
