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
    # F-D0047-061: 台北市, 069: 新北市, 001: 宜蘭縣
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    
    # 想要抓取的清單
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
            
            # 根據截圖精確定位：records -> Locations[0] -> location (List)
            records = data.get("records", {})
            locations_container = records.get("Locations") or records.get("locations") or []
            if not locations_container: continue
            
            locations_list = locations_container[0].get("location") or []
            
            for loc in locations_list:
                api_loc_name = loc.get("locationName", "")
                
                # 匹配邏輯：如果 API 回傳的「松山區」包含我們想要的「松山」
                matched_target = None
                for target in all_targets:
                    if target in api_loc_name:
                        matched_target = target
                        break
                
                if not matched_target: continue
                
                elements = loc.get("weatherElement", [])
                t, wx, pop = "--", "--", "0"
                
                for e in elements:
                    ename = (e.get("elementName") or e.get("ElementName") or "")
                    times = e.get("time") or e.get("Time") or []
                    if not times: continue
                    
                    val_obj = times[0].get("elementValue") or times[0].get("ElementValue") or []
                    val = val_obj[0].get("value", "--") if val_obj else "--"
                    
                    # 依據關鍵字擷取內容
                    if ename in ["T", "溫度", "Temperature"]: t = val
                    elif ename in ["Wx", "天氣現象", "Weather"]: wx = val
                    elif ename in ["PoP12h", "12小時降雨機率"]: pop = val
                
                weather_cache[matched_target] = f"{matched_target} {t}°{wx}({pop}%)"
        except:
            continue

    # --- 組合訊息 ---
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    has_content = False
    for group in [taipei_order, new_taipei_order, yilan_order]:
        lines = [weather_cache[n] for n in group if n in weather_cache]
        if lines:
            final_msg += "\n".join(lines) + "\n\n"
            has_content = True

    if not has_content:
        return "❌ 匹配失敗：API 有回傳資料但找不到指定的行政區，請確認地區名稱是否正確。"

    final_msg += "天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg.strip()

# --- 傳送邏輯 ---
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
