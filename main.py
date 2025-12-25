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
# 原有的股價抓取函式 (保留)
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
# 台北各區 + 礁溪天氣函式
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    
    targets = [{"id": "F-D0047-061", "name": "台北市"}, {"id": "F-D0047-001", "name": "宜蘭縣"}]
    results = []
    
    try:
        for target in targets:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{target['id']}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY})
            locations = r.json()["records"]["locations"][0]["location"]
            
            for loc in locations:
                name = loc["locationName"]
                if target["id"] == "F-D0047-001" and name != "礁溪鄉":
                    continue
                
                # 取得天氣元素 (溫度、天氣現象、降雨機率)
                elements = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in loc['weatherElement']}
                t = elements.get('T', '--')
                wx = elements.get('Wx', '--')
                pop = elements.get('PoP12h', '0')
                
                short_name = name.replace("區", "").replace("鄉", "")
                results.append(f"{short_name}{t}°{wx}(☔{pop}%)")

        # --- 處理中文星期格式 ---
        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        week_str = week_list[tw_time.weekday()] # 0是週一, 6是週日
        date_str = tw_time.strftime(f"%m/%d ({week_str})")

        return f"🌤 一分鐘報天氣 🌤 {date_str}\n" + "，".join(results) + \
               "\n\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    except Exception as e:
        return f"❌ 天氣抓取失敗: {e}"

# ------------------------------
# 原有的 Cloudflare & LINE 函式 (保留)
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]): return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    user_ids = []
    cursor = None
    while True:
        params = {'limit': 1000}
        if cursor: params['cursor'] = cursor
        r = requests.get(url, headers=headers, params=params)
        data = r.json()
        user_ids.extend([item['name'] for item in data['result']])
        cursor = data['result_info'].get('cursor')
        if not cursor: break
    return user_ids

def send_line_message_to_all(user_ids, message):
    if not user_ids: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(user_ids), 500):
        body = {"to": user_ids[i:i + 500], "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=body)

# ------------------------------
# 主程式
# ------------------------------
def main():
    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour
    
    all_users = get_all_user_ids_from_cloudflare()
    if not all_users: return

    # 早上 7 點執行天氣任務 (每天)
    if tw_hour == 7:
        weather_msg = get_weather_report()
        send_line_message_to_all(all_users, weather_msg)
    
    # 下午 14 點執行股價任務 (由 YAML 控制週一至五執行)
    elif 13 <= tw_hour <= 15:
        price = get_tsmc_price()
        if price >= TSMC_TARGET_PRICE:
            msg = f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）"
            send_line_message_to_all(all_users, msg)
        send_line_message_to_all(all_users, f"📢 tsmc 今日收盤價：{price} 元")

if __name__ == "__main__":
    main()
