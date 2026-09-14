import requests
import os
import json
import re
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
    # 要查詢的行政區
    # 臺北市：北投、萬華、信義
    # 新北市：淡水
    # --------------------------------------------------
    target_districts = [
        "北投區",
        "萬華區",
        "淡水區",
        "信義區"
    ]

    # --------------------------------------------------
    # 資料集
    # --------------------------------------------------
    weather_datasets = {
        "F-D0047-061": ["北投區", "萬華區", "信義區"],
        "F-D0047-069": ["淡水區"]
    }

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

        # ==================================================
        # JSON 大小寫不敏感的工具
        # ==================================================

        def get_key_ci(obj, key_names, default=None):
            """
            不管 API 回傳：
            LocationName
            locationName
            LOCATIONNAME

            都可以找到。
            """
            if not isinstance(obj, dict):
                return default

            wanted = {
                str(x).replace("_", "").lower()
                for x in key_names
            }

            for key, value in obj.items():
                normalized = str(key).replace("_", "").lower()

                if normalized in wanted:
                    return value

            return default


        # ==================================================
        # 時間解析
        # ==================================================

        def parse_time(value):

            if not value:
                return None

            try:
                value = str(value)

                dt = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )

                # 轉成台灣時間的 naive datetime
                if dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)

                return dt

            except:

                # 第二種格式
                try:
                    return datetime.strptime(
                        str(value),
                        "%Y-%m-%d %H:%M:%S"
                    )
                except:
                    return None


        # ==================================================
        # 遞迴搜尋所有行政區 Location
        #
        # 不再假設一定是：
        # records -> Locations -> Location
        #
        # 只要 JSON 裡有 LocationName，就可以找到。
        # ==================================================

        def find_all_locations(obj):

            result = []

            if isinstance(obj, dict):

                location_name = get_key_ci(
                    obj,
                    [
                        "LocationName",
                        "locationName"
                    ]
                )

                weather_elements = get_key_ci(
                    obj,
                    [
                        "WeatherElement",
                        "weatherElement"
                    ]
                )

                # 必須同時有行政區名稱與天氣資料
                if (
                    location_name
                    and isinstance(weather_elements, list)
                ):
                    result.append(obj)

                # 繼續往下找
                for value in obj.values():

                    result.extend(
                        find_all_locations(value)
                    )

            elif isinstance(obj, list):

                for item in obj:
                    result.extend(
                        find_all_locations(item)
                    )

            return result


        # ==================================================
        # 找 WeatherElement
        # ==================================================

        def get_weather_elements(location):

            elements = get_key_ci(
                location,
                [
                    "WeatherElement",
                    "weatherElement"
                ],
                []
            )

            if isinstance(elements, list):
                return elements

            return []


        # ==================================================
        # 找指定 Element
        # ==================================================

        def find_element(elements, names):

            wanted = {
                str(x).replace("_", "").lower()
                for x in names
            }

            for element in elements:

                if not isinstance(element, dict):
                    continue

                element_name = get_key_ci(
                    element,
                    [
                        "ElementName",
                        "elementName"
                    ],
                    ""
                )

                normalized = str(
                    element_name
                ).replace("_", "").lower()

                if normalized in wanted:
                    return element

            return None


        # ==================================================
        # 取得 Time
        # ==================================================

        def get_times(element):

            if not element:
                return []

            times = get_key_ci(
                element,
                [
                    "Time",
                    "time"
                ],
                []
            )

            if isinstance(times, list):
                return times

            return []


        # ==================================================
        # 取得 ElementValue
        # ==================================================

        def get_element_value(item):

            if not isinstance(item, dict):
                return {}

            value = get_key_ci(
                item,
                [
                    "ElementValue",
                    "elementValue"
                ],
                {}
            )

            if isinstance(value, dict):
                return value

            return {}


        # ==================================================
        # 找目前時段
        # ==================================================

        def find_current_time_data(times):

            if not times:
                return None

            # ----------------------------------------------
            # 第一優先：
            # StartTime <= 現在 < EndTime
            # ----------------------------------------------

            for item in times:

                if not isinstance(item, dict):
                    continue

                start = parse_time(
                    get_key_ci(
                        item,
                        ["StartTime", "startTime"]
                    )
                )

                end = parse_time(
                    get_key_ci(
                        item,
                        ["EndTime", "endTime"]
                    )
                )

                if start and end:

                    if start <= tw_time < end:
                        return item

            # ----------------------------------------------
            # 第二優先：
            # DataTime <= 現在
            # 取最新一筆
            # ----------------------------------------------

            latest = None
            latest_time = None

            for item in times:

                if not isinstance(item, dict):
                    continue

                data_time = parse_time(
                    get_key_ci(
                        item,
                        ["DataTime", "dataTime"]
                    )
                )

                if data_time and data_time <= tw_time:

                    if (
                        latest_time is None
                        or data_time > latest_time
                    ):
                        latest = item
                        latest_time = data_time

            if latest:
                return latest

            # ----------------------------------------------
            # 第三優先：
            # 找下一個即將開始的時段
            # ----------------------------------------------

            future_item = None
            future_time = None

            for item in times:

                if not isinstance(item, dict):
                    continue

                start = parse_time(
                    get_key_ci(
                        item,
                        ["StartTime", "startTime"]
                    )
                )

                if start and start > tw_time:

                    if (
                        future_time is None
                        or start < future_time
                    ):
                        future_item = item
                        future_time = start

            if future_item:
                return future_item

            # ----------------------------------------------
            # 最後使用第一筆
            # ----------------------------------------------

            return times[0]


        # ==================================================
        # 找今天的最高/最低溫
        # ==================================================

        def get_today_temperature(
            elements,
            temperature_names,
            value_names
        ):

            element = find_element(
                elements,
                temperature_names
            )

            if not element:
                return None

            times = get_times(element)

            today = tw_time.strftime("%Y-%m-%d")

            for item in times:

                if not isinstance(item, dict):
                    continue

                start = parse_time(
                    get_key_ci(
                        item,
                        ["StartTime", "startTime"]
                    )
                )

                data_time = parse_time(
                    get_key_ci(
                        item,
                        ["DataTime", "dataTime"]
                    )
                )

                check_time = start or data_time

                if not check_time:
                    continue

                if check_time.strftime("%Y-%m-%d") != today:
                    continue

                value = get_element_value(item)

                for value_name in value_names:

                    temperature = get_key_ci(
                        value,
                        [value_name]
                    )

                    if temperature is not None:
                        return temperature

            return None


        # ==================================================
        # 如果 MinT / MaxT 抓不到
        # 就從「溫度」全天資料中計算
        # ==================================================

        def get_temperature_range_from_temperature_element(
            elements
        ):

            temperature_element = find_element(
                elements,
                [
                    "溫度",
                    "Temperature",
                    "T"
                ]
            )

            if not temperature_element:
                return None, None

            times = get_times(
                temperature_element
            )

            today = tw_time.strftime("%Y-%m-%d")

            temperatures = []

            for item in times:

                if not isinstance(item, dict):
                    continue

                start = parse_time(
                    get_key_ci(
                        item,
                        ["StartTime", "startTime"]
                    )
                )

                data_time = parse_time(
                    get_key_ci(
                        item,
                        ["DataTime", "dataTime"]
                    )
                )

                check_time = start or data_time

                if not check_time:
                    continue

                if check_time.strftime("%Y-%m-%d") != today:
                    continue

                value = get_element_value(item)

                temp = get_key_ci(
                    value,
                    [
                        "Temperature",
                        "temperature",
                        "T"
                    ]
                )

                if temp is None:
                    continue

                # 可能是數字，也可能是 "28"
                match = re.search(
                    r"-?\d+(?:\.\d+)?",
                    str(temp)
                )

                if match:

                    temperatures.append(
                        float(match.group(0))
                    )

            if not temperatures:
                return None, None

            return (
                int(min(temperatures)),
                int(max(temperatures))
            )


        # ==================================================
        # 解析天氣描述
        # ==================================================

        def parse_weather_description(elements):

            weather_desc_element = find_element(
                elements,
                [
                    "天氣預報綜合描述",
                    "WeatherDescription"
                ]
            )

            if not weather_desc_element:
                return "", None

            times = get_times(
                weather_desc_element
            )

            current = find_current_time_data(
                times
            )

            if not current:
                return "", None

            value = get_element_value(
                current
            )

            weather_desc = get_key_ci(
                value,
                [
                    "WeatherDescription",
                    "weatherDescription",
                    "Description",
                    "description"
                ],
                ""
            )

            weather_desc = str(
                weather_desc or ""
            ).strip()

            if not weather_desc:
                return "", None

            # ----------------------------------------------
            # 天氣現象
            #
            # 例如：
            # 陰短暫陣雨。
            # 降雨機率40%。
            # ----------------------------------------------

            weather = weather_desc

            if "。" in weather_desc:
                weather = weather_desc.split(
                    "。"
                )[0].strip()

            # ----------------------------------------------
            # 降雨機率
            # ----------------------------------------------

            pop = None

            match = re.search(
                r"降雨機率\s*(\d+)\s*%",
                weather_desc
            )

            if match:
                pop = match.group(1)

            return weather, pop


        # ==================================================
        # 解析單一行政區
        # ==================================================

        def parse_location(location):

            district = get_key_ci(
                location,
                [
                    "LocationName",
                    "locationName"
                ],
                ""
            )

            if district not in target_districts:
                return None

            elements = get_weather_elements(
                location
            )

            if not elements:
                return None

            # ==================================================
            # 1. 天氣描述
            # ==================================================

            weather, pop = parse_weather_description(
                elements
            )

            # ==================================================
            # 2. 如果天氣描述沒有資料
            #    改抓「天氣現象」
            # ==================================================

            if not weather:

                weather_element = find_element(
                    elements,
                    [
                        "天氣現象",
                        "Wx",
                        "Weather"
                    ]
                )

                if weather_element:

                    current = find_current_time_data(
                        get_times(
                            weather_element
                        )
                    )

                    if current:

                        value = get_element_value(
                            current
                        )

                        weather = get_key_ci(
                            value,
                            [
                                "Weather",
                                "weather",
                                "Wx",
                                "wx"
                            ],
                            ""
                        )

                        weather = str(
                            weather or ""
                        ).strip()

            # ==================================================
            # 3. 降雨機率
            # ==================================================

            if pop is None:

                pop_element = find_element(
                    elements,
                    [
                        "12小時降雨機率",
                        "6小時降雨機率",
                        "降雨機率",
                        "PoP",
                        "PoP6h",
                        "ProbabilityOfPrecipitation"
                    ]
                )

                if pop_element:

                    current = find_current_time_data(
                        get_times(
                            pop_element
                        )
                    )

                    if current:

                        value = get_element_value(
                            current
                        )

                        pop = get_key_ci(
                            value,
                            [
                                "ProbabilityOfPrecipitation",
                                "PoP",
                                "PoP6h",
                                "降雨機率"
                            ]
                        )

            # ==================================================
            # 4. 最低溫
            # ==================================================

            min_temp = get_today_temperature(
                elements,
                [
                    "最低溫度",
                    "MinT",
                    "MinTemperature"
                ],
                [
                    "MinTemperature",
                    "minTemperature",
                    "MinT",
                    "minT",
                    "最低溫度"
                ]
            )

            # ==================================================
            # 5. 最高溫
            # ==================================================

            max_temp = get_today_temperature(
                elements,
                [
                    "最高溫度",
                    "MaxT",
                    "MaxTemperature"
                ],
                [
                    "MaxTemperature",
                    "maxTemperature",
                    "MaxT",
                    "maxT",
                    "最高溫度"
                ]
            )

            # ==================================================
            # 6. 如果最高/最低溫抓不到
            #    從「溫度」全天資料計算
            # ==================================================

            if min_temp is None or max_temp is None:

                calc_min, calc_max = (
                    get_temperature_range_from_temperature_element(
                        elements
                    )
                )

                if min_temp is None:
                    min_temp = calc_min

                if max_temp is None:
                    max_temp = calc_max

            # ==================================================
            # 7. 最後整理
            # ==================================================

            if not weather:
                weather = "天氣資料讀取中"

            if pop is None:
                pop = "?"

            if min_temp is None:
                min_temp = "?"

            if max_temp is None:
                max_temp = "?"

            return (
                f"📍 {district} "
                f"{min_temp}~{max_temp}° "
                f"{weather} "
                f"(降雨{pop}%)"
            )

        # ==================================================
        # 取得兩個城市資料
        # ==================================================

        weather_results = {}

        for dataset_id, districts in weather_datasets.items():

            url = (
                "https://opendata.cwa.gov.tw/"
                f"api/v1/rest/datastore/{dataset_id}"
            )

            params = {
                "Authorization": CWA_API_KEY,
                "format": "JSON"
            }

            # --------------------------------------------------
            # 直接指定需要的行政區
            # 這樣不用下載整個城市所有資料
            # --------------------------------------------------

            params["locationName"] = ",".join(
                districts
            )

            try:

                response = requests.get(
                    url,
                    params=params,
                    timeout=15
                )

                print(
                    f"CWA {dataset_id} HTTP "
                    f"{response.status_code}"
                )

                if response.status_code != 200:

                    print(
                        f"氣象 API {dataset_id} "
                        f"HTTP {response.status_code}"
                    )

                    continue

                data = response.json()

                # --------------------------------------------------
                # 找出 API 實際回傳的所有行政區
                # --------------------------------------------------

                all_locations = find_all_locations(
                    data
                )

                discovered_names = []

                for location in all_locations:

                    name = get_key_ci(
                        location,
                        [
                            "LocationName",
                            "locationName"
                        ],
                        ""
                    )

                    if name and name not in discovered_names:
                        discovered_names.append(name)

                print(
                    f"CWA {dataset_id} 找到行政區："
                    f"{discovered_names}"
                )

                # --------------------------------------------------
                # 解析需要的行政區
                # --------------------------------------------------

                for location in all_locations:

                    district = get_key_ci(
                        location,
                        [
                            "LocationName",
                            "locationName"
                        ],
                        ""
                    )

                    if district not in districts:
                        continue

                    result = parse_location(
                        location
                    )

                    if result:

                        weather_results[
                            district
                        ] = result

            except Exception as e:

                print(
                    f"氣象資料集 {dataset_id} "
                    f"解析失敗：{e}"
                )

        # ==================================================
        # 組合 LINE 訊息
        # ==================================================

        msg = (
            f"🌤 一分鐘報天氣 "
            f"{date_str} 🌤\n\n"
        )

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
        # 原本訊息完全保留
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
    # 只發送一次氣象
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
    # 例如深夜手動按下 Run
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
