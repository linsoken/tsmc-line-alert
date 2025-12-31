import requests
import os
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CWA_API_KEY = os.environ.get("CWA_API_KEY") 

# ------------------------------
# 1. 氣象解析 (最原始路徑抓取)
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少氣象金鑰"
    
    # 063:台北, 071:新北, 003:宜蘭
    api_map = {"F-D0047-063": ["北投區", "萬華區", "信義區"], "F-D0047-071": ["淡水區"], "F-D0047-003": ["礁溪鄉"]}
    target_districts = ["北投區", "萬華區", "信義區", "淡水區", "礁溪鄉"]
    weather_map = {}
    
    try:
        for api_id, dists in api_map.items():
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}?Authorization={CWA_API_KEY}&format=JSON&elementName=Wx,PoP12h,MinT,MaxT"
            r = requests.get(url, timeout=20)
            if r.status_code != 200: continue
            
            data = r.json()
            locations = data['records']['locations'][0]['location']
            for loc in locations:
                name = loc['locationName']
                if name in target_districts:
                    info = {}
                    for elem in loc['weatherElement']:
                        # 抓取該行政區的第一筆預報
                        info[elem['elementName']] = elem['time'][0]['elementValue'][0]['value']
                    weather_map[name] = info
    except Exception as e:
        return f"⚠️ 氣象解析發生技術錯誤: {str(e)}"

    now = datetime.utcnow() + timedelta(hours=8)
    week_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = now.strftime("%m/%d") + f" ({week_names[now.weekday()]})"
    
    msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
    for d in target_districts:
        w = weather_map.get(d)
        if w:
            msg += f"📍 {d} {w.get('MinT')}~{w.get('MaxT')}° {w.get('Wx')} (降雨{w.get('PoP12h')}%)\n"
        else:
            msg += f"📍 {d} 讀取失敗\n"
    
    msg += "\n天氣變化多留意，祝福您吉祥如意闔家平安幸福永相隨。"
    return msg

# ------------------------------
# 2. 基礎設施 (診斷發送版)
# ------------------------------
def get_users():
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
        headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=10)
        res_data = r.json()
        ids = [item['name'] for item in res_data.get('result', [])]
        print(f"✅ 成功讀取用戶數: {len(ids)}")
        return ids
    except Exception as e:
        print(f"❌ KV 錯誤: {e}")
        return []

def send_line(users, text):
    if not users or not text: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    
    # 強制過濾並轉換成 string list
    clean_users = [str(uid) for uid in users if uid]
    
    for i in range(0, len(clean_users), 500):
        payload = {
            "to": clean_users[i : i+500],
            "messages": [{"type": "text", "text": str(text)}]
        }
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"🚀 LINE {res.status_code}: {res.text}")

# ------------------------------
# 3. 主邏輯
# ------------------------------
def main():
    user_list = get_users()
    if not user_list:
        print("❌ 無用戶 ID，中止")
        return

    now_hour = (datetime.utcnow() + timedelta(hours=8)).hour

    # 定時邏輯
    if now_hour == 7:
        send_line(user_list, get_weather_report())
    elif 13 <= now_hour <= 15:
        # 下午時段直接抓 Yahoo 股價
        try:
            r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            price = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            if now_hour == 14:
                send_line(user_list, f"📢 TSMC 今日參考價：{price} 元")
        except:
            print("股價抓取失敗")
    else:
        # 測試模式
        print("🔧 啟動測試...")
        # 1. 測試天氣
        weather = get_weather_report()
        send_line(user_list, weather)
        # 2. 測試股價
        try:
            r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            p = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            send_line(user_list, f"📢 測試股價：{p} 元")
        except:
            send_line(user_list, "📢 測試股價失敗")

if __name__ == "__main__":
    main()
