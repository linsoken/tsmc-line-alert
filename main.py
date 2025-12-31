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
    # 配置各行政區對應的 API ID
    dist_configs = [
        {"id": "F-D0047-063", "name": "北投區"},
        {"id": "F-D0047-063", "name": "萬華區"},
        {"id": "F-D0047-063", "name": "信義區"},
        {"id": "F-D0047-071", "name": "淡水區"},
        {"id": "F-D0047-003", "name": "礁溪鄉"}
    ]
    
    weather_results = []
    
    for item in dist_configs:
        api_id = item["id"]
        dist_name = item["name"]
        try:
            # 使用篩選器縮小資料量，僅抓取必要元素
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_KEY}&format=JSON&locationName={dist_name}&elementName=Wx,MinT,MaxT,PoP12h"
            r = requests.get(url, timeout=12)
            
            if r.status_code == 200:
                data = r.json()
                # 修正處：篩選後的結構會直接跳到 location，我們用更保險的層級存取
                records = data.get('records', {})
                # 鄉鎮預報 API 結構：records -> locations[0] -> location[0]
                loc_list = records.get('locations', [{}])[0].get('location', [])
                
                if loc_list:
                    loc_data = loc_list[0]
                    # 解析天氣元素
                    elements = loc_data.get('weatherElement', [])
                    e = {elem['elementName']: elem['time'][0]['elementValue'][0]['value'] for elem in elements}
                    
                    wx = e.get('Wx', '未知')
                    mint = e.get('MinT', '--')
                    maxt = e.get('MaxT', '--')
                    pop = e.get('PoP12h', '0')
                    
                    weather_results.append(f"📍 {dist_name} {mint}~{maxt}° {wx} (降雨{pop}%)")
                else:
                    weather_results.append(f"📍 {dist_name} 找不到地區資料")
            else:
                weather_results.append(f"📍 {dist_name} 服務繁忙({r.status_code})")
        except Exception as e:
            print(f"Error fetching {dist_name}: {e}")
            weather_results.append(f"📍 {dist_name} 讀取逾時")
            
    return "\n".join(weather_results)

def main():
    # 1. 取得用戶 (Cloudflare KV)
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
        print(f"✅ 成功讀取用戶數: {len(users)}")
    except Exception as e:
        print(f"❌ KV 讀取失敗: {e}")
        return

    # 2. 抓取股價
    price_info = "📈 TSMC 股價更新中"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 取得氣象
    weather_report = get_precise_weather()
    now = datetime.utcnow() + timedelta(hours=8)
    
    # 4. 組合訊息
    final_msg = (
        f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n"
        f"{weather_report}\n\n"
        f"{price_info}\n\n"
        f"天氣變化多留意，祝福吉祥如意，平安幸福。"
    )

    # 5. LINE 發送
    if users:
        url = "https://api.line.me/v2/bot/message/multicast"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE 回應: {res.status_code}, {res.text}")

if __name__ == "__main__":
    main()
