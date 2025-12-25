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

TSMC_TARGET_PRICE = 1600

# ------------------------------
# 股價抓取函式
# ------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200: return None
    try:
        data = r.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except: return None

def get_price_from_finmind():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": "2024-01-01"}
    try:
        r = requests.get(url, params=params)
        return r.json()["data"][-1]["close"]
    except: return None

def get_tsmc_price():
    price = get_price_from_yahoo()
    if price is not None: return price
    price = get_price_from_finmind()
    if price is not None: return price
    raise Exception("❌ 無法取得股價")

# ------------------------------
# 天氣函式：支援分組斷行與指定順序
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    taipei_list = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_list = ["淡水", "板橋", "新店"]
    yilan_list = ["礁溪"]
    
    weather_cache = {}

    try:
        for api_id in api_ids:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY})
            locations = r.json()["records"]["locations"][0]["location"]
            
            for loc in locations:
                name = loc["locationName"].replace("區", "").replace("鄉", "").replace("市", "")
                elements = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in loc['weatherElement']}
                t = elements.get('T', '--')
                wx = elements.get('Wx', '--')
                pop = elements.get('PoP12h', '0')
                weather_cache[name] = f"{name} {t}°{wx}({pop}%)"

        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

        final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        final_msg += "\n".join([weather_cache[n] for n in taipei_list if n in weather_cache])
        final_msg += "\n\n"
        final_msg += "\n".join([weather_cache[n] for n in new_taipei_list if n in weather_cache])
        final_msg += "\n\n"
        final_msg += "\n".join([weather_cache[n] for n in yilan_list if n in weather_cache])
        final_msg += "\n\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
        
        return final_msg
    except Exception as e:
        return f"❌ 天氣抓取失敗: {e}"

# ------------------------------
# Cloudflare & LINE 函式
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        print("⚠️ 缺少 Cloudflare 環境變數設定")
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    user_ids = []
    cursor = None
    try:
        while True:
            params = {'limit': 1000}
            if cursor: params['cursor'] = cursor
            r = requests.get(url, headers=headers, params=params)
            data = r.json()
            user_ids.extend([item['name'] for item in data['result']])
            cursor = data['result_info'].get('cursor')
            if not cursor: break
        return user_ids
    except Exception as e:
        print(f"❌ 讀取 Cloudflare 失敗: {e}")
        return []

def send_line_message_to_all(user_ids, message):
    if not user_ids: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(user_ids), 500):
        body = {"to": user_ids[i:i + 500], "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=body)

# ------------------------------
# 主程式 (偵錯版)
# ------------------------------
def main():
    print("--- 1. 開始取得用戶清單 ---")
    all_users = get_all_user_ids_from_cloudflare()
    print(f"找到的用戶數量: {len(all_users)}")

    if not all_users:
        print("❌ 停止：Cloudflare 無法取得用戶，請確認 KV 內容與權限。")
        return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour
    print(f"--- 2. 時間判斷 ---")
    print(f"目前台灣小時：{tw_hour}")

    # --- 重要：為了測試天氣，我們加入一條強制執行邏輯 ---
    # 您手動點擊 Run workflow 時，這段會讓天氣訊息發出
    print("--- 3. 執行推播任務 ---")
    
    # 早上 7 點發天氣
    if tw_hour == 7:
        print("觸發早晨天氣任務...")
        msg = get_weather_report()
        send_line_message_to_all(all_users, msg)
        print("✅ 天氣推播成功送出")
    
    # 下午 2 點發股價 (平日執行，Cron 控制)
    elif 13 <= tw_hour <= 15:
        print("觸發下午股價任務...")
        price = get_tsmc_price()
        if price >= TSMC_TARGET_PRICE:
            send_line_message_to_all(all_users, f"📈 台積電股價已達 {price} 元！")
        send_line_message_to_all(all_users, f"📢 tsmc 今日收盤價：{price} 元")
        print("✅ 股價推播成功送出")

    else:
        # 如果非設定時間執行，我們可以強制印出天氣內容但不發送，或者直接強制發送一次測試
        print(f"非排程時間 ({tw_hour}點)，執行強制天氣測試發送...")
        test_msg = get_weather_report()
        send_line_message_to_all(all_users, test_msg)
        print("✅ 測試推播已發送")

if __name__ == "__main__":
    main()
