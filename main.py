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
# 氣象預報函式
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"
    
    # 063: 台北市, 071: 新北市, 003: 宜蘭縣
    api_ids = ["F-D0047-063", "F-D0047-071", "F-D0047-003"]
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    
    weather_map = {}
    now_utc8 = datetime.utcnow() + timedelta(hours=8)
    
    for api_id in api_ids:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {"Authorization": CWA_API_KEY, "format": "JSON", "elementName": "Wx,PoP12h,MinT,MaxT"}
        try:
            r = requests.get(url, params=params, timeout=25)
            data = r.json()
            locations_group = data.get("records", {}).get("locations", [])
            if not locations_group: continue
            
            locations = locations_group[0].get("location", [])
            for loc in locations:
                dist_name = loc.get("locationName")
                if dist_name in target_districts:
                    elements = loc.get("weatherElement", [])
                    info = {}
                    for elem in elements:
                        e_name = elem.get("elementName")
                        for t in elem.get("time", []):
                            # 檢查時間是否有效 (晚於現在)
                            end_t = t.get("endTime", "").replace("/", "-")
                            try:
                                if datetime.strptime(end_t, "%Y-%m-%d %H:%M:%S") > now_utc8:
                                    vals = t.get("elementValue", [])
                                    if vals:
                                        info[e_name] = vals[0].get("value")
                                        break
                            except: continue
                    weather_map[dist_name] = info
        except Exception as e:
            print(f"氣象 API {api_id} 錯誤: {e}")

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    for dist in target_districts:
        w = weather_map.get(dist, {})
        if w.get('Wx') and w.get('MinT'):
            msg += f"📍 {dist} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {dist} 氣象更新中\n"

    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 台積電股價抓取
# ------------------------------
def get_tsmc_price():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # 來源一: Yahoo
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers=headers, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        try:
            # 來源二: FinMind
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": (datetime.now()-timedelta(days=7)).strftime("%Y-%m-%d")}
            return requests.get(url, params=params, timeout=10).json()["data"][-1]["close"]
        except:
            raise Exception("無法取得股價")

# ------------------------------
# 基礎設施 (KV & LINE)
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not CF_API_TOKEN or not CF_ACCOUNT_ID:
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return [item['name'] for item in r.json().get('result', [])]
    except:
        return []

def send_line_message_to_all(user_ids, message):
    if not user_ids or not message:
        return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    # 每 500 人一組發送
    for i in range(0, len(user_ids), 500):
        body = {
            "to": user_ids[i:i + 500],
            "messages": [{"type": "text", "text": message}]
        }
        res = requests.post(url, headers=headers, json=body, timeout=10)
        print(f"LINE 發送狀態: {res.status_code}, 回應: {res.text}")

# ------------------------------
# 主程式
# ------------------------------
def main():
    users = get_all_user_ids_from_cloudflare()
    if not users:
        print("沒有用戶 ID")
        return

    tw_hour = (datetime.utcnow() + timedelta(hours=8)).hour

    # 定時執行邏輯
    if tw_hour == 7:
        send_line_message_to_all(users, get_weather_report())
    elif 13 <= tw_hour <= 15:
        try:
            price = get_tsmc_price()
            if tw_hour == 14:
                send_line_message_to_all(users, f"📢 TSMC 今日參考價：{price} 元")
            if price >= TSMC_TARGET_PRICE:
                send_line_message_to_all(users, f"📈 台積電股價已達 {price} 元！")
        except Exception as e:
            print(f"股價處理錯誤: {e}")
    else:
        # 測試模式 (Workflow Dispatch 手動觸發時會跑這裡)
        weather_msg = get_weather_report()
        send_line_message_to_all(users, weather_msg)
        try:
            price = get_tsmc_price()
            send_line_message_to_all(users, f"📢 測試成功：目前股價 {price} 元")
        except:
            print("股價抓取測試失敗")

if __name__ == "__main__":
    main()
