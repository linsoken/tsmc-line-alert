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
# 股價抓取邏輯
# ------------------------------
def get_tsmc_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return None
    except Exception as e:
        print(f"DEBUG: 股價抓取異常: {e}")
        return None

# ------------------------------
# 天氣抓取邏輯
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    taipei_list = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_list = ["淡水", "板橋", "新店"]
    yilan_list = ["礁溪"]
    
    weather_cache = {}

    for api_id in api_ids:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY}, timeout=15)
            data = r.json()
            
            records = data.get("records", {})
            locations_data = records.get("Locations") or records.get("locations")
            
            if not locations_data:
                print(f"DEBUG: {api_id} 無法取得 Locations 資料")
                continue
                
            locations = locations_data[0]["location"]
            for loc in locations:
                name = loc["locationName"].replace("區", "").replace("鄉", "").replace("市", "")
                elements = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in loc['weatherElement']}
                t = elements.get('T') or elements.get('Temperature', '--')
                wx = elements.get('Wx') or elements.get('Weather', '--')
                pop = elements.get('PoP12h') or elements.get('ProbabilityOfPrecipitation', '0')
                weather_cache[name] = f"{name} {t}°{wx}({pop}%)"
        except Exception as e:
            print(f"DEBUG: 天氣 API {api_id} 解析異常: {e}")
            continue

    if not weather_cache:
        return "❌ 氣象資料解析失敗"

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    t_nodes = [weather_cache[n] for n in taipei_list if n in weather_cache]
    if t_nodes: final_msg += "\n".join(t_nodes) + "\n\n"
    
    n_nodes = [weather_cache[n] for n in new_taipei_list if n in weather_cache]
    if n_nodes: final_msg += "\n".join(n_nodes) + "\n\n"
    
    y_nodes = [weather_cache[n] for n in yilan_list if n in weather_cache]
    if y_nodes: final_msg += "\n".join(y_nodes)

    final_msg += "\n\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

# ------------------------------
# Cloudflare & LINE 傳送邏輯
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        print("DEBUG: Cloudflare 環境變數不完整")
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        result = r.json().get('result', [])
        ids = [item['name'] for item in result]
        print(f"DEBUG: 從 KV 取得用戶 ID 數量: {len(ids)}")
        return ids
    except Exception as e:
        print(f"DEBUG: KV 讀取異常: {e}")
        return []

def send_line_message_to_all(user_ids, message):
    if not user_ids or not message:
        print("DEBUG: 沒用戶或沒訊息，取消發送")
        return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    try:
        for i in range(0, len(user_ids), 500):
            body = {"to": user_ids[i:i + 500], "messages": [{"type": "text", "text": message}]}
            r = requests.post(url, headers=headers, json=body, timeout=10)
            print(f"DEBUG: LINE API 回傳狀態碼: {r.status_code}")
    except Exception as e:
        print(f"DEBUG: LINE 發送異常: {e}")

# ------------------------------
# 主程式
# ------------------------------
def main():
    print("--- 程式開始執行 ---")
    all_users = get_all_user_ids_from_cloudflare()
    
    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour
    print(f"DEBUG: 目前台灣小時 = {tw_hour}")

    # 偵錯用：如果不是 7 點也想看結果，可以暫時把下方條件改成 if True:
    if tw_hour == 7:
        print("DEBUG: 進入 7 點天氣任務")
        report = get_weather_report()
        send_line_message_to_all(all_users, report)
    
    elif 13 <= tw_hour <= 15:
        print("DEBUG: 進入下午股價任務")
        price = get_tsmc_price()
        if price:
            if price >= TSMC_TARGET_PRICE:
                send_line_message_to_all(all_users, f"📈 台積電股價已達 {price} 元！")
            send_line_message_to_all(all_users, f"📢 tsmc 今日最新價：{price} 元")
    
    else:
        print(f"DEBUG: 目前時間 {tw_hour} 點不在排程內，不執行推播。")
    
    print("--- 程式執行結束 ---")

if __name__ == "__main__":
    main()
