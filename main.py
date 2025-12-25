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
    
    taipei_order = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_order = ["淡水", "板橋", "新店"]
    yilan_order = ["礁溪"]
    
    weather_cache = {}

    for api_id in api_ids:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY}, timeout=15)
            data = r.json()
            
            records = data.get("records", {})
            locs_container = records.get("Locations") or records.get("locations")
            if not locs_container:
                print(f"DEBUG: {api_id} 找不到 Locations 容器")
                continue
            
            locations = locs_container[0].get("location") or locs_container[0].get("Location")
            if not locations:
                print(f"DEBUG: {api_id} 找不到 location 清單")
                continue

            for loc in locations:
                raw_name = loc.get("locationName", "")
                # 清除行政區後綴
                clean_name = raw_name.replace("區", "").replace("鄉", "").replace("市", "").replace("鎮", "")
                
                elements = loc.get("weatherElement") or loc.get("WeatherElement")
                if not elements: continue
                
                t, wx, pop = "--", "--", "0"
                for e in elements:
                    # 診斷用：印出 API 到底給了什麼欄位名
                    e_name = (e.get('elementName') or e.get('ElementName') or "")
                    
                    times = e.get('time') or e.get('Time')
                    if not times: continue
                    
                    val_obj = times[0].get('elementValue') or times[0].get('ElementValue')
                    val = val_obj[0].get('value', '--') if val_obj else '--'
                    
                    # 使用最寬鬆的關鍵字判定
                    if any(k in e_name for k in ["T", "溫度", "Temperature"]): t = val
                    elif any(k in e_name for k in ["Wx", "天氣現象", "Weather"]): wx = val
                    elif any(k in e_name for k in ["PoP", "降雨", "Precipitation"]): pop = val
                
                weather_cache[clean_name] = f"{clean_name} {t}°{wx}({pop}%)"
                
        except Exception as e:
            print(f"DEBUG: {api_id} 執行出錯: {e}")

    # 診斷用：看快取裡到底存了什麼名稱
    print(f"DEBUG: 目前抓取到的地區有: {list(weather_cache.keys())}")

    if not weather_cache: return "❌ 氣象資料解析後完全為空"

    tw_time = datetime.utcnow() + timedelta(hours=8)
    date_str = tw_time.strftime("%m/%d (%A)") # 先用標準格式看時間

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    
    # 組合內容
    content_found = False
    for group in [taipei_order, new_taipei_order, yilan_order]:
        lines = []
        for name in group:
            if name in weather_cache:
                lines.append(weather_cache[name])
                content_found = True
        if lines:
            final_msg += "\n".join(lines) + "\n\n"

    if not content_found:
        final_msg += "(診斷報告：清單內地區與快取名稱不匹配)\n"
        final_msg += f"預期地區: {taipei_order[:3]}...\n"
        final_msg += f"實際地區: {list(weather_cache.keys())[:3]}...\n"

    final_msg += "\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
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
    if not all_users: return
    # 手動執行測試
    send_line_message_to_all(all_users, get_weather_report())

if __name__ == "__main__":
    main()
