import json
import math
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, render_template_string


app = Flask(__name__)


# ============================================================
# 自宅情報
# ============================================================

HOME_LAT = 34.8346
HOME_LON = 139.0481
HOME_ALTITUDE = 500

JST = timezone(timedelta(hours=9))


# ============================================================
# 気象庁 AMeDAS
# ============================================================

JMA_LATEST_URL = (
    "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
)

JMA_STATION_URL = (
    "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
)

JMA_MAP_URL = (
    "https://www.jma.go.jp/bosai/amedas/data/map/{}.json"
)


# ============================================================
# MET Norway
# ============================================================

MET_URL = (
    "https://api.met.no/weatherapi/locationforecast/2.0/complete"
)

MET_CONTACT_EMAIL = os.environ.get(
    "MET_CONTACT_EMAIL",
    "contact@example.com"
)

MET_HEADERS = {
    "User-Agent": (
        f"NarabotoWeather/1.0 ({MET_CONTACT_EMAIL})"
    ),
    "Accept": "application/json",
}


# ============================================================
# 共通
# ============================================================

def safe_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def coord_to_decimal(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, list) and len(value) >= 2:
        try:
            degree = float(value[0])
            minute = float(value[1])

            second = 0.0

            if len(value) >= 3:
                second = float(value[2])

            sign = -1 if degree < 0 else 1

            return sign * (
                abs(degree)
                + minute / 60
                + second / 3600
            )

        except (TypeError, ValueError):
            return None

    return None


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return r * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


def jst_now():
    return datetime.now(JST)


def get_json(url, timeout=20, headers=None):
    response = requests.get(
        url,
        timeout=timeout,
        headers=headers
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# AMeDAS
# ============================================================

WIND_DIRECTIONS = {
    0: "静穏",
    1: "北",
    2: "北北東",
    3: "北東",
    4: "東北東",
    5: "東",
    6: "東南東",
    7: "南東",
    8: "南南東",
    9: "南",
    10: "南南西",
    11: "南西",
    12: "西南西",
    13: "西",
    14: "西北西",
    15: "北西",
    16: "北北西",
}


def amedas_value(obs, key):
    if not obs:
        return None

    value = obs.get(key)

    if isinstance(value, list):
        if not value:
            return None

        return safe_float(value[0])

    return safe_float(value)


def get_latest_amedas_time():
    response = requests.get(
        JMA_LATEST_URL,
        timeout=20
    )

    response.raise_for_status()

    text = response.text.strip()

    dt = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    )

    return dt.astimezone(JST)


def station_distance(station):
    lat = coord_to_decimal(
        station.get("lat")
    )

    lon = coord_to_decimal(
        station.get("lon")
    )

    if lat is None or lon is None:
        return None

    return distance_km(
        HOME_LAT,
        HOME_LON,
        lat,
        lon
    )


def sorted_stations(stations):
    result = []

    for station_id, station in stations.items():

        distance = station_distance(
            station
        )

        if distance is None:
            continue

        result.append({
            "id": str(station_id),

            "name": (
                station.get("kjName")
                or station.get("enName")
                or str(station_id)
            ),

            "lat": coord_to_decimal(
                station.get("lat")
            ),

            "lon": coord_to_decimal(
                station.get("lon")
            ),

            "distance": distance,

            "type": station.get("type"),

            "elems": station.get(
                "elems",
                []
            ),
        })

    result.sort(
        key=lambda x: x["distance"]
    )

    return result


def get_obs(data, station_id):

    obs = (
        data.get(station_id)
        or data.get(str(station_id))
    )

    if obs is not None:
        return obs

    try:
        return data.get(
            int(station_id)
        )

    except Exception:
        return None


def find_nearest_rain_station(
    stations,
    data
):

    for station in stations:

        obs = get_obs(
            data,
            station["id"]
        )

        if obs is None:
            continue

        rain10 = amedas_value(
            obs,
            "precipitation10m"
        )

        rain1h = amedas_value(
            obs,
            "precipitation1h"
        )

        if (
            rain10 is not None
            or rain1h is not None
        ):
            return station, obs

    return None, None


def find_nearest_four_element_station(
    stations,
    data
):

    for station in stations:

        obs = get_obs(
            data,
            station["id"]
        )

        if obs is None:
            continue

        values = [
            amedas_value(
                obs,
                "temp"
            ),

            amedas_value(
                obs,
                "humidity"
            ),

            amedas_value(
                obs,
                "wind"
            ),

            amedas_value(
                obs,
                "windDirection"
            ),
        ]

        count = sum(
            value is not None
            for value in values
        )

        if count >= 2:
            return station, obs

    return None, None


def get_amedas():

    try:

        latest_dt = (
            get_latest_amedas_time()
        )

        timestamp = (
            latest_dt.strftime(
                "%Y%m%d%H%M%S"
            )
        )

        stations = get_json(
            JMA_STATION_URL
        )

        data = get_json(
            JMA_MAP_URL.format(
                timestamp
            )
        )

        station_list = sorted_stations(
            stations
        )

        rain_station, rain_obs = (
            find_nearest_rain_station(
                station_list,
                data
            )
        )

        four_station, four_obs = (
            find_nearest_four_element_station(
                station_list,
                data
            )
        )

        if rain_station is None:
            raise RuntimeError(
                "降水を観測できるAMeDASが見つかりません"
            )

        rain10 = amedas_value(
            rain_obs,
            "precipitation10m"
        )

        rain1h = amedas_value(
            rain_obs,
            "precipitation1h"
        )

        temp = None
        humidity = None
        wind = None
        wind_direction = "—"
        visibility = None

        if four_obs:

            temp = amedas_value(
                four_obs,
                "temp"
            )

            humidity = amedas_value(
                four_obs,
                "humidity"
            )

            wind = amedas_value(
                four_obs,
                "wind"
            )

            wind_direction_value = (
                amedas_value(
                    four_obs,
                    "windDirection"
                )
            )

            if (
                wind_direction_value
                is not None
            ):

                direction_int = int(
                    round(
                        wind_direction_value
                    )
                )

                wind_direction = (
                    WIND_DIRECTIONS.get(
                        direction_int,
                        "—"
                    )
                )

            visibility = amedas_value(
                four_obs,
                "visibility"
            )

        print(
            "AMeDAS:",
            rain_station["name"],
            four_station["name"]
            if four_station
            else "—",
            "rain10=",
            rain10,
            "temp=",
            temp,
            "wind=",
            wind
        )

        return {

            "ok": True,

            "rain_station":
                rain_station["name"],

            "rain_distance":
                rain_station["distance"],

            "four_station":
                (
                    four_station["name"]
                    if four_station
                    else "—"
                ),

            "four_distance":
                (
                    four_station["distance"]
                    if four_station
                    else None
                ),

            "observed_at":
                latest_dt,

            "rain10":
                rain10,

            "rain1h":
                rain1h,

            "temp":
                temp,

            "humidity":
                humidity,

            "wind":
                wind,

            "wind_direction":
                wind_direction,

            "visibility":
                visibility,
        }

    except Exception as e:

        print(
            "AMeDAS ERROR:",
            repr(e)
        )

        return {

            "ok": False,

            "rain_station": "—",
            "rain_distance": None,

            "four_station": "—",
            "four_distance": None,

            "observed_at": None,

            "rain10": None,
            "rain1h": None,

            "temp": None,
            "humidity": None,

            "wind": None,

            "wind_direction": "—",

            "visibility": None,

            "error": str(e),
        }


# ============================================================
# MET Norway
# ============================================================

def get_met_forecast():

    try:

        params = {
            "lat": HOME_LAT,
            "lon": HOME_LON,
            "altitude": HOME_ALTITUDE,
        }

        print(
            "MET REQUEST:",
            params
        )

        response = requests.get(
            MET_URL,
            params=params,
            headers=MET_HEADERS,
            timeout=30
        )

        print(
            "MET STATUS:",
            response.status_code
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:

        print(
            "MET ERROR:",
            repr(e)
        )

        return None


def get_period_data(data):

    for key in (
        "next_1_hours",
        "next_6_hours",
        "next_12_hours",
    ):

        value = data.get(key)

        if isinstance(value, dict):
            return value

    return {}


def symbol_to_japanese(symbol):

    if not symbol:
        return "—"

    s = symbol.lower()

    mapping = [

        ("heavyrain",
         "強い雨"),

        ("lightrain",
         "弱い雨"),

        ("rain",
         "雨"),

        ("sleet",
         "みぞれ"),

        ("snow",
         "雪"),

        ("fog",
         "霧"),

        ("thunderstorm",
         "雷雨"),

        ("fair",
         "晴れ"),

        ("clearsky",
         "快晴"),

        ("partlycloudy",
         "晴れ時々くもり"),

        ("cloudy",
         "くもり"),
    ]

    for key, value in mapping:

        if key in s:
            return value

    return "くもり"


def symbol_icon(symbol):

    if not symbol:
        return "🌤️"

    s = symbol.lower()

    if "thunder" in s:
        return "⛈️"

    if "heavyrain" in s:
        return "🌧️"

    if "lightrain" in s:
        return "🌦️"

    if "rain" in s:
        return "🌧️"

    if "sleet" in s:
        return "🌨️"

    if "snow" in s:
        return "❄️"

    if "fog" in s:
        return "🌫️"

    if "clearsky" in s:
        return "☀️"

    if "fair" in s:
        return "🌤️"

    if "partlycloudy" in s:
        return "⛅"

    if "cloudy" in s:
        return "☁️"

    return "🌤️"


def build_forecasts(met_json):

    if not met_json:
        return []

    timeseries = (
        met_json
        .get("properties", {})
        .get("timeseries", [])
    )

    forecasts = []

    for item in timeseries:

        try:

            time_text = item.get(
                "time"
            )

            if not time_text:
                continue

            dt = datetime.fromisoformat(
                time_text.replace(
                    "Z",
                    "+00:00"
                )
            ).astimezone(JST)

            data = item.get(
                "data",
                {}
            )

            instant = (
                data
                .get("instant", {})
                .get("details", {})
            )

            period = get_period_data(
                data
            )

            period_details = (
                period
                .get("details", {})
            )

            summary = (
                period
                .get("summary", {})
            )

            symbol = summary.get(
                "symbol_code"
            )

            temperature = safe_float(
                instant.get(
                    "air_temperature"
                )
            )

            humidity = safe_float(
                instant.get(
                    "relative_humidity"
                )
            )

            cloud_area_fraction = safe_float(
                instant.get(
                    "cloud_area_fraction"
                )
            )

            sea_pressure = safe_float(
                instant.get(
                    "air_pressure_at_sea_level"
                )
            )

            wind = safe_float(
                instant.get(
                    "wind_speed"
                )
            )

            wind_direction = safe_float(
                instant.get(
                    "wind_from_direction"
                )
            )

            precipitation = safe_float(
                period_details.get(
                    "precipitation_amount"
                )
            )

            thunder_probability = safe_float(
                period_details.get(
                    "probability_of_thunder"
                )
            )

            surface = None

            if (
                sea_pressure is not None
                and temperature is not None
            ):

                surface = (
                    sea_pressure
                    * math.exp(
                        -9.80665
                        * HOME_ALTITUDE
                        / (
                            287.05
                            * (
                                temperature
                                + 273.15
                            )
                        )
                    )
                )

            weather = (
                symbol_to_japanese(
                    symbol
                )
            )

            icon = symbol_icon(
                symbol
            )

            forecasts.append({

                "dt": dt,

                "temperature":
                    temperature,

                "humidity":
                    humidity,

                "cloud_area_fraction":
                    cloud_area_fraction,

                "sea_pressure":
                    sea_pressure,

                "surface_pressure":
                    surface,

                "wind":
                    wind,

                "wind_direction":
                    wind_direction,

                "precipitation":
                    precipitation,

                "thunder_probability":
                    thunder_probability,

                "symbol":
                    symbol,

                "weather":
                    weather,

                "icon":
                    icon,
            })

        except Exception as e:

            print(
                "FORECAST ITEM ERROR:",
                repr(e)
            )

    return forecasts


# ============================================================
# 気圧変化
# ============================================================

def add_pressure_change_info(
    forecasts
):

    result = []

    for index, item in enumerate(
        forecasts
    ):

        current = item.get(
            "surface_pressure"
        )

        previous = None

        for j in range(
            index - 1,
            -1,
            -1
        ):

            candidate = forecasts[j]

            diff_time = (
                item["dt"]
                - candidate["dt"]
            )

            if (
                diff_time
                >= timedelta(hours=2.5)
                and
                diff_time
                <= timedelta(hours=3.5)
            ):

                previous = candidate
                break

        change = None

        if (
            current is not None
            and previous is not None
            and previous.get(
                "surface_pressure"
            ) is not None
        ):

            change = (
                current
                - previous[
                    "surface_pressure"
                ]
            )

        if change is None:

            level = "normal"
            label = "安定"

        elif change <= -3.0:

            level = "strong-fall"
            label = "急低下"

        elif change <= -1.5:

            level = "fall"
            label = "低下"

        elif change >= 3.0:

            level = "strong-rise"
            label = "急上昇"

        elif change >= 1.5:

            level = "rise"
            label = "上昇"

        else:

            level = "normal"
            label = "安定"

        new_item = dict(item)

        new_item[
            "pressure_change"
        ] = change

        new_item[
            "pressure_level"
        ] = level

        new_item[
            "pressure_label"
        ] = label

        result.append(
            new_item
        )

    return result


def pressure_level(pressure):

    if pressure is None:
        return "—"

    if pressure >= 1020:
        return "高め"

    if pressure <= 1000:
        return "低め"

    return "標準"


def nearest_forecast(
    forecasts
):

    if not forecasts:
        return None

    now = jst_now()

    return min(
        forecasts,
        key=lambda x:
        abs(
            (
                x["dt"]
                - now
            ).total_seconds()
        )
    )


def pressure_trend(
    forecasts
):

    current = nearest_forecast(
        forecasts
    )

    if current is None:
        return "判定できません"

    current_pressure = (
        current.get(
            "surface_pressure"
        )
    )

    if current_pressure is None:
        return "判定できません"

    now = jst_now()

    future = [
        x
        for x in forecasts
        if x["dt"] >= now
    ]

    target = None

    for item in future:

        if (
            item["dt"] - now
            >= timedelta(hours=2)
        ):

            target = item
            break

    if target is None:
        return "安定"

    target_pressure = (
        target.get(
            "surface_pressure"
        )
    )

    if target_pressure is None:
        return "判定できません"

    difference = (
        target_pressure
        - current_pressure
    )

    if difference >= 3:
        return "上昇"

    if difference <= -3:
        return "急低下"

    if difference >= 1.5:
        return "上昇傾向"

    if difference <= -1.5:
        return "低下傾向"

    return "安定"


# ============================================================
# 天気の強さ
# ============================================================

def weather_display(item):

    rain = item.get(
        "precipitation"
    )

    thunder = item.get(
        "thunder_probability"
    )

    weather = item.get(
        "weather",
        ""
    )

    symbol = item.get(
        "symbol",
        ""
    )

    if (
        (
            thunder is not None
            and thunder >= 30
        )
        or "雷" in weather
        or "thunder" in symbol.lower()
    ):
        return "雷雨"

    if (
        rain is not None
        and rain >= 5
    ):
        return "強い雨"

    if (
        rain is not None
        and rain > 0
    ):
        return "雨"

    return weather

# ============================================================
# 状況表示
# ============================================================

def situation_display(item):

    situations = []

    rain = item.get("precipitation")
    thunder = item.get("thunder_probability")
    wind = item.get("wind")
    humidity = item.get("humidity")
    cloud = item.get("cloud_area_fraction")

    weather = item.get(
        "weather",
        ""
    ) or ""

    symbol = (
        item.get("symbol")
        or ""
    ).lower()

    fog_level = fog_visibility_level(item)

    # --------------------------------------------------------
    # 雷
    # --------------------------------------------------------

    thunder_risk = (
        (
            thunder is not None
            and thunder >= 30
        )
        or "雷" in weather
        or "thunder" in symbol
    )

    if thunder_risk:
        situations.append("⚡ 雷に注意")


    # --------------------------------------------------------
    # 強い雨
    # --------------------------------------------------------

    if rain is not None:

        if rain >= 5:
            situations.append("🌧️ 強い雨")

        elif rain >= 1:
            situations.append("🌧️ 雨")


    # --------------------------------------------------------
    # 霧・視界
    # --------------------------------------------------------

    if fog_level == "strong":

        situations.append(
            "🌫️ 霧・視界不良"
        )

    elif fog_level == "attention":

        situations.append(
            "🌫️ 霧・低い雲に注意"
        )


    # --------------------------------------------------------
    # 強風
    # --------------------------------------------------------

    if wind is not None:

        if wind >= 10:
            situations.append(
                "💨 強風"
            )

        elif wind >= 7:
            situations.append(
                "💨 風に注意"
            )


    # --------------------------------------------------------
    # 高湿度＋雲
    # 山間部で雲に包まれる可能性
    # --------------------------------------------------------

    if (
        humidity is not None
        and humidity >= 90
        and cloud is not None
        and cloud >= 90
        and fog_level == "normal"
    ):

        situations.append(
            "☁️ 低い雲に注意"
        )


    # --------------------------------------------------------
    # 降水なし・特に注意なし
    # --------------------------------------------------------

    if not situations:

        if (
            cloud is not None
            and cloud >= 80
        ):
            situations.append(
                "☁️ 雲が多い"
            )

        else:
            situations.append(
                "✓ 大きな注意なし"
            )


    return "・".join(
        situations
    )

# ============================================================
# 体調注意時間
# ============================================================

def health_attention_level(item):

    level = item.get(
        "pressure_level"
    )

    if level in (
        "strong-fall",
        "strong-rise"
    ):
        return "strong"

    if level in (
        "fall",
        "rise"
    ):
        return "attention"

    return "normal"


def health_attention_text(
    forecasts
):

    attention = []

    for item in forecasts:

        if (
            health_attention_level(
                item
            )
            != "normal"
        ):

            attention.append(
                item
            )

    if not attention:
        return None

    strong = [
        item
        for item in attention
        if health_attention_level(
            item
        ) == "strong"
    ]

    target = (
        strong
        if strong
        else attention
    )

    first = target[0]["dt"]
    last = target[-1]["dt"]

    if first.hour == last.hour:
        time_text = (
            f"{first:%H:%M}"
        )
    else:
        time_text = (
            f"{first:%H:%M}"
            f"〜"
            f"{last:%H:%M}"
        )

    fall_count = sum(
        item.get("pressure_level") in ("fall", "strong-fall")
        for item in target
    )

    rise_count = sum(
        item.get("pressure_level") in ("rise", "strong-rise")
        for item in target
    )

    if fall_count > rise_count:
        direction_text = "気圧が低下する時間帯"
    elif rise_count > fall_count:
        direction_text = "気圧が上昇する時間帯"
    else:
        direction_text = "気圧の変化が大きい時間帯"

    changes = [
        item.get("pressure_change")
        for item in target
        if item.get("pressure_change") is not None
    ]

    max_change = (
        max(changes, key=abs)
        if changes
        else None
    )

    return {
        "time": time_text,
        "strong": bool(strong),
        "items": target,
        "direction_text": direction_text,
        "max_change": max_change,
    }


# ============================================================
# 麓への移動時の体調注意
# ============================================================

def travel_health_level(item):

    level = item.get("pressure_level")

    if level in (
        "strong-fall",
        "strong-rise"
    ):
        return "strong"

    if level in (
        "fall",
        "rise"
    ):
        return "attention"

    return "normal"


def travel_health_attention_text(forecasts):

    attention = [
        item
        for item in forecasts
        if (
            item.get("dt") >= jst_now()
            and travel_health_level(item) != "normal"
        )
    ]

    if not attention:
        return None

    strong = [
        item
        for item in attention
        if travel_health_level(item) == "strong"
    ]

    target = strong if strong else attention

    first = target[0]["dt"]
    last = target[-1]["dt"]

    if first.hour == last.hour:
        time_text = f"{first:%H:%M}"
    else:
        time_text = f"{first:%H:%M}〜{last:%H:%M}"

    changes = [
        item.get("pressure_change")
        for item in target
        if item.get("pressure_change") is not None
    ]

    max_change = max(changes, key=abs) if changes else None

    return {
        "time": time_text,
        "strong": bool(strong),
        "items": target,
        "max_change": max_change,
    }


# ============================================================
# 麓への移動注意
# ============================================================

def travel_level(item):

    rain = item.get(
        "precipitation"
    )

    wind = item.get(
        "wind"
    )

    thunder = item.get(
        "thunder_probability"
    )

    weather = item.get(
        "weather",
        ""
    )

    symbol = (
        item.get(
            "symbol"
        )
        or ""
    )

    severe_rain = (
        rain is not None
        and rain >= 5
    )

    thunder_risk = (
        (
            thunder is not None
            and thunder >= 30
        )
        or "雷" in weather
        or "thunder"
        in symbol.lower()
    )

    strong_wind = (
        wind is not None
        and wind >= 10
    )

    fog = (
        "霧" in weather
        or "fog"
        in symbol.lower()
    )

    if (
        severe_rain
        or thunder_risk
        or strong_wind
    ):
        return "danger"

    if (
        (
            rain is not None
            and rain >= 1
        )
        or fog
        or (
            wind is not None
            and wind >= 7
        )
    ):
        return "attention"

    return "good"


def travel_reason(item):

    reasons = []

    rain = item.get(
        "precipitation"
    )

    wind = item.get(
        "wind"
    )

    thunder = item.get(
        "thunder_probability"
    )

    weather = item.get(
        "weather",
        ""
    )

    if (
        rain is not None
        and rain >= 5
    ):
        reasons.append(
            "強い雨"
        )

    elif (
        rain is not None
        and rain >= 1
    ):
        reasons.append(
            "雨"
        )

    if (
        thunder is not None
        and thunder >= 30
    ) or "雷" in weather:

        reasons.append(
            "雷"
        )

    if (
        wind is not None
        and wind >= 10
    ):
        reasons.append(
            "強風"
        )

    if "霧" in weather:
        reasons.append(
            "霧"
        )

    return "・".join(
        reasons
    )


def fog_visibility_level(item):

    weather = item.get("weather", "") or ""
    symbol = (item.get("symbol") or "").lower()
    humidity = item.get("humidity")
    precipitation = item.get("precipitation")
    cloud = item.get("cloud_area_fraction")

    # 予報で明示的に霧が出ている場合
    if "霧" in weather or "fog" in symbol:
        return "strong"

    # 高湿度＋雲の多い／降水のある時間帯は、
    # 山間部で霧・低い雲による視界低下の可能性があるとして注意表示。
    if humidity is not None and humidity >= 95:
        if (cloud is not None and cloud >= 80) or (precipitation is not None and precipitation > 0):
            return "attention"

    return "normal"


def fog_visibility_attention_text(forecasts):

    targets = [
        item for item in forecasts
        if item["dt"] >= jst_now()
        and fog_visibility_level(item) != "normal"
    ]

    if not targets:
        return None

    strong = [
        item for item in targets
        if fog_visibility_level(item) == "strong"
    ]

    target = strong if strong else targets

    first = target[0]["dt"]
    last = target[-1]["dt"]
    time_text = (
        f"{first:%H:%M}"
        if first.hour == last.hour and first.minute == last.minute
        else f"{first:%H:%M}〜{last:%H:%M}"
    )

    return {
        "time": time_text,
        "strong": bool(strong),
        "items": target,
    }


def best_travel_window(
    forecasts
):

    now = jst_now()

    future = [
        item
        for item in forecasts
        if item["dt"] >= now
        and travel_level(item) == "good"
    ]

    if not future:
        return None

    # 天候だけでなく、気圧変化が比較的小さい時間を優先。
    preferred = [
        item
        for item in future
        if travel_health_level(item) == "normal"
    ]

    if preferred:
        return preferred[0]

    return future[0]


# ============================================================
# 現在の気象状況
# ============================================================

def current_weather_status(
    amedas
):

    rain10 = amedas.get(
        "rain10"
    )

    rain1h = amedas.get(
        "rain1h"
    )

    visibility = amedas.get(
        "visibility"
    )

    if (
        visibility is not None
        and visibility <= 1000
    ):
        return (
            "🌫️ 視程が低下しています",
            "周辺AMeDASで視程1000m以下が観測されています。"
        )

    # 「今、雨が降っているか」は直近10分の実測を優先。
    if rain10 is not None:

        if rain10 >= 0.5:
            return (
                "🌧️ 雨を観測しています",
                f"周辺AMeDASの直近10分降水量は {rain10:.1f} mm です。"
            )

        if rain10 > 0:
            return (
                "🌦️ 弱い降水を観測しています",
                f"周辺AMeDASの直近10分降水量は {rain10:.1f} mm です。"
            )

    # 10分値が0でも1時間値に雨が残っていれば、
    # 「現在も雨」と断定せず、直近の降水として表示。
    if rain1h is not None and rain1h > 0:
        return (
            "🌦️ 直近1時間に降水あり",
            f"直近10分は降水なしですが、1時間降水量は {rain1h:.1f} mm です。"
        )

    if rain10 is not None:
        return (
            "✓ 周辺では現在、降水を観測していません",
            "直近10分のAMeDAS降水量は0.0 mmです。観測地点と自宅では差が出る場合があります。"
        )

    return (
        "— 現在の降水状況を確認できません",
        "周辺AMeDASの降水データを取得できませんでした。"
    )


# ============================================================
# HTML
# ============================================================

HTML = r"""
<!doctype html>

<html lang="ja">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>奈良本｜天気・気圧</title>

<script
    src="https://cdn.jsdelivr.net/npm/chart.js"
></script>

<style>

* {
    box-sizing: border-box;
}

html,
body {

    margin: 0;
    padding: 0;

    background: #171516;
    color: #eee8e8;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        "Noto Sans JP",
        sans-serif;
}

body {
    padding: 28px;
}

.page {
    max-width: 1180px;
    margin: 0 auto;
}

.header {

    border-bottom: 1px solid #393234;

    padding-bottom: 18px;

    margin-bottom: 24px;
}

.title {

    font-size: 26px;

    font-weight: 500;

    letter-spacing: .08em;
}

.title span {
    color: #c98991;
}

.updated {

    margin-top: 8px;

    color: #91888a;

    font-size: 13px;
}

.section {
    margin-top: 30px;
}

.section-title {

    font-size: 14px;

    letter-spacing: .12em;

    color: #c98991;

    margin-bottom: 14px;
}

.home-weather {

    background: #211d1e;

    border: 1px solid #3a3335;

    border-radius: 12px;

    padding: 24px;
}

.home-label {

    color: #aaa1a3;

    font-size: 13px;

    margin-bottom: 8px;
}

.home-temp {

    font-size: 54px;

    font-weight: 300;

    letter-spacing: -.03em;
}

.home-temp-unit {

    font-size: 20px;

    color: #aaa1a3;
}

.home-meta {

    margin-top: 8px;

    color: #b7afb1;

    font-size: 13px;
}

.note {

    color: #81797b;

    font-size: 11px;

    margin-top: 12px;

    line-height: 1.7;
}

.observation {

    border-top: 1px solid #393234;

    border-bottom: 1px solid #393234;

    padding: 18px 0;
}

.station {

    color: #b9b0b2;

    font-size: 13px;

    margin-bottom: 18px;

    line-height: 1.8;
}

.metrics {

    display: grid;

    grid-template-columns:
        repeat(5, minmax(0, 1fr));

    gap: 12px;
}

.metric {

    padding: 15px;

    background: #211d1e;

    border: 1px solid #332d2f;

    border-radius: 9px;
}

.metric-label {

    color: #81797b;

    font-size: 11px;

    margin-bottom: 8px;
}

.metric-value {

    font-size: 20px;

    font-weight: 400;
}

.pressure {

    display: grid;

    grid-template-columns:
        repeat(2, minmax(0, 1fr));

    gap: 14px;
}

.pressure-box {

    background: #211d1e;

    border: 1px solid #3a3335;

    border-radius: 10px;

    padding: 20px;
}

.pressure-label {

    color: #81797b;

    font-size: 12px;
}

.pressure-value {

    font-size: 30px;

    margin-top: 8px;
}

.trend {

    margin-top: 14px;

    color: #c98991;
}


/* =========================================================
   今後の注意情報
   ========================================================= */

.notice-area {

    border-top: 1px solid #393234;

    border-bottom: 1px solid #393234;

    padding: 18px 0;
}

.notice-box {

    background: #211d1e;

    border: 1px solid #3a3335;

    border-radius: 10px;

    padding: 18px;

    margin-bottom: 12px;
}

.notice-box:last-child {
    margin-bottom: 0;
}

.notice-box.attention {

    border-color: #73545a;

    background:
        linear-gradient(
            90deg,
            rgba(150,100,110,.10),
            #211d1e
        );
}

.notice-box.danger {

    border-color: #a05d68;

    background:
        linear-gradient(
            90deg,
            rgba(180,80,95,.20),
            #211d1e
        );

    box-shadow:
        inset 3px 0 0 #b86c77;
}

.notice-heading {

    font-size: 14px;

    letter-spacing: .05em;

    margin-bottom: 8px;
}

.notice-time {

    font-size: 23px;

    font-weight: 500;

    color: #e0b0b5;

    margin-bottom: 6px;
}

.notice-detail {

    color: #aaa1a3;

    font-size: 12px;

    line-height: 1.8;
}

.notice-safe {

    color: #b7aaa9;

    font-size: 13px;
}

.status {

    padding: 20px 0;

    border-bottom: 1px solid #393234;
}

.status-main {
    font-size: 19px;
}

.status-sub {

    margin-top: 7px;

    color: #92898b;

    font-size: 13px;
}



/* =========================================================
   1時間ごとの天気
   ========================================================= */

.hourly {
    width: 100%;
    border-top: 1px solid #393234;
    border-bottom: 1px solid #393234;
    overflow: hidden;
}

.hour-row {
    display: grid;

    grid-template-columns:
        90px
        80px
        1fr
        95px
        105px
        115px
        120px;

    align-items: center;

    min-height: 64px;

    border-bottom: 1px solid #302a2c;

    gap: 8px;

    padding: 7px 4px;

    font-size: 13px;
}

.hour-row:last-child {
    border-bottom: 0;
}


/* ヘッダー */

.hour-row.header-row {
    min-height: 42px;

    color: #81797b;

    font-size: 11px;

    letter-spacing: .05em;
}


/* 時間 */

.header-row > div:nth-child(1) {
    text-align: left;
    padding-left: 8px;
}


/* 天気 */

.header-row > div:nth-child(2) {
    text-align: center;
}


/* 状況 */

.header-row > div:nth-child(3) {
    text-align: center;
}


/* 気温・降水量・気圧・麓への移動 */

.header-row > div:nth-child(4),
.header-row > div:nth-child(5),
.header-row > div:nth-child(6),
.header-row > div:nth-child(7) {
    text-align: center;
}


/* データ */

.hour-time {
    font-size: 15px;
    color: #d6ced0;
    white-space: nowrap;
}

.hour-icon {
    font-size: 23px;
    text-align: center;
}

.hour-weather {
    color: #d4cccd;
    text-align: center;
}
.hour-situation {
    text-align: center;
    padding-left: 0;
}

.hour-temp {
    text-align: center;
}

.hour-rain {
    text-align: center;
}

.hour-pressure {
    text-align: center;
    color: #aaa1a3;
}


/* 麓への移動 */

.hour-row > div:last-child {
    text-align: center;
}

.travel-status {
    text-align: center;

    font-size: 11px;

    border-radius: 999px;

    padding: 5px 7px;
}

.travel-good {
    color: #a9b0a8;

    background: rgba(
        120,
        140,
        125,
        .10
    );
}

.travel-attention {
    color: #d0a995;

    background: rgba(
        180,
        125,
        90,
        .13
    );
}

.travel-danger {
    color: #e0a3a9;

    background: rgba(
        180,
        75,
        90,
        .18
    );

    font-weight: 600;
}

.health-attention {
    color: #e0a3a9;

    font-weight: 600;
}

.row-attention {
    background:
        linear-gradient(
            90deg,
            rgba(160,100,110,.08),
            transparent
        );
}

.row-danger {
    background:
        linear-gradient(
            90deg,
            rgba(180,70,85,.17),
            transparent
        );

    box-shadow:
        inset 3px 0 0 #ad6973;
}


/* =========================================================
   グラフ
   ========================================================= */

.chart-box {

    background: #211d1e;

    border: 1px solid #332d2f;

    border-radius: 12px;

    padding: 14px 16px 12px;

    height: 420px;

    box-shadow: inset 0 1px 0 rgba(255,255,255,.02);
}

.chart-box.pressure-chart-box {
    height: 440px;
}

.pressure-alerts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 8px;
    margin-top: 10px;
}

.pressure-alert {
    padding: 10px 12px;
    border-radius: 9px;
    border: 1px solid #3b3436;
    background: #1d191a;
    font-size: 12px;
    line-height: 1.6;
}

.pressure-alert.strong {
    border-color: #85545d;
    background: rgba(180,70,85,.10);
}

.pressure-alert.attention {
    border-color: #695358;
    background: rgba(150,100,110,.07);
}

.pressure-alert-title {
    font-weight: 600;
    margin-bottom: 2px;
}

.pressure-alert-detail {
    color: #aaa1a3;
}

.chart-subtitle {
    margin: -5px 0 10px;
    color: #8d8587;
    font-size: 11px;
}

.chart-box canvas {

    width: 100% !important;

    height: 100% !important;
}

.temperature-legend {

    display: flex;
    flex-wrap: wrap;
    gap: 10px 14px;
    margin-top: 10px;
    color: #91888a;
    font-size: 10px;
}

.temperature-legend span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.temp-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.temp-freeze { background: #315f9e; }
.temp-cold { background: #5c8fd8; }
.temp-cool { background: #62b5d6; }
.temp-mild { background: #65b99a; }
.temp-warm { background: #9fbe68; }
.temp-hot { background: #d7c45f; }
.temp-veryhot { background: #df9a55; }
.temp-extreme { background: #d96b6b; }
.temp-danger { background: #a93643; }


.chart-explanation {

    margin-top: 10px;

    color: #81797b;

    font-size: 11px;

    line-height: 1.7;
}

.legend-note {

    display: flex;

    gap: 18px;

    flex-wrap: wrap;

    margin-top: 10px;

    color: #91888a;

    font-size: 11px;
}

.legend-item {

    display: flex;

    align-items: center;

    gap: 6px;
}

.legend-dot {

    width: 9px;

    height: 9px;

    border-radius: 50%;

    background: #8d6b70;
}

.legend-dot.strong {
    background: #b87880;
}

.legend-dot.rise {
    background: #706e86;
}

.error {

    color: #b8878d;

    font-size: 12px;

    padding: 10px 0;
}

.footer {

    margin-top: 35px;

    padding-top: 18px;

    border-top: 1px solid #393234;

    color: #70696b;

    font-size: 11px;
}


/* =========================================================
   スマホ
   ========================================================= */

@media (max-width: 800px) {

    body {
        padding: 18px;
    }

    .metrics {

        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }

    .pressure {
        grid-template-columns: 1fr;
    }

    .home-temp {
        font-size: 46px;
    }

    .hourly {
        overflow-x: auto;
    }

    .hour-row {

        min-width: 660px;
    }

    .chart-box {

        height: 390px;

        padding: 10px;
    }

    .chart-box.pressure-chart-box {
        height: 410px;
    }
}
/* =========================================================
24時間 天気グラフ
========================================================= */

.weather-chart-card {

background: #211d1e;

border: 1px solid #332d2f;

border-radius: 12px;

padding: 18px 18px 20px;

box-shadow:
    inset 0 1px 0 rgba(255,255,255,.02);


}

.weather-chart-header {


display: flex;

align-items: center;

margin-bottom: 18px;


}

.weather-chart-kicker {


color: #81797b;

font-size: 10px;

letter-spacing: .16em;

margin-bottom: 5px;


}

.weather-chart-name {


color: #eee8e8;

font-size: 17px;

letter-spacing: .06em;


}

/* =========================================================
天気タイムライン
========================================================= */

.weather-timeline {


display: grid;

grid-template-columns:
    repeat(24, minmax(52px, 1fr));

min-width: 1248px;

border-top: 1px solid #393234;

border-bottom: 1px solid #393234;

padding: 12px 0 14px;

margin-bottom: 18px;


}

.weather-time-item {


text-align: center;

min-width: 0;


}

.weather-time {


color: #91888a;

font-size: 10px;

margin-bottom: 8px;

white-space: nowrap;


}

.weather-icon-large {


font-size: 22px;

line-height: 1.2;


}

/* =========================================================
グラフタイトル
========================================================= */

.weather-chart-title {


color: #aaa1a3;

font-size: 12px;

letter-spacing: .06em;

margin: 12px 0 7px;


}

.rain-title {


margin-top: 20px;


}

/* =========================================================
グラフ本体
========================================================= */

.weather-chart-panel {


position: relative;

width: 100%;

min-width: 1248px;


}

.temperature-panel {


height: 180px;


}

.rain-panel {


height: 125px;


}

.weather-chart-panel canvas {


width: 100% !important;

height: 100% !important;


}

/* =========================================================
横スクロール
========================================================= */

.weather-chart-card {


overflow-x: auto;


}

.weather-chart-card::-webkit-scrollbar {


height: 7px;


}

.weather-chart-card::-webkit-scrollbar-track {


background: #1b1819;


}

.weather-chart-card::-webkit-scrollbar-thumb {


background: #51484a;

border-radius: 999px;


}

/* =========================================================
スマホ
========================================================= */

@media (max-width: 800px) {


.weather-chart-card {

    padding: 16px 12px 18px;

}

.weather-chart-panel {

    min-width: 1248px;

}

.weather-timeline {

    min-width: 1248px;

}

.temperature-panel {

    height: 170px;

}

.rain-panel {

    height: 115px;

}


}
/* =========================================================
   🐕 いよかん生活ガイド
   ========================================================= */

.dog-guide-card {
    background: #211d1e;
    border: 1px solid #332d2f;
    border-radius: 12px;
    padding: 16px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.02);
}

.dog-guide-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
}

.dog-guide-item {
    background: #1b1819;
    border: 1px solid #302a2c;
    border-radius: 10px;
    padding: 14px 10px;
    text-align: center;
}

.dog-guide-icon {
    font-size: 23px;
    margin-bottom: 6px;
}

.dog-guide-label {
    color: #8f8789;
    font-size: 11px;
    margin-bottom: 7px;
}

.dog-guide-value {
    color: #eee8e8;
    font-size: 13px;
    font-weight: 600;
}

.dog-guide-times {
    margin-top: 12px;
    border-top: 1px solid #302a2c;
}

.dog-guide-time-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    padding: 10px 4px;
    border-bottom: 1px solid #302a2c;
    font-size: 12px;
}

.dog-guide-time-row span {
    color: #938b8d;
}

.dog-guide-time-row strong {
    color: #e7e0e1;
    font-weight: 500;
    text-align: right;
}

@media (max-width: 800px) {

    .dog-guide-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
    }

    .dog-guide-item {
        padding: 12px 8px;
    }

    .dog-guide-time-row {
        font-size: 11px;
    }
}

</style>

</head>


<body>

<div class="page">


<header class="header">

    <div class="title">
        <span>奈良本</span>｜標高 約500m
    </div>

    <div class="updated">
        {{ updated }}
    </div>

</header>


<!-- ===================================================== -->
<!-- 自宅現在推定 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        自宅の現在推定
    </div>

    <div class="home-weather">

        <div class="home-label">
            奈良本・標高約500m地点
        </div>

        <div class="home-temp">

            {% if home_temp is not none %}

                {{ "%.1f"|format(home_temp) }}

                <span class="home-temp-unit">
                    ℃
                </span>

            {% else %}

                —

            {% endif %}

        </div>

        <div class="home-meta">

            {% if home_forecast_time %}
                推定時刻 {{ home_forecast_time }}
            {% endif %}

            {% if home_weather %}
                ｜{{ home_icon }} {{ home_weather }}
            {% endif %}

        </div>

        <div class="note">

            ※気象モデル（MET Norway）による自宅地点の推定値です。<br>
            ※自宅に温度計を設置した実測値ではありません。

        </div>

    </div>

</section>


<!-- ===================================================== -->
<!-- 自宅気圧 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        自宅地点の気圧
    </div>

    <div class="pressure">


        <div class="pressure-box">

            <div class="pressure-label">
                標高約500mの自宅地点
            </div>

            <div class="pressure-value">

                {% if home_surface_pressure is not none %}

                    {{ "%.1f"|format(home_surface_pressure) }}
                    hPa

                {% else %}

                    —

                {% endif %}

            </div>

        </div>


        <div class="pressure-box">

            <div class="pressure-label">
                海面更正気圧
            </div>

            <div class="pressure-value">

                {% if home_sea_pressure is not none %}

                    {{ "%.1f"|format(home_sea_pressure) }}
                    hPa

                {% else %}

                    —

                {% endif %}

            </div>

        </div>


    </div>


    <div class="trend">

        {% if home_surface_pressure is not none %}

            {{ pressure_level_text }}
            ｜{{ pressure_trend_text }}

        {% else %}

            気圧の傾向を判定できません

        {% endif %}

    </div>

</section>


<!-- ===================================================== -->
<!-- 周辺観測 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        現在の周辺観測
    </div>

    <div class="observation">

        {% if amedas.ok %}

        <div class="station">

            降水：
            {{ amedas.rain_station }}

            {% if amedas.rain_distance is not none %}
                ｜約{{ "%.1f"|format(amedas.rain_distance) }}km
            {% endif %}

            <br>

            気温・湿度・風：
            {{ amedas.four_station }}

            {% if amedas.four_distance is not none %}
                ｜約{{ "%.1f"|format(amedas.four_distance) }}km
            {% endif %}

            ｜観測時刻
            {{ amedas.observed_at.strftime("%Y/%m/%d %H:%M") }}

        </div>

        {% else %}

        <div class="station">
            AMeDASデータ取得エラー
        </div>

        {% endif %}


        <div class="metrics">


            <div class="metric">

                <div class="metric-label">
                    気温
                </div>

                <div class="metric-value">

                    {% if amedas.temp is not none %}
                        {{ "%.1f"|format(amedas.temp) }} ℃
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    湿度
                </div>

                <div class="metric-value">

                    {% if amedas.humidity is not none %}
                        {{ "%.0f"|format(amedas.humidity) }} %
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    降水量（10分）
                </div>

                <div class="metric-value">

                    {% if amedas.rain10 is not none %}
                        {{ "%.1f"|format(amedas.rain10) }} mm
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    風速
                </div>

                <div class="metric-value">

                    {% if amedas.wind is not none %}
                        {{ "%.1f"|format(amedas.wind) }} m/s
                    {% else %}
                        —
                    {% endif %}

                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    風向
                </div>

                <div class="metric-value">

                    {{ amedas.wind_direction }}

                </div>

            </div>


        </div>


        <div class="note">

            ※現在値は気象庁AMeDASによる周辺観測です。<br>
            ※自宅周辺と観測地点では、特に風・雨・霧などに差が出る場合があります。

        </div>

    </div>

</section>


<!-- ===================================================== -->
<!-- 現在の気象状況 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        現在の気象状況
    </div>

    <div class="status">

        <div class="status-main">
            {{ weather_status }}
        </div>

        <div class="status-sub">
            {{ weather_status_sub }}
        </div>

    </div>

</section>


<!-- ===================================================== -->
<!-- 今後の注意情報 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        ⚠️ 今後の注意情報
    </div>

    <div class="notice-area">


        {% if health_attention %}

        <div class="
            notice-box
            {% if health_attention.strong %}
                danger
            {% else %}
                attention
            {% endif %}
        ">

            <div class="notice-heading">
                🩺 体調注意
            </div>

            <div class="notice-time">

                {% if health_attention.strong %}
                    ⚠️ 特に注意
                {% endif %}

                {{ health_attention.time }}

            </div>

            <div class="notice-detail">

                {{ health_attention.direction_text }}です。<br>
                気圧変化で体調に影響を受けやすい方は、以下の時間帯を目安に無理をしないよう注意してください。<br>

               {% for item in health_attention["items"] %}
                    {{ item.dt.strftime("%H:%M") }}
                    {{ item.pressure_label }}

                    {% if item.pressure_change is not none %}
                        （{{ "%+.1f"|format(item.pressure_change) }} hPa / 3時間）
                    {% endif %}

                    {% if not loop.last %}
                        ｜ 
                    {% endif %}

                {% endfor %}

                <br>
                ※気象条件から見た注意喚起であり、体調不良を予測・診断するものではありません。

            </div>

        </div>

        {% endif %}


        {% if travel_health_attention %}

        <div class="notice-box {% if travel_health_attention.strong %}danger{% else %}attention{% endif %}">

            <div class="notice-heading">
                🚗🩺 麓への移動と体調
            </div>

            <div class="notice-time">
                {% if travel_health_attention.strong %}
                    ⚠️ 特に注意
                {% else %}
                    気圧変化に注意
                {% endif %}
                ｜{{ travel_health_attention.time }}
            </div>

            <div class="notice-detail">
                この時間帯は気圧の変化があり、標高約500mの自宅から麓へ移動するときの気圧変化も重なります。<br>
                気圧変化に敏感な方は、体調に不安がある場合、可能なら急な変化の時間帯を避けて移動することをおすすめします。<br>

                {% if travel_health_attention.max_change is not none %}
                    この時間帯の最大変化：{{ "%+.1f"|format(travel_health_attention.max_change) }} hPa / 3時間<br>
                {% endif %}

                ※気圧変化と体調の関係には個人差があります。これは気象条件から見た注意情報で、体調不良を予測・診断するものではありません。<br>
                ※標高約500mから麓への移動では周囲の気圧も上がります。実際の移動先の標高・天候・道路状況も確認してください。
            </div>

        </div>

        {% endif %}


        {% if fog_visibility_attention %}

        <div class="notice-box {% if fog_visibility_attention.strong %}danger{% else %}attention{% endif %}">

            <div class="notice-heading">
                🌫️ 霧・視界注意
            </div>

            <div class="notice-time">
                {% if fog_visibility_attention.strong %}
                    ⚠️ 霧の予報あり
                {% else %}
                    視界低下に注意
                {% endif %}
                ｜{{ fog_visibility_attention.time }}
            </div>

            <div class="notice-detail">
                この時間帯は、霧または高湿度・雲・降水などの条件から、山間部で霧や低い雲に包まれて視界が悪くなる可能性があります。<br>
                標高約500mの自宅周辺では、麓より先に視界が悪化することがあります。特に車での移動時は無理をせず、実際の道路状況を確認してください。<br>
                {% for item in fog_visibility_attention["items"] %}
                    {{ item.dt.strftime("%H:%M") }} {{ item.weather }}{% if item.humidity is not none %}・湿度 {{ "%.0f"|format(item.humidity) }}%{% endif %}{% if not loop.last %} ｜ {% endif %}
                {% endfor %}
                <br>
                ※これは気象条件から見た視界低下の注意情報です。実際の霧の発生や視程を保証するものではありません。
            </div>

        </div>

        {% endif %}


        {% if travel_window %}

        <div class="notice-box">

            <div class="notice-heading">
                🚗 麓への移動
            </div>

            <div class="notice-time">

                🟢
                {{ travel_window.dt.strftime("%H:%M") }}頃から
                比較的移動しやすい見込み

            </div>

            <div class="notice-detail">

                今後の予報の中で、
                雨・雷・強風などの影響が比較的小さい時間帯です。<br>

                ※山道の実際の路面・霧・交通状況は別途確認してください。

            </div>

        </div>

        {% endif %}


        {% if travel_danger_items %}

        <div class="notice-box danger">

            <div class="notice-heading">
                🚗⚠️ 麓への移動注意
            </div>

            <div class="notice-time">

                {{ travel_danger_start }}
                〜
                {{ travel_danger_end }}

            </div>

            <div class="notice-detail">

                強い雨・雷・強風などにより、
                山道の運転条件が悪化する可能性があります。

            </div>

        </div>

        {% endif %}


        {% if not health_attention and not travel_health_attention and not fog_visibility_attention and not travel_window and not travel_danger_items %}

        <div class="notice-safe">
            現時点では、大きな注意情報はありません。
        </div>

        {% endif %}


    </div>

</section>

<!-- =========================================================
     🐕 いよかん生活ガイド
     ========================================================= -->

<section class="section">

    <div class="section-title">
        🐕 いよかん生活ガイド
    </div>

    <div class="dog-guide-card">

        <div class="dog-guide-grid">

            <div class="dog-guide-item">
                <div class="dog-guide-icon">🏠</div>
                <div class="dog-guide-label">
                    自宅の散歩
                </div>
                <div class="dog-guide-value">
                    {% if good_walk_times %}
                        🟢 散歩OK
                    {% else %}
                        🔴 注意
                    {% endif %}
                </div>
            </div>


            <div class="dog-guide-item">
                <div class="dog-guide-icon">🌊</div>
                <div class="dog-guide-label">
                    麓の散歩
                </div>
                <div class="dog-guide-value">
                    🟡 判定準備中
                </div>
            </div>


            <div class="dog-guide-item">
                <div class="dog-guide-icon">🔥</div>
                <div class="dog-guide-label">
                    アスファルト
                </div>
                <div class="dog-guide-value">
                    {% if asphalt_ng_times %}
                        🔴 NG時間あり
                    {% else %}
                        🟢 問題なし
                    {% endif %}
                </div>
            </div>


            <div class="dog-guide-item">
                <div class="dog-guide-icon">❄️</div>
                <div class="dog-guide-label">
                    エアコン
                </div>
                <div class="dog-guide-value">
                    {% if aircon_times %}
                        🟠 使用推奨
                    {% else %}
                        🟢 基本不要
                    {% endif %}
                </div>
            </div>

        </div>


        <div class="dog-guide-times">

            <div class="dog-guide-time-row">
                <span>🐾 散歩おすすめ</span>
                <strong>
                    {% if good_walk_times %}
                        {{ good_walk_times | join("・") }}
                    {% else %}
                        なし
                    {% endif %}
                </strong>
            </div>


            <div class="dog-guide-time-row">
                <span>🔥 アスファルトNG</span>
                <strong>
                    {% if asphalt_ng_times %}
                        {{ asphalt_ng_times | join("・") }}
                    {% else %}
                        なし
                    {% endif %}
                </strong>
            </div>


            <div class="dog-guide-time-row">
                <span>❄️ 冷房推奨</span>
                <strong>
                    {% if aircon_times %}
                        {{ aircon_times | join("・") }}
                    {% else %}
                        なし
                    {% endif %}
                </strong>
            </div>

        </div>

    </div>

</section>

<!-- ===================================================== -->
<!-- 24時間・1時間ごとの天気 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        🌦️ 24時間の天気
    </div>

    <div class="note">
        奈良本・標高約500m地点の予報
    </div>


    {% if forecasts %}

    <div class="hourly">

        <div class="hour-row header-row">

            <div>時間</div>
            <div>天気</div>
            <div>状況</div>
            <div>気温</div>
            <div>降水量</div>
            <div>気圧</div>
            <div>麓への移動</div>

        </div>


        {% for item in forecasts %}

        <div class="
            hour-row
            {% if item.travel_level == 'danger' %}
                row-danger
            {% elif item.travel_level == 'attention' or item.health_level != 'normal' %}
                row-attention
            {% endif %}
        ">


             <div class="hour-time">
                {{ item.dt.strftime("%H:%M") }}
            </div>


<div class="hour-weather">

    <span class="hour-icon">
        {{ item.icon }}
    </span>

    <span class="weather-name">
        {{ item.display_weather }}
    </span>

</div>


<div class="
    hour-situation
    {% if item.travel_level == 'danger' %}
        danger
    {% elif item.travel_level == 'attention'
          or item.health_level != 'normal'
          or item.fog_visibility_level != 'normal' %}
        attention
    {% endif %}
">

    {% if item.health_level == "strong" %}
        🩺
    {% endif %}

    {{ item.situation }}

</div>


            <div class="hour-temp">

                {% if item.temperature is not none %}
                    {{ "%.1f"|format(item.temperature) }}℃
                {% else %}
                    —
                {% endif %}

            </div>


            <div class="hour-rain">

                {% if item.precipitation is not none %}

                    {{ "%.1f"|format(item.precipitation) }}mm

                {% else %}

                    —

                {% endif %}

            </div>


            <div class="hour-pressure">

                {% if item.surface_pressure is not none %}

                    {{ "%.1f"|format(item.surface_pressure) }}

                    {% if item.pressure_level == "strong-fall" %}
                        <br>
                        <span class="health-attention">
                            ↓ 急低下
                        </span>
                    {% elif item.pressure_level == "fall" %}
                        <br>
                        ↓ 低下
                    {% elif item.pressure_level == "strong-rise" %}
                        <br>
                        ↑ 急上昇
                    {% elif item.pressure_level == "rise" %}
                        <br>
                        ↑ 上昇
                    {% endif %}

                {% else %}

                    —

                {% endif %}

            </div>


            <div>

                {% if item.travel_level == "danger" %}

                    <div class="
                        travel-status
                        travel-danger
                    ">
                        🔴 注意
                    </div>

                {% elif item.health_level == "strong" %}

                    <div class="
                        travel-status
                        travel-danger
                    ">
                        🩺 気圧注意
                    </div>

                {% elif item.travel_level == "attention" or item.health_level == "attention" %}

                    <div class="
                        travel-status
                        travel-attention
                    ">
                        🟠 注意
                    </div>

                {% else %}

                    <div class="
                        travel-status
                        travel-good
                    ">
                        🟢 比較的良好
                    </div>

                {% endif %}

            </div>


        </div>

        {% endfor %}

    </div>


    {% else %}

    <div class="error">
        自宅地点の予報データを取得できませんでした。
    </div>

    {% endif %}

</section>


<!-- ===================================================== -->

<!-- 24時間 天気グラフ -->

<!-- ===================================================== -->

<section class="section">


<div class="section-title">
    📈 24時間の天気グラフ
</div>

<div class="weather-chart-card">

    <div class="weather-chart-header">
        <div>
            <div class="weather-chart-kicker">
                NEXT 24 HOURS
            </div>

            <div class="weather-chart-name">
                天気の流れ
            </div>
        </div>
    </div>

    <!-- 天気 -->
    <div class="weather-timeline" id="weatherTimeline"></div>

    <!-- 気温 -->
    <div class="weather-chart-title">
        🌡️ 気温
    </div>

    <div class="weather-chart-panel temperature-panel">
        <canvas id="temperatureChart"></canvas>
    </div>

    <!-- 降水量 -->
    <div class="weather-chart-title rain-title">
        💧 降水量
    </div>

    <div class="weather-chart-panel rain-panel">
        <canvas id="rainChart"></canvas>
    </div>

</div>

<div class="chart-explanation">

    天気の変化、気温、降水量を分けて表示しています。<br>
    気温は温度帯によって色分けしています。

</div>


</section>

<!-- ===================================================== -->
<!-- 24時間 気圧 -->
<!-- ===================================================== -->

<section class="section">

    <div class="section-title">
        📉 24時間の気圧
    </div>

    <div class="chart-subtitle">
        線＝自宅地点の気圧　｜　棒＝直近3時間の気圧変化　｜　背景＝注意時間帯
    </div>

    <div class="chart-box pressure-chart-box">

        <canvas id="pressureChart"></canvas>

    </div>

    <div id="pressureAlerts" class="pressure-alerts"></div>


    <div class="legend-note">

        <div class="legend-item">

            <span class="legend-dot"></span>

            気圧変化あり

        </div>


        <div class="legend-item">

            <span class="legend-dot strong"></span>

            大きな気圧変化

        </div>


        <div class="legend-item">

            <span class="legend-dot rise"></span>

            上昇方向

        </div>

    </div>


    <div class="chart-explanation">

        3時間程度の気圧変化を目安にしています。<br>
        「急低下」「急上昇」は短時間の気圧変化が大きい時間帯です。

    </div>

</section>


<footer class="footer">

    奈良本｜標高 約500m
    ｜24時間予報：MET Norway

</footer>


</div>


<script>

const forecastLabels =
    {{ chart_labels | safe }};

const temperatures =
    {{ chart_temperatures | safe }};

const forecastIcons =
    {{ chart_icons | safe }};

const precipitation =
    {{ chart_precipitation | safe }};

const pressures =
    {{ chart_pressures | safe }};

const pressureLevels =
    {{ pressure_levels | safe }};

const pressureChanges =
    {{ pressure_changes | safe }};


const gridColor = "#302a2c";
const textColor = "#8d8587";
/* =========================================================
24時間 天気グラフ
========================================================= */

function temperatureColor(value) {


if (value === null || value === undefined) {
    return "#9a9294";
}

if (value < 0) {
    return "#315f9e";
}

if (value < 5) {
    return "#5c8fd8";
}

if (value < 10) {
    return "#62b5d6";
}

if (value < 15) {
    return "#65b99a";
}

if (value < 20) {
    return "#9fbe68";
}

if (value < 25) {
    return "#d7c45f";
}

if (value < 30) {
    return "#df9a55";
}

if (value < 35) {
    return "#d96b6b";
}

return "#a93643";


}

/* =========================================================
天気タイムライン
========================================================= */

const weatherTimeline =
document.getElementById("weatherTimeline");

if (weatherTimeline) {


weatherTimeline.innerHTML =
    forecastLabels.map((label, index) => {

        return `
            <div class="weather-time-item">

                <div class="weather-time">
                    ${label}
                </div>

                <div class="weather-icon-large">
                    ${forecastIcons[index] || "🌤️"}
                </div>

            </div>
        `;

    }).join("");


}

/* =========================================================
気温グラフ
========================================================= */

new Chart(
document.getElementById("temperatureChart"),
{


    type: "line",

    data: {

        labels: forecastLabels,

        datasets: [

            {

                label: "気温",

                data: temperatures,

                tension: 0.35,

                pointRadius: 3,

                pointHoverRadius: 6,

                borderWidth: 2.5,

                pointBackgroundColor:
                    temperatures.map(
                        temperatureColor
                    ),

                pointBorderColor:
                    temperatures.map(
                        temperatureColor
                    ),

                segment: {

                    borderColor(context) {

                        return temperatureColor(
                            context.p1.parsed.y
                        );

                    }

                }

            }

        ]

    },

    options: {

        responsive: true,

        maintainAspectRatio: false,

        interaction: {

            mode: "index",

            intersect: false

        },

        plugins: {

            legend: {

                display: false

            },

            tooltip: {

                callbacks: {

                    title(items) {

                        const index =
                            items[0]?.dataIndex ?? 0;

                        return (
                            `${forecastLabels[index]} ` +
                            `${forecastIcons[index] || ""}`
                        );

                    },

                    label(context) {

                        const temp =
                            temperatures[
                                context.dataIndex
                            ];

                        return (
                            `気温 ${
                                temp !== null
                                    ? temp.toFixed(1)
                                    : "—"
                            }℃`
                        );

                    }

                }

            }

        },

        scales: {

            x: {

                display: false,

                grid: {

                    display: false

                }

            },

            y: {

                ticks: {

                    color: textColor,

                    callback(value) {

                        return value + "℃";

                    }

                },

                grid: {

                    color: gridColor

                }

            }

        }

    }

}


);

/* =========================================================
降水量グラフ
========================================================= */

new Chart(
document.getElementById("rainChart"),
{


    type: "bar",

    data: {

        labels: forecastLabels,

        datasets: [

            {

                label: "降水量",

                data: precipitation,

                backgroundColor:
                    "rgba(70,150,215,0.55)",

                borderColor:
                    "rgba(70,150,215,0.85)",

                borderWidth: 1,

                barPercentage: 0.58,

                categoryPercentage: 0.88

            }

        ]

    },

    options: {

        responsive: true,

        maintainAspectRatio: false,

        interaction: {

            mode: "index",

            intersect: false

        },

        plugins: {

            legend: {

                display: false

            },

            tooltip: {

                callbacks: {

                    title(items) {

                        const index =
                            items[0]?.dataIndex ?? 0;

                        return (
                            `${forecastLabels[index]} ` +
                            `${forecastIcons[index] || ""}`
                        );

                    },

                    label(context) {

                        const rain =
                            precipitation[
                                context.dataIndex
                            ];

                        return (
                            `降水量 ${
                                rain !== null
                                    ? rain.toFixed(1)
                                    : "—"
                            }mm`
                        );

                    }

                }

            }

        },

        scales: {

            x: {

                ticks: {

                    color: textColor,

                    maxTicksLimit: 12,

                    autoSkip: true,

                    padding: 5

                },

                grid: {

                    color: gridColor

                }

            },

            y: {

                beginAtZero: true,

                ticks: {

                    color: textColor,

                    callback(value) {

                        return value + "mm";

                    }

                },

                grid: {

                    color: gridColor

                }

            }

        }

    }

}


);


/* =========================================================
   24時間 気圧グラフ
   気圧の線＋3時間変化の棒＋注意時間帯の背景＋注意ラベル
   ========================================================= */

const pressureBackgroundPlugin = {
    id: "pressureBackgroundPlugin",

    beforeDatasetsDraw(chart) {
        const ctx = chart.ctx;
        const xScale = chart.scales.x;
        const chartArea = chart.chartArea;
        if (!xScale || !chartArea) return;

        ctx.save();

        for (let i = 0; i < pressureLevels.length; i++) {
            const level = pressureLevels[i];
            if (!level || level === "normal") continue;

            const x1 = xScale.getPixelForValue(i);
            const x2 = i < pressureLevels.length - 1
                ? xScale.getPixelForValue(i + 1)
                : x1 + 30;

            let fill = "rgba(150,110,120,0.07)";
            if (level === "strong-fall" || level === "strong-rise") {
                fill = "rgba(190,80,100,0.20)";
            } else if (level === "fall") {
                fill = "rgba(170,105,115,0.10)";
            } else if (level === "rise") {
                fill = "rgba(105,105,140,0.10)";
            }

            ctx.fillStyle = fill;
            ctx.fillRect(
                x1,
                chartArea.top,
                x2 - x1,
                chartArea.bottom - chartArea.top
            );
        }

        ctx.restore();
    },

    afterDatasetsDraw(chart) {
        const ctx = chart.ctx;
        const xScale = chart.scales.x;
        const yScale = chart.scales.y;
        if (!xScale || !yScale) return;

        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";

        for (let i = 0; i < pressureLevels.length; i++) {
            const level = pressureLevels[i];
            const change = pressureChanges[i];
            if (!level || level === "normal" || change === null) continue;
            if (pressures[i] === null || pressures[i] === undefined) continue;

            const x = xScale.getPixelForValue(i);
            const y = yScale.getPixelForValue(pressures[i]);

            let label = "";
            if (level === "strong-fall") label = "⚠ 急低下";
            else if (level === "fall") label = "↓ 低下";
            else if (level === "strong-rise") label = "⚠ 急上昇";
            else if (level === "rise") label = "↑ 上昇";

            ctx.font = (level === "strong-fall" || level === "strong-rise")
                ? "600 10px sans-serif"
                : "10px sans-serif";
            ctx.fillStyle = (level === "strong-fall" || level === "strong-rise")
                ? "#e0a3a9"
                : "#b09ba0";

            ctx.fillText(label, x, y - 8);
        }

        ctx.restore();
    }
};

new Chart(document.getElementById("pressureChart"), {
    type: "line",
    plugins: [pressureBackgroundPlugin],
    data: {
        labels: forecastLabels,
        datasets: [
            {
                label: "気圧",
                data: pressures,
                yAxisID: "pressure",
                tension: 0.32,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 2.5,
                pointBackgroundColor: pressures.map((_, i) => {
                    const level = pressureLevels[i];
                    if (level === "strong-fall" || level === "strong-rise") return "#d97b86";
                    if (level === "fall") return "#b58c94";
                    if (level === "rise") return "#8c88a5";
                    return "#b7afb1";
                }),
                pointBorderColor: pressures.map((_, i) => {
                    const level = pressureLevels[i];
                    if (level === "strong-fall" || level === "strong-rise") return "#d97b86";
                    if (level === "fall") return "#b58c94";
                    if (level === "rise") return "#8c88a5";
                    return "#b7afb1";
                })
            },
            {
                type: "bar",
                label: "3時間変化",
                data: pressureChanges,
                yAxisID: "change",
                backgroundColor: pressureChanges.map((value, i) => {
                    const level = pressureLevels[i];
                    if (level === "strong-fall") return "rgba(210,90,105,0.72)";
                    if (level === "fall") return "rgba(180,110,120,0.48)";
                    if (level === "strong-rise") return "rgba(135,125,165,0.72)";
                    if (level === "rise") return "rgba(120,115,155,0.48)";
                    return "rgba(130,125,135,0.18)";
                }),
                borderWidth: 0,
                barPercentage: 0.72,
                categoryPercentage: 0.9
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
            padding: { top: 28, bottom: 14, left: 4, right: 4 }
        },
        interaction: { mode: "index", intersect: false },
        plugins: {
            legend: {
                display: true,
                labels: { color: textColor, usePointStyle: true, boxWidth: 8 }
            },
            tooltip: {
                callbacks: {
                    title(items) {
                        const index = items[0]?.dataIndex ?? 0;
                        return `${forecastLabels[index]} ${pressureLevels[index] === "strong-fall" || pressureLevels[index] === "strong-rise" ? "⚠" : ""}`;
                    },
                    label(context) {
                        const index = context.dataIndex;
                        if (context.datasetIndex === 0) {
                            const pressure = pressures[index];
                            return `気圧 ${pressure !== null ? pressure.toFixed(1) : "—"} hPa`;
                        }
                        const change = pressureChanges[index];
                        return `3時間変化 ${change !== null ? (change >= 0 ? "+" : "") + change.toFixed(1) : "—"} hPa`;
                    }
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    color: textColor,
                    maxTicksLimit: 12,
                    autoSkip: true,
                    padding: 6
                },
                grid: { color: gridColor }
            },
            pressure: {
                type: "linear",
                position: "left",
                ticks: {
                    color: textColor,
                    callback(value) { return value + " hPa"; }
                },
                grid: { color: gridColor }
            },
            change: {
                type: "linear",
                position: "right",
                beginAtZero: true,
                grid: { drawOnChartArea: false },
                ticks: {
                    color: textColor,
                    callback(value) { return (value >= 0 ? "+" : "") + value.toFixed(1) + " hPa"; }
                }
            }
        }
    }
});

/* =========================================================
   グラフ下の「注意時間」
   ========================================================= */

const pressureAlerts = document.getElementById("pressureAlerts");
if (pressureAlerts) {
    const alerts = [];

    for (let i = 0; i < pressureLevels.length; i++) {
        const level = pressureLevels[i];
        if (!level || level === "normal") continue;

        const change = pressureChanges[i];
        const label =
            level === "strong-fall" ? "⚠ 急低下" :
            level === "fall" ? "↓ 気圧低下" :
            level === "strong-rise" ? "⚠ 急上昇" :
            "↑ 気圧上昇";

        const strong = level === "strong-fall" || level === "strong-rise";
        const cls = strong ? "strong" : "attention";
        const changeText = change === null
            ? ""
            : `（3時間で ${change >= 0 ? "+" : ""}${change.toFixed(1)} hPa）`;

        alerts.push(
            `<div class="pressure-alert ${cls}">` +
            `<div class="pressure-alert-title">${label}　${forecastLabels[i]}</div>` +
            `<div class="pressure-alert-detail">${strong ? "この時間帯は特に注意" : "気圧の変化がある時間帯"}${changeText}</div>` +
            `</div>`
        );
    }

    if (alerts.length) {
        pressureAlerts.innerHTML = alerts.slice(0, 8).join("");
    } else {
        pressureAlerts.innerHTML =
            `<div class="pressure-alert"><div class="pressure-alert-title">✓ 大きな気圧変化はありません</div><div class="pressure-alert-detail">今後24時間では、設定した基準で注意が必要な時間帯はありません。</div></div>`;
    }
}

</script>


</body>

</html>
"""


# ============================================================
# メイン
# ============================================================

@app.route("/")
def index():

    now = jst_now()

    amedas = get_amedas()

    met_json = get_met_forecast()

    all_forecasts = (
        build_forecasts(
            met_json
        )
    )

    all_forecasts = (
        add_pressure_change_info(
            all_forecasts
        )
    )


    # --------------------------------------------------------
    # 現在の自宅推定
    # --------------------------------------------------------

    current_forecast = (
        nearest_forecast(
            all_forecasts
        )
    )

    home_temp = None
    home_surface_pressure = None
    home_sea_pressure = None
    home_weather = None
    home_icon = "🌤️"
    home_forecast_time = None


    if current_forecast:

        home_temp = (
            current_forecast[
                "temperature"
            ]
        )

        home_surface_pressure = (
            current_forecast[
                "surface_pressure"
            ]
        )

        home_sea_pressure = (
            current_forecast[
                "sea_pressure"
            ]
        )

        home_weather = (
            current_forecast[
                "weather"
            ]
        )

        home_icon = (
            current_forecast[
                "icon"
            ]
        )

        home_forecast_time = (
            current_forecast["dt"]
            .strftime(
                "%Y/%m/%d %H:%M"
            )
        )


    # --------------------------------------------------------
    # これから24時間
    # --------------------------------------------------------

    end_time = (
        now + timedelta(hours=24)
    )

    forecasts = [

        item

        for item in all_forecasts

        if (
            now
            - timedelta(minutes=30)
            <= item["dt"]
            <= end_time
        )

    ]


    # 同一時間帯の重複削除

    unique = []

    seen = set()

    for item in forecasts:

        key = item["dt"].strftime(
            "%Y%m%d%H"
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(item)

    forecasts = unique[:24]


    # --------------------------------------------------------
    # 各時間の表示情報
    # --------------------------------------------------------

    for item in forecasts:

        item["display_weather"] = (
            weather_display(item)
        )
        item["situation"] = (
            situation_display(item)
        )

        item["health_level"] = (
            health_attention_level(
                item
            )
        )

        item["travel_level"] = (
            travel_level(item)
        )

        item["fog_visibility_level"] = (
            fog_visibility_level(item)
        )

        item["travel_reason"] = (
            travel_reason(item)
        )


    # --------------------------------------------------------
    # 気圧
    # --------------------------------------------------------

    pressure_trend_text = (
        pressure_trend(
            all_forecasts
        )
    )

    pressure_level_text = (
        pressure_level(
            home_surface_pressure
        )
    )


    # --------------------------------------------------------
    # 現在の気象状況
    # --------------------------------------------------------

    (
        weather_status,
        weather_status_sub
    ) = current_weather_status(
        amedas
    )


    # --------------------------------------------------------
    # 体調注意
    # --------------------------------------------------------

    health_attention = (
        health_attention_text(
            forecasts
        )
    )

    travel_health_attention = (
        travel_health_attention_text(
            forecasts
        )
    )

    fog_visibility_attention = (
        fog_visibility_attention_text(
            forecasts
        )
    )


    # --------------------------------------------------------
    # 麓への移動
    # --------------------------------------------------------

    travel_window = (
        best_travel_window(
            forecasts
        )
    )


    travel_danger_items = [

        item

        for item in forecasts

        if item["travel_level"]
        == "danger"

    ]


    travel_danger_start = None
    travel_danger_end = None


    if travel_danger_items:

        travel_danger_start = (
            travel_danger_items[0]["dt"]
            .strftime("%H:%M")
        )

        travel_danger_end = (
            travel_danger_items[-1]["dt"]
            .strftime("%H:%M")
        )


    # --------------------------------------------------------
    # グラフ用データ
    # --------------------------------------------------------

    chart_labels = [

        item["dt"].strftime(
            "%H:%M"
        )

        for item in forecasts

    ]


    chart_temperatures = [

        item["temperature"]

        for item in forecasts

    ]


    chart_icons = [

        item["icon"]

        for item in forecasts

    ]


    chart_precipitation = [

        item["precipitation"]

        for item in forecasts

    ]


    chart_pressures = [

        item["surface_pressure"]

        for item in forecasts

    ]


    pressure_levels = [

        item["pressure_level"]

        for item in forecasts

    ]


    pressure_changes = [

        item["pressure_change"]

        for item in forecasts

    ]

# =========================================================
# 🐕 いよかん生活ガイド
# =========================================================

def dog_aircon_level(temp, humidity):
    """犬基準のエアコン判定"""

    if temp is None:
        return "unknown"

    # 25℃以下は基本的にエアコン不要
    if temp <= 25:
        if humidity is not None and humidity >= 90:
            return "attention"
        return "off"

    if temp <= 27:
        return "watch"

    if temp <= 29:
        return "recommended"

    return "strong"


def dog_walk_level(temp, rain, wind, humidity=None):
    """犬基準の散歩判定"""

    if temp is None:
        return "attention"

    # 雨
    if rain is not None and rain >= 5:
        return "danger"

    # 強い風
    if wind is not None and wind >= 10:
        return "danger"

    # 暑さ
    if temp >= 30:
        return "danger"

    if temp >= 27:
        return "attention"

    if humidity is not None and humidity >= 90 and temp >= 25:
        return "attention"

    if rain is not None and rain > 0:
        return "attention"

    return "good"


def dog_asphalt_level(temp, rain, cloud=None):
    """アスファルトの注意度"""

    if temp is None:
        return "attention"

    # 雨で路面が濡れている場合
    if rain is not None and rain > 0:
        return "good"

    # 暑い時間帯
    if temp >= 30:
        return "danger"

    if temp >= 27:
        return "attention"

    return "good"


dog_guidance = []

for item in forecasts:

    temp = item.get("temperature")
    rain = item.get("precipitation", 0)
    humidity = item.get("humidity")
    wind = item.get("wind_speed")

    walk = dog_walk_level(
        temp,
        rain,
        wind,
        humidity
    )

    asphalt = dog_asphalt_level(
        temp,
        rain
    )

    aircon = dog_aircon_level(
        temp,
        humidity
    )

    dog_guidance.append({
        "time": item["dt"].strftime("%H:%M"),
        "temperature": temp,
        "walk": walk,
        "asphalt": asphalt,
        "aircon": aircon
    })


# 散歩おすすめ時間
good_walk_times = [
    item["time"]
    for item in dog_guidance
    if item["walk"] == "good"
]

# アスファルトNG時間
asphalt_ng_times = [
    item["time"]
    for item in dog_guidance
    if item["asphalt"] == "danger"
]
# エアコン推奨時間
aircon_times = [
    item["time"]
    for item in dog_guidance
    if item["aircon"] in ("recommended", "strong")
]

# --------------------------------------------------------
# JSON
# --------------------------------------------------------

chart_labels_json = json.dumps(
    chart_labels,
    ensure_ascii=False
)

chart_temperatures_json = json.dumps(
    chart_temperatures,
    ensure_ascii=False
)

chart_icons_json = json.dumps(
    chart_icons,
    ensure_ascii=False
)

chart_precipitation_json = json.dumps(
    chart_precipitation,
    ensure_ascii=False
)

chart_pressures_json = json.dumps(
    chart_pressures,
    ensure_ascii=False
)

pressure_levels_json = json.dumps(
    pressure_levels,
    ensure_ascii=False
)

pressure_changes_json = json.dumps(
    pressure_changes,
    ensure_ascii=False
)
# ============================================================
# Render / Gunicorn
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )

    )