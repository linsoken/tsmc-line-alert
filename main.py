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
# 氣象預報函式 (升級為鄉鎮區版本 F-D0047-089)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"
    
    # 鄉鎮預報 API (全台灣)
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-089"
    
    # 指定要抓取的目標地區
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    
    # 參數設定：限定縣市可以縮小下載量，提高穩定度
    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "locationName": "臺北市,新北市,宜蘭縣",
        "elementName": "Wx,PoP12h,MinT,MaxT"
    }
    
    try:
        r = requests.get(url, params=params, timeout=25)
        data = r.json()
        
        # 建立一個查找表
        weather_map = {}
        
        # 解析縣市層級
        locations_list = data.get("records", {}).get("locations", [])
        for county in locations_list:
            # 解析鄉鎮區層級
            for loc in county.get("location", []):
                dist_name = loc.get("locationName")
                if dist_name in target_districts:
                    elements = loc.get("weatherElement", [])
                    info = {}
                    for elem in elements:
                        eid = elem.get("elementName")
                        # 取第一時段 (通常是未來 12 小時)
                        val = elem.get("time", [{}])[0].get("elementValue", [{}])[0].get("value")
                        info[eid] = val
                    weather_map[dist_name] = info

        # 組合時間標題
        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

        msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        
        # 依照您要求的順序排列
        for dist in target_districts:
            w = weather_map.get(dist)
            if w:
                # 格式：📍 北投區 17~21° 陰時多雲短暫雨 (降雨60%)
                msg += f"📍 {dist} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
            else:
                msg += f"📍 {dist} 資料讀取失敗\n"

        msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
        return msg
    except Exception as e:
        return f"❌ 氣象解析失敗: {str(e)}"

# ------------------------------
# 台積電股價抓取
# ------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {"User-Agent": "Mozilla/5.0"}
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
        print(f"🟢 使用 Yahoo Finance 抓到價格：{price}")
        return price
    price = get_price_from_finmind()
    if price is not None:
        print(f"🟢 使用 FinMind 抓到價格：{price}")
        return price
    raise Exception("❌ Yahoo + FinMind 都無法取得股價")

# ------------------------------
# Cloudflare KV 用戶取得
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        print("⚠️ 缺少 Cloudflare KV 設定")
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
# LINE 群發推播
# ------------------------------
def send_line_message_to_all(user_ids, message):
    if not user_ids or not message: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(user_ids), 500):
        batch_ids = user_ids[i:i + 500]
        body = {"to": batch_ids, "messages": [{"type": "text", "text": message}]}
        r = requests.post(url, headers=headers, json=body, timeout=10)
        print(f"推播狀態: {r.status_code}")

# ------------------------------
# 主程式邏輯整合
# ------------------------------
def main():
    all_users = get_all_user_ids_from_cloudflare()
    if not all_users:
        print("❌ 無法取得用戶 ID，結束運行。")
        return

    # 取得台灣當前小時
    tw_now = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_now.hour

    # --- 早上 7 點 (UTC 23:00)：推播氣象 ---
    if tw_hour == 7:
        print("執行早晨氣象推播...")
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)
    
    # --- 下午 1 點到 3 點：執行台積電監控 ---
    elif 13 <= tw_hour <= 15:
        print("執行台積電股價監控...")
        try:
            price = get_tsmc_price()
            if price >= TSMC_TARGET_PRICE:
                msg = f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）"
                send_line_message_to_all(all_users, msg)
            
            # 收盤通知 (假設 14 點為主要收盤通知時間)
            if tw_hour == 14:
                daily_msg = f"📢 TSMC 今日參考價：{price} 元"
                send_line_message_to_all(all_users, daily_msg)
        except Exception as e:
            print(f"股價監控出錯: {e}")

    # --- 手動觸發或測試 ---
    else:
        print("非定時區間，執行測試模式...")
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)

if __name__ == "__main__":
    main()
