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
    
    # 改用更穩定的「今明 36 小時天氣預報」API
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {"Authorization": CWA_API_KEY, "format": "JSON", "locationName": ["臺北市", "新北市", "宜蘭縣"]}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        locations = data.get("records", {}).get("location", [])
        
        weather_results = {}
        for loc in locations:
            city = loc.get("locationName", "")
            elements = loc.get("weatherElement", [])
            
            # 提取所需資訊
            wx = elements[0]['time'][0]['parameter']['parameterName']  # 天氣現象
            pop = elements[1]['time'][0]['parameter']['parameterName'] # 降雨機率
            min_t = elements[2]['time'][0]['parameter']['parameterName'] # 最低溫
            max_t = elements[4]['time'][0]['parameter']['parameterName'] # 最高溫
            
            weather_results[city] = f"{city} {min_t}~{max_t}° {wx} (降雨{pop}%)"
        
        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

        final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        final_msg += f"📍 {weather_results.get('臺北市', '台北資料缺失')}\n"
        final_msg += f"📍 {weather_results.get('新北市', '新北資料缺失')}\n"
        final_msg += f"📍 {weather_results.get('宜蘭縣', '宜蘭資料缺失')}\n\n"
        final_msg += "天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
        return final_msg

    except Exception as e:
        return f"❌ 氣象解析發生未知錯誤: {str(e)}"

# --- 下方發送邏輯維持不變 ---
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
