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
    target_districts = ["北投區", "萬華區", "信義區", "淡水區"]
    rain_hours = [7, 13, 19]

    try:
        tw_time = datetime.utcnow() + timedelta(hours=8)
        week_list = [
            "星期一", "星期二", "星期三", "星期四",
            "星期五", "星期六", "星期日"
        ]
        date_str = tw_time.strftime(
            f"%m/%d ({week_list[tw_time.weekday()]})"
        )

        def parse_time(value):
            if not value:
                return None
            try:
                dt = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
                if dt.tzinfo is not None:
                    from datetime import timezone
                    dt = dt.astimezone(
                        timezone(timedelta(hours=8))
                    )
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
                # CWA 部分資料會把多個欄位放在同一個 ElementValue 陣列，
                # 不只取第一個，避免第一個不是降雨機率。
                merged = {}
                for v in value:
                    if isinstance(v, dict):
                        merged.update(v)
                return merged
            return value if isinstance(value, dict) else {}

        def get_value_ci(value, *keys):
            if not isinstance(value, dict):
                return None
            for key in keys:
                if key in value:
                    return value[key]
            lower_map = {
                str(k).lower(): v
                for k, v in value.items()
            }
            for key in keys:
                if key.lower() in lower_map:
                    return lower_map[key.lower()]
            return None

        def find_current_time_data(times):
            if not times:
                return None

            for item in times:
                start = parse_time(item.get("StartTime"))
                end = parse_time(item.get("EndTime"))
                if start and end and start <= tw_time < end:
                    return item

            latest = None
            for item in times:
                data_time = parse_time(item.get("DataTime"))
                if data_time and data_time <= tw_time:
                    if (
                        latest is None
                        or data_time > (
                            parse_time(latest.get("DataTime"))
                            or datetime.min
                        )
                    ):
                        latest = item

            return latest if latest is not None else times[0]

        def get_value_for_target_time(times, target_time):
            """找出涵蓋指定時間的預報資料。"""
            if not times:
                return None

            # 優先使用 StartTime / EndTime 判斷預報區間。
            for item in times:
                start = parse_time(item.get("StartTime"))
                end = parse_time(item.get("EndTime"))
                if start and end and start <= target_time < end:
                    return get_value_ci(
                        get_element_value(item),
                        "ProbabilityOfPrecipitation",
                        "PoP6h",
                        "PoP",
                        "value",
                        "Value"
                    )

            # 某些資料格式只有 DataTime，則取 target 前最近的一筆。
            latest = None
            latest_time = None
            for item in times:
                data_time = parse_time(item.get("DataTime"))
                if data_time and data_time <= target_time:
                    if latest_time is None or data_time > latest_time:
                        latest = item
                        latest_time = data_time

            if latest is not None:
                return get_value_ci(
                    get_element_value(latest),
                    "ProbabilityOfPrecipitation",
                    "PoP6h",
                    "PoP",
                    "value",
                    "Value"
                )

            return None

        def get_rain_probabilities(elements):
            """
            取得 07:00、13:00、19:00 的降雨機率。

            優先：
              1. PoP6h 元素
              2. WeatherDescription 中的「降雨機率XX%」

            這樣可以相容中央氣象署不同 JSON 格式。
            """

            result = {
                hour: None
                for hour in rain_hours
            }

            def extract_probability(value):
                if value is None:
                    return None

                if isinstance(value, bool):
                    return None

                if isinstance(value, (int, float)):
                    return (
                        str(int(value))
                        if float(value).is_integer()
                        else str(value)
                    )

                text = str(value).strip()

                # 直接抓「降雨機率 20%」
                patterns = [
                    r"降雨機率\s*(\d+(?:\.\d+)?)\s*%",
                    r"降雨機率\s*(\d+(?:\.\d+)?)\s*％",

                    # 英文欄位格式
                    r"ProbabilityOfPrecipitation\s*[=:：]\s*(\d+(?:\.\d+)?)",
                    r"PoP6h\s*[=:：]\s*(\d+(?:\.\d+)?)",
                    r"PoP\s*[=:：]\s*(\d+(?:\.\d+)?)"
                ]

                for pattern in patterns:
                    match = re.search(
                        pattern,
                        text,
                        re.IGNORECASE
                    )

                    if match:
                        return match.group(1)

                # 如果本身就是「20」或「20%」
                match = re.fullmatch(
                    r"\s*(\d+(?:\.\d+)?)\s*%?\s*",
                    text
                )

                if match:
                    return match.group(1)

                return None

            def recursive_probability(value):
                """
                遞迴尋找 CWA JSON 裡的降雨機率，
                相容 dict / list / 不同大小寫欄位名稱。
                """

                if isinstance(value, dict):

                    # 先找最可能的欄位
                    preferred_keys = [
                        "ProbabilityOfPrecipitation",
                        "PoP6h",
                        "PoP",
                        "probabilityofprecipitation",
                        "pop6h",
                        "pop",
                        "6小時降雨機率"
                    ]

                    for key in preferred_keys:
                        if key in value:
                            found = extract_probability(
                                value[key]
                            )

                            if found is not None:
                                return found

                    # 不同 JSON 可能是：
                    # {"value": "20", "measure": "百分比"}
                    raw_value = value.get(
                        "value",
                        value.get("Value")
                    )

                    measure = value.get(
                        "measure",
                        value.get("Measure", "")
                    )

                    if raw_value is not None:

                        found = extract_probability(
                            raw_value
                        )

                        if found is not None:

                            # 有百分比標示，直接採用
                            if (
                                "百分比" in str(measure)
                                or "%" in str(raw_value)
                                or "％" in str(raw_value)
                            ):
                                return found

                    # 繼續往下搜尋所有欄位
                    for val in value.values():

                        found = recursive_probability(val)

                        if found is not None:
                            return found

                elif isinstance(value, list):

                    for val in value:

                        found = recursive_probability(val)

                        if found is not None:
                            return found

                return None

            def item_probability(item):

                # 標準 CWA JSON
                found = recursive_probability(
                    item.get("ElementValue")
                )

                if found is not None:
                    return found

                # 有些版本直接放在 Time 裡
                for key in [
                    "ProbabilityOfPrecipitation",
                    "PoP6h",
                    "PoP",
                    "6小時降雨機率"
                ]:

                    if key in item:

                        found = extract_probability(
                            item.get(key)
                        )

                        if found is not None:
                            return found

                return None

            # ==================================================
            # 第一階段：尋找 PoP6h
            # ==================================================

            pop6h_elements = []

            for element in elements:

                name = str(
                    element.get(
                        "ElementName",
                        ""
                    )
                ).strip()

                if (
                    name.lower() == "pop6h"
                    or name == "6小時降雨機率"
                ):
                    pop6h_elements.append(element)

            for element in pop6h_elements:

                times = element.get(
                    "Time",
                    []
                )

                if not isinstance(times, list):
                    continue

                for hour in rain_hours:

                    if result[hour] is not None:
                        continue

                    target_time = tw_time.replace(
                        hour=hour,
                        minute=0,
                        second=0,
                        microsecond=0
                    )

                    # 先用 StartTime / EndTime
                    for item in times:

                        start = parse_time(
                            item.get("StartTime")
                        )

                        end = parse_time(
                            item.get("EndTime")
                        )

                        if not (start and end):
                            continue

                        if start <= target_time < end:

                            value = item_probability(
                                item
                            )

                            if value is not None:

                                result[hour] = value

                                break

                    # 沒有 StartTime / EndTime 時，
                    # 使用 DataTime 前最近的一筆
                    if result[hour] is None:

                        candidates = []

                        for item in times:

                            data_time = parse_time(
                                item.get("DataTime")
                            )

                            if (
                                data_time is not None
                                and data_time <= target_time
                            ):

                                value = item_probability(
                                    item
                                )

                                if value is not None:

                                    candidates.append(
                                        (
                                            data_time,
                                            value
                                        )
                                    )

                        if candidates:

                            candidates.sort(
                                key=lambda x: x[0]
                            )

                            result[hour] = candidates[-1][1]

            # ==================================================
            # 第二階段：
            # 如果 PoP6h 找不到，從 WeatherDescription 抓
            # 「降雨機率20%」之類的文字
            # ==================================================

            desc_el = find_element(
                elements,
                [
                    "天氣預報綜合描述",
                    "WeatherDescription"
                ]
            )

            if desc_el:

                times = desc_el.get(
                    "Time",
                    []
                )

                if isinstance(times, list):

                    for hour in rain_hours:

                        if result[hour] is not None:
                            continue

                        target_time = tw_time.replace(
                            hour=hour,
                            minute=0,
                            second=0,
                            microsecond=0
                        )

                        matched_item = None

                        # 先找涵蓋指定時間的區間
                        for item in times:

                            start = parse_time(
                                item.get("StartTime")
                            )

                            end = parse_time(
                                item.get("EndTime")
                            )

                            if (
                                start
                                and end
                                and start <= target_time < end
                            ):

                                matched_item = item
                                break

                        # 如果沒有區間，找完全相同 DataTime
                        if matched_item is None:

                            for item in times:

                                data_time = parse_time(
                                    item.get("DataTime")
                                )

                                if (
                                    data_time is not None
                                    and data_time == target_time
                                ):

                                    matched_item = item
                                    break

                        if matched_item:

                            value = get_element_value(
                                matched_item
                            )

                            description = get_value_ci(
                                value,
                                "WeatherDescription",
                                "Description",
                                "weatherDescription",
                                "value",
                                "Value"
                            )

                            probability = extract_probability(
                                description
                            )

                            if probability is not None:

                                result[hour] = probability

            # ==================================================
            # 第三階段：
            # WeatherDescription 沒有完全對應時間時，
            # 找指定時間之前最近一筆
            # ==================================================

            if desc_el:

                times = desc_el.get(
                    "Time",
                    []
                )

                if isinstance(times, list):

                    for hour in rain_hours:

                        if result[hour] is not None:
                            continue

                        target_time = tw_time.replace(
                            hour=hour,
                            minute=0,
                            second=0,
                            microsecond=0
                        )

                        candidates = []

                        for item in times:

                            data_time = parse_time(
                                item.get("DataTime")
                            )

                            if (
                                data_time is None
                                or data_time > target_time
                            ):
                                continue

                            value = get_element_value(
                                item
                            )

                            description = get_value_ci(
                                value,
                                "WeatherDescription",
                                "Description",
                                "weatherDescription",
                                "value",
                                "Value"
                            )

                            probability = extract_probability(
                                description
                            )

                            if probability is not None:

                                candidates.append(
                                    (
                                        data_time,
                                        probability
                                    )
                                )

                        if candidates:

                            candidates.sort(
                                key=lambda x: x[0]
                            )

                            result[hour] = candidates[-1][1]

            # ==================================================
            # 診斷訊息
            # ==================================================

            print(
                "🌧 降雨機率解析結果：",
                result
            )

            return result

        def get_daily_temperature(elements, names, today_str):
            # 先嘗試直接讀取 CWA 的 MinT / MaxT 欄位。
            element = find_element(elements, names)
            if element:
                for item in element.get("Time", []):
                    check_time = (
                        parse_time(item.get("StartTime"))
                        or parse_time(item.get("DataTime"))
                    )
                    if (
                        check_time
                        and check_time.strftime("%Y-%m-%d") == today_str
                    ):
                        value = get_element_value(item)
                        result = get_value_ci(
                            value,
                            "MinTemperature", "MinT", "最低溫度",
                            "MaxTemperature", "MaxT", "最高溫度",
                            "Temperature", "value", "Value"
                        )
                        if result is not None:
                            return str(result)

            # 有些版本沒有獨立的 MinT / MaxT，
            # 改用今天逐時溫度計算今日最低 / 最高溫。
            temperature_element = find_element(
                elements,
                ["溫度", "T", "Temperature"]
            )
            if temperature_element:
                values = []
                for item in temperature_element.get("Time", []):
                    data_time = parse_time(item.get("DataTime"))
                    if (
                        not data_time
                        or data_time.strftime("%Y-%m-%d") != today_str
                    ):
                        continue
                    value = get_element_value(item)
                    raw = get_value_ci(
                        value,
                        "Temperature", "T", "value", "Value"
                    )
                    if raw is None:
                        continue
                    try:
                        values.append(float(raw))
                    except (TypeError, ValueError):
                        continue

                if values:
                    result = (
                        min(values)
                        if (
                            "MinT" in names
                            or "最低溫度" in names
                            or "MinTemperature" in names
                        )
                        else max(values)
                    )
                    return (
                        str(int(result))
                        if float(result).is_integer()
                        else str(result)
                    )

            return None

        def parse_location(location):
            district = location.get("LocationName", "")
            if district not in target_districts:
                return None

            elements = location.get("WeatherElement", [])
            if not elements:
                return None

            # 天氣狀況：維持原本抓目前時段的方式。
            desc_el = find_element(
                elements,
                ["天氣預報綜合描述", "WeatherDescription"]
            )
            weather_desc = ""
            if desc_el:
                current = find_current_time_data(
                    desc_el.get("Time", [])
                )
                if current:
                    value = get_element_value(current)
                    weather_desc = get_value_ci(
                        value,
                        "WeatherDescription",
                        "Description",
                        "weatherDescription",
                        "value",
                        "Value"
                    ) or ""
                    if not isinstance(weather_desc, str):
                        weather_desc = str(weather_desc)

            weather = ""
            if weather_desc:
                weather = weather_desc.split("。")[0].strip()

            if not weather:
                wx_el = find_element(
                    elements,
                    ["天氣現象", "Wx", "Weather"]
                )
                if wx_el:
                    current = find_current_time_data(
                        wx_el.get("Time", [])
                    )
                    if current:
                        weather = get_value_ci(
                            get_element_value(current),
                            "Weather",
                            "Wx",
                            "value",
                            "Value"
                        ) or ""

            # 今日最高 / 最低溫度。
            min_temp = max_temp = None
            if weather_desc:
                m = re.search(
                    r"最低溫度\s*攝氏\s*(-?\d+(?:\.\d+)?)\s*度",
                    weather_desc
                )
                if m:
                    min_temp = m.group(1)

                m = re.search(
                    r"最高溫度\s*攝氏\s*(-?\d+(?:\.\d+)?)\s*度",
                    weather_desc
                )
                if m:
                    max_temp = m.group(1)

            today_str = tw_time.strftime("%Y-%m-%d")
            if min_temp is None:
                min_temp = get_daily_temperature(
                    elements,
                    ["MinT", "MinTemperature", "最低溫度"],
                    today_str
                )
            if max_temp is None:
                max_temp = get_daily_temperature(
                    elements,
                    ["MaxT", "MaxTemperature", "最高溫度"],
                    today_str
                )

            rain_probs = get_rain_probabilities(elements)

            # LINE 顯示格式：
            # 📍 北投區 25~28° 陰
            #    07:00 降雨20%
            #    13:00 降雨30%
            #    19:00 降雨40%
            lines = [
                (
                    f"📍 {district} "
                    f"{min_temp if min_temp is not None else '?'}~"
                    f"{max_temp if max_temp is not None else '?'}° "
                    f"{weather or '天氣資料讀取中'}"
                )
            ]

            # 排版：
            # 排版：
            # 使用 5 個半形空格，讓時間再往右一點，對齊行政區名稱下方。
            # 「降雨」與百分比之間固定 1 個空格。
            # 📍 北投區 25~28° 多雲
            #    07:00   降雨 20%
            #    13:00   降雨 20%
            #    19:00   降雨 20%
            for hour in rain_hours:
                pop = rain_probs.get(hour)
                pop_text = str(pop) if pop is not None else "?"
                lines.append(
                    f"      {hour:02d}:00   降雨 {pop_text}%"
                )

            return "\n".join(lines)


        weather_results = {}

        for dataset_id in weather_datasets:
            url = (
                "https://opendata.cwa.gov.tw/api/v1/rest/datastore/"
                f"{dataset_id}"
            )
            params = {
                "format": "JSON",
                # CWA 官方 API 參數名稱是 locationName（小寫 l）。
                "locationName": ",".join(target_districts),
                # 明確要求 6 小時降雨機率，不使用 12 小時 PoP。
                "elementName": "Wx,PoP6h,WeatherDescription,MinT,MaxT,T"
            }

            try:
                response = requests.get(
                    url,
                    headers={"Authorization": CWA_API_KEY},
                    params=params,
                    timeout=15
                )
                if response.status_code != 200:
                    print(
                        f"氣象 API {dataset_id} "
                        f"HTTP {response.status_code}"
                    )
                    continue

                records = response.json().get("records", {})
                locations = (
                    records.get("locations")
                    or records.get("Locations")
                    or []
                )

                location_list = []
                for group in locations:
                    if isinstance(group, dict):
                        if "location" in group:
                            location_list.extend(
                                group.get("location", [])
                            )
                        elif "Location" in group:
                            location_list.extend(
                                group.get("Location", [])
                            )

                if not location_list:
                    location_list = locations

                for location in location_list:
                    if isinstance(location, dict):
                        result = parse_location(location)
                        if result:
                            weather_results[
                                location.get("LocationName", "")
                            ] = result

            except Exception as e:
                print(
                    f"氣象資料集 {dataset_id} 解析失敗：{e}"
                )

        msg = (
            f"🌤 一分鐘報天氣 {date_str} 🌤\n\n"
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
        msg += (
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

        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=10
        )

        if response.status_code >= 300:
            print(
                f"LINE 推播失敗 HTTP {response.status_code}: "
                f"{response.text}"
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

    # GitHub Actions 手動執行時，天氣與股價都推播
    is_manual_run = (
        os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    )

    if is_manual_run:

        weather_msg = (
            get_weather_report()
        )

        send_line_message_to_all(
            all_users,
            weather_msg
        )

    # --------------------------------------------------
    # 早上 5 點（或排程微小延遲的 6 點）
    # 只發送一次氣象，絕不重疊
    # --------------------------------------------------
    if (tw_hour == 5 or tw_hour == 6) and not is_manual_run:

        weather_msg = (
            get_weather_report()
        )

        send_line_message_to_all(
            all_users,
            weather_msg
        )

    # --------------------------------------------------
    # 下午 1 點以後
    # 13:00 ~ 23:59
    # GitHub Actions 若排程延遲，也仍然執行台積電監控
    # --------------------------------------------------
    elif 13 <= tw_hour <= 23 or is_manual_run:

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
