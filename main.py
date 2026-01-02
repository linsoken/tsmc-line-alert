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
            # 使用篩選器，只抓該區的 Wx, MinT, MaxT, PoP12h
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{item['id']}?Authorization={CWA_KEY}&format=JSON&locationName={item['name']}&elementName=Wx,MinT,MaxT,PoP12h"
            r = requests.get(url, timeout=12)
            
            if r.status_code == 200:
                data = r.json()
                # 關鍵修正：針對篩選後的結構進行極簡化抓取
                # 結構通常為: records -> locations[0] -> location[0]
                records = data.get('records', {})
                locs_node = records.get('locations', [{}])[0]
                loc_data = locs_node.get('location', [{}])[0]
                
                elements = loc_data.get('weatherElement', [])
                # 將天氣元素存入字典，取第一筆時間區間的值
                e_map = {}
                for elem in elements:
                    name = elem.get('elementName')
                    times = elem.get('time', [])
                    if times:
                        val = times[0].get('elementValue', [{}])[0].get('value')
                        e_map[name] = val
                
                # 格式化輸出
                wx = e_map.get('Wx', '未知')
                mint = e_map.get('MinT', '--')
                maxt = e_map.get('MaxT', '--')
                pop = e_map.get('PoP12h', '0')
                
                results.append(f"📍 {item['name']} {mint}~{maxt}° {wx} (降雨{pop}%)")
            else:
                results.append(f"📍 {item['name']} 服務繁忙")
        except Exception as e:
            print(f"Error on {item['name']}: {e}")
            results.append(f"📍 {item['name']} 資料讀取中")
            
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

    # 2. 抓取股價與達標判斷
    price_info = ""
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
        if price >= 1600:
            price_info += "\n🚨 【目標達成】台積電已達 1600 元！"
    except: 
        price_info = "📈 股價資訊更新中"

    # 3. 組合訊息
    now = datetime.utcnow() + timedelta(hours=8)
    weather_report = get_precise_weather()
    
    final_msg = (
        f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n"
        f"{weather_report}\n\n"
        f"{price_info}\n\n"
        f"天氣變化多留意，祝吉祥如意，平安幸福。"
    )

    # 4. 發送 LINE Multicast
    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        res = requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE 回應: {res.status_code}, {res.text}")

if __name__ == "__main__":
    main()
