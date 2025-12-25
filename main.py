import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CWA_API_KEY = os.environ.get("CWA_API_KEY") 

def get_loc_weather(api_id, loc_name):
    """抓取特定行政區的氣象資訊 (包含溫度區間)"""
    try:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {"Authorization": CWA_API_KEY, "locationName": loc_name}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        # 取得該區的氣象元素
        loc_data = data['records']['locations'][0]['location'][0]
        elements = loc_data['weatherElement']
        
        wx, pop, min_t, max_t = "--", "0", "--", "--"
        
        for e in elements:
            e_name = e.get('elementName')
            # 取得目前的預報時段 (index 0)
            val = e['time'][0]['elementValue'][0]['value']
            
            if e_name == "Wx": wx = val
            elif e_name == "PoP12h": pop = val
            elif e_name == "MinT": min_t = val
            elif e_name == "MaxT": max_t = val
            elif e_name == "T" and min_t == "--": # 若沒 MinT 則用平均溫替代
                min_t = max_t = val

        display_name = loc_name.replace("區", "").replace("鎮", "").replace("鄉", "")
        return f"📍 {display_name} {min_t}~{max_t}° {wx} (降雨{pop}%)"
    except:
        return None

def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    
    # 定義清單與對應 API
    taipei_order = ["北投區", "士林區", "萬華區", "信義區", "松山區", "中正區", "大安區", "大同區", "中山區", "內湖區", "南港區", "文山區"]
    new_taipei_order = ["淡水區"]
    yilan_order = ["礁溪鄉"]

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"

    # 依序抓取並組合
    groups = [
        ("F-D0047-061", taipei_order), 
        ("F-D0047-069", new_taipei_order), 
        ("F-D0047-001", yilan_order)
    ]

    group_texts = []
    for api_id, locs in groups:
        lines = []
        for loc in locs:
            info = get_loc_weather(api_id, loc)
            if info: lines.append(info)
        if lines:
            group_texts.append("\n".join(lines))

    final_msg += "\n\n".join(group_texts)
    final_msg += "\n\n天氣變化多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

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
