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

def get_tsmc_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        return None

def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    
    # 定義顯示順序
    taipei_order = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_order = ["淡水", "板橋", "新店"]
    yilan_order = ["礁溪"]
    
    weather_cache = {}

    for api_id in api_ids:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY}, timeout=15)
            data = r.json()
            
            # 取得記錄容器
            records = data.get("records", {})
            locs_container = records.get("Locations") or records.get("locations")
            if not locs_container: continue
            
            locations = locs_container[0].get("location") or locs_container[0].get("Location")
            if not locations: continue

            for loc in locations:
                # 清理名稱：將「松山區」轉為「松山」
                raw_name = loc.get("locationName", "")
                clean_name = raw_name.replace("區", "").replace("鄉", "").replace("市", "").replace("鎮", "")
                
                elements = loc.get("weatherElement") or loc.get("WeatherElement")
                if not elements: continue
                
                t, wx, pop = "--", "--", "0"
                for e in elements:
                    e_name = e.get('elementName') or e.get('ElementName')
                    times = e.get('time') or e.get('Time')
                    if not times: continue
                    
                    # 取得第一個時段的值
                    val_obj = times[0].get('elementValue') or times[0].get('ElementValue')
                    val = val_obj[0].get('value', '--') if val_obj else '--'
                    
                    if e_name in ['T', '溫度']: t = val
                    elif e_name in ['Wx', '天氣現象']: wx = val
                    elif e_name in ['PoP12h', '12小時降雨機率']: pop = val
                
                weather_cache[clean_name] = f"{clean_name} {t}°{wx}({pop}%)"
        except:
            continue

    if not weather_cache: return "❌ 氣象資料解析失敗"

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    # 組合訊息
    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    for group in [taipei_order, new_taipei_order, yilan_order]:
        group_lines = [weather_cache[name] for name in group if name in weather_cache]
        if group_lines:
            final_msg += "\n".join(group_lines) + "\n\n"

    final_msg += "天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg.strip()

def get_all_user_ids_from_cloudflare():
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

def main():
    all_users = get_all_user_ids_from_cloudflare()
    if not all_users: return
    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour

    if tw_hour == 7:
        send_line_message_to_all(all_users, get_weather_report())
    elif 13 <= tw_hour <= 15:
        price = get_tsmc_price()
        if price:
            msg = f"📢 tsmc 今日最新價：{price} 元"
            if price >= TSMC_TARGET_PRICE:
                msg = f"📈 台積電股價已達 {price} 元！\n" + msg
            send_line_message_to_all(all_users, msg)
    else:
        # 手動測試用 (非排程時間按 Run 就會發送)
        send_line_message_to_all(all_users, get_weather_report())

if __name__ == "__main__":
    main()
