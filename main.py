import requests
import os
import json
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CWA_API_KEY = os.environ.get("CWA_API_KEY") 

TSMC_TARGET_PRICE = 1600

# ------------------------------
# 股價抓取函式 (Yahoo & FinMind)
# ------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200: return None
        data = r.json()
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except: return None

def get_price_from_finmind():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockPrice", "data_id": "2330", "start_date": "2024-01-01"}
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json()["data"][-1]["close"]
    except: return None

def get_tsmc_price():
    price = get_price_from_yahoo()
    if price is not None: return price
    price = get_price_from_finmind()
    if price is not None: return price
    raise Exception("❌ 無法取得股價")

# ------------------------------
# 天氣函式：解決 'locations' 報錯並優化格式
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY: return "⚠️ 缺少 CWA_API_KEY"
    
    # 061:台北市, 069:新北市, 001:宜蘭縣
    api_ids = ["F-D0047-061", "F-D0047-069", "F-D0047-001"]
    
    # 定義顯示順序
    taipei_list = ["北投", "士林", "萬華", "信義", "松山", "中正", "大安", "大同", "中山", "內湖", "南港", "文山"]
    new_taipei_list = ["淡水", "板橋", "新店"]
    yilan_list = ["礁溪"]
    
    weather_cache = {}

    for api_id in api_ids:
        try:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{api_id}"
            r = requests.get(url, params={"Authorization": CWA_API_KEY}, timeout=15)
            data = r.json()
            
            # 強化結構檢查，防止 'locations' 報錯
            if "records" not in data or "locations" not in data["records"] or not data["records"]["locations"]:
                print(f"⚠️ API {api_id} 回傳資料不完整: {data.get('message', '未知錯誤')}")
                continue
                
            locations = data["records"]["locations"][0]["location"]
            
            for loc in locations:
                # 名稱淨化 (北投、板橋、礁溪)
                name = loc["locationName"].replace("區", "").replace("鄉", "").replace("市", "")
                
                # 取得天氣元素 (T:溫度, Wx:現象, PoP12h:降雨機率)
                elements = {e['elementName']: e['time'][0]['elementValue'][0]['value'] for e in loc['weatherElement']}
                t = elements.get('T', '--')
                wx = elements.get('Wx', '--')
                pop = elements.get('PoP12h', '0')
                
                # 儲存格式化字串 (無雨傘符號)
                weather_cache[name] = f"{name} {t}°{wx}({pop}%)"
                
        except Exception as e:
            print(f"⚠️ 抓取 {api_id} 發生錯誤: {e}")
            continue

    if not weather_cache:
        return "❌ 氣象局資料解析失敗，請檢查 API Key 是否有效或伺服器狀態。"

    # --- 組合訊息文字 ---
    tw_time = datetime.utcnow() + timedelta(hours=8)
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

    # 標題
    final_msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"

    # 1. 台北市
    tpe_nodes = [weather_cache[n] for n in taipei_list if n in weather_cache]
    if tpe_nodes:
        final_msg += "\n".join(tpe_nodes) + "\n\n"

    # 2. 新北市
    ntpc_nodes = [weather_cache[n] for n in new_taipei_list if n in weather_cache]
    if ntpc_nodes:
        final_msg += "\n".join(ntpc_nodes) + "\n\n"

    # 3. 宜蘭 (礁溪)
    yil_nodes = [weather_cache[n] for n in yilan_list if n in weather_cache]
    if yil_nodes:
        final_msg += "\n".join(yil_nodes)

    # 結尾祝福語
    final_msg += "\n\n天氣多變請多留意，阿賢祝福您吉祥如意闔家平安幸福永相隨。"
    
    return final_msg

# ------------------------------
# Cloudflare KV & LINE 傳送函式
# ------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        print("⚠️ 缺少 Cloudflare 環境變數")
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    user_ids = []
    cursor = None
    try:
        while True:
            params = {'limit': 1000}
            if cursor: params['cursor'] = cursor
            r = requests.get(url, headers=headers, params=params, timeout=10)
            data = r.json()
            user_ids.extend([item['name'] for item in data['result']])
            cursor = data['result_info'].get('cursor')
            if not cursor: break
        return user_ids
    except Exception as e:
        print(f"❌ 讀取 Cloudflare 失敗: {e}")
        return []

def send_line_message_to_all(user_ids, message):
    if not user_ids or not message: return
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    for i in range(0, len(user_ids), 500):
        body = {"to": user_ids[i:i + 500], "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=body, timeout=10)

# ------------------------------
# 主程式 (正式運行版)
# ------------------------------
def main():
    print("--- 開始執行任務 ---")
    all_users = get_all_user_ids_from_cloudflare()
    print(f"DEBUG: 找到用戶數量 = {len(all_users)}")

    if not all_users:
        print("❌ 錯誤：無法取得用戶清單。")
        return

    tw_time = datetime.utcnow() + timedelta(hours=8)
    tw_hour = tw_time.hour
    print(f"DEBUG: 目前台灣小時 = {tw_hour}")

    # 早上 7 點推送天氣
    if tw_hour == 7:
        print("執行早晨天氣任務...")
        report = get_weather_report()
        send_line_message_to_all(all_users, report)
        print("✅ 天氣推播已嘗試送出")

    # 下午 2 點左右推送股價 (Cron 排程應控制在 14:00)
    elif 13 <= tw_hour <= 15:
        print("執行下午股價任務...")
        try:
            price = get_tsmc_price()
            if price >= TSMC_TARGET_PRICE:
                send_line_message_to_all(all_users, f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）")
            send_line_message_to_all(all_users, f"📢 tsmc 今日收盤價：{price} 元")
            print("✅ 股價推播已嘗試送出")
        except Exception as e:
            print(f"❌ 股價任務失敗: {e}")

    # 非指定時間手動測試 (若要正式上線，可將下面 else 刪除或註解)
    else:
        print("非定時執行時間，執行測試發送...")
        report = get_weather_report()
        send_line_message_to_all(all_users, report)
        print("✅ 測試發送完成")

if __name__ == "__main__":
    main()
