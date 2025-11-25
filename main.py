import requests
import os

TSMC_TARGET_PRICE = 1500  # 你要通知的價格
USER_ID = os.environ["LINE_USER_ID"]
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

# ------------------------------
#  Yahoo Finance 先抓（快），如果被擋再用 FinMind 補
# ------------------------------
def get_price_from_yahoo():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    headers = {
        "User-Agent": "Mozilla/5.0"  # GitHub Actions 需要 User-Agent
    }
    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        print(f"⚠ Yahoo API 回傳狀態碼：{r.status_code}")
        return None

    try:
        data = r.json()  # 若回傳 HTML 會直接失敗
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return price
    except Exception:
        print("⚠ Yahoo 回傳不是 JSON，可能被擋。前 200 字：")
        print(r.text[:200])
        return None


# ------------------------------
#  Yahoo 失敗時，改用 FinMind
# ------------------------------
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


# ------------------------------
#  自動選擇最穩定的價格來源
# ------------------------------
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


# ------------------------------
#  LINE 推播
# ------------------------------
def send_line_message(message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    body = {
        "to": USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    requests.post(url, headers=headers, json=body)
    print("📨 已送出 LINE 推播")


# ------------------------------
#  主程式
# ------------------------------
def main():
    price = get_tsmc_price()

    if price >= TSMC_TARGET_PRICE:
        send_line_message(f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）")
    else:
        print(f"目前價格 {price}，未達通知條件")
        
    send_line_message(f"📢 tsmc 今日價格為：{price} 元")

if __name__ == "__main__":
    main()
