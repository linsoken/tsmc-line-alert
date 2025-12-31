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

TSMC_TARGET_PRICE = 1600

# ------------------------------
# 氣象預報 (極致保險搜尋法)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少氣象金鑰"
    
    api_map = {
        "F-D0047-063": ["北投區", "萬華區", "信義區"],
        "F-D0047-071": ["淡水區"],
        "F-D0047-003": ["礁溪鄉"]
    }
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    weather_map = {}
    
    for api_id, dists in api_map.items():
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY, "format": "JSON"}, timeout=20)
            if r.status_code != 200: continue
            
            data = r.json()
            # 遍歷所有層級尋找 location
            records = data.get('records', {})
            locations_list = records.get('locations', [])
            if not locations_list: continue
            
            locations = locations_list[0].get('location', [])
            for loc in locations:
                name = loc.get('locationName')
                if name in target_districts:
                    info = {}
                    elements = loc.get('weatherElement', [])
                    for elem in elements:
                        e_name = elem.get('elementName')
                        # 抓取第一筆時間資料的數值
                        time_slots = elem.get('time', [])
                        if time_slots:
                            vals = time_slots[0].get('elementValue', [])
                            if vals:
                                info[e_name] = vals[0].get('value')
                    weather_map[name] = info
        except Exception as e:
            print(f"解析 {api_id} 出錯: {e}")

    now = datetime.utcnow() + timedelta(hours=8)
    # 強制手動轉換星期，避免系統語系造成錯誤
    week_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = now.strftime("%m/%d") + f" ({week_map[now.weekday()]})"
    
    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    found_any = False
    for d in target_districts:
        w = weather_map.get(d, {})
        if w.get('Wx'):
            found_any = True
            msg += f"📍 {d} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {d} 更新中\n"
            
    if not found_any:
        return "⚠️ 氣象資料解析失敗，請檢查 API Key 或 CWA 服務狀態。"

    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 台積電股價 (維持正常運作邏輯)
# ------------------------------
def get_tsmc_price():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers=headers, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        try:
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": (datetime.now()-timedelta(days=5)).strftime("%Y-%m-%d")}
            return requests.get(url, params=params, timeout=10).json()["data"][-1]["close"]
        except: return "資料讀取失敗"

# ------------------------------
# 基礎設施
# ------------------------------
def get_users():
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        return [item['name'] for item in r.json().get('result', [])]
    except: return []

def send_line(users, text):
    if not users or not text or "缺少氣象金鑰" in text: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(users), 500):
        payload = {"to": users[i:i+500], "messages": [{"type": "text", "text": text}]}
        requests.post(url, headers=headers, json=payload, timeout=10)

# ------------------------------
# 主程式
# ------------------------------
def main():
    user_list = get_users()
    if not user_list: return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    now_hour = tw_time.hour
    
    # 早上 7 點發天氣
    if now_hour == 7:
        send_line(user_list, get_weather_report())
        
    # 下午 1 點到 3 點監控台積電
    elif 13 <= now_hour <= 15:
        price = get_tsmc_price()
        if isinstance(price, (int, float)):
            if now_hour == 14: # 14點定時回報
                send_line(user_list, f"📢 TSMC 今日參考價：{price} 元")
            if price >= TSMC_TARGET_PRICE: # 達標警報
                send_line(user_list, f"📈 台積電已達標！目前股價：{price} 元")
        else:
            print("股價讀取異常")

    # 測試模式 (其他時間點手動觸發)
    else:
        print("執行測試模式...")
        # 測試天氣
        weather_info = get_weather_report()
        send_line(user_list, weather_info)
        # 測試股價
        price = get_tsmc_price()
        send_line(user_list, f"📢 測試成功！目前股價：{price} 元")

if __name__ == "__main__":
    main()
