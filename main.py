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

TSMC_TARGET_PRICE = 1600  # 您要通知的價格門檻

# ------------------------------
# 氣象預報函式 (分縣市精確抓取，解決讀取中問題)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"
    
    # 063: 台北市, 071: 新北市, 003: 宜蘭縣
    api_ids = ["F-D0047-063", "F-D0047-071", "F-D0047-003"]
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    
    weather_map = {}
    
    for api_id in api_ids:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {
            "Authorization": CWA_API_KEY,
            "format": "JSON",
            "elementName": "Wx,PoP12h,MinT,MaxT"
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                print(f"API {api_id} 請求失敗")
                continue
                
            data = r.json()
            # 取得該縣市下的所有鄉鎮
            locations = data.get("records", {}).get("locations", [{}])[0].get("location", [])
            
            for loc in locations:
                dist_name = loc.get("locationName")
                if dist_name in target_districts:
                    elements = loc.get("weatherElement", [])
                    info = {}
                    for elem in elements:
                        eid = elem.get("elementName")
                        times = elem.get("time", [])
                        if times:
                            # 抓取第一時段預報值
                            val = times[0].get("elementValue", [{}])[0].get("value")
                            info[eid] = val
                    weather_map[dist_name] = info
        except Exception as e:
            print(f"抓取 API {api_id} 出錯: {e}")

    # 組合時間與星期
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    # 按照您要求的順序輸出
    for dist in target_districts:
        w = weather_map.get(dist)
        if w and w.get('Wx'):
            # 格式：📍 北投區 17~21° 陰時多雲短暫雨 (降雨60%)
            msg += f"📍 {dist} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {dist} 資料讀取中\n"

    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 台積電股價抓取 (Yahoo + FinMind 雙來源)
# ------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200: return None
        data = r.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except: return None

def get_price_from_finmind():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")}
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json()["data"][-1]["close"]
    except: return None

def get_tsmc_price():
    price = get_price_from_yahoo()
    if price is not None:
        print(f"🟢 使用 Yahoo 抓到價格：{price}")
        return price
    price = get_price_from_finmind()
    if price is not None:
        print(f"🟢 使用 FinMind 抓到價格：{price}")
        return price
    raise Exception("❌ 無法取得股價")

# ------------------------------
# Cloudflare KV 用戶 ID 取得
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    user_ids = []
    cursor = None
    while True:
        params = {'limit': 1000}
        if cursor: params['cursor'] = cursor
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            data = r.json()
            if not data.get('success'): break
            user_ids.extend([item['name'] for item in data['result']])
            cursor = data.get('result_info', {}).get('cursor')
            if not cursor: break
        except: break
    return user_ids

# ------------------------------
# LINE 推播發送
# ------------------------------
def send_line_message_to_all(user_ids, message):
    if not user_ids or not message: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(user_ids), 500):
        batch_ids = user_ids[i:i + 500]
        body = {"to": batch_ids, "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=body, timeout=10)

# ------------------------------
# 主程式執行逻辑
# ------------------------------
def main():
    all_users = get_all_user_ids_from_cloudflare()
    if not all_users:
        print("❌ 無法取得用戶清單")
        return

    tw_now = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_now.hour

    # 早上 7 點：推播氣象
    if tw_hour == 7:
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)
    
    # 下午 1 點到 3 點：執行台積電監控
    elif 13 <= tw_hour <= 15:
        try:
            price = get_tsmc_price()
            if price >= TSMC_TARGET_PRICE:
                msg = f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）"
                send_line_message_to_all(all_users, msg)
            
            if tw_hour == 14: # 14點發送收盤參考價
                send_line_message_to_all(all_users, f"📢 TSMC 今日收盤/參考價：{price} 元")
        except Exception as e:
            print(f"股價監控出錯: {e}")

    # 其他時間（測試或手動觸發）
    else:
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)
        try:
            price = get_tsmc_price()
            send_line_message_to_all(all_users, f"📢 測試模式：目前股價 {price} 元")
        except:
            print("測試模式股價抓取失敗")

if __name__ == "__main__":
    main()
