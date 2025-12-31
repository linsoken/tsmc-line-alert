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
# 氣象預報函式 (強化時間匹配邏輯)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"
    
    # 063: 台北市, 071: 新北市, 003: 宜蘭縣
    api_ids = ["F-D0047-063", "F-D0047-071", "F-D0047-003"]
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    
    weather_map = {}
    now_utc = datetime.utcnow() + timedelta(hours=8) # 台灣現在時間
    
    for api_id in api_ids:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {"Authorization": CWA_API_KEY, "format": "JSON", "elementName": "Wx,PoP12h,MinT,MaxT"}
        try:
            r = requests.get(url, params=params, timeout=25)
            data = r.json()
            locations = data.get("records", {}).get("locations", [{}])[0].get("location", [])
            
            for loc in locations:
                dist_name = loc.get("locationName")
                if dist_name in target_districts:
                    elements = loc.get("weatherElement", [])
                    info = {}
                    for elem in elements:
                        eid = elem.get("elementName")
                        # 尋找「結束時間」晚於「現在時間」的第一筆預報
                        for time_slot in elem.get("time", []):
                            end_time_str = time_slot.get("endTime", "")
                            if end_time_str:
                                end_dt = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")
                                if end_dt > now_utc:
                                    val = time_slot.get("elementValue", [{}])[0].get("value")
                                    info[eid] = val
                                    break # 找到合適的時段就跳出
                    weather_map[dist_name] = info
        except Exception as e:
            print(f"API {api_id} 解析出錯: {e}")

    # 組合訊息
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    for dist in target_districts:
        w = weather_map.get(dist)
        # 檢查關鍵欄位是否都有抓到
        if w and w.get('Wx') and w.get('MinT'):
            msg += f"📍 {dist} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {dist} 氣象更新中\n"

    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 台積電股價抓取 (保留原始邏輯)
# ------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except: return None

def get_price_from_finmind():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")}
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json()["data"][-1]["close"]
    except: return None

def get_tsmc_price():
    p = get_price_from_yahoo()
    if p: return p
    p = get_price_from_finmind()
    if p: return p
    raise Exception("無法取得股價")

# ------------------------------
# 基礎設施函式 (KV, LINE)
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]): return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return [item['name'] for item in r.json().get('result', [])]
    except: return []

def send_line_message_to_all(user_ids, message):
    if not user_ids or not message: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(user_ids), 500):
        body = {"to": user_ids[i:i + 500], "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=body, timeout=10)

# ------------------------------
# 主程式
# ------------------------------
def main():
    users = get_all_user_ids_from_cloudflare()
    if not users: return

    tw_hour = (datetime.utcnow() + timedelta(hours=8)).hour

    if tw_hour == 7:
        send_line_message_to_all(users, get_weather_report())
    elif 13 <= tw_hour <= 15:
        try:
            p = get_tsmc_price()
            if p >= TSMC_TARGET_PRICE:
                send_line_message_to_all(users, f"📈 台積電股價已達 {p} 元！")
            if tw_hour == 14:
                send_line_message_to_all(users, f"📢 TSMC 今日參考價：{p} 元")
        except: pass
    else:
        # 測試模式
        send_line_message_to_all(users, get_weather_report())
        try:
            p = get_tsmc_price()
            send_line_message_to_all(users, f"📢 測試成功：股價 {p} 元")
        except: pass

if __name__ == "__main__":
    main()
