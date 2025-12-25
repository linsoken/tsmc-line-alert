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
            
            # 修正 1：相容 Locations 或 locations
            locs_container = records.get("Locations") or records.get("locations")
            if not locs_container: continue
            
            # 修正 2：相容 location 欄位
            locations = locs_container[0].get("location") or locs_container[0].get("Location")
            if not locations: continue

            for loc in locations:
                name = loc.get("locationName", "").replace("區", "").replace("鄉", "").replace("市", "")
                
                # 修正 3：相容 weatherElement 大小寫
                w_elements = loc.get("weatherElement") or loc.get("WeatherElement")
                if not w_elements: continue
                
                # 修正 4：相容 elementName 大小寫
                elements = {
                    (e.get('elementName') or e.get('ElementName')): e['time'][0]['elementValue'][0]['value'] 
                    for e in w_elements
                }
                
                t = elements.get('T') or elements.get('Temperature', '--')
                wx = elements.get('Wx') or elements.get('Weather', '--')
                pop = elements.get('PoP12h') or elements.get('ProbabilityOfPrecipitation', '0')
                weather_cache[name] = f"{name} {t}°{wx}({pop}%)"
        except Exception as e:
            print(f"DEBUG: 解析 {api_id} 失敗: {e}")
            continue

    if not weather_cache: return "❌ 氣象資料解析失敗"

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    for group in [taipei_list, new_taipei_list, yilan_list]:
        nodes = [weather_cache[n] for n in group if n in weather_cache]
        if nodes: final_msg += "\n".join(nodes) + "\n\n"
    
    final_msg += "天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg.strip()

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
        # 手動測試用
        send_line_message_to_all(all_users, get_weather_report())

if __name__ == "__main__":
    main()
