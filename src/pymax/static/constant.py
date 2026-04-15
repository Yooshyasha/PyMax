from random import choice, randint
from re import Pattern, compile
from typing import Final

import ua_generator
from pymax.utils import MixinsUtils
from websockets.typing import Origin

ANDROID_DEVICES: Final[list[dict[str, str]]] = [
    {"model": "SM-S928B", "name": "Samsung Galaxy S24 Ultra", "screen": "1440x3120 3.0x"},
    {"model": "SM-S921B", "name": "Samsung Galaxy S24", "screen": "1080x2340 2.625x"},
    {"model": "SM-S916B", "name": "Samsung Galaxy S23+", "screen": "1080x2340 2.625x"},
    {"model": "SM-S911B", "name": "Samsung Galaxy S23", "screen": "1080x2340 2.625x"},
    {"model": "SM-A556B", "name": "Samsung Galaxy A55", "screen": "1080x2340 2.625x"},
    {"model": "SM-A546B", "name": "Samsung Galaxy A54", "screen": "1080x2340 2.625x"},
    {"model": "SM-A356B", "name": "Samsung Galaxy A35", "screen": "1080x2340 2.625x"},
    {"model": "Pixel 9 Pro", "name": "Google Pixel 9 Pro", "screen": "1280x2856 2.75x"},
    {"model": "Pixel 9", "name": "Google Pixel 9", "screen": "1080x2424 2.75x"},
    {"model": "Pixel 8 Pro", "name": "Google Pixel 8 Pro", "screen": "1344x2992 2.75x"},
    {"model": "Pixel 8", "name": "Google Pixel 8", "screen": "1080x2400 2.75x"},
    {"model": "Pixel 8a", "name": "Google Pixel 8a", "screen": "1080x2400 2.75x"},
    {"model": "Pixel 7a", "name": "Google Pixel 7a", "screen": "1080x2400 2.75x"},
    {"model": "24053PY09G", "name": "Xiaomi 14T Pro", "screen": "1220x2712 2.75x"},
    {"model": "23127PN0CG", "name": "Xiaomi 14", "screen": "1200x2670 2.75x"},
    {"model": "22101316G", "name": "Xiaomi 13", "screen": "1080x2400 2.75x"},
    {"model": "2201116SG", "name": "Xiaomi 12 Pro", "screen": "1440x3200 3.0x"},
    {"model": "23078RKD5C", "name": "Redmi Note 13 Pro+", "screen": "1080x2400 2.75x"},
    {"model": "23076RN4BI", "name": "Redmi Note 13 Pro", "screen": "1080x2400 2.75x"},
    {"model": "220733SG", "name": "POCO F4 GT", "screen": "1080x2400 2.75x"},
    {"model": "CPH2581", "name": "OnePlus 12R", "screen": "1264x2772 3.0x"},
    {"model": "CPH2551", "name": "OnePlus 12", "screen": "1440x3168 3.0x"},
    {"model": "NE2215", "name": "OnePlus 10 Pro", "screen": "1440x3216 3.0x"},
    {"model": "RMX3835", "name": "realme GT 5 Pro", "screen": "1264x2780 3.0x"},
    {"model": "V2309", "name": "vivo X100 Pro", "screen": "1260x2800 3.0x"},
    {"model": "LE2127", "name": "OnePlus 9 Pro", "screen": "1440x3216 3.0x"},
    {"model": "M2101K6G", "name": "Redmi Note 10 Pro", "screen": "1080x2400 2.75x"},
    {"model": "220333QAG", "name": "POCO X4 Pro", "screen": "1080x2400 2.75x"},
]

ANDROID_OS_VERSIONS: Final[list[int]] = [12, 13, 14, 15]

ANDROID_BUILD_TAGS: Final[list[str]] = [
    "SP1A.210812.016", "TP1A.220624.014", "TQ3A.230901.001",
    "UP1A.231005.007", "AP3A.241005.015", "BP1A.250305.019",
]

CHROME_MOBILE_VERSIONS: Final[list[str]] = [
    "120.0.6099.230", "121.0.6167.180", "122.0.6261.119",
    "123.0.6312.118", "124.0.6367.113", "125.0.6422.165",
    "126.0.6478.122", "127.0.6533.103", "128.0.6613.88",
    "129.0.6668.70", "130.0.6723.58",
]

DESKTOP_OS_POOL: Final[list[dict[str, str]]] = [
    {"os_version": "Windows 10", "device_name": "Windows"},
    {"os_version": "Windows 11", "device_name": "Windows"},
    {"os_version": "macOS Sonoma", "device_name": "macOS"},
    {"os_version": "macOS Ventura", "device_name": "macOS"},
    {"os_version": "macOS Monterey", "device_name": "macOS"},
    {"os_version": "macOS Sequoia", "device_name": "macOS"},
    {"os_version": "Ubuntu 22.04", "device_name": "Linux"},
    {"os_version": "Ubuntu 24.04", "device_name": "Linux"},
    {"os_version": "Fedora 39", "device_name": "Linux"},
    {"os_version": "Fedora 40", "device_name": "Linux"},
    {"os_version": "Arch Linux", "device_name": "Linux"},
]

DESKTOP_SCREENS: Final[list[str]] = [
    "1920x1080 1.0x",
    "1366x768 1.0x",
    "1440x900 1.0x",
    "1536x864 1.0x",
    "1600x900 1.0x",
    "1680x1050 1.0x",
    "2560x1440 1.0x",
    "2560x1440 1.25x",
    "3840x2160 1.5x",
    "3840x2160 2.0x",
    "2560x1600 2.0x",
    "1920x1200 1.0x",
]

WEB_BROWSERS: Final[list[str]] = [
    "Chrome", "Firefox", "Edge", "Safari", "Opera",
    "Vivaldi", "Brave", "Chromium",
]

TIMEZONES: Final[list[str]] = [
    "Europe/Moscow",
    "Europe/Kaliningrad",
    "Europe/Samara",
    "Asia/Yekaterinburg",
    "Asia/Omsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok",
    "Asia/Kamchatka",
]

PHONE_REGEX: Final[Pattern[str]] = compile(r"^\+?\d{10,15}$")
WEBSOCKET_URI: Final[str] = "wss://ws-api.oneme.ru/websocket"
SESSION_STORAGE_DB = "session.db"
WEBSOCKET_ORIGIN: Final[Origin] = Origin("https://web.max.ru")
HOST: Final[str] = "api.oneme.ru"
PORT: Final[int] = 443
DEFAULT_TIMEOUT: Final[float] = 20.0
DEFAULT_DEVICE_TYPE: Final[str] = "DESKTOP"
DEFAULT_LOCALE: Final[str] = "ru"
DEFAULT_DEVICE_LOCALE: Final[str] = "ru"
DEFAULT_APP_VERSION: Final[str] = "26.3.0"
DEFAULT_BUILD_NUMBER: Final[int] = 6498
DEFAULT_CLIENT_SESSION_ID: Final[int] = randint(1, 15)

DEFAULT_DEVICE_NAME: Final[str] = choice(WEB_BROWSERS)
DEFAULT_SCREEN: Final[str] = choice(DESKTOP_SCREENS)
DEFAULT_OS_VERSION: Final[str] = choice(
    [entry["os_version"] for entry in DESKTOP_OS_POOL]
)
DEFAULT_USER_AGENT: Final[str] = ua_generator.generate(
    device="desktop", browser=("chrome", "firefox", "edge"),
).text
DEFAULT_TIMEZONE: Final[str] = choice(TIMEZONES)
DEFAULT_CHAT_MEMBERS_LIMIT: Final[int] = 50
DEFAULT_MARKER_VALUE: Final[int] = 0
DEFAULT_PING_INTERVAL: Final[float] = 30.0
RECV_LOOP_BACKOFF_DELAY: Final[float] = 0.5


class _Unset:
    pass


UNSET = _Unset()

first_names = [
    "Алексей", "Мария", "Иван", "Екатерина", "Дмитрий",
    "Ольга", "Сергей", "Анна", "Никита", "Татьяна"
]

last_names = [
    "Иванов", "Петрова", "Смирнов", "Кузнецова", "Попов",
    "Васильева", "Михайлов", "Федорова", "Соколов", "Морозова"
]
