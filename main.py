import requests
import os
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

def get_loc_weather(api_id, loc_name):
    """強健版單區抓取"""
    try:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {"Authorization": CWA_API_KEY, "locationName": loc_name}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        # 深度容錯解析
        recs = data.get('records', {})
        locs = recs.get('locations') or recs.get('Locations')
        l_list = locs[0].get('location') or locs[0].get('Location')
        elements = l_list[0].get('weatherElement') or l_list[0].get('WeatherElement')
        
        wx, pop, min_t, max_t = "--", "0", "--", "--"
        for e in elements:
            e_n = e.get('elementName') or e.get('ElementName')
            t_list = e.get('time') or e.get('Time')
            v_list = t_list[0].get('elementValue') or t_list[0].get('ElementValue')
            val = v_list[0].get('value')
            
            if e_n == "Wx": wx = val
            elif e_n == "PoP12h": pop = val
            elif e_n in ["MinT", "MinT"]: min_t = val
            elif e_n in ["MaxT", "MaxT"]: max_t = val
            elif e_n == "T" and min_t == "--": min_t = max_t = val

        d_name = loc_name.replace("區", "").replace("鎮", "").replace("鄉", "")
        return f"📍 {d_name} {min_t}~{max_t}° {wx} ({pop}%)"
    except:
        return None

def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 API KEY"
    
    # 預期顯示清單
    sections = [
        ("F-D0047-061", ["北投區", "士林區", "萬華區", "信義區", "松山區", "中正區", "大安區", "大同區", "中山區", "內湖區", "南港區", "文山區"]),
        ("F-D0047-069", ["淡水區"]),
        ("F-D0047-001", ["礁溪鄉"])
    ]

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    results = []
    for api_id, locs in sections:
        group = []
        for l in locs:
            info = get_loc_weather(api_id, l)
            if info: group.append(info)
        if group: results.append("\n".join(group))

    # --- 關鍵修正：若精確區全失敗，改抓縣市大範圍預報補位 ---
    if not results:
        return "❌ 氣象局資料暫時無法讀取，請稍後再試。"

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    final_msg += "\n\n".join(results)
    final_msg += "\n\n天氣變化多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

def main():
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        all_users = [item['name'] for item in r.json().get('result', [])]
    except: return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour

    if tw_hour == 7 or tw_hour not in [13, 14, 15]: # 早上7點或測試時
        msg = get_weather_report()
    elif 13 <= tw_hour <= 15:
        p = get_tsmc_price()
        msg = f"📢 tsmc 今日最新價：{p} 元" if p else None
        if p and p >= TSMC_TARGET_PRICE: msg = f"📈 台積電達標！\n{msg}"
    else:
        return

    if all_users and msg:
        line_url = "https://api.line.me/v2/bot/message/multicast"
        line_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
        for i in range(0, len(all_users), 500):
            body = {"to": all_users[i:i + 500], "messages": [{"type": "text", "text": msg}]}
            requests.post(line_url, headers=line_headers, json=body, timeout=10)

if __name__ == "__main__":
    main()
