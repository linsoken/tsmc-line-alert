import requests
import os
import json
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CWA_API_KEY = os.environ.get("CWA_API_KEY") 

TSMC_TARGET_PRICE = 1800  # 您要通知的價格

# ------------------------------
# 氣象預報函式 (使用最穩定的 F-C0032-001)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"
    
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {"Authorization": CWA_API_KEY, "format": "JSON", "locationName": ["臺北市", "新北市", "宜蘭縣"]}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        locations = data.get("records", {}).get("location", [])
        
        weather_results = {}
        for loc in locations:
            city = loc.get("locationName", "")
            elements = loc.get("weatherElement", [])
            wx = elements[0]['time'][0]['parameter']['parameterName']
            pop = elements[1]['time'][0]['parameter']['parameterName']
            min_t = elements[2]['time'][0]['parameter']['parameterName']
            max_t = elements[4]['time'][0]['parameter']['parameterName']
            weather_results[city] = f"📍 {city} {min_t}~{max_t}° {wx} (降雨{pop}%)"
        
        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

        msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        msg += f"{weather_results.get('臺北市', '📍 臺北市 資料讀取中')}\n"
        msg += f"{weather_results.get('新北市', '📍 新北市 資料讀取中')}\n"
        msg += f"{weather_results.get('宜蘭縣', '📍 宜蘭縣 資料讀取中')}\n\n"
        msg += "飯後起身走走能穩定血糖，每天深蹲有益健康，可增加肌力、強化下肢與核心，對預防骨質疏鬆、改善循環很有幫助! 祝福您吉祥如意闔家平安幸福永相隨。"
        return msg
    except Exception as e:
        return f"❌ 氣象解析失敗: {str(e)}"

# ------------------------------
# 台積電股價抓取 (保留您原本的雙來源邏輯)
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
    params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": "2024-01-01"}
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
            cursor = data['result_info'].get('cursor')
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
        requests.post(url, headers=headers, json=body, timeout=10)

# ------------------------------
# 主程式邏輯整合
# ------------------------------
def main():
    all_users = get_all_user_ids_from_cloudflare()
    if not all_users:
        print("❌ 無法取得用戶 ID，結束運行。")
        return

    # 取得台灣當前小時
    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour

    # --- 早上 7 點：推播氣象 ---
    if tw_hour == 7:
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)
    
    # --- 下午 1 點到 3 點：執行原有的台積電監控 ---
    elif 13 <= tw_hour <= 15:
        price = get_tsmc_price()
        if price >= TSMC_TARGET_PRICE:
            msg = f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）"
            send_line_message_to_all(all_users, msg)
        
        daily_msg = f"📢 tsmc 今日收盤價：{price} 元"
        send_line_message_to_all(all_users, daily_msg)

    # --- 非定時手動觸發：同時執行氣象與股價 (供測試) ---
    else:
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)
        try:
            price = get_tsmc_price()
            send_line_message_to_all(all_users, f"📢 測試抓取股價成功：{price} 元")
        except:
            print("測試股價抓取失敗。")

if __name__ == "__main__":
    main()
