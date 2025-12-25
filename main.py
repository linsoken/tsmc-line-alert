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
    # 指定 API ID：061(台北), 069(新北), 001(宜蘭)
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    
    taipei_order = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_order = ["淡水", "板橋", "新店"]
    yilan_order = ["礁溪"]
    
    weather_cache = {}

    for api_id in api_ids:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY}, timeout=15)
            data = r.json()
            
            # 遍歷尋找 location 列表 (這段最保險，不管層級多深都找得到)
            records = data.get("records", {})
            locations_list = []
            if "Locations" in records and isinstance(records["Locations"], list):
                locations_list = records["Locations"][0].get("location", [])
            elif "locations" in records and isinstance(records["locations"], list):
                locations_list = records["locations"][0].get("location", [])
            
            for loc in locations_list:
                name = loc.get("locationName", "")
                if not name: continue
                
                # 清除名稱後綴
                clean_name = name.replace("區", "").replace("鄉", "").replace("市", "").replace("鎮", "")
                
                elements = loc.get("weatherElement", [])
                t, wx, pop = "--", "--", "0"
                
                for e in elements:
                    ename = e.get("elementName", "")
                    # 取得第一個時間點的預報
                    times = e.get("time", [])
                    if not times: continue
                    
                    # 抓取數值
                    vals = times[0].get("elementValue", [])
                    if not vals: continue
                    val = vals[0].get("value", "--")
                    
                    if ename in ["T", "溫度"]: t = val
                    elif ename in ["Wx", "天氣現象"]: wx = val
                    elif ename in ["PoP12h", "降雨機率"]: pop = val
                
                weather_cache[clean_name] = f"{clean_name} {t}°{wx}({pop}%)"
        except Exception as e:
            print(f"DEBUG: {api_id} 出錯: {e}")

    # --- 組合訊息文字 ---
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_map = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_map[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    found_any = False
    for group in [taipei_order, new_taipei_order, yilan_order]:
        group_lines = []
        for n in group:
            if n in weather_cache:
                group_lines.append(weather_cache[n])
                found_any = True
        if group_lines:
            final_msg += "\n".join(group_lines) + "\n\n"

    if not found_any:
        return "❌ 抓不到指定地區的氣象，請檢查 API 授權或行政區名稱。"

    final_msg += "天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg.strip()

# --- LINE & KV 邏輯 (不變) ---
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
