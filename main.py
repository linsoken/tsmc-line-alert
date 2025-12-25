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
            locs_container = records.get("Locations") or records.get("locations")
            if not locs_container: continue
            locations = locs_container[0].get("location") or locs_container[0].get("Location")
            if not locations: continue

            for loc in locations:
                name = loc.get("locationName", "").replace("區", "").replace("鄉", "").replace("市", "")
                w_elements = loc.get("weatherElement") or loc.get("WeatherElement")
                if not w_elements: continue
                
                # 建立氣象字典，同時支援中文與英文 Key
                elements_map = {}
                for e in w_elements:
                    e_name = e.get('elementName') or e.get('ElementName')
                    times = e.get('time') or e.get('Time')
                    if e_name and times:
                        val_obj = times[0].get('elementValue') or times[0].get('ElementValue')
                        if val_obj:
                            elements_map[e_name] = val_obj[0].get('value', '--')
                
                # 同時檢查中文與英文欄位名稱
                t = elements_map.get('T') or elements_map.get('溫度', '--')
                wx = elements_map.get('Wx') or elements_map.get('天氣現象', '--')
                pop = elements_map.get('PoP12h') or elements_map.get('12小時降雨機率', '0')
                weather_cache[name] = f"{name} {t}°{wx}({pop}%)"
        except:
            continue

    if not weather_cache: return "❌ 氣象資料解析失敗"

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

    final_msg += "\n\n天氣變化多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

def get_all_user_ids_from_cloudflare():
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return [item['name'] for item in r.json().get('result', [])]
    except:
        return []

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
            if price >= TSMC_TARGET_PRICE:
                send_line_message_to_all(all_users, f"📈 台積電股價已達 {price} 元！")
            send_line_message_to_all(all_users, f"📢 tsmc 今日最新價：{price} 元")
    else:
        # 手動執行時發送天氣訊息
        send_line_message_to_all(all_users, get_weather_report())

if __name__ == "__main__":
    main()
