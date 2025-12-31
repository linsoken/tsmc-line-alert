import requests
import os
import json
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_API_KEY = os.environ.get("CWA_API_KEY")

# ------------------------------
# 1. 基礎發送函式
# ------------------------------
def send_line(users, text):
    if not users or not text: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    payload = {"to": users, "messages": [{"type": "text", "text": str(text)}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"🚀 LINE 發送狀態: {res.status_code}, 回應: {res.text}")
    except Exception as e:
        print(f"❌ LINE 發送失敗: {e}")

# ------------------------------
# 2. 氣象預報解析
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少氣象金鑰"
    
    api_map = {"F-D0047-063": ["北投區", "萬華區", "信義區"], "F-D0047-071": ["淡水區"], "F-D0047-003": ["礁溪鄉"]}
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    weather_map = {}
    
    for api_id, dists in api_map.items():
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            params = {"Authorization": CWA_API_KEY, "format": "JSON"}
            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200: continue
            
            data = r.json()
            # 鄉鎮預報結構
            locations = data.get('records', {}).get('locations', [{}])[0].get('location', [])
            for loc in locations:
                name = loc.get('locationName')
                if name in target_districts:
                    info = {}
                    for elem in loc.get('weatherElement', []):
                        e_name = elem.get('elementName')
                        # 抓取第一筆預報
                        times = elem.get('time', [])
                        if times:
                            val = times[0].get('elementValue', [{}])[0].get('value')
                            info[e_name] = val
                    weather_map[name] = info
        except: continue

    tw_now = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_now.strftime("%m/%d") + f" ({week_list[tw_now.weekday()]})"
    
    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    for d in target_districts:
        w = weather_map.get(d, {})
        if w.get('Wx'):
            msg += f"📍 {d} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {d} 讀取中\n"
    
    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 3. 主程式
# ------------------------------
def main():
    # 取得用戶
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
        print(f"✅ 成功讀取用戶數: {len(users)}")
    except:
        print("❌ 用戶讀取失敗")
        return

    tw_hour = (datetime.utcnow() + timedelta(hours=8)).hour

    # 早上 7 點發天氣
    if tw_hour == 7:
        send_line(users, get_weather_report())
        
    # 下午 1-3 點發股價
    elif 13 <= tw_hour <= 15:
        try:
            r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            price = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            if tw_hour == 14:
                send_line(users, f"📢 TSMC 今日參考價：{price} 元")
        except: pass

    # 測試模式
    else:
        print("🔧 執行測試模式...")
        # 1. 先試發股價 (確保 LINE 通訊沒問題)
        try:
            r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
            p = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            send_line(users, f"📢 測試成功！目前 TSMC 股價：{p} 元")
        except:
            send_line(users, "📢 測試股價抓取失敗")
            
        # 2. 再發天氣
        send_line(users, get_weather_report())

if __name__ == "__main__":
    main()
