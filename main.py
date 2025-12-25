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
    """萬用路徑抓取：自動匹配大小寫與不同層級"""
    try:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {"Authorization": CWA_API_KEY, "locationName": loc_name}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        # 逐層向下挖掘，相容大小寫
        records = data.get("records", {})
        locations_container = records.get("locations") or records.get("Locations")
        if not locations_container: return None
        
        location_list = locations_container[0].get("location") or locations_container[0].get("Location")
        if not location_list: return None
        
        target_loc = location_list[0]
        elements = target_loc.get("weatherElement") or target_loc.get("WeatherElement")
        
        wx, pop, t, min_t, max_t = "--", "0", "--", "--", "--"
        
        for e in elements:
            e_name = e.get("elementName") or e.get("ElementName")
            time_list = e.get("time") or e.get("Time")
            if not time_list: continue
            
            val_list = time_list[0].get("elementValue") or time_list[0].get("ElementValue")
            val = val_list[0].get("value") if val_list else "--"
            
            if e_name == "Wx": wx = val
            elif e_name == "PoP12h": pop = val
            elif e_name == "T": t = val
            elif e_name == "MinT": min_t = val
            elif e_name == "MaxT": max_t = val
        
        # 數值修正邏輯
        lo = min_t if min_t != "--" else t
        hi = max_t if max_t != "--" else t
        
        display_name = loc_name.replace("區", "").replace("鎮", "").replace("鄉", "")
        return f"📍 {display_name} {lo}~{hi}° {wx} (降雨{pop}%)"
    except Exception as e:
        print(f"DEBUG: {loc_name} 解析失敗: {e}")
        return None

def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 API KEY"
    
    # 按照您的要求排序
    sections = [
        ("F-D0047-061", ["北投區", "士林區", "萬華區", "信義區", "松山區", "中正區", "大安區", "大同區", "中山區", "內湖區", "南港區", "文山區"]),
        ("F-D0047-069", ["淡水區"]),
        ("F-D0047-001", ["礁溪鄉"])
    ]

    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    all_lines = []
    for api_id, locs in sections:
        group_lines = []
        for l in locs:
            info = get_loc_weather(api_id, l)
            if info: group_lines.append(info)
        if group_lines:
            all_lines.append("\n".join(group_lines))

    if not all_lines:
        return "❌ 深度解析失敗，請確認氣象局 API 權限或行政區名稱。"

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    final_msg += "\n\n".join(all_lines)
    final_msg += "\n\n天氣變化多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

def main():
    # 讀取用戶清單
    kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(kv_url, headers=headers, timeout=10)
        all_users = [item['name'] for item in r.json().get('result', [])]
    except: return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour

    # 邏輯分流：早上報天氣，下午報股票，其餘手動執行報天氣
    if tw_hour == 7:
        msg = get_weather_report()
    elif 13 <= tw_hour <= 15:
        p = get_tsmc_price()
        msg = f"📢 tsmc 今日最新價：{p} 元" if p else None
        if p and p >= TSMC_TARGET_PRICE:
            msg = f"📈 台積電達標！\n{msg}"
    else:
        msg = get_weather_report()

    if all_users and msg:
        line_url = "https://api.line.me/v2/bot/message/multicast"
        line_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
        for i in range(0, len(all_users), 500):
            body = {"to": all_users[i:i + 500], "messages": [{"type": "text", "text": msg}]}
            requests.post(line_url, headers=line_headers, json=body, timeout=10)

if __name__ == "__main__":
    main()
