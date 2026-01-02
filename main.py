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
            # 加上篩選器，讓 API 只回傳特定行政區的四項數據
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{item['id']}?Authorization={CWA_KEY}&format=JSON&locationName={item['name']}&elementName=Wx,MinT,MaxT,PoP12h"
            r = requests.get(url, timeout=12)
            
            if r.status_code == 200:
                data = r.json()
                # 關鍵修正：針對「有篩選器」的特殊結構路徑進行安全抓取
                # 結構通常是 records -> locations[0] -> location[0]
                recs = data.get('records', {})
                locs_node = recs.get('locations', [{}])[0]
                loc_list = locs_node.get('location', [])
                
                if loc_list:
                    loc_data = loc_list[0]
                    elements = loc_data.get('weatherElement', [])
                    
                    # 使用字典存儲，並遍歷時間段（time）尋找第一個非空值
                    e_map = {}
                    for elem in elements:
                        name = elem.get('elementName')
                        for t in elem.get('time', []):
                            val = t.get('elementValue', [{}])[0].get('value')
                            if val and val.strip() and val != " ":
                                e_map[name] = val
                                break
                    
                    wx = e_map.get('Wx', '未知')
                    mint = e_map.get('MinT', '--')
                    maxt = e_map.get('MaxT', '--')
                    pop = e_map.get('PoP12h', '0')
                    
                    results.append(f"📍 {item['name']} {mint}~{maxt}° {wx} (降雨{pop}%)")
                else:
                    results.append(f"📍 {item['name']} 解析無資料")
            else:
                results.append(f"📍 {item['name']} 服務忙碌")
        except:
            results.append(f"📍 {item['name']} 讀取超時")
            
    return "\n".join(results)

def main():
    # 1. 取得用戶 (Cloudflare KV)
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except: return

    # 2. 抓取股價與警報
    price_info = ""
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
        if price >= 1600:
            price_info += "\n🚨 【目標達成】台積電已達 1600 元！"
    except: price_info = "📈 股價資訊更新中"

    # 3. 組合與發送
    now = datetime.utcnow() + timedelta(hours=8)
    weather_report = get_precise_weather()
    
    final_msg = (
        f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n"
        f"{weather_report}\n\n"
        f"{price_info}\n\n"
        f"天氣變化多留意，祝吉祥如意，平安幸福。"
    )

    if users:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post("https://api.line.me/v2/bot/message/multicast", headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
