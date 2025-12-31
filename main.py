import requests
import os
import json
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_API_KEY = os.environ.get("CWA_API_KEY") 

# ------------------------------
# 氣象預報 (保險解析版)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少氣象金鑰"
    
    # 063:台北, 071:新北, 003:宜蘭
    api_map = {"F-D0047-063": ["北投區", "萬華區", "信義區"], "F-D0047-071": ["淡水區"], "F-D0047-003": ["礁溪鄉"]}
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    weather_map = {}
    
    for api_id, dists in api_map.items():
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY, "format": "JSON"}, timeout=20)
            data = r.json()
            locations = data['records']['locations'][0]['location']
            for loc in locations:
                name = loc['locationName']
                if name in target_districts:
                    info = {}
                    for elem in loc['weatherElement']:
                        # 抓取該行政區的第一筆預報
                        val = elem['time'][0]['elementValue'][0]['value']
                        info[elem['elementName']] = val
                    weather_map[name] = info
        except Exception as e:
            print(f"解析 {api_id} 失敗: {e}")

    now = datetime.utcnow() + timedelta(hours=8)
    date_str = now.strftime("%m/%d (%a)").replace("Mon","星期一").replace("Tue","星期二").replace("Wed","星期三").replace("Thu","星期四").replace("Fri","星期五").replace("Sat","星期六").replace("Sun","星期日")
    
    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    for d in target_districts:
        w = weather_map.get(d, {})
        if w.get('Wx'):
            msg += f"📍 {d} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {d} 讀取中...\n"
    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 台積電股價 (簡約版)
# ------------------------------
def get_tsmc_price():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers=headers, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:
        return "暫時無法取得"

# ------------------------------
# 基礎設施 (診斷發送版)
# ------------------------------
def get_users():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        print("❌ Cloudflare 環境變數缺失")
        return []
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        r = requests.get(url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, timeout=10)
        return [item['name'] for item in r.json().get('result', [])]
    except Exception as e:
        print(f"❌ KV 讀取失敗: {e}")
        return []

def send_line(users, text):
    if not users or not text: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(users), 500):
        payload = {"to": users[i:i+500], "messages": [{"type": "text", "text": text}]}
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE 發送結果: {res.status_code}, 內容: {res.text}")

# ------------------------------
# 主程式
# ------------------------------
def main():
    user_list = get_users()
    if not user_list:
        print("‼️ 無用戶可發送")
        return

    now_hour = (datetime.utcnow() + timedelta(hours=8)).hour
    
    # 早上7點發天氣，下午1-3點發股價，其餘時間測試
    if now_hour == 7:
        send_line(user_list, get_weather_report())
    elif 13 <= now_hour <= 15:
        price = get_tsmc_price()
        send_line(user_list, f"📢 TSMC 今日股價：{price} 元")
    else:
        # 測試模式：先發天氣，再發股價
        print("🔧 執行測試模式...")
        send_line(user_list, get_weather_report())
        send_line(user_list, f"📢 測試成功！目前股價：{get_tsmc_price()} 元")

if __name__ == "__main__":
    main()
