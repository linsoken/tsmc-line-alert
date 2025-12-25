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
    try:
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
        # 加上時間過濾，確保抓到的是最新的資料
        params = {"Authorization": CWA_API_KEY, "locationName": loc_name}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        loc_data = data['records']['locations'][0]['location'][0]
        elements = loc_data['weatherElement']
        
        wx, pop, t, min_t, max_t = "--", "0", "--", "--", "--"
        
        for e in elements:
            e_name = e.get('elementName')
            # 取得最新的時段數值
            val = e['time'][0]['elementValue'][0]['value']
            
            if e_name == "Wx": wx = val
            elif e_name == "PoP12h": pop = val
            elif e_name == "T": t = val
            elif e_name == "MinT": min_t = val
            elif e_name == "MaxT": max_t = val
        
        # 修正邏輯：如果沒有 MinT/MaxT，就用 T 代替
        lo = min_t if min_t != "--" else t
        hi = max_t if max_t != "--" else t
        
        display_name = loc_name.replace("區", "").replace("鎮", "").replace("鄉", "")
        return f"📍 {display_name} {lo}~{hi}° {wx} (降雨{pop}%)"
    except Exception as e:
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

    if not results: return "❌ 無法取得氣象細節，請檢查 API 額度或連線。"

    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    final_msg += "\n\n".join(results)
    final_msg += "\n\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    return final_msg

def main():
    # 取得 KV 中的用戶
    kv_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    try:
        r = requests.get(kv_url, headers=headers, timeout=10)
        all_users = [item['name'] for item in r.json().get('result', [])]
    except: return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour

    msg = None
    # 早上 7 點發天氣
    if tw_hour == 7:
        msg = get_weather_report()
    # 下午 1-3 點發台積電
    elif 13 <= tw_hour <= 15:
        p = get_tsmc_price()
        if p:
            msg = f"📢 tsmc 今日最新價：{p} 元"
            if p >= TSMC_TARGET_PRICE:
                msg = f"📈 台積電達標！\n{msg}"
    # 其他時間手動執行發天氣測試
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
