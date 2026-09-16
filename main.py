import requests
import re
import os
import json
from datetime import datetime, timedelta


# =========================================================
# 環境變數
# =========================================================

CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID")

CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

CWA_API_KEY = os.environ.get("CWA_API_KEY")

TSMC_TARGET_PRICE = 2500


# =========================================================
# CWA 天氣資料
# =========================================================

def get_weather_data(dataset_id, location_name):

    url = (
        f"https://opendata.cwa.gov.tw/"
        f"api/v1/rest/datastore/{dataset_id}"
    )

    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON"
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        if response.status_code != 200:
            print(
                f"氣象資料集 {dataset_id} "
                f"HTTP錯誤：{response.status_code}"
            )
            return None

        data = response.json()

        return data

    except Exception as e:

        print(
            f"氣象資料集 {dataset_id} "
            f"讀取失敗：{e}"
        )

        return None


# =========================================================
# 解析天氣地點
# =========================================================

def parse_location(
    data,
    location_name
):

    try:

        records = data.get(
            "records",
            {}
        )

        locations = records.get(
            "Locations",
            []
        )

        for locations_item in locations:

            location_list = (
                locations_item
                .get("Location", [])
            )

            for location in location_list:

                name = location.get(
                    "LocationName"
                )

                if name == location_name:

                    return location

        return None

    except Exception as e:

        print(
            f"解析地點失敗：{e}"
        )

        return None


# =========================================================
# 取得天氣描述
# =========================================================

def get_weather_description(
    location
):

    try:

        weather_elements = (
            location
            .get("WeatherElement", [])
        )

        for element in weather_elements:

            element_name = element.get(
                "ElementName"
            )

            if element_name == "Wx":

                times = element.get(
                    "Time",
                    []
                )

                if times:

                    parameter = (
                        times[0]
                        .get("ElementValue", [{}])[0]
                    )

                    return (
                        parameter
                        .get("Weather", "")
                    )

        return ""

    except Exception:

        return ""


# =========================================================
# 取得最高最低溫
# =========================================================

def get_temperature_range(
    location
):

    min_temp = None
    max_temp = None

    try:

        weather_elements = (
            location
            .get("WeatherElement", [])
        )

        for element in weather_elements:

            element_name = element.get(
                "ElementName"
            )

            if element_name in [
                "MinT",
                "MaxT"
            ]:

                times = element.get(
                    "Time",
                    []
                )

                if not times:
                    continue

                value = (
                    times[0]
                    .get("ElementValue", [{}])[0]
                    .get("Temperature")
                )

                if value is None:
                    continue

                if element_name == "MinT":
                    min_temp = value

                elif element_name == "MaxT":
                    max_temp = value

        return min_temp, max_temp

    except Exception:

        return None, None


# =========================================================
# 取得降雨機率
# =========================================================

def get_rain_probabilities(
    location
):

    results = []

    try:

        weather_elements = (
            location
            .get("WeatherElement", [])
        )

        for element in weather_elements:

            element_name = element.get(
                "ElementName",
                ""
            )

            if element_name not in [
                "PoP6h",
                "PoP",
                "ProbabilityOfPrecipitation"
            ]:
                continue

            times = element.get(
                "Time",
                []
            )

            for item in times:

                start_time = item.get(
                    "StartTime",
                    ""
                )

                end_time = item.get(
                    "EndTime",
                    ""
                )

                element_value = item.get(
                    "ElementValue",
                    []
                )

                if not element_value:
                    continue

                value_obj = (
                    element_value[0]
                )

                value = (
                    value_obj.get("ProbabilityOfPrecipitation")
                    or value_obj.get("PoP6h")
                    or value_obj.get("PoP")
                    or value_obj.get("value")
                    or value_obj.get("Value")
                )

                if value is None:
                    continue

                try:

                    value = int(
                        float(value)
                    )

                except:

                    continue

                if start_time:

                    try:

                        dt = datetime.fromisoformat(
                            start_time
                            .replace("Z", "+00:00")
                        )

                        display_time = (
                            dt.strftime("%H:%M")
                        )

                    except:

                        display_time = start_time

                else:

                    display_time = ""

                results.append(
                    (
                        display_time,
                        value
                    )
                )

        # -------------------------------------------------
        # 如果 PoP 資料沒有抓到
        # 從 WeatherDescription 抓「降雨機率 XX%」
        # -------------------------------------------------

        if not results:

            for element in weather_elements:

                element_name = element.get(
                    "ElementName",
                    ""
                )

                if element_name not in [
                    "WeatherDescription",
                    "Wx"
                ]:
                    continue

                times = element.get(
                    "Time",
                    []
                )

                for item in times:

                    element_value = item.get(
                        "ElementValue",
                        []
                    )

                    if not element_value:
                        continue

                    text = json.dumps(
                        element_value,
                        ensure_ascii=False
                    )

                    match = re.search(
                        r"降雨機率\s*(\d+)\s*%",
                        text
                    )

                    if not match:
                        continue

                    value = int(
                        match.group(1)
                    )

                    start_time = item.get(
                        "StartTime",
                        ""
                    )

                    if start_time:

                        try:

                            dt = datetime.fromisoformat(
                                start_time
                                .replace("Z", "+00:00")
                            )

                            display_time = (
                                dt.strftime("%H:%M")
                            )

                        except:

                            display_time = start_time

                    else:

                        display_time = ""

                    results.append(
                        (
                            display_time,
                            value
                        )
                    )

        # -------------------------------------------------
        # 去除重複時間
        # -------------------------------------------------

        unique = {}

        for time_str, value in results:

            if time_str not in unique:
                unique[time_str] = value

        results = list(
            unique.items()
        )

        # -------------------------------------------------
        # 排序
        # -------------------------------------------------

        results.sort(
            key=lambda x: x[0]
        )

        print(
            f"🌧 降雨機率解析結果：{results}"
        )

        return results

    except Exception as e:

        print(
            f"降雨機率解析失敗：{e}"
        )

        return []


# =========================================================
# Yahoo 股價
# =========================================================

def get_price_from_yahoo():

    url = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/2330.TW"
    )

    params = {
        "range": "5d",
        "interval": "1d"
    }

    headers = {
        "User-Agent":
            "Mozilla/5.0"
    }

    try:

        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        if r.status_code != 200:
            return None

        data = r.json()

        result = (
            data
            .get("chart", {})
            .get("result")
        )

        if not result:
            return None

        meta = result[0].get(
            "meta",
            {}
        )

        price = (
            meta.get("regularMarketPrice")
        )

        if price is not None:
            return float(price)

        return None

    except Exception as e:

        print(
            f"Yahoo 股價取得失敗：{e}"
        )

        return None


# =========================================================
# FinMind 股價
# =========================================================

def get_price_from_finmind():

    url = (
        "https://api.finmindtrade.com/"
        "api/v4/data"
    )

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": "2330",
        "start_date": (
            datetime.now()
            .strftime("%Y-%m-%d")
        )
    }

    try:

        r = requests.get(
            url,
            params=params,
            timeout=10
        )

        if r.status_code != 200:
            return None

        data = r.json()

        records = data.get(
            "data",
            []
        )

        if not records:
            return None

        price = records[-1].get(
            "close"
        )

        if price is not None:
            return float(price)

        return None

    except Exception as e:

        print(
            f"FinMind 股價取得失敗：{e}"
        )

        return None


# =========================================================
# 取得台積電股價
# =========================================================

def get_tsmc_price():

    price = get_price_from_yahoo()

    if price is not None:
        return price

    price = get_price_from_finmind()

    return price


# =========================================================
# 台積電估值資料
# =========================================================

def get_tsmc_valuation():

    url = (
        "https://finance.yahoo.com/"
        "quote/2330.TW/"
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
    }

    try:

        r = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        print(
            f"📊 Yahoo 估值頁面 HTTP 狀態："
            f"{r.status_code}"
        )

        if r.status_code != 200:

            print(
                "❌ Yahoo 估值頁面無法取得"
            )

            return None, None, None

        html = r.text

        # -------------------------------------------------
        # 抓取 Trailing P/E
        # -------------------------------------------------

        pe = None

        patterns_pe = [

            r'"trailingPE":\{"raw":([0-9.]+)',

            r'"trailingPE":([0-9.]+)',

            r'PE Ratio \(TTM\)</span>.*?'
            r'([0-9]+\.[0-9]+)'

        ]

        for pattern in patterns_pe:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE |
                re.DOTALL
            )

            if match:

                try:

                    pe = float(
                        match.group(1)
                    )

                    break

                except:

                    pass

        # -------------------------------------------------
        # 抓取 EPS 成長率
        # -------------------------------------------------

        earnings_growth = None

        patterns_growth = [

            r'"earningsGrowth":\{"raw":(-?[0-9.]+)',

            r'"earningsGrowth":(-?[0-9.]+)'

        ]

        for pattern in patterns_growth:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE
            )

            if match:

                try:

                    earnings_growth = float(
                        match.group(1)
                    )

                    break

                except:

                    pass

        # -------------------------------------------------
        # EPS 成長率轉百分比
        # -------------------------------------------------

        growth_percent = None

        if earnings_growth is not None:

            growth_percent = (
                earnings_growth * 100
            )

        # -------------------------------------------------
        # 計算 PEG
        # -------------------------------------------------

        peg = None

        if (
            pe is not None
            and growth_percent is not None
            and growth_percent != 0
        ):

            peg = (
                pe /
                growth_percent
            )

        print(
            f"📊 台積電估值解析："
            f"PE={pe}, "
            f"EPS Growth={growth_percent}%, "
            f"PEG={peg}"
        )

        return (
            pe,
            growth_percent,
            peg
        )

    except Exception as e:

        print(
            f"❌ 台積電估值資料取得失敗："
            f"{e}"
        )

        return None, None, None


# =========================================================
# 取得歷史股價
# =========================================================

def get_tsmc_history():

    url = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/2330.TW"
    )

    params = {
        "range": "3mo",
        "interval": "1d"
    }

    headers = {
        "User-Agent":
            "Mozilla/5.0"
    }

    try:

        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        if r.status_code != 200:
            return []

        data = r.json()

        result = (
            data
            .get("chart", {})
            .get("result")
        )

        if not result:
            return []

        closes = (
            result[0]
            .get("indicators", {})
            .get("quote", [{}])[0]
            .get("close", [])
        )

        return [
            float(x)
            for x in closes
            if x is not None
        ]

    except Exception as e:

        print(
            f"歷史股價取得失敗：{e}"
        )

        return []


# =========================================================
# RSI
# =========================================================

def calculate_rsi(
    prices,
    period=14
):

    if len(prices) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(prices)):

        change = (
            prices[i] -
            prices[i - 1]
        )

        if change > 0:

            gains.append(change)
            losses.append(0)

        else:

            gains.append(0)
            losses.append(abs(change))

    avg_gain = (
        sum(gains[-period:]) /
        period
    )

    avg_loss = (
        sum(losses[-period:]) /
        period
    )

    if avg_loss == 0:
        return 100.0

    rs = (
        avg_gain /
        avg_loss
    )

    rsi = (
        100 -
        (100 / (1 + rs))
    )

    return round(
        rsi,
        2
    )


# =========================================================
# 20 日乖離率
# =========================================================

def calculate_bias(
    prices,
    period=20
):

    if len(prices) < period:
        return None

    ma = (
        sum(prices[-period:]) /
        period
    )

    current = prices[-1]

    bias = (
        (current - ma) /
        ma *
        100
    )

    return round(
        bias,
        2
    )


# =========================================================
# Cloudflare KV
# =========================================================

def get_kv(key):

    url = (
        f"https://api.cloudflare.com/"
        f"client/v4/accounts/"
        f"{CF_ACCOUNT_ID}/storage/"
        f"kv/namespaces/"
        f"{CF_KV_NAMESPACE_ID}/values/"
        f"{key}"
    )

    headers = {
        "Authorization":
            f"Bearer {CF_API_TOKEN}"
    }

    try:

        r = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if r.status_code == 200:
            return r.text

        return None

    except Exception as e:

        print(
            f"KV 讀取失敗：{e}"
        )

        return None


def set_kv(
    key,
    value
):

    url = (
        f"https://api.cloudflare.com/"
        f"client/v4/accounts/"
        f"{CF_ACCOUNT_ID}/storage/"
        f"kv/namespaces/"
        f"{CF_KV_NAMESPACE_ID}/values/"
        f"{key}"
    )

    headers = {
        "Authorization":
            f"Bearer {CF_API_TOKEN}",
        "Content-Type":
            "text/plain"
    }

    try:

        r = requests.put(
            url,
            headers=headers,
            data=value,
            timeout=10
        )

        return (
            r.status_code == 200
        )

    except Exception as e:

        print(
            f"KV 寫入失敗：{e}"
        )

        return False


# =========================================================
# LINE Multicast
# =========================================================

def send_line_multicast(
    message
):

    url = (
        "https://api.line.me/v2/bot/"
        "message/multicast"
    )

    headers = {
        "Content-Type":
            "application/json",
        "Authorization":
            f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }

    user_ids_text = get_kv(
        "line_user_ids"
    )

    if not user_ids_text:
        print(
            "沒有 LINE 使用者 ID"
        )
        return

    try:

        user_ids = json.loads(
            user_ids_text
        )

    except Exception:

        user_ids = []

    if not user_ids:
        print(
            "LINE 使用者 ID 清單為空"
        )
        return

    payload = {
        "to": user_ids,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    try:

        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10
        )

        print(
            f"LINE 發送結果："
            f"{r.status_code}"
        )

        if r.status_code != 200:

            print(
                r.text
            )

    except Exception as e:

        print(
            f"LINE 發送失敗：{e}"
        )


# =========================================================
# 主程式
# =========================================================

def main():

    now = datetime.now()

    print(
        f"目前時間：{now}"
    )

    # =====================================================
    # 天氣推播
    # =====================================================

    weather_locations = [

        (
            "F-D0047-061",
            "北投區"
        ),

        (
            "F-D0047-069",
            "萬華區"
        ),

        (
            "F-D0047-069",
            "信義區"
        ),

        (
            "F-D0047-061",
            "淡水區"
        )

    ]

    weather_messages = []

    for dataset_id, location_name in weather_locations:

        data = get_weather_data(
            dataset_id,
            location_name
        )

        if not data:

            weather_messages.append(
                f"📍 {location_name} "
                f"天氣資料讀取失敗"
            )

            continue

        location = parse_location(
            data,
            location_name
        )

        if not location:

            weather_messages.append(
                f"📍 {location_name} "
                f"天氣資料解析失敗"
            )

            continue

        weather = get_weather_description(
            location
        )

        min_temp, max_temp = (
            get_temperature_range(
                location
            )
        )

        rain_probs = (
            get_rain_probabilities(
                location
            )
        )

        temp_text = ""

        if (
            min_temp is not None
            and max_temp is not None
        ):

            temp_text = (
                f"{min_temp}~"
                f"{max_temp}° "
            )

        message = (
            f"📍 {location_name} "
            f"{temp_text}"
            f"{weather}"
        )

        for time_str, value in rain_probs:

            message += (
                f"\n      "
                f"{time_str}   "
                f"降雨 {value}%"
            )

        weather_messages.append(
            message
        )

    # =====================================================
    # 天氣訊息
    # =====================================================

    weather_msg = (
        f"🌤 一分鐘報天氣 "
        f"{now.strftime('%m/%d')} "
        f"(星期"
        f"{'一二三四五六日'[now.weekday()]}"
        f") 🌤\n\n"
        + "\n".join(
            weather_messages
        )
        + "\n\n"
        "祝福您吉祥如意闔家平安幸福永相隨。"
    )

    # =====================================================
    # 手動執行時直接發天氣
    # =====================================================

    if os.environ.get(
        "GITHUB_EVENT_NAME"
    ) == "workflow_dispatch":

        send_line_multicast(
            weather_msg
        )

    # =====================================================
    # 每日天氣時間
    # =====================================================

    if now.hour in [
        5,
        6
    ]:

        send_line_multicast(
            weather_msg
        )

    # =====================================================
    # 台積電
    # =====================================================

    if (
        13 <= now.hour <= 23
        or
        os.environ.get(
            "GITHUB_EVENT_NAME"
        ) == "workflow_dispatch"
    ):

        price = get_tsmc_price()

        # -------------------------------------------------
        # 取得本益比、EPS 成長率、PEG
        # -------------------------------------------------

        pe_val, eps_growth_val, peg_val = (
            get_tsmc_valuation()
        )

        rsi_val = None
        bias_val = None

        history = (
            get_tsmc_history()
        )

        if history:

            rsi_val = calculate_rsi(
                history
            )

            bias_val = calculate_bias(
                history
            )

        # -------------------------------------------------
        # 估值資訊
        # -------------------------------------------------

        valuation_lines = []

        if pe_val is not None:

            valuation_lines.append(
                f"本益比："
                f"{pe_val:.1f} 倍"
            )

        if eps_growth_val is not None:

            valuation_lines.append(
                f"EPS 成長率："
                f"{eps_growth_val:.1f}%"
            )

        if peg_val is not None:

            valuation_lines.append(
                f"PEG："
                f"{peg_val:.2f}"
            )

        # -------------------------------------------------
        # 技術指標
        # -------------------------------------------------

        technical_parts = []

        if rsi_val is not None:

            technical_parts.append(
                f"14日RSI: "
                f"{rsi_val}"
            )

        if bias_val is not None:

            technical_parts.append(
                f"20日乖離率: "
                f"{bias_val}%"
            )

        indicator_lines = []

        indicator_lines.extend(
            valuation_lines
        )

        if technical_parts:

            indicator_lines.append(
                "、".join(
                    technical_parts
                )
            )

        indicator_str = (
            "\n".join(
                indicator_lines
            )
        )

        # -------------------------------------------------
        # 超過目標價
        # -------------------------------------------------

        overheat_note = ""

        if (
            price is not None
            and price >= TSMC_TARGET_PRICE
        ):

            overheat_note = (
                f"\n\n⚠️ 台積電目前股價"
                f"{price} 元，"
                f"已達到設定目標價 "
                f"{TSMC_TARGET_PRICE} 元"
            )

        # -------------------------------------------------
        # 每日台積電訊息
        # -------------------------------------------------

        if price is not None:

            daily_msg = (
                f"📢 tsmc 今日收盤價："
                f"{price} 元"
            )

            if indicator_str:

                daily_msg += (
                    "\n"
                    +
                    indicator_str
                )

            daily_msg += (
                overheat_note
            )

            print(
                daily_msg
            )

            send_line_multicast(
                daily_msg
            )


# =========================================================
# 執行
# =========================================================

if __name__ == "__main__":

    main()
