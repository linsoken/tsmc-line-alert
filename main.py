import requests
import os

TSMC_TARGET_PRICE = 1500  # 你要通知的價格
USER_ID = os.environ["LINE_USER_ID"]
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

def get_tsmc_price():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    r = requests.get(url)
    data = r.json()
    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    return price

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

def main():
    price = get_tsmc_price()

    if price >= TSMC_TARGET_PRICE:
        send_line_message(f"📈 台積電股價已達 {price} 元！\n（提醒門檻：{TSMC_TARGET_PRICE}）")
    else:
        print(f"目前價格 {price}，未達通知條件")

if __name__ == "__main__":
    main()
