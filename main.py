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

TSMC_TARGET_PRICE = 2500  # 您要通知的價格


# ------------------------------
# 氣象預報函式
# ------------------------------
def get_weather_report():

    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"

    # --------------------------------------------------
    # 臺北市、新北市鄉鎮天氣預報
    #
    # 臺北市：
    # F-D0047-061
    #
    # 新北市：
    # F-D0047-069
    # --------------------------------------------------

    weather_datasets = [
        "F-D0047-061",  # 臺北市
        "F-D0047-069"   # 新北市
    ]

    # 需要顯示的行政區
    target_districts = [
        "北投區",
        "萬華區",
        "淡水區",
        "信義區"
    ]

    try:

        # --------------------------------------------------
        # 台灣時間
        # --------------------------------------------------
        tw_time = datetime.utcnow() + timedelta(hours=8)

        week_list = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日"
        ]

        date_str = tw_time.strftime(
            f"%m/%d ({week_list[tw_time.weekday()]})"
        )

        # --------------------------------------------------
        # 時間解析
        # --------------------------------------------------
        def parse_time(time_string):

            if not time_string:
                return None

            try:

                return datetime.fromisoformat(
                    time_string.replace("Z", "+00:00")
                ).replace(tzinfo=None)

            except:

                return None

        # --------------------------------------------------
        # 取得指定 Element
        # --------------------------------------------------
        def get_element_times(elements, names):

            for element in elements:

                element_name = element.get(
                    "ElementName",
                    ""
                )

                if element_name in names:

                    return element.get(
                        "Time",
                        []
                    )

            return []

        # --------------------------------------------------
        # 從一個行政區取得天氣
        # --------------------------------------------------
        def get_district_weather(location):

            district_name = location.get(
                "LocationName",
                ""
            )

            if district_name not in target_districts:
                return None

            elements = location.get(
                "WeatherElement",
                []
            )

            # 防止 API 大小寫格式不同
            if not elements:

                elements = location.get(
                    "weatherElement",
                    []
                )

            # --------------------------------------------------
            # 天氣現象
            # --------------------------------------------------
            weather_times = get_element_times(
                elements,
                [
                    "天氣現象",
                    "Weather",
                    "Wx"
                ]
            )

            # --------------------------------------------------
            # 降雨機率
            # --------------------------------------------------
            pop_times = get_element_times(
                elements,
                [
                    "12小時降雨機率",
                    "ProbabilityOfPrecipitation",
                    "PoP"
                ]
            )

            # --------------------------------------------------
            # 最低溫
            # --------------------------------------------------
            min_temp_times = get_element_times(
                elements,
                [
                    "最低溫度",
                    "MinT",
                    "MinTemperature"
                ]
            )

            # --------------------------------------------------
            # 最高溫
            # --------------------------------------------------
            max_temp_times = get_element_times(
                elements,
                [
                    "最高溫度",
                    "MaxT",
                    "MaxTemperature"
                ]
            )

            # ==================================================
            # 找目前時段的天氣
            # ==================================================
            current_weather = None

            for item in weather_times:

                start_time = parse_time(
                    item.get("StartTime")
                )

                end_time = parse_time(
                    item.get("EndTime")
                )

                if start_time and end_time:

                    if start_time <= tw_time <= end_time:

                        value = item.get(
                            "ElementValue",
                            {}
                        )

                        current_weather = (
                            value.get("Weather")
                            or value.get("weather")
                            or value.get("WeatherDescription")
                        )

                        break

            # 如果沒有找到目前時段
            # 使用第一筆資料
            if not current_weather and weather_times:

                value = weather_times[0].get(
                    "ElementValue",
                    {}
                )

                current_weather = (
                    value.get("Weather")
                    or value.get("weather")
                    or value.get("WeatherDescription")
                )

            # ==================================================
            # 找目前時段的降雨機率
            # ==================================================
            current_pop = None

            for item in pop_times:

                start_time = parse_time(
                    item.get("StartTime")
                )

                end_time = parse_time(
                    item.get("EndTime")
                )

                if start_time and end_time:

                    if start_time <= tw_time <= end_time:

                        value = item.get(
                            "ElementValue",
                            {}
                        )

                        current_pop = (
                            value.get(
                                "ProbabilityOfPrecipitation"
                            )
                            or value.get("PoP")
                            or value.get("pop")
                        )

                        break

            # 如果沒有找到目前時段
            if current_pop is None and pop_times:

                value = pop_times[0].get(
                    "ElementValue",
                    {}
                )

                current_pop = (
                    value.get(
                        "ProbabilityOfPrecipitation"
                    )
                    or value.get("PoP")
                    or value.get("pop")
                )

            # ==================================================
            # 找今天最低溫
            # ==================================================
            min_temp = None

            today_str = tw_time.strftime(
                "%Y-%m-%d"
            )

            for item in min_temp_times:

                start_time = parse_time(
                    item.get("StartTime")
                )

                if (
                    start_time
                    and start_time.strftime(
                        "%Y-%m-%d"
                    ) == today_str
                ):

                    value = item.get(
                        "ElementValue",
                        {}
                    )

                    min_temp = (
                        value.get(
                            "MinTemperature"
                        )
                        or value.get("MinT")
                        or value.get("minT")
                    )

                    if min_temp is not None:
                        break

            # ==================================================
            # 找今天最高溫
            # ==================================================
            max_temp = None

            for item in max_temp_times:

                start_time = parse_time(
                    item.get("StartTime")
                )

                if (
                    start_time
                    and start_time.strftime(
                        "%Y-%m-%d"
                    ) == today_str
                ):

                    value = item.get(
                        "ElementValue",
                        {}
                    )

                    max_temp = (
                        value.get(
                            "MaxTemperature"
                        )
                        or value.get("MaxT")
                        or value.get("maxT")
                    )

                    if max_temp is not None:
                        break

            # ==================================================
            # 找不到今天溫度時，使用第一筆
            # ==================================================
            if min_temp is None and min_temp_times:

                value = min_temp_times[0].get(
                    "ElementValue",
                    {}
                )

                min_temp = (
                    value.get(
                        "MinTemperature"
                    )
                    or value.get("MinT")
                    or value.get("minT")
                )

            if max_temp is None and max_temp_times:

                value = max_temp_times[0].get(
                    "ElementValue",
                    {}
                )

                max_temp = (
                    value.get(
                        "MaxTemperature"
                    )
                    or value.get("MaxT")
                    or value.get("maxT")
                )

            # ==================================================
            # 預設值
            # ==================================================
            if current_weather is None:
                current_weather = "天氣資料讀取中"

            if current_pop is None:
                current_pop = "?"

            if min_temp is None:
                min_temp = "?"

            if max_temp is None:
                max_temp = "?"

            # ==================================================
            # 組成一行
            # ==================================================
            return (
                f"📍 {district_name} "
                f"{min_temp}~{max_temp}° "
                f"{current_weather} "
                f"(降雨{current_pop}%)"
            )

        # ==================================================
        # 取得兩個資料集
        # ==================================================
        weather_results = {}

        for dataset_id in weather_datasets:

            url = (
                "https://opendata.cwa.gov.tw/"
                f"api/v1/rest/datastore/{dataset_id}"
            )

            params = {
                "Authorization": CWA_API_KEY,
                "format": "JSON"
            }

            try:

                r = requests.get(
                    url,
                    params=params,
                    timeout=15
                )

                if r.status_code != 200:
                    continue

                data = r.json()

                locations = data.get(
                    "records",
                    {}
                ).get(
                    "Locations",
                    []
                )

                # --------------------------------------------------
                # API 有可能：
                #
                # Locations
                #   └─ Location
                #
                # 也可能直接就是 Location
                # --------------------------------------------------
                location_list = []

                for group in locations:

                    if isinstance(group, dict):

                        if "Location" in group:

                            location_list.extend(
                                group.get(
                                    "Location",
                                    []
                                )
                            )

                        elif "location" in group:

                            location_list.extend(
                                group.get(
                                    "location",
                                    []
                                )
                            )

                if not location_list:
                    location_list = locations

                # --------------------------------------------------
                # 解析每一個行政區
                # --------------------------------------------------
                for location in location_list:

                    result = get_district_weather(
                        location
                    )

                    if result:

                        district_name = location.get(
                            "LocationName",
                            ""
                        )

                        weather_results[
                            district_name
                        ] = result

            except Exception:
                # 某一個資料集失敗，不影響另一個
                continue

        # ==================================================
        # 組合 LINE 天氣訊息
        # ==================================================
        msg = (
            f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
        )

        # 按照指定順序顯示
        for district in target_districts:

            msg += (
                weather_results.get(
                    district,
                    f"📍 {district} 天氣資料讀取中"
                )
                + "\n"
            )

        msg += "\n"

        # ==================================================
        # 原本的文字完全保留
        # ==================================================
        msg += (
            "每天深蹲有益健康，肌肉是身體最大的葡萄糖使用器官，"
            "也是最大的血糖代謝器官，占比高達80%呢! "
            "2026年年底就會來到3000元的! "
            "祝福您吉祥如意闔家平安幸福永相隨。"
        )

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
