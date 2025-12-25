import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CWA_API_KEY = os.environ.get("CWA_API_KEY") 

def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    
    # 標準化顯示順序
    taipei_order = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_order = ["淡水", "板橋", "新店"]
    yilan_order = ["礁溪"]
    all_targets = taipei_order + new_taipei_order + yilan_order
    
    weather_cache = {}

    for api_id in api_ids:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY}, timeout=15)
            data = r.json()
            
            # 根據截圖精確定位：records -> Locations[0] -> Location (大寫 L)
            records = data.get("records", {})
            locations_outer = records.get("Locations") or records.get("locations")
            if not locations_outer: continue
            
            # 關鍵點：截圖顯示內部行政區清單的 Key 是 "Location" (單數/大寫)
            location_list = locations_outer[0].get("Location") or locations_outer[0].get("location")
            if not location_list: continue

            for loc in location_list:
                api_name = loc.get("locationName", "")
                
                # 模糊比對地區
                matched_key = None
                for t in all_targets:
                    if t in api_name:
                        matched_key = t
                        break
                
                if not matched_key: continue
                
                # 擷取氣象元素：截圖顯示是 "WeatherElement" (大寫 W)
                elements = loc.get("WeatherElement") or loc.get("weatherElement") or []
                t, wx, pop = "--", "--", "0"
                
                for e in elements:
                    ename = e.get("ElementName") or e.get("elementName") or ""
                    times = e.get("Time") or e.get("time") or []
                    if not times: continue
                    
                    # 擷取數值：截圖顯示是 "ElementValue" (大寫 E)
                    val_list = times[0].get("ElementValue") or times[0].get("elementValue") or []
                    if not val_list: continue
                    
                    # 針對溫度 (T) 和 降雨機率 (PoP12h) 取值
                    val = val_list[0].get("value") or val_list[0].get("Temperature") or "--"
                    
                    if ename in ["T", "溫度"]: t = val
                    elif ename in ["Wx", "天氣現象"]: wx = val
                    elif ename in ["PoP12h", "12小時降雨機率"]: pop = val
                
                weather_cache[matched_key] = f"{matched_key} {t}°{wx}({pop}%)"
        except Exception as e:
            print(f"DEBUG Error for {api_id}: {e}")
            continue

    # --- 組合訊息文字 ---
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    found_any = False
    for group in [taipei_order, new_taipei_order, yilan_order]:
        group_lines = [weather_cache[n] for n in group if n in weather_cache]
        if group_lines:
            final_msg += "\n".join(group_lines) + "\n\n"
            found_any = True

    if not found_any:
        return "❌ 深度解析失敗：請檢查 GitHub Actions 的 Log，欄位名稱可能不符合預期。"

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
    if all_users:
        send_line_message_to_all(all_users, get_weather_report())

if __name__ == "__main__":
    main()
