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
    """
    使用中央氣象署 F-D0047 鄉鎮天氣預報：
    - F-D0047-061：臺北市
    - F-D0047-069：新北市

    顯示：
    北投區、萬華區、淡水區、信義區
    今日最低溫~最高溫、目前天氣、目前降雨機率
    """

    if not CWA_API_KEY:
        return "⚠️ 缺少 CWA_API_KEY，無法取得氣象資訊。"

    weather_datasets = [
        "F-D0047-061",  # 臺北市
        "F-D0047-069"   # 新北市
    ]

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

        today_str = tw_time.strftime("%Y-%m-%d")

        # --------------------------------------------------
        # 大小寫不敏感取值
        # --------------------------------------------------
        def get_value_ci(data, *keys):
            if not isinstance(data, dict):
                return None

            for key in keys:
                if key in data:
                    return data[key]

            lower_map = {
                str(k).lower(): v
                for k, v in data.items()
            }

            for key in keys:
                if str(key).lower() in lower_map:
                    return lower_map[str(key).lower()]

            return None

        # --------------------------------------------------
        # CWA JSON 的 elementValue 是「陣列」
        #
        # 實際格式：
        # "elementValue": [
        #     {"value": "28"}
        # ]
        #
        # 這是前一版讀不到溫度、天氣、降雨機率的主要原因。
        # --------------------------------------------------
        def get_element_value(item):
            value = get_value_ci(
                item,
                "ElementValue",
                "elementValue"
            )

            if isinstance(value, list):
                if not value:
                    return {}

                first = value[0]

                if isinstance(first, dict):
                    return first

                return {"value": first}

            if isinstance(value, dict):
                return value

            if value is None:
                return {}

            return {"value": value}

        # --------------------------------------------------
        # 時間解析
        # --------------------------------------------------
        def parse_time(value):
            if not value:
                return None

            try:
                text = str(value).strip()

                # 例如：
                # 2026-09-14T06:00:00+08:00
                # 2026-09-14T06:00:00
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"

                dt = datetime.fromisoformat(text)

                # CWA 鄉鎮預報通常就是 +08:00。
                # 如果沒有時區，直接視為台灣時間。
                if dt.tzinfo is None:
                    return dt

                # 將 UTC / 其他時區轉成台灣時間。
                # 不額外 import timezone，直接以 UTC offset 計算。
                utc_dt = dt.astimezone(
                    __import__("datetime").timezone.utc
                )

                tw_dt = utc_dt + timedelta(hours=8)

                return tw_dt.replace(tzinfo=None)

            except Exception:
                return None

        # --------------------------------------------------
        # 取得 WeatherElement
        # --------------------------------------------------
        def get_weather_elements(location):
            elements = get_value_ci(
                location,
                "weatherElement",
                "WeatherElement"
            )

            return elements if isinstance(elements, list) else []

        # --------------------------------------------------
        # 取得 ElementName
        # --------------------------------------------------
        def get_element_name(element):
            return get_value_ci(
                element,
                "elementName",
                "ElementName"
            ) or ""

        # --------------------------------------------------
        # 尋找指定的 WeatherElement
        # --------------------------------------------------
        def find_element(elements, names):
            wanted = {
                str(name).lower()
                for name in names
            }

            for element in elements:
                name = str(
                    get_element_name(element)
                ).lower()

                if name in wanted:
                    return element

            return None

        # --------------------------------------------------
        # 取得 time 陣列
        # --------------------------------------------------
        def get_times(element):
            times = get_value_ci(
                element,
                "time",
                "Time"
            )

            return times if isinstance(times, list) else []

        # --------------------------------------------------
        # 找目前有效的時間區間
        # --------------------------------------------------
        def find_current_time_data(times):
            if not times:
                return None

            # 第一優先：StartTime <= 現在 < EndTime
            for item in times:
                start = parse_time(
                    get_value_ci(
                        item,
                        "startTime",
                        "StartTime"
                    )
                )

                end = parse_time(
                    get_value_ci(
                        item,
                        "endTime",
                        "EndTime"
                    )
                )

                if start and end:
                    if start <= tw_time < end:
                        return item

            # 第二優先：DataTime <= 現在，
            # 取最新的一筆
            latest = None
            latest_time = None

            for item in times:
                data_time = parse_time(
                    get_value_ci(
                        item,
                        "dataTime",
                        "DataTime"
                    )
                )

                if data_time and data_time <= tw_time:
                    if (
                        latest_time is None
                        or data_time > latest_time
                    ):
                        latest = item
                        latest_time = data_time

            if latest is not None:
                return latest

            # 最後使用第一筆
            return times[0]

        # --------------------------------------------------
        # 從 elementValue 取真正的 value
        # --------------------------------------------------
        def get_real_value(item):
            value = get_element_value(item)

            # CWA JSON 最常見：
            # {"value": "28"}
            result = get_value_ci(
                value,
                "value",
                "Value"
            )

            if result is not None:
                return result

            # 某些舊/不同格式可能直接把欄位名稱放裡面
            for key in [
                "WeatherDescription",
                "Weather",
                "Wx",
                "ProbabilityOfPrecipitation",
                "PoP",
                "PoP6h",
                "MinTemperature",
                "MaxTemperature",
                "MinT",
                "MaxT"
            ]:
                result = get_value_ci(
                    value,
                    key
                )

                if result is not None:
                    return result

            return None

        # --------------------------------------------------
        # 取得指定日期的最高/最低溫
        # --------------------------------------------------
        def get_daily_temperature(
            elements,
            element_names,
            today
        ):
            element = find_element(
                elements,
                element_names
            )

            if not element:
                return None

            times = get_times(element)

            # 先找今天的資料
            for item in times:
                check_time = parse_time(
                    get_value_ci(
                        item,
                        "dataTime",
                        "DataTime"
                    )
                )

                if check_time is None:
                    check_time = parse_time(
                        get_value_ci(
                            item,
                            "startTime",
                            "StartTime"
                        )
                    )

                if (
                    check_time
                    and check_time.strftime("%Y-%m-%d")
                    == today
                ):
                    value = get_real_value(item)

                    if value is not None and str(value).strip() != "":
                        return value

            # 如果日期欄位沒有符合，再嘗試第一筆
            if times:
                value = get_real_value(times[0])

                if value is not None and str(value).strip() != "":
                    return value

            return None

        # --------------------------------------------------
        # 解析單一行政區
        # --------------------------------------------------
        def parse_location(location):
            district = get_value_ci(
                location,
                "locationName",
                "LocationName"
            ) or ""

            if district not in target_districts:
                return None

            elements = get_weather_elements(location)

            if not elements:
                print(
                    f"CWA 找到 {district}，但沒有 weatherElement"
                )
                return None

            # ==================================================
            # 1. WeatherDescription
            # ==================================================
            weather_desc = ""

            weather_desc_element = find_element(
                elements,
                [
                    "WeatherDescription",
                    "天氣預報綜合描述"
                ]
            )

            if weather_desc_element:
                current = find_current_time_data(
                    get_times(weather_desc_element)
                )

                if current:
                    value = get_real_value(current)

                    if value is not None:
                        weather_desc = str(value).strip()

            # ==================================================
            # 2. Wx / Weather
            # ==================================================
            weather = ""

            weather_element = find_element(
                elements,
                [
                    "Wx",
                    "Weather",
                    "天氣現象"
                ]
            )

            if weather_element:
                current = find_current_time_data(
                    get_times(weather_element)
                )

                if current:
                    value = get_real_value(current)

                    if value is not None:
                        weather = str(value).strip()

            # WeatherDescription 通常會包含：
            # 「陰短暫陣雨。降雨機率40%。溫度攝氏...」
            #
            # 使用第一個「。」以前的內容作為簡短天氣。
            if weather_desc:
                first_sentence = (
                    weather_desc
                    .split("。")[0]
                    .strip()
                )

                if first_sentence:
                    weather = first_sentence

            # ==================================================
            # 3. 降雨機率
            # ==================================================
            pop = None

            if weather_desc:
                match = re.search(
                    r"降雨機率\s*(\d+)\s*%",
                    weather_desc
                )

                if match:
                    pop = match.group(1)

            # 如果 WeatherDescription 沒有降雨機率，
            # 再抓 PoP / PoP6h
            if pop is None:
                pop_element = find_element(
                    elements,
                    [
                        "PoP",
                        "PoP6h",
                        "12小時降雨機率",
                        "6小時降雨機率",
                        "ProbabilityOfPrecipitation"
                    ]
                )

                if pop_element:
                    current = find_current_time_data(
                        get_times(pop_element)
                    )

                    if current:
                        value = get_real_value(current)

                        if value is not None:
                            pop = str(value).strip()

            # ==================================================
            # 4. 今日最低溫
            # ==================================================
            min_temp = get_daily_temperature(
                elements,
                [
                    "MinT",
                    "MinTemperature",
                    "最低溫度"
                ],
                today_str
            )

            # ==================================================
            # 5. 今日最高溫
            # ==================================================
            max_temp = get_daily_temperature(
                elements,
                [
                    "MaxT",
                    "MaxTemperature",
                    "最高溫度"
                ],
                today_str
            )

            # ==================================================
            # 6. 最後整理
            # ==================================================
            if not weather:
                weather = "天氣資料讀取中"

            if pop is None:
                pop = "?"

            if min_temp is None:
                min_temp = "?"

            if max_temp is None:
                max_temp = "?"

            # 數字如果是 28.0，顯示成 28
            def clean_number(value):
                if value is None:
                    return "?"

                text = str(value).strip()

                try:
                    number = float(text)

                    if number.is_integer():
                        return str(int(number))

                    return str(number)

                except Exception:
                    return text

            min_temp = clean_number(min_temp)
            max_temp = clean_number(max_temp)
            pop = clean_number(pop)

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

        for dataset_id in weather_datasets:
            url = (
                "https://opendata.cwa.gov.tw/"
                f"api/v1/rest/datastore/{dataset_id}"
            )

            params = {
                "Authorization": CWA_API_KEY,
                "format": "JSON",

                # 只要求需要的四個行政區，
                # 減少 API 回傳資料量。
                "LocationName": ",".join(
                    target_districts
                )
            }

            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=15
                )

                if response.status_code != 200:
                    print(
                        f"氣象 API {dataset_id} "
                        f"HTTP {response.status_code}"
                    )
                    continue

                data = response.json()

                records = data.get(
                    "records",
                    {}
                )

                # CWA 鄉鎮 JSON 實際主要結構：
                #
                # records
                #   └── locations
                #         └── location
                #
                locations_groups = get_value_ci(
                    records,
                    "locations",
                    "Locations"
                )

                location_list = []

                if isinstance(
                    locations_groups,
                    list
                ):
                    for group in locations_groups:
                        if not isinstance(group, dict):
                            continue

                        group_locations = get_value_ci(
                            group,
                            "location",
                            "Location"
                        )

                        if isinstance(
                            group_locations,
                            list
                        ):
                            location_list.extend(
                                group_locations
                            )

                elif isinstance(
                    locations_groups,
                    dict
                ):
                    group_locations = get_value_ci(
                        locations_groups,
                        "location",
                        "Location"
                    )

                    if isinstance(
                        group_locations,
                        list
                    ):
                        location_list.extend(
                            group_locations
                        )

                # 某些格式直接就是 location 陣列
                if not location_list:
                    direct_locations = get_value_ci(
                        records,
                        "location",
                        "Location"
                    )

                    if isinstance(
                        direct_locations,
                        list
                    ):
                        location_list = direct_locations

                print(
                    f"CWA {dataset_id} 找到行政區："
                    f"{[get_value_ci(x, 'locationName', 'LocationName') for x in location_list if isinstance(x, dict)]}"
                )

                for location in location_list:
                    if not isinstance(
                        location,
                        dict
                    ):
                        continue

                    result = parse_location(
                        location
                    )

                    if result:
                        district = get_value_ci(
                            location,
                            "locationName",
                            "LocationName"
                        )

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
