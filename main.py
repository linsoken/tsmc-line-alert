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
    
    # 想要顯示的標準名稱
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
            
            # 定義位置列表
            records = data.get("records", {})
            locs_group = records.get("Locations") or records.get("locations") or []
            if not locs_group: continue
            
            locations = locs_group[0].get("location") or locs_group[0].get("Location") or []
            
            for loc in locations:
                api_name = loc.get("locationName", "").strip()
                
                # 模糊匹配：只要 API 的「松山區」包含我們的「松山」，就認定成功
                target_key = None
                for target in all_targets:
                    if target in api_name:
                        target_key = target
                        break
                
                if not target_key: continue
                
                # 擷取氣象元素
                elements = loc.get("weatherElement") or loc.get("WeatherElement") or []
                t, wx, pop = "--", "--", "0"
                
                for e in elements:
                    ename = (e.get("elementName") or e.get("ElementName") or "")
                    times = e.get("time") or e.get("Time") or []
                    if not times: continue
                    
                    val_list = times[0].get("elementValue") or times[0].get("ElementValue") or []
                    if not val_list: continue
                    val = val_list[0].get("value", "--")
                    
                    if ename in ["T", "溫度", "Temperature"]: t = val
                    elif ename in ["Wx", "天氣現象", "Weather"]: wx = val
                    elif ename in ["PoP12h", "12小時降雨機率", "ProbabilityOfPrecipitation"]: pop = val
                
                weather_cache[target_key] = f"{target_key} {t}°{wx}({pop}%)"
        except Exception as e:
            print(f"DEBUG Error: {e}")
            continue

    # --- 組合訊息文字 ---
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    content_list = []
    for group in [taipei_order, new_taipei_order, yilan_order]:
        group_lines = [weather_cache[n] for n in group if n in weather_cache]
        if group_lines:
            content_list.append("\n".join(group_lines))

    if not content_list:
        return "❌ 匹配失敗：API 正常但地區比對不成功，請檢查名稱正確性。"

    final_msg += "\n\n".join(content_list)
    final_msg += "\n\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

# --- 傳送邏輯維持不變 ---
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
