import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_KEY = os.environ.get("CWA_API_KEY")

def get_weather_stable():
    """改用穩定度最高的縣市預報 API"""
    # 只需要請求一次這個 API 就能拿到全台灣資料
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_KEY}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200: return "🌦 氣象資料連線異常"
        
        data = r.json()
        raw_locs = data['records']['location']
        
        # 建立縣市查找表
        weather_map = {}
        for loc in raw_locs:
            name = loc['locationName']
            elems = {e['elementName']: e['time'][0]['parameter']['parameterName'] for e in loc['weatherElement']}
            weather_map[name] = elems

        # 將原本的行政區映射到所屬縣市
        # 北投/萬華/信義 -> 臺北市, 淡水 -> 新北市, 礁溪 -> 宜蘭縣
        report_list = []
        mapping = {
            "北投區": "臺北市", "萬華區": "臺北市", "信義區": "臺北市",
            "淡水區": "新北市", "礁溪鄉": "宜蘭縣"
        }
        
        for dist, city in mapping.items():
            w = weather_map.get(city)
            if w:
                # 這裡格式：📍 北投區 (臺北市) 17~21° 陰天 (降雨10%)
                report_list.append(f"📍 {dist} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP') or '0'}%)")
            else:
                report_list.append(f"📍 {dist} 資料讀取中")
        
        return "\n".join(report_list)
    except Exception as e:
        print(f"Weather Error: {e}")
        return "🌦 氣象署伺服器維護中"

def main():
    # 1. 取得用戶 ID
    users = []
    try:
        kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(kv_url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except: return

    # 2. 抓取股價
    price_info = "📈 TSMC 股價資訊更新中"
    try:
        p_res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        price = p_res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        price_info = f"📈 TSMC 目前股價：{price} 元"
    except: pass

    # 3. 取得氣象 (改用穩定版)
    weather_report = get_weather_stable()

    # 4. 組合與發送
    now = datetime.utcnow() + timedelta(hours=8)
    final_msg = f"🌤 一分鐘報天氣 {now.strftime('%m/%d')} 🌤\n\n{weather_report}\n\n{price_info}\n\n天氣變化多留意，祝福吉祥如意，平安幸福。"

    if users:
        url = "https://api.line.me/v2/bot/message/multicast"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"to": users, "messages": [{"type": "text", "text": final_msg}]}
        requests.post(url, headers=headers, json=payload, timeout=10)

if __name__ == "__main__":
    main()
