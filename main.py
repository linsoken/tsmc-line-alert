import requests
import os
import json # ### [新增] 引入 json 庫，雖然 requests.post 時會自動處理，但保留習慣。

#--- [新增] Cloudflare 相關環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
#----------------------------------------
TSMC_TARGET_PRICE = 1500  #你要通知的價格
# USER_ID = os.environ["LINE_USER_ID"] # ### [修改] 註銷，不再使用單一 USER_ID
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

#------------------------------
#  Yahoo Finance 先抓（快），如果被擋再用 FinMind 補
#------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {
        "User-Agent": "Mozilla/5.0"  # GitHub Actions 需要 User-Agent
    }
    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        print(f"⚠ Yahoo API 回傳狀態碼：{r.status_code}")
        return None

    try:
        data = r.json()  # 若回傳 HTML 會直接失敗
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return price
    except Exception:
        print("⚠ Yahoo 回傳不是 JSON，可能被擋。前 200 字：")
        print(r.text[:200])
        return None


#------------------------------
#Yahoo 失敗時，改用 FinMind
#------------------------------
def get_price_from_finmind():
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": "2330",
        "start_date": "2024-01-01"
    }

    try:
        r = requests.get(url, params=params)
        data = r.json()
        price = data["data"][-1]["close"]
        print(f"🟢 使用 FinMind 抓到價格：{price}")
        return price
    except Exception as e:
        print("❌ FinMind 抓取失敗：", e)
        return None


#------------------------------
#自動選擇最穩定的價格來源
#------------------------------
def get_tsmc_price():
    print("🔍 嘗試從 Yahoo Finance 取得價格…")
    price = get_price_from_yahoo()

    if price is not None:
        print(f"🟢 使用 Yahoo Finance 抓到價格：{price}")
        return price

    print("⚠ Yahoo 失敗，改用 FinMind API…")
    price = get_price_from_finmind()

    if price is not None:
        return price

    raise Exception("❌ Yahoo + FinMind 都無法取得股價")


#------------------------------
#### [新增] 取得所有 LINE 用戶 ID (透過 Cloudflare API)
#------------------------------
def get_all_user_ids_from_cloudflare():
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, CF_KV_NAMESPACE_ID]):
        print("❌ 缺少 Cloudflare 認證資訊，無法取得用戶清單。")
        return []

    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}/keys"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    user_ids = []
    cursor = None
    
    # 處理 KV API 的分頁
    while True:
        params = {'limit': 1000} 
        if cursor:
            params['cursor'] = cursor
            
        try:
            r = requests.get(url, headers=headers, params=params)
            r.raise_for_status() 
            data = r.json()
            
            if not data.get('success'):
                print(f"❌ Cloudflare API 錯誤: {data.get('errors')}")
                return []
                
            user_ids.extend([item['name'] for item in data['result']])
            
            cursor = data['result_info'].get('cursor')
            if not cursor:
                break 
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 取得 Cloudflare KV 失敗: {e}")
            return []
            
    print(f"✅ 成功從 Cloudflare 取得 {len(user_ids)} 個用戶 ID。")
    return user_ids


#------------------------------
#### [修改] LINE 推播 (改用 Multicast API 支援群發)
#------------------------------
# 函數名稱變更為更適合群發的名稱，並接受 user_ids 清單
def send_line_message_to_all(user_ids, message):
    if not user_ids:
        print("⚠ 用戶 ID 清單為空，跳過推播。")
        return
        
    # LINE Multicast API 一次最多 500 個 ID，需分批發送
    url = "https://api.line.me/v2/bot/message/multicast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    # 將 user_ids 分成每批最多 500 個
    for i in range(0, len(user_ids), 500):
        batch_ids = user_ids[i:i + 500]
        
        body = {
            "to": batch_ids, # ### [修改] 傳入 ID 清單，而非單一 ID
            "messages": [{"type": "text", "text": message}]
        }
        r = requests.post(url, headers=headers, json=body)
        
        if r.status_code == 200:
            print(f"📨 已送出 LINE 推播到 {len(batch_ids)} 位用戶。")
        else:
            print(f"❌ LINE Multicast 失敗 (狀態碼: {r.status_code}, 回覆: {r.text})")


#------------------------------
#主程式 ### [修改] 整合 KV 讀取和群發推播邏輯
#------------------------------
def main():
    price = get_tsmc_price()
    
    # 1. ### [新增] 取得所有用戶 ID
    all_users = get_all_user_ids_from_cloudflare()
    
    if not all_users:
        print("無法取得任何用戶 ID，結束運行。")
        return

    # 2. ### [修改] 檢查價格並送出達標通知
    if price >= TSMC_TARGET_PRICE:
        notification_message = f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）"
        # 使用新的群發函數
        send_line_message_to_all(all_users, notification_message)
    else:
        print(f"目前價格 {price}，未達通知條件")
    
    # 3. ### [修改] 送出每日收盤價通知給所有用戶
    daily_message = f"📢 tsmc 今日收盤價：{price} 元"
    send_line_message_to_all(all_users, daily_message)

if __name__ == "__main__":
    main()
