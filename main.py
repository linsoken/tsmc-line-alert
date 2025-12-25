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
    """強力解析：掃描所有數值欄位"""
    try:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        params = {"Authorization": CWA_API_KEY, "locationName": loc_name}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        
        # 逐層向下挖掘
        recs = data.get("records", {})
        locs_wrapper = recs.get("locations") or recs.get("Locations")
        loc_item = locs_wrapper[0].get("location") or locs_wrapper[0].get("Location")
        elements = loc_item[0].get("weatherElement") or loc_item[0].get("WeatherElement")
        
        wx, pop, t, min_t, max_t = "--", "0", "--", "--", "--"
        
        for e in elements:
            e_name = e.get("elementName") or e.get("ElementName")
            times = e.get("time") or e.get("Time")
            if not times: continue
            
            # 取得數值對象
            val_objs = times[0].get("elementValue") or times[0].get("ElementValue")
            if not val_objs: continue
            
            # 氣象局有時會把數值放在 'value' 或 'measures'
            val = val_objs[0].get("value") or val_objs[0].get("measures") or "--"
            
            if e_name in ["Wx", "天氣現象"]: wx = val
            elif e_name in ["PoP12h", "12小時降雨機率"]: pop = val
            elif e_name in ["T", "溫度"]: t = val
            elif e_name in ["MinT", "最低溫度"]: min_t = val
            elif e_name in ["MaxT", "最高溫度"]: max_t = val
        
        # 容錯：若無區間溫則用平均溫
        low = min_t if min_t != "--" else t
        high = max_t if max_t != "--" else t
        
        display_name = loc_name.replace("區", "").replace("鎮", "").replace("鄉", "")
        return f"📍 {display_name} {low}~{high}° {wx} (降雨{pop}%)"
    except:
        return None

def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 API KEY"
    
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

    if not results: return "❌ 解析失敗：請檢查 API 額度或名稱正確性"

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    final_msg += "\n\n".join(results)
    final_msg += "\n\n天氣變化多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

def main():
    # 取得用戶
    kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(kv_url, headers=headers, timeout=10)
        users = [item['name'] for item in r.json().get('result', [])]
    except: return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour

    msg = None
    if tw_hour == 7:
        msg = get_weather_report()
    elif 13 <= tw_hour <= 15:
        p = get_tsmc_price()
        if p:
            msg = f"📢 tsmc 今日最新價：{p} 元"
            if p >= TSMC_TARGET_PRICE: msg = f"📈 台積電達標！\n{msg}"
    else:
        msg = get_weather_report() # 手動測試

    if users and msg:
        line_url = "https://api.line.me/v2/bot/message/multicast"
        line_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
        for i in range(0, len(users), 500):
            body = {"to": users[i:i + 500], "messages": [{"type": "text", "text": msg}]}
            requests.post(line_url, headers=line_headers, json=body, timeout=10)

if __name__ == "__main__":
    main()
