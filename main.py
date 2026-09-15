import requests
import re
import os
import json
from datetime import datetime, timedelta

# --- 環境變數 ---
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CWA_API_KEY = os.environ.get("CWA_API_KEY")

TSMC_TARGET_PRICE = 2500  # 您要通知的價格


# ------------------------------
# 氣象預報函式
# ------------------------------
def get_weather_report():
    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"

    weather_datasets = ["F-D0047-061", "F-D0047-069"]
    target_districts = ["北投區", "萬華區", "淡水區", "信義區"]

    try:
        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        date_str = tw_time.strftime(f"%m/%d ({week_list[tw_time.weekday()]})")

        def parse_time(value):
            if not value: return None
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    from datetime import timezone
                    dt = dt.astimezone(timezone(timedelta(hours=8)))
                return dt.replace(tzinfo=None)
            except Exception:
                return None

        def find_element(elements, names):
            for element in elements:
                if element.get("ElementName", "") in names:
                    return element
            return None

        def get_element_value(item):
            value = item.get("ElementValue", {})
            if isinstance(value, list):
                value = value[0] if value else {}
            return value if isinstance(value, dict) else {}

        def get_value_ci(value, *keys):
            if not isinstance(value, dict): return None
            for key in keys:
                if key in value: return value[key]
            lower_map = {str(k).lower(): v for k, v in value.items()}
            for key in keys:
                if key.lower() in lower_map: return lower_map[key.lower()]
            return None

        def find_current_time_data(times):
            if not times: return None
            for item in times:
                start = parse_time(item.get("StartTime")); end = parse_time(item.get("EndTime"))
                if start and end and start <= tw_time < end: return item
            latest = None
            for item in times:
                data_time = parse_time(item.get("DataTime"))
                if data_time and data_time <= tw_time:
                    if latest is None or data_time > (parse_time(latest.get("DataTime")) or datetime.min): latest = item
            return latest if latest is not None else times[0]

        def get_daily_temperature(elements, names, today_str):
            element = find_element(elements, names)
            if not element: return None
            for item in element.get("Time", []):
                check_time = parse_time(item.get("StartTime")) or parse_time(item.get("DataTime"))
                if check_time and check_time.strftime("%Y-%m-%d") == today_str:
                    value = get_element_value(item)
                    result = get_value_ci(value, "MinTemperature", "MinT", "MaxTemperature", "MaxT", "最低溫度", "最高溫度")
                    if result is not None: return str(result)
            return None

        def parse_location(location):
            district = location.get("LocationName", "")
            if district not in target_districts: return None
            elements = location.get("WeatherElement", [])
            if not elements: return None

            desc_el = find_element(elements, ["天氣預報綜合描述", "WeatherDescription"])
            weather_desc = ""
            if desc_el:
                current = find_current_time_data(desc_el.get("Time", []))
                if current:
                    value = get_element_value(current)
                    weather_desc = get_value_ci(value, "WeatherDescription", "Description", "weatherDescription", "value", "Value") or ""
                    if not isinstance(weather_desc, str): weather_desc = str(weather_desc)

            weather = ""
            if weather_desc:
                weather = weather_desc.split("。")[0].strip()

            if not weather:
                wx_el = find_element(elements, ["天氣現象", "Wx", "Weather"])
                if wx_el:
                    current = find_current_time_data(wx_el.get("Time", []))
                    if current:
                        weather = get_value_ci(get_element_value(current), "Weather", "Wx", "value", "Value") or ""

            pop = None
            if weather_desc:
                m = re.search(r"降雨機率\s*(\d+)\s*%", weather_desc)
                if m: pop = m.group(1)
            if pop is None:
                pop_el = find_element(elements, ["12小時降雨機率", "6小時降雨機率", "PoP", "PoP6h", "ProbabilityOfPrecipitation"])
                if pop_el:
                    current = find_current_time_data(pop_el.get("Time", []))
                    if current:
                        pop = get_value_ci(get_element_value(current), "ProbabilityOfPrecipitation", "PoP", "PoP6h", "value", "Value")
                        if pop is not None: pop = str(pop)

            min_temp = max_temp = None
            if weather_desc:
                m = re.search(r"最低溫度\s*攝氏\s*(-?\d+(?:\.\d+)?)\s*度", weather_desc)
                if m: min_temp = m.group(1)
                m = re.search(r"最高溫度\s*攝氏\s*(-?\d+(?:\.\d+)?)\s*度", weather_desc)
                if m: max_temp = m.group(1)

            today_str = tw_time.strftime("%Y-%m-%d")
            if min_temp is None: min_temp = get_daily_temperature(elements, ["MinT", "MinTemperature", "最低溫度"], today_str)
            if max_temp is None: max_temp = get_daily_temperature(elements, ["MaxT", "MaxTemperature", "最高溫度"], today_str)

            return f"📍 {district} {min_temp if min_temp is not None else '?'}~{max_temp if max_temp is not None else '?'}° {weather or '天氣資料讀取中'} (降雨{pop if pop is not None else '?'}%)"

        weather_results = {}
        for dataset_id in weather_datasets:
            url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}"
            params = {"Authorization": CWA_API_KEY, "format": "JSON", "LocationName": ",".join(target_districts)}
            try:
                response = requests.get(url, params=params, timeout=15)
                if response.status_code != 200:
                    print(f"氣象 API {dataset_id} HTTP {response.status_code}"); continue
                records = response.json().get("records", {})
                locations = records.get("locations") or records.get("Locations") or []
                location_list = []
                for group in locations:
                    if isinstance(group, dict):
                        if "location" in group: location_list.extend(group.get("location", []))
                        elif "Location" in group: location_list.extend(group.get("Location", []))
                if not location_list: location_list = locations
                for location in location_list:
                    if isinstance(location, dict):
                        result = parse_location(location)
                        if result: weather_results[location.get("LocationName", "")] = result
            except Exception as e:
                print(f"氣象資料集 {dataset_id} 解析失敗：{e}")

        msg = f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        for district in target_districts:
            msg += weather_results.get(district, f"📍 {district} 天氣資料讀取中") + "\n"
        msg += "\n"
        msg += ("每天深蹲有益健康，肌肉是身體最大的葡萄糖使用器官，"
                "也是最大的血糖代謝器官，占比高達80%呢! "
                "2026年年底就會來到3000元的! "
                "祝福您吉祥如意闔家平安幸福永相隨。")
        return msg
    except Exception as e:
        return f"❌ 氣象解析失敗: {str(e)}"

# ------------------------------
# 台積電股價抓取 (優化 Headers)
# ------------------------------
def get_price_from_yahoo():

    url = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/2330.TW"
    )

    # 強化 Headers 模擬，避免被 Yahoo 拒絕連線
    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",

        "Accept":
            "text/html,application/xhtml+xml,application/json"
    }

    try:

        r = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if r.status_code != 200:
            return None

        data = r.json()

        return (
            data["chart"]["result"][0]
            ["meta"]["regularMarketPrice"]
        )

    except:

        return None


def get_price_from_finmind():

    url = (
        "https://api.finmindtrade.com/"
        "api/v4/data"
    )

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": "2330",
        "start_date": "2024-01-01"
    }

    try:

        r = requests.get(
            url,
            params=params,
            timeout=10
        )

        return r.json()["data"][-1]["close"]

    except:

        return None


def get_tsmc_price():

    price = get_price_from_yahoo()

    if price is not None:
        return price

    price = get_price_from_finmind()

    if price is not None:
        return price

    raise Exception("❌ 無法取得股價")


# ------------------------------
# Cloudflare KV 與 LINE 推播
# ------------------------------
def get_all_user_ids_from_cloudflare():

    if not all([
        CF_ACCOUNT_ID,
        CF_API_TOKEN,
        CF_KV_NAMESPACE_ID
    ]):
        return []

    url = (
        f"https://api.cloudflare.com/client/v4/"
        f"accounts/{CF_ACCOUNT_ID}/storage/kv/"
        f"namespaces/{CF_KV_NAMESPACE_ID}/keys"
    )

    headers = {
        "Authorization":
            f"Bearer {CF_API_TOKEN}",

        "Content-Type":
            "application/json"
    }

    user_ids = []

    cursor = None

    while True:

        params = {
            "limit": 1000
        }

        if cursor:
            params["cursor"] = cursor

        try:

            r = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )

            data = r.json()

            if not data.get("success"):
                break

            user_ids.extend([
                item["name"]
                for item in data["result"]
            ])

            cursor = data[
                "result_info"
            ].get("cursor")

            if not cursor:
                break

        except:

            break

    return user_ids


def send_line_message_to_all(
    user_ids,
    message
):

    if not user_ids or not message:
        return

    url = (
        "https://api.line.me/"
        "v2/bot/message/multicast"
    )

    headers = {
        "Content-Type":
            "application/json",

        "Authorization":
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    for i in range(
        0,
        len(user_ids),
        500
    ):

        batch_ids = user_ids[
            i:i + 500
        ]

        body = {
            "to": batch_ids,

            "messages": [
                {
                    "type": "text",
                    "text": message
                }
            ]
        }

        requests.post(
            url,
            headers=headers,
            json=body,
            timeout=10
        )


# ------------------------------
# 主程式
# ------------------------------
def main():

    all_users = (
        get_all_user_ids_from_cloudflare()
    )

    if not all_users:

        print(
            "❌ 無法取得用戶 ID，結束運行。"
        )

        return

    tw_time = (
        datetime.utcnow()
        + timedelta(hours=8)
    )

    tw_hour = tw_time.hour

    # --------------------------------------------------
    # 早上 7 點（或排程微小延遲的 8 點）
    # 只發送一次氣象，絕不重疊
    # --------------------------------------------------
    if tw_hour == 7 or tw_hour == 8:

        weather_msg = (
            get_weather_report()
        )

        send_line_message_to_all(
            all_users,
            weather_msg
        )

    # --------------------------------------------------
    # 下午 1 點到 6 點
    # 13:00 ~ 18:59
    # 執行台積電監控
    # --------------------------------------------------
    elif 13 <= tw_hour <= 18:

        try:

            price = get_tsmc_price()

            rsi_val = None
            bias_val = None

            # ------------------------------
            # 計算指標
            # ------------------------------
            try:

                h_url = (
                    "https://query1.finance.yahoo.com/"
                    "v8/finance/chart/2330.TW?"
                    "range=1mo&interval=1d"
                )

                # 歷史資料同步加入強化 Headers
                h_headers = {
                    "User-Agent":
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36"
                }

                r_hist = requests.get(
                    h_url,
                    headers=h_headers,
                    timeout=10
                )

                c = [
                    x
                    for x in (
                        r_hist.json()
                        ["chart"]["result"][0]
                        ["indicators"]["quote"][0]
                        ["close"]
                    )
                    if x is not None
                ]

                if len(c) > 14:

                    d = [
                        c[i] - c[i - 1]
                        for i in range(1, len(c))
                    ]

                    g = (
                        sum([
                            x
                            for x in d[-14:]
                            if x > 0
                        ]) / 14
                    )

                    l = (
                        sum([
                            -x
                            for x in d[-14:]
                            if x < 0
                        ]) / 14
                    )

                    rsi_val = (
                        round(
                            100 - (
                                100 /
                                (1 + (g / l))
                            ),
                            2
                        )
                        if l != 0
                        else 100
                    )

                if len(c) >= 20:

                    ma20 = (
                        sum(c[-20:]) / 20
                    )

                    bias_val = round(
                        (
                            (price - ma20)
                            / ma20
                        ) * 100,
                        2
                    )

            except:

                pass

            # ------------------------------
            # 組合訊息
            # ------------------------------
            indicators = []

            if rsi_val is not None:

                indicators.append(
                    f"14日RSI: {rsi_val}"
                )

            if bias_val is not None:

                indicators.append(
                    f"20日乖離率: {bias_val}%"
                )

            indicator_str = (
                f" ({'、'.join(indicators)})"
                if indicators
                else ""
            )

            overheat_note = (
                "\n目前指標過熱！"
                if (
                    (
                        rsi_val
                        and rsi_val > 75
                    )
                    or
                    (
                        bias_val
                        and bias_val > 10
                    )
                )
                else ""
            )

            # ------------------------------
            # 達標通知
            # ------------------------------
            if price >= TSMC_TARGET_PRICE:

                msg = (
                    f"📈 台積電股價已達 "
                    f"{price} 元！"
                    f"{indicator_str}\n"
                    f"（提醒門檻："
                    f"{TSMC_TARGET_PRICE}）"
                    f"{overheat_note}"
                )

                send_line_message_to_all(
                    all_users,
                    msg
                )

            # ------------------------------
            # 每日收盤行情
            # ------------------------------
            daily_msg = (
                f"📢 tsmc 今日收盤價："
                f"{price} 元"
                f"{indicator_str}"
                f"{overheat_note}"
            )

            send_line_message_to_all(
                all_users,
                daily_msg
            )

        except Exception as e:

            print(
                f"股市監控失敗: {e}"
            )

    # --------------------------------------------------
    # 其他時間
    # 例如深夜手動按下 Run 測試
    # 只單純推播天氣
    # --------------------------------------------------
    else:

        weather_msg = (
            get_weather_report()
        )

        send_line_message_to_all(
            all_users,
            weather_msg
        )


if __name__ == "__main__":
    main()
