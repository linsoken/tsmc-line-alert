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
    
    # 標準化名稱清單
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
            
            # 第一層檢查：records
            records = data.get("records", {})
            # 第二層檢查：Locations 或 locations (複數)
            locs_group = records.get("Locations") or records.get("locations")
            if not locs_group or not isinstance(locs_group, list): continue
            
            # 第三層檢查：內部 location 或 Location (單數)
            location_list = locs_group[0].get("location") or locs_group[0].get("Location")
            if not location_list: continue

            for loc in location_list:
                api_name = loc.get("locationName", "").strip()
                
                # 模糊匹配：API 的「松山區」包含我們的「松山」就過關
                matched_key = next((t for t in all_targets if t in api_name), None)
                if not matched_key: continue
                
                # 取得氣象元素列表
                elements = loc.get("weatherElement") or loc.get("WeatherElement") or []
                t, wx, pop = "--", "--", "0"
                
                for e in elements:
                    ename = (e.get("elementName") or e.get("ElementName") or "")
                    times = e.get("time") or e.get("Time") or []
                    if not times: continue
                    
                    # 取得第一個時段的值
                    val_list = times[0].get("elementValue") or times[0].get("ElementValue") or []
                    val = val_list[0].get("value", "--") if val_list else "--"
                    
                    # 匹配欄位
                    if ename in ["T", "溫度"]: t = val
                    elif ename in ["Wx", "天氣現象"]: wx = val
                    elif ename in ["PoP12h", "降雨機率", "12小時降雨機率"]: pop = val
                
                weather_cache[matched_key] = f"{matched_key} {t}°{wx}({pop}%)"
        except:
            continue

    # --- 組合訊息文字 ---
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    has_data = False
    for group in [taipei_order, new_taipei_order, yilan_order]:
        lines = [weather_cache[n] for n in group if n in weather_cache]
        if lines:
            final_msg += "\n".join(lines) + "\n\n"
            has_data = True

    if not has_data:
        return "❌ 結構比對失敗：API 資料存在但路徑抓取錯誤，請檢查 JSON 結構層級。"

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
