#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🛰️ AIS Global Tracker v16.1 — Ultimate Edition
👻 Powered by Cyber Ghost
📢 https://t.me/cyber_ghost_error_404_chanel
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
import signal as _sig
import socket
import sqlite3
import sys
import threading
import time
import urllib.request as ur
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import websockets


if not AISSTREAM_API_KEY:
    log("⚠️ AISSTREAM_API_KEY تنظیم نشده — فقط داده Synthetic نمایش داده می‌شود")
if not DATADOCKED_API_KEY:
    log("⚠️ DATADOCKED_API_KEY تنظیم نشده — DataDocked غیرفعال است")

# ═══════════════════════════════════════════════════════════════
#  🎨 Branding
# ═══════════════════════════════════════════════════════════════
CREATOR_NAME    = "Cyber Ghost"
CREATOR_ID      = "https://t.me/Cyber_Ghost_error_404"
CREATOR_CHANNEL = "https://t.me/cyber_ghost_error_404_chanel"
VERSION         = "v16.1"

# ═══════════════════════════════════════════════════════════════
#  🔑 API Keys
# ═══════════════════════════════════════════════════════════════
AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()
DATADOCKED_API_KEY = os.environ.get("DATADOCKED_API_KEY", "").strip()

# ═══════════════════════════════════════════════════════════════
#  🌐 Host / Port
# ═══════════════════════════════════════════════════════════════
HOST = os.environ.get("AIS_HOST", "0.0.0.0")
PORT = int(os.environ.get("AIS_PORT", "7999"))

# ═══════════════════════════════════════════════════════════════
#  📁 Data Directory
# ═══════════════════════════════════════════════════════════════
def _resolve_data_dir() -> Path:
    env_dir = os.environ.get("AIS_DATA_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    try:
        script_dir = Path(__file__).resolve().parent
        p = script_dir / "AIS_Data"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        p = Path.home() / "AIS_Data"
        p.mkdir(parents=True, exist_ok=True)
        return p


DATA_DIR: Path = _resolve_data_dir()
DB_PATH: Path = DATA_DIR / "ais_history.db"
LOG_PATH: Path = DATA_DIR / "ais_tracker.log"

# ═══════════════════════════════════════════════════════════════
#  📝 Logging
# ═══════════════════════════════════════════════════════════════
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log_obj = logging.getLogger("AIS")

def log(msg: str):
    log_obj.info(msg)
    try:
        print(msg, flush=True)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
#  📡 LAN IP
# ═══════════════════════════════════════════════════════════════
def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

# ═══════════════════════════════════════════════════════════════
#  🌍 AISStream — یک اتصال واحد با پوشش جهانی
# ═══════════════════════════════════════════════════════════════
# ✅ راه‌حل اصلی HTTP 429: فقط یک اتصال با bounding box بزرگ
GLOBAL_BOUNDING_BOXES = [
    [[-90.0, -180.0], [90.0, 180.0]],   # کل کره زمین
]

TRAIL_MAX        = 300
STALE_SECONDS    = 1800
PURGE_INTERVAL   = 60
MAX_VESSELS      = 200_000
BROADCAST_EVERY  = 1.0

# ═══════════════════════════════════════════════════════════════
#  🕌 Hormuz Polygon
# ═══════════════════════════════════════════════════════════════
HORMUZ_POLYGON = [
    [27.30, 55.80], [27.10, 56.30], [26.80, 56.90], [26.50, 57.30],
    [26.20, 57.50], [25.80, 57.20], [25.60, 56.80], [25.40, 56.40],
    [25.50, 56.00], [26.00, 55.50], [26.60, 55.20],
]

def point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((xi > lon) != (xj > lon)) and \
           (lat < (yj - yi) * (lon - xi) / (xj - xi + 1e-12) + yi):
            inside = not inside
        j = i
    return inside

# ═══════════════════════════════════════════════════════════════
#  🚨 Alerts
# ═══════════════════════════════════════════════════════════════
alerts: deque = deque(maxlen=500)
alerts_lock = threading.Lock()
alerted_mmsi: set = set()
alerted_lock = threading.Lock()


def check_hormuz_alert(mmsi: str, name: str, lat: float, lon: float,
                       course: Optional[float], speed: Optional[float],
                       country: str) -> Optional[dict]:
    if lat is None or lon is None:
        return None
    in_zone = point_in_polygon(lat, lon, HORMUZ_POLYGON)
    with alerted_lock:
        already = mmsi in alerted_mmsi
        if in_zone and not already:
            alerted_mmsi.add(mmsi)
            direction = (
                "🇮🇷 ورود به خلیج فارس" if course and 180 <= course <= 360
                else "🌊 خروج به دریای عمان" if course
                else "❓ نامشخص"
            )
            alert = {
                "id": f"{mmsi}_{int(time.time())}",
                "mmsi": mmsi,
                "name": name or "نامشخص",
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "course": course,
                "speed": speed,
                "country": country or "",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": time.time(),
                "direction": direction,
            }
            with alerts_lock:
                alerts.appendleft(alert)
            return alert
        if not in_zone and already:
            alerted_mmsi.discard(mmsi)
    return None

# ═══════════════════════════════════════════════════════════════
#  🌍 MID Country table
# ═══════════════════════════════════════════════════════════════
MID_COUNTRY = {
    201: ("آلبانی", "AL"), 202: ("آندورا", "AD"), 203: ("اتریش", "AT"),
    205: ("بلژیک", "BE"), 206: ("بلاروس", "BY"), 207: ("بلغارستان", "BG"),
    209: ("قبرس", "CY"), 210: ("قبرس", "CY"), 211: ("آلمان", "DE"),
    213: ("گرجستان", "GE"), 214: ("مولداوی", "MD"), 215: ("مالت", "MT"),
    216: ("ارمنستان", "AM"), 218: ("آلمان", "DE"), 219: ("دانمارک", "DK"),
    224: ("اسپانیا", "ES"), 225: ("اسپانیا", "ES"), 226: ("فرانسه", "FR"),
    227: ("فرانسه", "FR"), 228: ("فرانسه", "FR"), 229: ("مالت", "MT"),
    230: ("فنلاند", "FI"), 231: ("جزایر فارو", "FO"), 232: ("انگلستان", "GB"),
    233: ("انگلستان", "GB"), 234: ("انگلستان", "GB"), 235: ("انگلستان", "GB"),
    236: ("جبل‌طارق", "GI"), 237: ("یونان", "GR"), 238: ("کرواسی", "HR"),
    239: ("یونان", "GR"), 240: ("یونان", "GR"), 241: ("یونان", "GR"),
    242: ("مراکش", "MA"), 243: ("مجارستان", "HU"), 244: ("هلند", "NL"),
    245: ("هلند", "NL"), 246: ("هلند", "NL"), 247: ("ایتالیا", "IT"),
    248: ("مالت", "MT"), 249: ("مالت", "MT"), 250: ("ایرلند", "IE"),
    251: ("ایسلند", "IS"), 253: ("لوکزامبورگ", "LU"), 255: ("مادیرا", "PT"),
    257: ("نروژ", "NO"), 258: ("نروژ", "NO"), 259: ("نروژ", "NO"),
    261: ("لهستان", "PL"), 262: ("مونته‌نگرو", "ME"), 263: ("پرتغال", "PT"),
    264: ("رومانی", "RO"), 265: ("سوئد", "SE"), 266: ("سوئد", "SE"),
    267: ("اسلواکی", "SK"), 269: ("سوئیس", "CH"), 270: ("چک", "CZ"),
    271: ("ترکیه", "TR"), 272: ("اوکراین", "UA"), 273: ("روسیه", "RU"),
    274: ("مقدونیه", "MK"), 275: ("لتونی", "LV"), 276: ("استونی", "EE"),
    277: ("لیتوانی", "LT"), 278: ("اسلوونی", "SI"), 279: ("صربستان", "RS"),
    301: ("آنگویلا", "AI"), 303: ("آلاسکا", "US"), 304: ("آنتیگوا", "AG"),
    305: ("آنتیگوا", "AG"), 306: ("کوراسائو", "CW"), 307: ("آروبا", "AW"),
    308: ("باهاما", "BS"), 309: ("باهاما", "BS"), 310: ("برمودا", "BM"),
    311: ("باهاما", "BS"), 312: ("بلیز", "BZ"), 314: ("باربادوس", "BB"),
    316: ("کانادا", "CA"), 319: ("جزایر کیمن", "KY"), 321: ("کاستاریکا", "CR"),
    323: ("کوبا", "CU"), 325: ("دومینیکا", "DM"), 327: ("دومینیکن", "DO"),
    330: ("گرنادا", "GD"), 331: ("گرینلند", "GL"), 332: ("گواتمالا", "GT"),
    334: ("هندوراس", "HN"), 336: ("هائیتی", "HT"), 338: ("آمریکا", "US"),
    339: ("جامائیکا", "JM"), 345: ("مکزیک", "MX"), 350: ("نیکاراگوئه", "NI"),
    351: ("پاناما", "PA"), 352: ("پاناما", "PA"), 353: ("پاناما", "PA"),
    354: ("پاناما", "PA"), 355: ("پاناما", "PA"), 356: ("پاناما", "PA"),
    357: ("پاناما", "PA"), 358: ("پورتوریکو", "PR"), 359: ("السالوادور", "SV"),
    361: ("سنت پیر", "PM"), 362: ("ترینیداد", "TT"), 364: ("ترکس", "TC"),
    366: ("آمریکا", "US"), 367: ("آمریکا", "US"), 368: ("آمریکا", "US"),
    369: ("آمریکا", "US"), 370: ("پاناما", "PA"), 371: ("پاناما", "PA"),
    372: ("پاناما", "PA"), 373: ("پاناما", "PA"), 374: ("پاناما", "PA"),
    375: ("سنت وینسنت", "VC"), 376: ("سنت وینسنت", "VC"), 377: ("سنت وینسنت", "VC"),
    378: ("جزایر ویرجین", "VG"), 379: ("جزایر ویرجین آمریکا", "VI"),
    401: ("افغانستان", "AF"), 403: ("عربستان", "SA"), 405: ("بنگلادش", "BD"),
    408: ("بحرین", "BH"), 410: ("بوتان", "BT"), 412: ("چین", "CN"),
    413: ("چین", "CN"), 414: ("چین", "CN"), 416: ("تایوان", "TW"),
    417: ("سریلانکا", "LK"), 419: ("هند", "IN"), 422: ("ایران 🇮🇷", "IR"),
    423: ("آذربایجان", "AZ"), 425: ("عراق", "IQ"), 428: ("اسرائیل", "IL"),
    431: ("ژاپن", "JP"), 432: ("ژاپن", "JP"), 434: ("ترکمنستان", "TM"),
    436: ("قزاقستان", "KZ"), 437: ("ازبکستان", "UZ"), 438: ("اردن", "JO"),
    440: ("کره جنوبی", "KR"), 441: ("کره جنوبی", "KR"), 443: ("فلسطین", "PS"),
    445: ("کره شمالی", "KP"), 447: ("کویت", "KW"), 450: ("لبنان", "LB"),
    451: ("قرقیزستان", "KG"), 453: ("ماکائو", "MO"), 455: ("مالدیو", "MV"),
    457: ("مغولستان", "MN"), 459: ("نپال", "NP"), 461: ("عمان", "OM"),
    463: ("پاکستان", "PK"), 466: ("قطر", "QA"), 468: ("سوریه", "SY"),
    470: ("امارات", "AE"), 472: ("تاجیکستان", "TJ"), 473: ("یمن", "YE"),
    475: ("یمن", "YE"), 477: ("هنگ‌کنگ", "HK"), 478: ("بوسنی", "BA"),
    501: ("سرزمین آدلی", "AQ"), 503: ("استرالیا", "AU"), 506: ("میانمار", "MM"),
    508: ("برونئی", "BN"), 510: ("میکرونزی", "FM"), 511: ("پالائو", "PW"),
    512: ("نیوزیلند", "NZ"), 514: ("کامبوج", "KH"), 515: ("کامبوج", "KH"),
    518: ("جزایر کوک", "CK"), 520: ("فیجی", "FJ"), 525: ("اندونزی", "ID"),
    529: ("کیریباتی", "KI"), 531: ("لائوس", "LA"), 533: ("مالزی", "MY"),
    538: ("جزایر مارشال", "MH"), 540: ("کالدونیای جدید", "NC"),
    542: ("نیوئه", "NU"), 544: ("نائورو", "NR"), 546: ("پلی‌نزی فرانسه", "PF"),
    548: ("فیلیپین", "PH"), 553: ("پاپوآ گینه نو", "PG"), 557: ("جزایر سلیمان", "SB"),
    559: ("ساموآی آمریکا", "AS"), 561: ("ساموآ", "WS"), 563: ("سنگاپور", "SG"),
    564: ("سنگاپور", "SG"), 565: ("سنگاپور", "SG"), 566: ("سنگاپور", "SG"),
    567: ("تایلند", "TH"), 570: ("تونگا", "TO"), 572: ("تووالو", "TV"),
    574: ("ویتنام", "VN"), 576: ("وانواتو", "VU"), 577: ("وانواتو", "VU"),
    578: ("والیس", "WF"), 601: ("آفریقای جنوبی", "ZA"), 603: ("آنگولا", "AO"),
    605: ("الجزایر", "DZ"), 607: ("سنت پاول", "TF"), 608: ("آسنسیون", "SH"),
    609: ("بوروندی", "BI"), 610: ("بنین", "BJ"), 611: ("بوتسوانا", "BW"),
    612: ("آفریقای مرکزی", "CF"), 613: ("کامرون", "CM"), 615: ("کنگو", "CG"),
    616: ("کومور", "KM"), 617: ("کیپ ورد", "CV"), 618: ("کروزه", "TF"),
    619: ("ساحل عاج", "CI"), 620: ("کومور", "KM"), 621: ("جیبوتی", "DJ"),
    622: ("مصر", "EG"), 624: ("اتیوپی", "ET"), 625: ("اریتره", "ER"),
    626: ("گابن", "GA"), 627: ("غنا", "GH"), 629: ("گامبیا", "GM"),
    630: ("گینه بیسائو", "GW"), 631: ("گینه استوایی", "GQ"), 632: ("گینه", "GN"),
    633: ("بورکینافاسو", "BF"), 634: ("کنیا", "KE"), 635: ("کرگولن", "TF"),
    636: ("لیبریا", "LR"), 637: ("لیبریا", "LR"), 638: ("سودان جنوبی", "SS"),
    642: ("لیبی", "LY"), 644: ("لسوتو", "LS"), 645: ("موریس", "MU"),
    647: ("ماداگاسکار", "MG"), 649: ("مالی", "ML"), 650: ("موزامبیک", "MZ"),
    654: ("موریتانی", "MR"), 655: ("مالاوی", "MW"), 656: ("نیجر", "NE"),
    657: ("نیجریه", "NG"), 659: ("نامیبیا", "NA"), 660: ("رئونیون", "RE"),
    661: ("رواندا", "RW"), 662: ("سودان", "SD"), 663: ("سنگال", "SN"),
    664: ("سیشل", "SC"), 665: ("سنت هلنا", "SH"), 666: ("سومالی", "SO"),
    667: ("سیرالئون", "SL"), 668: ("سائوتومه", "ST"), 669: ("اسواتینی", "SZ"),
    670: ("چاد", "TD"), 671: ("توگو", "TG"), 672: ("تونس", "TN"),
    674: ("تانزانیا", "TZ"), 675: ("اوگاندا", "UG"), 676: ("کنگو دموکراتیک", "CD"),
    677: ("تانزانیا", "TZ"), 678: ("زامبیا", "ZM"), 679: ("زیمبابوه", "ZW"),
    701: ("آرژانتین", "AR"), 710: ("برزیل", "BR"), 720: ("بولیوی", "BO"),
    725: ("شیلی", "CL"), 730: ("کلمبیا", "CO"), 735: ("اکوادور", "EC"),
    740: ("فالکلند", "FK"), 745: ("گویان فرانسه", "GF"), 750: ("گویان", "GY"),
    755: ("پاراگوئه", "PY"), 760: ("پرو", "PE"), 765: ("سورینام", "SR"),
    770: ("اروگوئه", "UY"), 775: ("ونزوئلا", "VE"),
}


def mid_to_country(mmsi: str) -> tuple:
    if not mmsi or len(mmsi) < 3:
        return ("نامشخص", "")
    if mmsi.startswith("970"):
        return ("SAR Transponder", "")
    if mmsi.startswith("972"):
        return ("MOB Device", "")
    if mmsi.startswith("974"):
        return ("EPIRB", "")
    try:
        return MID_COUNTRY.get(int(mmsi[:3]), ("نامشخص", ""))
    except Exception:
        return ("نامشخص", "")


SHIP_TYPES = {
    0: "نامشخص", 20: "Wing-in-Ground", 29: "هواپیمای SAR",
    30: "ماهیگیری 🎣", 31: "یدک‌کش ⚓", 32: "یدک‌کش بزرگ ⚓",
    33: "لایروبی 🚧", 34: "پشتیبانی غواصی 🤿", 35: "نظامی 🎖️",
    36: "بادبانی ⛵", 37: "قایق تفریحی 🛥️", 40: "شناور تندرو 🚤",
    50: "قایق راهنما 🧭", 51: "جستجو و نجات 🚁", 52: "یدک‌کش ⚓",
    53: "قایق بندری 🛶", 54: "ضد آلودگی ♻️", 55: "مجری قانون 🚔",
    58: "حمل پزشکی 🚑", 60: "مسافربری 🛳️", 70: "باربری 📦",
    80: "نفتکش 🛢️", 90: "سایر",
}
NAV_STATUS = {
    0: "🟢 در حال حرکت", 1: "🟡 لنگر انداخته", 2: "🔴 غیرقابل کنترل",
    3: "🟠 مانور محدود", 4: "🟠 محدودیت آبخور", 5: "🔵 پهلو گرفته",
    6: "🟣 به گل نشسته", 7: "🎣 مشغول ماهیگیری", 8: "⛵ در حال بادبانی",
    11: "⚡ در حال یدک‌کشی", 12: "🟢 پهلوگیری", 14: "🚨 SAR",
    15: "⚫ نامشخص",
}
TYPE_CATEGORIES = {
    "cargo": list(range(70, 80)),
    "tanker": list(range(80, 90)),
    "passenger": list(range(60, 70)),
    "tug": [31, 32, 52],
    "fishing": [30],
    "military": [35],
    "pleasure": [36, 37],
    "high_speed": [40],
    "law": [55],
    "sar": [51],
}
CATEGORY_ICONS = {
    "cargo": "📦", "tanker": "🛢️", "passenger": "🛳️", "tug": "⚓",
    "fishing": "🎣", "military": "🎖️", "pleasure": "🛥️",
    "high_speed": "🚤", "law": "🚔", "sar": "🚁", "other": "🚢",
}


def get_category(tc: Optional[int]) -> str:
    if not tc:
        return "other"
    for cat, codes in TYPE_CATEGORIES.items():
        if tc in codes:
            return cat
    return "other"

# ═══════════════════════════════════════════════════════════════
#  🗂 State
# ═══════════════════════════════════════════════════════════════
vessels: Dict[str, dict] = {}
vessels_lock = threading.RLock()
report_count = 0
report_lock = threading.Lock()
vessel_order_counter = 0
order_lock = threading.Lock()

ws_clients: set = set()
ws_lock = threading.RLock()

db_queue: deque = deque()
db_queue_lock = threading.Lock()

pending_updates: Dict[str, dict] = {}
pending_lock = threading.Lock()

new_ships_buffer: deque = deque(maxlen=500)
new_ships_lock = threading.Lock()

# Per-source status
source_status: Dict[str, dict] = {
    "aisstream":  {"state": "idle", "reports": 0, "last": None, "error": None},
    "datadocked": {"state": "idle", "reports": 0, "last": None, "error": None},
    "synthetic":  {"state": "idle", "reports": 0, "last": None, "error": None},
}
source_status_lock = threading.Lock()

_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None


def next_order() -> int:
    global vessel_order_counter
    with order_lock:
        vessel_order_counter += 1
        return vessel_order_counter


def set_source_state(name: str, state: str, error: Optional[str] = None):
    with source_status_lock:
        if name in source_status:
            source_status[name]["state"] = state
            source_status[name]["last"] = time.time()
            if error is not None:
                source_status[name]["error"] = error

# ═══════════════════════════════════════════════════════════════
#  🔄 Thread-safe Broadcast
# ═══════════════════════════════════════════════════════════════
def safe_broadcast(msg: dict):
    if _MAIN_LOOP is None or _MAIN_LOOP.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(broadcast(msg), _MAIN_LOOP)
    except Exception as e:
        log(f"⚠️ safe_broadcast: {e}")

# ═══════════════════════════════════════════════════════════════
#  🗄️ Database
# ═══════════════════════════════════════════════════════════════
_db_local = threading.local()


def _db_conn() -> sqlite3.Connection:
    c = getattr(_db_local, "conn", None)
    if c is None:
        c = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15.0)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=10000")
        _db_local.conn = c
    return c


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mmsi TEXT, name TEXT,
            lat REAL, lon REAL, speed REAL, course REAL, heading REAL,
            nav_status INTEGER, time_utc TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mmsi ON positions(mmsi);
        CREATE INDEX IF NOT EXISTS idx_time ON positions(created_at);
    """)
    conn.commit()
    conn.close()


def queue_position(mmsi, name, lat, lon, speed, course, heading, nav, t):
    with db_queue_lock:
        db_queue.append((mmsi, name, lat, lon, speed, course, heading, nav, t))


def flush_db_queue():
    with db_queue_lock:
        if not db_queue:
            return
        rows = list(db_queue)
        db_queue.clear()
    try:
        c = _db_conn()
        c.executemany(
            "INSERT INTO positions (mmsi,name,lat,lon,speed,course,heading,"
            "nav_status,time_utc) VALUES (?,?,?,?,?,?,?,?,?)", rows)
        c.commit()
    except Exception as e:
        log(f"⚠️ DB flush: {e}")


def get_history(mmsi: str, hours: int = 24) -> list:
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        c = _db_conn()
        rows = c.execute(
            "SELECT lat,lon,speed,course,time_utc FROM positions "
            "WHERE mmsi=? AND created_at > ? ORDER BY id ASC LIMIT 5000",
            (mmsi, since)).fetchall()
        return [{"lat": r[0], "lon": r[1], "speed": r[2],
                 "course": r[3], "time": r[4]} for r in rows]
    except Exception as e:
        log(f"⚠️ get_history: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
#  📥 Handlers
# ═══════════════════════════════════════════════════════════════
def safe_dict(v: dict) -> dict:
    return {k: val for k, val in v.items() if k != "trail" and not k.startswith("_")}


def queue_update(mmsi: str, snap: dict, mt: str, trail=None):
    with pending_lock:
        if mmsi not in pending_updates:
            pending_updates[mmsi] = {"mmsi": mmsi, "data": snap, "type": mt}
        else:
            pending_updates[mmsi]["data"].update(snap)
        if trail is not None:
            pending_updates[mmsi]["trail"] = trail


def handle_static(mmsi: str, data: dict, meta: dict):
    try:
        sd = data["Message"]["ShipStaticData"]
    except Exception:
        return
    eta = sd.get("Eta") or {}
    dim = sd.get("Dimension", {})
    country, iso = mid_to_country(mmsi)
    is_new = False
    name_snap = ""
    with vessels_lock:
        is_new = mmsi not in vessels
        if is_new:
            vessels[mmsi] = {
                "mmsi": mmsi, "trail": [], "order": next_order(),
                "country": country, "country_code": iso,
            }
        v = vessels[mmsi]
        v["name"] = sd.get("Name", "").strip() or v.get("name", "")
        v["imo"] = sd.get("ImoNumber")
        v["callsign"] = sd.get("CallSign", "").strip()
        v["type_code"] = sd.get("Type")
        v["type_name"] = SHIP_TYPES.get(sd.get("Type"), "نامشخص")
        v["category"] = get_category(sd.get("Type"))
        v["destination"] = sd.get("Destination", "").strip()
        if eta:
            v["eta"] = (f"{eta.get('Month','?')}/{eta.get('Day','?')} "
                        f"{eta.get('Hour','?')}:{eta.get('Minute','?')}")
        v["length"] = dim.get("A", 0) + dim.get("B", 0)
        v["width"] = dim.get("C", 0) + dim.get("D", 0)
        v["draught"] = sd.get("MaximumStaticDraught")
        v["last_seen"] = time.time()
        v["source"] = "aisstream"
        snap = safe_dict(v)
        name_snap = v.get("name", "")
    if is_new:
        with new_ships_lock:
            new_ships_buffer.append(
                f"📡 AISStream • {name_snap or 'نامشخص'} • {country} • MMSI: {mmsi}")
    queue_update(mmsi, snap, "static")


def handle_position(mmsi: str, data: dict, meta: dict):
    try:
        pr = data["Message"]["PositionReport"]
    except Exception:
        return
    lat = round(pr.get("Latitude", 0), 6)
    lon = round(pr.get("Longitude", 0), 6)
    speed = pr.get("Sog")
    course = pr.get("Cog")
    heading = pr.get("TrueHeading")
    nav = pr.get("NavigationalStatus", 15)
    country, iso = mid_to_country(mmsi)

    with vessels_lock:
        if mmsi not in vessels:
            vessels[mmsi] = {
                "mmsi": mmsi, "trail": [], "order": next_order(),
                "country": country, "country_code": iso,
            }
        v = vessels[mmsi]
        v.update({
            "lat": lat, "lon": lon, "speed": speed, "course": course,
            "heading": heading, "nav_status_code": nav,
            "nav_status": NAV_STATUS.get(nav, "⚫ نامشخص"),
            "time_utc": meta.get("time_utc", ""),
            "last_seen": time.time(),
            "country": country, "country_code": iso,
            "source": "aisstream",
        })
        if not v.get("name"):
            v["name"] = (meta.get("ShipName") or "").strip()
        if "category" not in v:
            v["category"] = "other"
        trail = v.setdefault("trail", [])
        if not trail or trail[-1] != [lat, lon]:
            trail.append([lat, lon])
            if len(trail) > TRAIL_MAX:
                del trail[:len(trail) - TRAIL_MAX]
        if speed and course and speed > 0.5:
            dkm = speed * 0.514444 * 900
            dlat = (dkm / 111.32) * math.cos(math.radians(course))
            dlon = (dkm / (111.32 * math.cos(math.radians(lat) + 1e-9))) * \
                   math.sin(math.radians(course))
            v["predicted"] = [round(lat + dlat, 6), round(lon + dlon, 6)]
        snap = safe_dict(v)
        trail_snap = list(trail)
        v_name = v.get("name")
        v_time = v.get("time_utc", "")

    alert = check_hormuz_alert(mmsi, v_name, lat, lon, course, speed, country)
    if alert:
        safe_broadcast({"type": "alert", "data": alert})

    with source_status_lock:
        source_status["aisstream"]["reports"] = source_status["aisstream"].get("reports", 0) + 1
        source_status["aisstream"]["last"] = time.time()

    queue_position(mmsi, v_name, lat, lon, speed, course, heading, nav, v_time)
    queue_update(mmsi, snap, "position", trail_snap)

# ═══════════════════════════════════════════════════════════════
#  🌐 AISStream Collector — تک اتصال جهانی
# ═══════════════════════════════════════════════════════════════
async def ais_collector():
    """یک اتصال واحد AISStream با پوشش جهانی — جلوگیری از 429"""
    global report_count
    if not AISSTREAM_API_KEY:
        log("⚠️ AISSTREAM_API_KEY تنظیم نشده")
        set_source_state("aisstream", "no-key")
        return

    uri = "wss://stream.aisstream.io/v0/stream"
    backoff = 10
    consecutive_429 = 0

    while True:
        try:
            set_source_state("aisstream", "connecting")
            log("🔌 اتصال AISStream (پوشش جهانی)...")
            async with websockets.connect(
                uri, compression="deflate",
                ping_interval=20, ping_timeout=20, close_timeout=5,
                max_size=2 ** 23, max_queue=2000, open_timeout=20,
            ) as ws:
                await ws.send(json.dumps({
                    "APIKey": AISSTREAM_API_KEY,
                    "BoundingBoxes": GLOBAL_BOUNDING_BOXES,
                    "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                }))
                log("✅ AISStream متصل شد")
                set_source_state("aisstream", "running", None)
                backoff = 10
                consecutive_429 = 0

                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    mt = data.get("MessageType")
                    if mt == "SubscriptionConfirmation":
                        continue
                    meta = data.get("MetaData", {})
                    mmsi = str(meta.get("MMSI", ""))
                    if not mmsi:
                        continue
                    if mt == "ShipStaticData":
                        handle_static(mmsi, data, meta)
                    elif mt == "PositionReport":
                        handle_position(mmsi, data, meta)
                        with report_lock:
                            report_count += 1

        except websockets.exceptions.InvalidStatus as e:
            status_code = getattr(e, "status_code", None) or \
                          getattr(getattr(e, "response", None), "status_code", 0)
            if status_code == 429:
                consecutive_429 += 1
                wait = min(60 * consecutive_429, 300)  # 60, 120, 180, 240, 300
                log(f"⏸️ AISStream rate-limited (429) — انتظار {wait}s "
                    f"(تلاش {consecutive_429})")
                set_source_state("aisstream", "rate-limited",
                                 f"HTTP 429 — انتظار {wait}s")
                await asyncio.sleep(wait)
            else:
                log(f"❌ AISStream HTTP {status_code} — {backoff}s")
                set_source_state("aisstream", "error", f"HTTP {status_code}")
                await asyncio.sleep(backoff)
                backoff = min(int(backoff * 1.6), 120)
        except websockets.exceptions.ConnectionClosed as e:
            log(f"⚡ AISStream قطع ({e.code}) — {backoff}s")
            set_source_state("aisstream", "reconnecting", f"code={e.code}")
            await asyncio.sleep(backoff)
            backoff = min(int(backoff * 1.5), 60)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log(f"❌ AISStream: {type(e).__name__}: {e} — {backoff}s")
            set_source_state("aisstream", "error", f"{type(e).__name__}: {e}")
            await asyncio.sleep(backoff)
            backoff = min(int(backoff * 1.6), 120)

# ═══════════════════════════════════════════════════════════════
#  🎭 SYNTHETIC FLEET — همیشه کشتی نشون میده
# ═══════════════════════════════════════════════════════════════
SYNTH_PREFIXES = [
    "EVER", "MSC", "MAERSK", "CMA CGM", "COSCO", "OOCL", "HMM", "ONE",
    "HYUNDAI", "NYK", "MOL", "K-LINE", "YANG MING", "HAPAG LLOYD",
    "PACIFIC", "ATLANTIC", "INDIAN", "ORIENT", "GLOBAL", "OCEAN",
    "SEA", "STAR", "GOLDEN", "SILVER", "DIAMOND", "ROYAL", "IMPERIAL",
    "FRONT", "NISSOS", "ADVANTAGE", "ARDMORE", "STENA", "MINERVA",
    "IRAN", "PERSIAN", "GULF", "ARABIAN", "RED SEA", "NILE", "SUEZ",
    "SIRIUS", "POLARIS", "VEGA", "RIGEL", "ORION", "ANDROMEDA", "NOVA",
    "AURORA", "COMET", "METEOR", "PHOENIX", "TITAN", "ATLAS", "HERA",
]
SYNTH_SUFFIXES = [
    "GIVEN", "OSCAR", "GULSUN", "IRINA", "ANTARES", "SIRIUS", "POLARIS",
    "TRIUMPH", "VICTORY", "GLORY", "SPIRIT", "HARMONY", "VOYAGER",
    "PIONEER", "EXPLORER", "DISCOVERY", "ODYSSEY", "JOURNEY", "LEGACY",
    "HORIZON", "MAJESTY", "SOVEREIGN", "EMPIRE", "KINGDOM", "DYNASTY",
    "ALTAIR", "RIGEL", "VEGA", "DENEB", "CASTOR", "POLLUX", "ARCTURUS",
    "CAPELLA", "ALDEBARAN", "REGULUS", "SPICA", "ANTARES", "BELLATRIX",
    "SENTINEL", "GUARDIAN", "PROTECTOR", "DEFENDER", "CHALLENGER",
]
SYNTH_DESTINATIONS = [
    "ROTTERDAM", "SINGAPORE", "SHANGHAI", "NINGBO", "BUSAN", "HONG KONG",
    "JEBEL ALI", "SHENZHEN", "GUANGZHOU", "QINGDAO", "TIANJIN",
    "PORT KLANG", "TANJUNG PELEPAS", "LAEM CHABANG", "HO CHI MINH",
    "LOS ANGELES", "LONG BEACH", "NEW YORK", "SAVANNAH", "HOUSTON",
    "HAMBURG", "ANTWERP", "BREMERHAVEN", "LE HAVRE", "FELIXSTOWE",
    "BANDAR ABBAS", "KHOR FAKKAN", "FUJAIRAH", "MUSCAT", "SALALAH",
    "DAMMAM", "JUBAIL", "KUWAIT", "BASRA", "UMM QASR", "ALEXANDRIA",
    "PIRAEUS", "VALENCIA", "BARCELONA", "GENOA", "ISTANBUL", "ODESSA",
    "SANTOS", "BUENOS AIRES", "MONTEVIDEO", "CALLAO", "VALPARAISO",
    "DURBAN", "CAPE TOWN", "LAGOS", "MOMBASA", "PORT SAID", "SUEZ",
]
SYNTH_CALLSIGNS_PREFIX = [
    "3E", "9V", "9H", "A8", "C6", "D5", "EL", "H3", "HO", "HP",
    "IB", "J8", "LA", "LX", "OD", "ON", "OU", "OW", "OY", "OZ",
    "P3", "S6", "T8", "TC", "V7", "VQ", "VR", "VU", "W8", "YB",
    "ZD", "ZP", "9M", "9N", "9W", "A4", "A7", "B7", "C4", "CQ",
]

# خطوط کشتیرانی اصلی جهان
SHIPPING_LANES = [
    # Persian Gulf → Hormuz → India
    [(30.0, 48.5), (29.5, 49.0), (28.5, 50.0), (27.5, 51.5), (27.0, 52.5),
     (26.5, 53.5), (26.3, 54.5), (26.5, 55.5), (26.3, 56.5), (25.5, 57.5),
     (24.0, 58.5), (22.0, 60.0), (20.0, 62.0), (18.0, 65.0), (15.0, 68.0),
     (12.0, 72.0), (9.0, 76.0), (7.0, 79.0), (6.5, 80.5)],
    # Suez → Red Sea → Aden
    [(31.3, 32.3), (30.0, 32.5), (28.0, 33.0), (26.0, 34.0), (24.0, 35.5),
     (22.0, 37.0), (20.0, 38.5), (18.0, 40.0), (16.0, 41.0), (14.0, 42.0),
     (12.5, 43.5), (12.0, 45.0), (11.5, 47.0), (11.0, 49.0), (10.5, 51.0)],
    # Gibraltar → Mediterranean → Suez
    [(36.0, -5.6), (36.5, -3.0), (37.0, 0.0), (37.5, 3.0), (38.0, 6.0),
     (37.8, 9.5), (37.5, 12.0), (36.5, 15.0), (35.5, 18.0), (34.5, 21.0),
     (33.5, 24.0), (32.5, 28.0), (31.5, 30.5), (31.3, 32.3)],
    # Malacca
    [(1.5, 103.5), (2.5, 102.0), (3.5, 100.5), (5.0, 99.5), (6.0, 98.0),
     (6.5, 96.0), (6.0, 94.5), (5.5, 93.0)],
    # English Channel
    [(50.0, 0.5), (50.5, -0.5), (50.3, -1.5), (50.0, -3.0), (49.5, -4.5),
     (49.0, -5.5), (48.5, -6.5)],
    # Panama
    [(9.5, -79.8), (9.0, -79.0), (8.5, -78.0), (8.0, -77.0), (7.0, -76.0)],
    # Atlantic Europe → NA
    [(51.0, 1.5), (51.5, -2.0), (51.0, -6.0), (50.0, -11.0), (48.0, -16.0),
     (46.0, -22.0), (44.0, -28.0), (42.0, -35.0), (40.5, -42.0), (40.0, -50.0)],
    # Trans-Pacific
    [(35.0, 140.0), (38.0, 155.0), (41.0, 170.0), (43.0, -175.0),
     (42.0, -160.0), (40.0, -145.0), (38.0, -130.0), (36.0, -122.0)],
    # Cape of Good Hope
    [(34.0, 18.5), (35.0, 20.0), (36.0, 23.0), (35.0, 27.0), (33.0, 30.0)],
    # Brazil
    [(-23.0, -43.5), (-25.0, -45.0), (-28.0, -47.0), (-32.0, -50.0),
     (-35.0, -53.0), (-37.0, -56.0)],
    # Australia → SE Asia
    [(-33.9, 151.2), (-32.0, 153.5), (-28.0, 154.0), (-22.0, 154.0),
     (-18.0, 152.5), (-14.0, 148.0), (-10.0, 142.0), (-7.0, 135.0),
     (-3.0, 128.0), (0.0, 120.0), (3.0, 115.0), (5.0, 110.0)],
]

SYNTH_MMSI_PREFIXES = [
    "366", "367", "368", "369", "232", "233", "234", "235",
    "244", "245", "246", "258", "259", "257", "211", "218",
    "226", "227", "228", "247", "248", "249", "224", "225",
    "271", "422", "403", "470", "447", "466", "461", "408",
    "412", "413", "414", "431", "432", "440", "441", "563",
    "564", "565", "566", "533", "503", "512", "710", "701",
]

SYNTH_TYPE_PROBS = [
    (70, 0.35), (80, 0.25), (60, 0.08), (31, 0.08),
    (30, 0.05), (35, 0.04), (37, 0.05), (40, 0.05),
    (55, 0.03), (51, 0.02),
]


def _gen_mmsi() -> str:
    return random.choice(SYNTH_MMSI_PREFIXES) + str(random.randint(100000, 999999))


def _gen_callsign() -> str:
    return random.choice(SYNTH_CALLSIGNS_PREFIX) + \
           "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=4))


def _gen_name() -> str:
    style = random.random()
    if style < 0.5:
        return f"{random.choice(SYNTH_PREFIXES)} {random.choice(SYNTH_SUFFIXES)}"
    elif style < 0.8:
        return f"{random.choice(SYNTH_PREFIXES)}{random.randint(1, 99)}"
    else:
        return f"{random.choice(SYNTH_PREFIXES)}-{random.choice(SYNTH_SUFFIXES)[:4]}"


def _pick_ship_type() -> int:
    r = random.random()
    cum = 0.0
    for tc, p in SYNTH_TYPE_PROBS:
        cum += p
        if r <= cum:
            return tc
    return 70


def _create_synthetic_vessel(force_hormuz: bool = False) -> dict:
    lane = random.choice(SHIPPING_LANES)
    if force_hormuz:
        lane = SHIPPING_LANES[0]
    t = random.random()
    idx = min(int(t * (len(lane) - 1)), len(lane) - 2)
    frac = t * (len(lane) - 1) - idx
    p1, p2 = lane[idx], lane[idx + 1]
    lat = p1[0] + (p2[0] - p1[0]) * frac + random.uniform(-0.05, 0.05)
    lon = p1[1] + (p2[1] - p1[1]) * frac + random.uniform(-0.05, 0.05)

    mmsi = _gen_mmsi()
    tc = _pick_ship_type()
    cat = get_category(tc)
    country, iso = mid_to_country(mmsi)

    dy = p2[0] - p1[0]
    dx = p2[1] - p1[1]
    course = (math.degrees(math.atan2(dx, dy))) % 360

    if cat == "tanker":
        speed = random.uniform(9, 14)
    elif cat == "cargo":
        speed = random.uniform(12, 22)
    elif cat == "passenger":
        speed = random.uniform(18, 25)
    elif cat == "tug":
        speed = random.uniform(5, 10)
    elif cat == "fishing":
        speed = random.uniform(2, 8)
    elif cat == "high_speed":
        speed = random.uniform(25, 40)
    elif cat == "military":
        speed = random.uniform(15, 30)
    else:
        speed = random.uniform(5, 18)

    return {
        "mmsi": mmsi,
        "name": _gen_name(),
        "callsign": _gen_callsign(),
        "imo": random.randint(9000000, 9999999),
        "type_code": tc,
        "type_name": SHIP_TYPES.get(tc, "نامشخص"),
        "category": cat,
        "country": country,
        "country_code": iso,
        "destination": random.choice(SYNTH_DESTINATIONS),
        "eta": f"{random.randint(1, 12)}/{random.randint(1, 28)} "
               f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}",
        "length": random.randint(80, 400),
        "width": random.randint(12, 60),
        "draught": round(random.uniform(5, 16), 1),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "speed": round(speed, 1),
        "course": round(course, 1),
        "heading": round(course, 1),
        "nav_status_code": 0,
        "nav_status": NAV_STATUS[0],
        "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": time.time(),
        "trail": [[round(lat, 6), round(lon, 6)]],
        "order": next_order(),
        "source": "synthetic",
        "_lane": lane,
        "_dir": 1,
        "_lane_progress": t,
    }


def _move_synthetic(v: dict, dt: float):
    lane = v.get("_lane") or SHIPPING_LANES[0]
    progress = v.get("_lane_progress", 0.0) + \
               (v.get("speed", 10) / 50000.0) * dt * v.get("_dir", 1)
    if progress >= 1.0:
        progress = 1.0
        v["_dir"] = -1
    elif progress <= 0.0:
        progress = 0.0
        v["_dir"] = 1
    v["_lane_progress"] = progress

    t = progress * (len(lane) - 1)
    idx = min(int(t), len(lane) - 2)
    frac = t - idx
    p1, p2 = lane[idx], lane[idx + 1]
    lat = p1[0] + (p2[0] - p1[0]) * frac + random.uniform(-0.01, 0.01)
    lon = p1[1] + (p2[1] - p1[1]) * frac + random.uniform(-0.01, 0.01)

    dy = p2[0] - p1[0]
    dx = p2[1] - p1[1]
    course = (math.degrees(math.atan2(dx, dy))) % 360
    if v.get("_dir", 1) < 0:
        course = (course + 180) % 360

    v["lat"] = round(lat, 6)
    v["lon"] = round(lon, 6)
    v["course"] = round(course, 1)
    v["heading"] = round(course, 1)
    v["time_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    v["last_seen"] = time.time()

    if random.random() < 0.02:
        base = v.get("speed", 10)
        v["speed"] = round(max(2.0, min(40.0, base + random.uniform(-2, 2))), 1)

    trail = v.setdefault("trail", [])
    if not trail or trail[-1] != [v["lat"], v["lon"]]:
        trail.append([v["lat"], v["lon"]])
        if len(trail) > TRAIL_MAX:
            del trail[:len(trail) - TRAIL_MAX]

    speed = v.get("speed", 0)
    if speed and course and speed > 0.5:
        dkm = speed * 0.514444 * 900
        dlat = (dkm / 111.32) * math.cos(math.radians(course))
        dlon = (dkm / (111.32 * math.cos(math.radians(lat) + 1e-9))) * \
               math.sin(math.radians(course))
        v["predicted"] = [round(lat + dlat, 6), round(lon + dlon, 6)]


async def synthetic_fleet_generator():
    """ناوگان شبیه‌سازی‌شده — همیشه چیز برای نمایش هست"""
    global report_count
    set_source_state("synthetic", "starting")
    log("🎭 راه‌اندازی ناوگان Synthetic...")

    TARGET_COUNT = 350
    HORMUZ_FRACTION = 0.12

    for i in range(TARGET_COUNT):
        force_hormuz = (random.random() < HORMUZ_FRACTION)
        v = _create_synthetic_vessel(force_hormuz=force_hormuz)
        mmsi = v["mmsi"]
        with vessels_lock:
            while mmsi in vessels:
                v = _create_synthetic_vessel(force_hormuz=force_hormuz)
                mmsi = v["mmsi"]
            vessels[mmsi] = v
    log(f"🎭 {TARGET_COUNT} شناور شبیه‌سازی‌شده ساخته شد")
    set_source_state("synthetic", "running")

    tick = 0
    last_time = time.time()
    while True:
        await asyncio.sleep(2.0)
        now = time.time()
        dt = now - last_time
        last_time = now
        tick += 1

        with vessels_lock:
            synth = [(m, v) for m, v in vessels.items()
                     if v.get("source") == "synthetic"]

        for mmsi, v in synth:
            _move_synthetic(v, dt)
            snap = safe_dict(v)
            trail_snap = list(v.get("trail", []))

            alert = check_hormuz_alert(
                mmsi, v.get("name"), v.get("lat"), v.get("lon"),
                v.get("course"), v.get("speed"), v.get("country")
            )
            if alert:
                safe_broadcast({"type": "alert", "data": alert})

            if tick % 20 == 0 and random.random() < 0.05:
                queue_position(mmsi, v.get("name"), v.get("lat"), v.get("lon"),
                               v.get("speed"), v.get("course"), v.get("heading"),
                               v.get("nav_status_code", 0), v.get("time_utc", ""))

            queue_update(mmsi, snap, "position", trail_snap)

        with source_status_lock:
            source_status["synthetic"]["reports"] = \
                source_status["synthetic"].get("reports", 0) + len(synth)
            source_status["synthetic"]["last"] = now

        with report_lock:
            report_count += len(synth)

        # Replenish
        if len(synth) < TARGET_COUNT - 20:
            to_add = TARGET_COUNT - len(synth)
            for _ in range(to_add):
                force_hormuz = (random.random() < HORMUZ_FRACTION)
                v = _create_synthetic_vessel(force_hormuz=force_hormuz)
                with vessels_lock:
                    if v["mmsi"] in vessels:
                        continue
                    vessels[v["mmsi"]] = v

# ═══════════════════════════════════════════════════════════════
#  🌐 DataDocked Poller — با چند روش احراز هویت
# ═══════════════════════════════════════════════════════════════
DATADOCKED_SAMPLES = [
    "353136000", "9247431", "538005432", "636014222", "367458840",
    "311042900", "538007579", "244660749", "477439900", "563087800",
]


def _fetch_url(url: str, headers: Optional[dict] = None,
               timeout: float = 15.0) -> dict:
    req = ur.Request(url, headers=headers or {"User-Agent": "AIS-Tracker/16.1"})
    with ur.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _try_datadocked(base: str, ident: str, api_key: str) -> dict:
    """همه روش‌های احراز هویت رو امتحان میکنه"""
    url = f"{base}/get-vessel-location?imo_or_mmsi={ident}"
    variants = [
        {"accept": "application/json", "x-api-key": api_key},
        {"accept": "application/json", "X-API-Key": api_key},
        {"accept": "application/json", "api-key": api_key},
        {"accept": "application/json", "Authorization": f"Bearer {api_key}"},
        {"accept": "application/json", "Authorization": api_key},
    ]
    last_err = None
    for headers in variants:
        try:
            return _fetch_url(url, headers, 15.0)
        except ur.HTTPError as e:
            if e.code == 403:
                last_err = e
                continue
            raise
        except Exception:
            raise
    if last_err:
        raise RuntimeError(f"403 Forbidden (همه روش‌ها تست شد)")
    raise RuntimeError("نامشخص")


async def datadocked_poller():
    if not DATADOCKED_API_KEY:
        log("⚠️ DATADOCKED_API_KEY تنظیم نشده")
        set_source_state("datadocked", "no-key")
        return

    base = "https://datadocked.com/api/vessels_operations"
    loop = asyncio.get_event_loop()
    set_source_state("datadocked", "running")
    consecutive_failures = 0
    logged_403 = False

    while True:
        for ident in DATADOCKED_SAMPLES:
            try:
                data = await loop.run_in_executor(
                    None, _try_datadocked, base, ident, DATADOCKED_API_KEY)
                detail = data.get("detail", {}) if isinstance(data, dict) else {}
                mmsi = str(detail.get("mmsi", ident))
                lat = float(detail.get("latitude", 0) or 0)
                lon = float(detail.get("longitude", 0) or 0)
                if not lat and not lon:
                    continue
                country, iso = mid_to_country(mmsi)
                with vessels_lock:
                    if mmsi not in vessels:
                        vessels[mmsi] = {
                            "mmsi": mmsi, "trail": [], "order": next_order(),
                            "country": country, "country_code": iso,
                        }
                    v = vessels[mmsi]
                    if not v.get("name"):
                        v["name"] = (detail.get("name") or "").strip()
                    v["lat"] = lat
                    v["lon"] = lon
                    v["speed"] = float(detail.get("speed", 0) or 0)
                    v["course"] = detail.get("course")
                    v["destination"] = detail.get("destination", "")
                    v["nav_status"] = detail.get("navigationalStatus", "")
                    v["source"] = "datadocked"
                    v["last_seen"] = time.time()
                    v["country"] = country
                    v["country_code"] = iso
                    v["category"] = v.get("category", "other")
                    trail = v.setdefault("trail", [])
                    if not trail or trail[-1] != [lat, lon]:
                        trail.append([lat, lon])
                        if len(trail) > TRAIL_MAX:
                            del trail[:len(trail) - TRAIL_MAX]
                    snap = safe_dict(v)
                    trail_snap = list(trail)
                queue_update(mmsi, snap, "position", trail_snap)
                log(f"✅ DataDocked OK: {detail.get('name') or mmsi} "
                    f"@ {lat:.3f},{lon:.3f}")
                consecutive_failures = 0
                logged_403 = False
                with source_status_lock:
                    source_status["datadocked"]["reports"] = \
                        source_status["datadocked"].get("reports", 0) + 1
                    source_status["datadocked"]["last"] = time.time()
                    source_status["datadocked"]["error"] = None
            except Exception as e:
                consecutive_failures += 1
                msg = f"{type(e).__name__}: {str(e)[:100]}"
                if not logged_403:
                    log(f"⚠️ DataDocked: {msg}")
                    logged_403 = True
                set_source_state("datadocked", "error", msg)
            await asyncio.sleep(6)
        await asyncio.sleep(120 if consecutive_failures > 5 else 60)

# ═══════════════════════════════════════════════════════════════
#  📡 Broadcasting
# ═══════════════════════════════════════════════════════════════
async def broadcast(message: dict):
    payload = json.dumps(message, ensure_ascii=False)
    with ws_lock:
        clients = list(ws_clients)
    if not clients:
        return
    dead = []
    for c in clients:
        try:
            await c.send_text(payload)
        except Exception:
            dead.append(c)
    if dead:
        with ws_lock:
            for d in dead:
                ws_clients.discard(d)


async def broadcaster():
    while True:
        await asyncio.sleep(BROADCAST_EVERY)
        with pending_lock:
            if not pending_updates:
                continue
            batch = list(pending_updates.values())
            pending_updates.clear()
        with ws_lock:
            if not ws_clients:
                continue
        payload = json.dumps({"type": "batch", "updates": batch},
                             ensure_ascii=False)
        with ws_lock:
            clients = list(ws_clients)
        dead = []
        for c in clients:
            try:
                await c.send_text(payload)
            except Exception:
                dead.append(c)
        if dead:
            with ws_lock:
                for d in dead:
                    ws_clients.discard(d)


async def db_writer():
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(3)
        with db_queue_lock:
            has = bool(db_queue)
        if has:
            await loop.run_in_executor(None, flush_db_queue)


async def status_logger():
    while True:
        await asyncio.sleep(20)
        with vessels_lock:
            vc = len(vessels)
        with alerts_lock:
            ac = len(alerts)
        with report_lock:
            rc = report_count
        with ws_lock:
            wc = len(ws_clients)
        log(f"📊 {vc:,} شناور | {rc:,} گزارش | 🚨 {ac} هشدار | 🔗 {wc} کلاینت")


async def purge_stale_vessels():
    while True:
        await asyncio.sleep(PURGE_INTERVAL)
        now = time.time()
        stale = []
        with vessels_lock:
            for m, v in list(vessels.items()):
                if v.get("source") == "synthetic":
                    continue
                if v.get("last_seen") and now - v["last_seen"] > STALE_SECONDS:
                    stale.append(m)
            for m in stale:
                del vessels[m]
        if stale:
            payload = json.dumps({"type": "remove", "mmsi": stale},
                                 ensure_ascii=False)
            with ws_lock:
                clients = list(ws_clients)
            for c in clients:
                try:
                    await c.send_text(payload)
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════════
#  🚀 FastAPI
# ═══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()

    log("🚀 راه‌اندازی...")
    init_db()
    log(f"🗄️ DB: {DB_PATH}")
    log(f"📂 Data dir: {DATA_DIR}")

    tasks = [
        asyncio.create_task(synthetic_fleet_generator()),
        asyncio.create_task(ais_collector()),
        asyncio.create_task(datadocked_poller()),
        asyncio.create_task(broadcaster()),
        asyncio.create_task(db_writer()),
        asyncio.create_task(status_logger()),
        asyncio.create_task(purge_stale_vessels()),
    ]
    lan_ip = get_lan_ip()
    log(f"🌐 لوکال   : http://localhost:{PORT}")
    log(f"📱 شبکه    : http://{lan_ip}:{PORT}")
    log("🚨 هشدار تنگه هرمز فعال است")
    log("📡 منابع: Synthetic + AISStream + DataDocked\n")
    yield
    log("🛑 در حال خاموش شدن...")
    for t in tasks:
        t.cancel()
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        pass
    flush_db_queue()
    log("✅ خاموش شد")


app = FastAPI(title="AIS Global Tracker", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.get("/api/health")
async def health():
    with vessels_lock:
        vc = len(vessels)
    return {"status": "ok", "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "vessels": vc}


@app.get("/api/metrics")
async def metrics():
    with vessels_lock:
        vc = len(vessels)
    with report_lock:
        rc = report_count
    with alerts_lock:
        ac = len(alerts)
    with ws_lock:
        wc = len(ws_clients)
    return {"vessels": vc, "reports_total": rc, "alerts": ac, "ws_clients": wc}


@app.get("/api/sources")
async def api_sources():
    with source_status_lock:
        return {"sources": {k: dict(v) for k, v in source_status.items()}}


@app.get("/api/alerts")
async def api_alerts():
    with alerts_lock:
        return {"alerts": list(alerts)[:100]}


@app.get("/api/history/{mmsi}")
async def api_history(mmsi: str, hours: int = Query(24, ge=1, le=168)):
    return {"mmsi": mmsi, "history": get_history(mmsi, hours)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with ws_lock:
        ws_clients.add(ws)
    log(f"🔗 کلاینت متصل ({len(ws_clients)})")
    try:
        with vessels_lock:
            init = {
                "type": "initial",
                "count": len(vessels),
                "total_reports": report_count,
                "vessels": [safe_dict(v) | {"trail": v.get("trail", [])}
                            for v in vessels.values()],
            }
        await ws.send_text(json.dumps(init, ensure_ascii=False))
        with alerts_lock:
            alerts_init = list(alerts)[:100]
        await ws.send_text(json.dumps(
            {"type": "alerts_init", "alerts": alerts_init},
            ensure_ascii=False))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        with ws_lock:
            ws_clients.discard(ws)
        log(f"🔌 کلاینت قطع ({len(ws_clients)})")

# ═══════════════════════════════════════════════════════════════
#  🌍 HTML
# ═══════════════════════════════════════════════════════════════
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<title>🛰️ AIS Global Tracker | Cyber Ghost</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"/>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
:root{--bg:#080c14;--panel:#0f172a;--panel2:#1e293b;--border:#1e293b;
  --text:#e2e8f0;--muted:#64748b;--accent:#38bdf8;--green:#22c55e;
  --red:#ef4444;--orange:#f59e0b;--ghost:#e94560;--purple:#a855f7}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{font-family:'Segoe UI',Tahoma,sans-serif;background:var(--bg);color:var(--text)}
#app{display:flex;height:100vh;direction:rtl}
#sidebar{width:400px;background:var(--panel);border-left:1px solid var(--border);
  display:flex;flex-direction:column;z-index:10;box-shadow:-4px 0 24px rgba(0,0,0,.5)}
.sb-head{padding:14px 16px;border-bottom:1px solid var(--border);
  background:linear-gradient(135deg,#0f172a,#1e293b)}
.logo{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:700;color:var(--accent)}
.brand{font-size:11px;color:var(--ghost);margin-top:4px;display:flex;align-items:center;gap:6px}
.brand .dot{width:7px;height:7px;background:var(--ghost);border-radius:50%;
  box-shadow:0 0 10px var(--ghost);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.src-panel{padding:8px 14px;background:rgba(8,12,20,.4);
  border-bottom:1px solid var(--border);font-size:10px;display:flex;flex-wrap:wrap;gap:6px}
.src-item{display:flex;align-items:center;gap:4px;padding:3px 8px;border-radius:10px;
  background:var(--panel2);border:1px solid var(--border)}
.src-dot{width:6px;height:6px;border-radius:50%;background:var(--muted)}
.src-dot.on{background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 1.5s infinite}
.src-dot.warn{background:var(--orange);box-shadow:0 0 6px var(--orange)}
.src-dot.err{background:var(--red);box-shadow:0 0 6px var(--red)}
.tabs{display:flex;padding:8px 12px 0;gap:6px;border-bottom:1px solid var(--border);
  background:rgba(8,12,20,.3)}
.tab{flex:1;padding:8px 6px;background:var(--panel2);border:1px solid var(--border);
  border-bottom:none;border-radius:8px 8px 0 0;cursor:pointer;text-align:center;
  font-size:11px;color:var(--muted);transition:.2s;position:relative}
.tab:hover{color:var(--text)}
.tab.active{background:var(--panel);color:var(--accent);font-weight:700;
  border-color:var(--accent);border-bottom-color:var(--panel)}
.tab .badge{position:absolute;top:-4px;right:-4px;background:var(--red);color:#fff;
  font-size:9px;padding:1px 5px;border-radius:8px;font-weight:700;display:none}
.tab .badge.show{display:block;animation:bounce .5s}
@keyframes bounce{0%,100%{transform:scale(1)}50%{transform:scale(1.3)}}
.panel-content{flex:1;display:none;flex-direction:column;overflow:hidden}
.panel-content.active{display:flex}
.kpi-grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:6px;padding:12px}
.kpi{background:var(--panel2);border:1px solid var(--border);border-radius:10px;
  padding:8px 4px;text-align:center}
.kpi b{display:block;font-size:17px;color:var(--green);font-variant-numeric:tabular-nums}
.kpi.mil b{color:#22c55e}.kpi.mov b{color:#f59e0b}
.kpi.alert b{color:var(--red)}
.kpi span{font-size:9px;color:var(--muted)}
#search{width:calc(100% - 24px);margin:0 12px 8px;padding:10px 12px;
  background:var(--panel2);border:1px solid var(--border);border-radius:8px;
  color:var(--text);font-family:inherit;font-size:13px;outline:none;transition:.2s}
#search:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(56,189,248,.15)}
.filters{display:flex;flex-wrap:wrap;gap:5px;padding:0 12px 10px}
.chip{font-size:10px;padding:4px 10px;border-radius:12px;background:var(--panel2);
  border:1px solid var(--border);cursor:pointer;color:var(--muted);transition:.2s}
.chip:hover{border-color:var(--accent);color:var(--text)}
.chip.active{background:var(--accent);color:#080c14;font-weight:700;border-color:var(--accent)}
.chip.mil.active{background:#22c55e;border-color:#22c55e;color:#080c14}
.list-head{padding:8px 14px;font-size:11px;color:var(--muted);
  border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  display:flex;justify-content:space-between;background:rgba(8,12,20,.5)}
#vlist,#alist{list-style:none;overflow-y:auto;overflow-anchor:none;flex:1}
#vlist::-webkit-scrollbar,#alist::-webkit-scrollbar{width:5px}
#vlist::-webkit-scrollbar-thumb,#alist::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.vi{padding:9px 14px;border-bottom:1px solid var(--border);cursor:pointer;
  display:flex;gap:10px;align-items:center;border-right:3px solid transparent;
  transition:background .15s, border-right-color .15s}
.vi:hover{background:var(--panel2);border-right-color:var(--accent)}
.vi.active{background:var(--panel2);border-right-color:var(--green);
  box-shadow:inset 0 0 0 1px var(--green)}
.vi.mil{border-right-color:#22c55e}
.vi-ic{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:15px;flex-shrink:0;border:2px solid}
.vi-info{flex:1;min-width:0}
.vi-name{font-size:12.5px;font-weight:700;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.vi-meta{font-size:10px;color:var(--muted);margin-top:2px;display:flex;gap:8px}
.vi-speed{font-size:11px;color:var(--green);font-weight:700;white-space:nowrap;
  min-width:50px;text-align:left}
.empty{padding:40px 20px;text-align:center;color:var(--muted);font-size:12px}
.al{padding:10px 14px;border-bottom:1px solid var(--border);cursor:pointer;
  border-right:4px solid var(--red);background:rgba(239,68,68,.05);transition:.15s}
.al:hover{background:rgba(239,68,68,.12)}
.al-head{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;
  color:#fca5a5}
.al-head .icon{font-size:18px}
.al-body{margin-top:6px;font-size:11px;color:var(--muted);display:flex;
  flex-wrap:wrap;gap:8px}
.al-body span{display:inline-flex;align-items:center;gap:3px}
.al-time{font-size:9px;color:var(--muted);margin-top:4px;text-align:left;
  direction:ltr;font-family:monospace}
.al-empty{padding:40px 20px;text-align:center;color:var(--muted);font-size:12px}
.al-empty .big{font-size:48px;margin-bottom:12px}
.sb-foot{padding:8px;border-top:1px solid var(--border);display:flex;gap:6px;
  justify-content:center;background:rgba(8,12,20,.5)}
.sb-foot a{font-size:10px;color:var(--accent);text-decoration:none;
  padding:4px 10px;border-radius:6px;border:1px solid transparent;transition:.2s}
.sb-foot a:hover{background:var(--panel2);border-color:var(--border)}
#map-wrap{flex:1;position:relative}
#map{width:100%;height:100%}
.maplibregl-popup-content{background:var(--panel)!important;color:var(--text)!important;
  border-radius:10px!important;border:1px solid var(--border)!important;
  padding:14px!important;font-family:inherit!important;direction:rtl}
.maplibregl-popup-tip{border-top-color:var(--panel)!important}
#drawer{position:fixed;top:0;bottom:0;left:0;right:auto;width:400px;
  background:var(--panel);border-right:1px solid var(--border);
  transform:translateX(-100%);transition:transform .3s cubic-bezier(.4,0,.2,1);
  z-index:2000;display:flex;flex-direction:column;
  box-shadow:4px 0 30px rgba(0,0,0,.6);pointer-events:none}
#drawer.open{transform:translateX(0);pointer-events:auto}
#drawer-close{position:absolute;top:12px;left:12px;width:34px;height:34px;border-radius:8px;
  background:var(--panel2);border:1px solid var(--border);color:var(--text);
  cursor:pointer;font-size:16px;z-index:2;transition:.2s}
#drawer-close:hover{background:var(--red);color:#fff}
#drawer-body{overflow-y:auto;padding:20px;flex:1}
#drawer-body::-webkit-scrollbar{width:5px}
#drawer-body::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.d-head{text-align:center;padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:16px}
.d-photo-wrap{width:100%;height:180px;background:#000;border-radius:10px;
  margin-bottom:12px;border:1px solid var(--border);overflow:hidden;
  display:flex;align-items:center;justify-content:center;position:relative}
.d-photo{width:100%;height:100%;object-fit:contain;display:block}
.d-photo-label{position:absolute;top:6px;right:6px;font-size:9px;
  background:rgba(0,0,0,.6);padding:2px 8px;border-radius:10px;color:var(--muted)}
.d-ic{width:72px;height:72px;border-radius:50%;display:inline-flex;align-items:center;
  justify-content:center;font-size:34px;border:3px solid;background:rgba(255,255,255,.03);
  margin-bottom:10px}
.d-name{font-size:18px;font-weight:700}
.d-type{font-size:12px;color:var(--muted);margin-top:4px}
.d-flag{display:inline-block;padding:3px 12px;border-radius:10px;font-size:11px;
  margin-top:6px;background:rgba(34,197,94,.15);color:#22c55e;border:1px solid #22c55e}
.d-badge{display:inline-block;padding:3px 12px;border-radius:10px;font-size:11px;
  margin-top:8px;background:rgba(56,189,248,.15);color:var(--accent);border:1px solid var(--accent)}
.sec{margin-bottom:18px}
.sec-t{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;
  margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:6px}
.row{display:flex;justify-content:space-between;padding:7px 0;font-size:12.5px;
  border-bottom:1px dashed rgba(30,41,59,.7)}
.row:last-child{border-bottom:none}
.row .lbl{color:var(--muted);display:flex;align-items:center;gap:6px}
.row .val{font-weight:700;text-align:left;direction:ltr}
.val.green{color:var(--green)}
.compass{width:64px;height:64px;border-radius:50%;border:2px solid var(--border);
  position:relative;margin:0 auto;background:var(--panel2)}
.compass-arrow{position:absolute;top:50%;left:50%;width:2px;height:28px;
  background:var(--accent);transform-origin:bottom center;
  transform:translate(-50%,-100%) rotate(0deg);transition:transform .5s;border-radius:1px}
.compass-arrow::before{content:'';position:absolute;top:-7px;left:50%;transform:translateX(-50%);
  border:5px solid transparent;border-bottom-color:var(--accent)}
.compass-n{position:absolute;top:4px;left:50%;transform:translateX(-50%);
  font-size:9px;color:var(--muted);font-weight:700}
.speed-bar{height:6px;background:var(--panel2);border-radius:3px;overflow:hidden;margin-top:5px}
.speed-fill{height:100%;background:linear-gradient(90deg,var(--green),var(--orange),var(--red));
  transition:width .5s;border-radius:3px}
.actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.btn{flex:1;min-width:110px;padding:9px;border-radius:8px;border:1px solid var(--border);
  background:var(--panel2);color:var(--text);cursor:pointer;font-family:inherit;
  font-size:12px;transition:.2s;text-decoration:none;text-align:center;
  display:flex;align-items:center;justify-content:center;gap:6px}
.btn:hover{background:var(--accent);color:#080c14;border-color:var(--accent)}
#map-ctl{position:absolute;top:14px;left:14px;display:flex;flex-direction:column;gap:6px;z-index:500}
#map-ctl button{width:38px;height:38px;background:var(--panel);border:1px solid var(--border);
  color:var(--text);border-radius:8px;cursor:pointer;font-size:16px;transition:.2s;
  display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.4)}
#map-ctl button:hover{background:var(--accent);color:#080c14}
#map-ctl button.on{background:var(--green);color:#080c14}
#conn-status{position:absolute;bottom:14px;left:14px;padding:6px 14px;border-radius:20px;
  font-size:11px;background:rgba(15,23,42,.9);border:1px solid var(--border);z-index:500;
  display:flex;align-items:center;gap:8px}
#conn-status .sdot{width:8px;height:8px;border-radius:50%;background:var(--green);
  box-shadow:0 0 8px var(--green)}
#conn-status.off .sdot{background:var(--red);box-shadow:0 0 8px var(--red)}
#toast{position:fixed;top:20px;left:50%;transform:translateX(-50%) translateY(-120%);
  background:linear-gradient(135deg,#7f1d1d,#dc2626);color:#fff;padding:14px 22px;
  border-radius:12px;box-shadow:0 8px 30px rgba(220,38,38,.6);z-index:9999;
  font-size:13px;font-weight:700;display:flex;align-items:center;gap:12px;
  transition:transform .4s cubic-bezier(.4,0,.2,1);pointer-events:none;direction:rtl;
  border:1px solid #ef4444;max-width:90vw}
#toast.show{transform:translateX(-50%) translateY(0)}
#toast .ticon{font-size:24px;animation:shake .5s infinite}
@keyframes shake{0%,100%{transform:rotate(-8deg)}50%{transform:rotate(8deg)}}
@media(max-width:900px){#sidebar{width:320px}#drawer{width:100%}}
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <div class="sb-head">
      <div class="logo">🛰️ AIS Global Tracker</div>
      <div class="brand"><span class="dot"></span> Cyber Ghost — v16.1</div>
    </div>
    <div class="src-panel" id="src-panel">
      <div class="src-item"><span class="src-dot" id="src-aisstream"></span>AISStream</div>
      <div class="src-item"><span class="src-dot" id="src-datadocked"></span>DataDocked</div>
      <div class="src-item"><span class="src-dot" id="src-synthetic"></span>Synthetic</div>
    </div>
    <div class="tabs">
      <div class="tab active" data-tab="vessels">🚢 شناورها</div>
      <div class="tab" data-tab="alerts">🚨 هشدارها<span class="badge" id="alerts-badge">0</span></div>
    </div>
    <div class="panel-content active" id="tab-vessels">
      <div class="kpi-grid">
        <div class="kpi"><b id="kpi-v">0</b><span>فعال</span></div>
        <div class="kpi mov"><b id="kpi-m">0</b><span>در حرکت</span></div>
        <div class="kpi"><b id="kpi-a">0</b><span>لنگر</span></div>
        <div class="kpi mil"><b id="kpi-mil">0</b><span>🎖️ نظامی</span></div>
      </div>
      <input id="search" placeholder="🔍 جستجو: نام، MMSI، مقصد، کشور..."/>
      <div class="filters" id="filters"></div>
      <div class="list-head"><span>📋 شناورها</span><span id="last-upd">—</span></div>
      <ul id="vlist"><div class="empty">در حال دریافت داده...</div></ul>
    </div>
    <div class="panel-content" id="tab-alerts">
      <div class="kpi-grid" style="grid-template-columns:1fr 1fr">
        <div class="kpi alert"><b id="kpi-alerts">0</b><span>هشدار فعال</span></div>
        <div class="kpi"><b id="kpi-alerts-total">0</b><span>کل هشدارها</span></div>
      </div>
      <div class="list-head"><span>🚨 هشدارهای تنگه هرمز</span>
        <span style="color:var(--red);font-size:10px">🔴 LIVE</span></div>
      <ul id="alist">
        <div class="al-empty">
          <div class="big">🚨</div>
          <div>منتظر عبور کشتی از تنگه هرمز...</div>
        </div>
      </ul>
    </div>
    <div class="sb-foot">
      <a href="https://t.me/Cyber_Ghost_error_404" target="_blank">🆔 آیدی</a>
      <a href="https://t.me/cyber_ghost_error_404_chanel" target="_blank">📢 کانال</a>
    </div>
  </aside>
  <div id="map-wrap">
    <div id="map"></div>
    <div id="map-ctl">
      <button id="btn-fit" title="نمایش همه">🎯</button>
      <button id="btn-trails" class="on" title="مسیر">〰️</button>
      <button id="btn-predict" title="پیش‌بینی">🔮</button>
      <button id="btn-military" title="فقط نظامی">🎖️</button>
      <button id="btn-hormuz" title="تنگه هرمز">🕌</button>
    </div>
    <div id="conn-status"><span class="sdot"></span><span id="conn-text">در حال اتصال...</span></div>
  </div>
  <div id="drawer">
    <button id="drawer-close">✕</button>
    <div id="drawer-body"></div>
  </div>
  <div id="toast">
    <span class="ticon">🚨</span>
    <span id="toast-text">هشدار جدید</span>
  </div>
</div>
<script>
const map = new maplibregl.Map({
  container:'map',
  style:{version:8,
    sources:{osm:{type:'raster',
      tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize:256, attribution:'© OSM | Cyber Ghost'}},
    layers:[{id:'osm',type:'raster',source:'osm',
      paint:{'raster-brightness-min':0.15,'raster-brightness-max':0.6,
             'raster-saturation':-0.3,'raster-contrast':0.1}}]},
  center:[55,27], zoom:5, attributionControl:false
});
map.addControl(new maplibregl.NavigationControl({position:'bottom-right'}),'bottom-right');
const HORMUZ_POLYGON = [
  [27.30,55.80],[27.10,56.30],[26.80,56.90],[26.50,57.30],
  [26.20,57.50],[25.80,57.20],[25.60,56.80],[25.40,56.40],
  [25.50,56.00],[26.00,55.50],[26.60,55.20],[27.30,55.80]
];
map.on('load', ()=>{
  map.addSource('hormuz', {type:'geojson',
    data:{type:'Feature', geometry:{type:'Polygon',
      coordinates:[HORMUZ_POLYGON.map(p=>[p[1],p[0]])]}}});
  map.addLayer({id:'hormuz-fill', type:'fill', source:'hormuz',
    paint:{'fill-color':'#ef4444','fill-opacity':0.08}});
  map.addLayer({id:'hormuz-line', type:'line', source:'hormuz',
    paint:{'line-color':'#ef4444','line-width':2,'line-dasharray':[6,3],
           'line-opacity':0.7}});
  map.addSource('hormuz-label', {type:'geojson',
    data:{type:'Feature', geometry:{type:'Point', coordinates:[56.4, 26.6]},
      properties:{label:'🕌 تنگه هرمز'}}});
  map.addLayer({id:'hormuz-label', type:'symbol', source:'hormuz-label',
    layout:{'text-field':['get','label'],'text-size':13,'text-anchor':'center'},
    paint:{'text-color':'#ef4444','text-halo-color':'#000','text-halo-width':2}});
});
const vessels={}, markers={}, popups={};
const svgCache=new Map();
const knownMMSI=new Set();
let selectedMMSI=null;
let showTrails=true, showPredict=false;
let activeFilter='all';
let ws=null, renderScheduled=false, lastListKey='';
let alerts=[];
let toastTimer=null;
const CAT_COLORS={cargo:'#f59e0b',tanker:'#ef4444',passenger:'#e94560',
  tug:'#3b82f6',fishing:'#10b981',military:'#22c55e',pleasure:'#a855f7',
  high_speed:'#f97316',law:'#3b82f6',sar:'#f43f5e',other:'#38bdf8'};
const CAT_ICONS={cargo:'📦',tanker:'🛢️',passenger:'🛳️',tug:'⚓',fishing:'🎣',
  military:'🎖️',pleasure:'🛥️',high_speed:'🚤',law:'🚔',sar:'🚁',other:'🚢'};
const colorFor=v=>CAT_COLORS[v.category]||CAT_COLORS.other;
const iconFor =v=>CAT_ICONS[v.category]||CAT_ICONS.other;
function makeShipSVG(v){
  const key=`${v.mmsi}|${v.category}|${v.name}|${v.type_name}|${v.country}`;
  if(svgCache.has(key)) return svgCache.get(key);
  const icon=iconFor(v), c=colorFor(v);
  const name=(v.name||'نامشخص').substring(0,22).replace(/[<>&]/g,'');
  const country=(v.country||'').substring(0,20).replace(/[<>&]/g,'');
  const typeName=(v.type_name||'').substring(0,22).replace(/[<>&]/g,'');
  const mmsi=v.mmsi||'';
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="180" viewBox="0 0 400 180">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#0a0f1c"/>
  </linearGradient>
  <linearGradient id="acc" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="${c}"/>
    <stop offset="100%" stop-color="${c}" stop-opacity="0.2"/>
  </linearGradient>
</defs>
<rect width="400" height="180" fill="url(#bg)"/>
<rect x="8" y="8" width="384" height="164" fill="none" stroke="${c}"
  stroke-width="1.5" stroke-dasharray="8,4" rx="12" opacity="0.5"/>
<circle cx="200" cy="72" r="42" fill="none" stroke="${c}" stroke-width="1" opacity="0.3"/>
<circle cx="200" cy="72" r="52" fill="none" stroke="${c}" stroke-width="0.5" opacity="0.15"/>
<text x="200" y="82" font-size="56" text-anchor="middle"
  dominant-baseline="middle">${icon}</text>
<rect x="60" y="128" width="280" height="2" fill="url(#acc)"/>
<text x="200" y="150" font-size="15" font-weight="bold" text-anchor="middle"
  fill="#e2e8f0" font-family="Tahoma">${name}</text>
<text x="200" y="167" font-size="10" text-anchor="middle"
  fill="#64748b" font-family="Tahoma">${typeName} • ${country} • MMSI: ${mmsi}</text>
</svg>`;
  const data='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
  if(svgCache.size>500) svgCache.clear();
  svgCache.set(key, data);
  return data;
}
document.querySelectorAll('.tab').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel-content').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('tab-'+t.dataset.tab).classList.add('active');
  };
});
const FILTERS=[
  {k:'all',l:'🌐 همه'},{k:'military',l:'🎖️ نظامی',mil:true},
  {k:'cargo',l:'📦 باربری'},{k:'tanker',l:'🛢️ نفتکش'},
  {k:'passenger',l:'🛳️ مسافربری'},{k:'tug',l:'⚓ یدک‌کش'},
  {k:'fishing',l:'🎣 ماهیگیری'},{k:'pleasure',l:'🛥️ تفریحی'},
];
const fEl=document.getElementById('filters');
FILTERS.forEach(f=>{
  const c=document.createElement('div');
  c.className='chip'+(f.k==='all'?' active':'')+(f.mil?' mil':'');
  c.textContent=f.l; c.dataset.filter=f.k;
  c.onclick=()=>{
    activeFilter=f.k;
    document.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
    c.classList.add('active');
    document.getElementById('btn-military').classList.toggle('on',f.k==='military');
    lastListKey=''; scheduleRender();
  };
  fEl.appendChild(c);
});
function withPosition(v){return v.lat!=null&&v.lon!=null;}
function renderList(){
  const q=document.getElementById('search').value.toLowerCase().trim();
  const list=Object.values(vessels)
    .filter(withPosition)
    .filter(v=>activeFilter==='all'||v.category===activeFilter)
    .filter(v=>!q ||
      (v.name||'').toLowerCase().includes(q) ||
      String(v.mmsi).includes(q) ||
      (v.destination||'').toLowerCase().includes(q) ||
      (v.country||'').toLowerCase().includes(q))
    .sort((a,b)=>(a.order||0)-(b.order||0));
  const ul=document.getElementById('vlist');
  const listKey=activeFilter+'|'+q+'|'+list.length+'|'+
                (list[0]?.mmsi||'')+'|'+(list[list.length-1]?.mmsi||'');
  if(listKey!==lastListKey){
    lastListKey=listKey;
    if(!list.length){
      ul.innerHTML=`<div class="empty">${Object.keys(vessels).length?'نتیجه‌ای یافت نشد':'در حال دریافت...'}</div>`;
      return;
    }
    const scrollTop=ul.scrollTop;
    ul.innerHTML=list.slice(0,300).map(v=>{
      const c=colorFor(v),e=iconFor(v);
      const spd=v.speed!=null?Number(v.speed).toFixed(1)+' kn':'—';
      const cls=(selectedMMSI===String(v.mmsi)?' active':'')+(v.category==='military'?' mil':'');
      return `<li class="vi${cls}" data-mmsi="${v.mmsi}">
        <div class="vi-ic" style="color:${c};border-color:${c}">${e}</div>
        <div class="vi-info">
          <div class="vi-name">${v.name||'نامشخص'}</div>
          <div class="vi-meta"><span>🆔 ${v.mmsi}</span>
            ${v.country?`<span>🌍 ${v.country}</span>`:''}</div>
        </div>
        <div class="vi-speed">${spd}</div>
      </li>`;
    }).join('');
    ul.querySelectorAll('.vi').forEach(li=>li.onclick=()=>selectVessel(li.dataset.mmsi));
    requestAnimationFrame(()=>{ul.scrollTop=scrollTop;});
  }
}
function renderAlerts(){
  const ul=document.getElementById('alist');
  if(!alerts.length){
    ul.innerHTML=`<div class="al-empty">
      <div class="big">🚨</div>
      <div>منتظر عبور کشتی از تنگه هرمز...</div>
    </div>`;
    return;
  }
  ul.innerHTML=alerts.map(a=>`
    <li class="al" data-mmsi="${a.mmsi}">
      <div class="al-head">
        <span class="icon">${(a.direction||'').includes('ورود')?'🇮🇷':'🌊'}</span>
        <span>${a.name}</span>
      </div>
      <div class="al-body">
        <span>🆔 ${a.mmsi}</span>
        ${a.country?`<span>🌍 ${a.country}</span>`:''}
        <span>${a.direction}</span>
        ${a.speed!=null?`<span>⚡ ${Number(a.speed).toFixed(1)} kn</span>`:''}
      </div>
      <div class="al-time">🕒 ${a.time} • ${a.lat},${a.lon}</div>
    </li>`).join('');
  ul.querySelectorAll('.al').forEach(li=>{
    li.onclick=()=>{
      const v=vessels[li.dataset.mmsi];
      if(v) selectVessel(li.dataset.mmsi);
    };
  });
}
function showToast(text){
  const t=document.getElementById('toast');
  document.getElementById('toast-text').textContent=text;
  t.classList.add('show');
  if(toastTimer) clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>t.classList.remove('show'),6000);
}
function highlightSelected(){
  document.querySelectorAll('.vi').forEach(li=>{
    li.classList.toggle('active',li.dataset.mmsi===String(selectedMMSI));
  });
}
function renderMarkers(){
  const ids=new Set(Object.keys(vessels));
  for(const m in markers){
    if(!ids.has(m)){markers[m].remove();delete markers[m];delete popups[m];}
  }
  let count=0;
  Object.values(vessels).forEach(v=>{
    if(!withPosition(v)) return;
    const mmsi=String(v.mmsi);
    const match=activeFilter==='all'||v.category===activeFilter;
    if(!match){
      if(markers[mmsi]){markers[mmsi].remove();delete markers[mmsi];}
      return;
    }
    const c=colorFor(v),e=iconFor(v);
    const isMil=v.category==='military';
    const size=isMil?34:26, fs=isMil?16:13;
    if(markers[mmsi]){
      markers[mmsi].setLngLat([v.lon,v.lat]);
      const el=markers[mmsi].getElement();
      el.style.borderColor=c;
      el.style.boxShadow=`0 0 0 2px rgba(0,0,0,.5),0 0 14px ${c}`;
      el.innerHTML=e;
    } else {
      const el=document.createElement('div');
      el.style.cssText=`width:${size}px;height:${size}px;border-radius:50%;
        display:flex;align-items:center;justify-content:center;font-size:${fs}px;
        border:2px solid ${c};background:#080c14;
        box-shadow:0 0 0 2px rgba(0,0,0,.5),0 0 14px ${c};cursor:pointer;
        transition:transform .15s`;
      el.innerHTML=e;
      el.onmouseenter=()=>el.style.transform='scale(1.4)';
      el.onmouseleave=()=>el.style.transform='scale(1)';
      el.onclick=()=>selectVessel(mmsi);
      const m=new maplibregl.Marker({element:el,anchor:'center'})
        .setLngLat([v.lon,v.lat]).addTo(map);
      markers[mmsi]=m;
      popups[mmsi]=new maplibregl.Popup({offset:18,maxWidth:'320px'})
        .setHTML(popupHTML(v));
      m.setPopup(popups[mmsi]);
    }
    if(popups[mmsi]) popups[mmsi].setHTML(popupHTML(v));
    count++;
  });
}
function updateTrails(){
  if(!map.getSource('trails')){
    map.addSource('trails',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
    map.addLayer({id:'trails',type:'line',source:'trails',
      paint:{'line-color':['get','color'],'line-width':2,
             'line-opacity':0.7,'line-dasharray':[4,3]}});
  }
  const feats=[];
  let n=0;
  for(const v of Object.values(vessels)){
    if(n>250) break;
    if(!v.trail||v.trail.length<2) continue;
    if(activeFilter!=='all'&&v.category!==activeFilter) continue;
    feats.push({type:'Feature',properties:{color:colorFor(v)},
      geometry:{type:'LineString',coordinates:v.trail.map(p=>[p[1],p[0]])}});
    n++;
  }
  map.getSource('trails').setData({type:'FeatureCollection',features:feats});
}
function updateFocusedTrail(v){
  if(!map.getSource('focused-trail')){
    map.addSource('focused-trail',{type:'geojson',
      data:{type:'FeatureCollection',features:[]}});
    map.addLayer({id:'focused-trail-glow',type:'line',source:'focused-trail',
      paint:{'line-color':['get','color'],'line-width':14,'line-opacity':0.15,'line-blur':6}});
    map.addLayer({id:'focused-trail',type:'line',source:'focused-trail',
      paint:{'line-color':['get','color'],'line-width':4,'line-opacity':1,
             'line-dasharray':[6,4]}});
  }
  const feats=[];
  if(v&&v.trail&&v.trail.length>1){
    feats.push({type:'Feature',properties:{color:colorFor(v)},
      geometry:{type:'LineString',coordinates:v.trail.map(p=>[p[1],p[0]])}});
  }
  map.getSource('focused-trail').setData({type:'FeatureCollection',features:feats});
}
function updatePredictions(){
  if(!map.getSource('predict')){
    map.addSource('predict',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
    map.addLayer({id:'predict',type:'line',source:'predict',
      paint:{'line-color':'#a855f7','line-width':2,'line-opacity':0.6,
             'line-dasharray':[2,4]},
      layout:{'visibility':showPredict?'visible':'none'}});
  }
  const feats=[];
  if(showPredict){
    let n=0;
    for(const v of Object.values(vessels)){
      if(n>200) break;
      if(!v.predicted||!v.lat||!v.lon) continue;
      feats.push({type:'Feature',
        geometry:{type:'LineString',
          coordinates:[[v.lon,v.lat],[v.predicted[1],v.predicted[0]]]}});
      n++;
    }
  }
  map.getSource('predict').setData({type:'FeatureCollection',features:feats});
}
function selectVessel(mmsi){
  mmsi=String(mmsi);
  selectedMMSI=mmsi;
  const v=vessels[mmsi];
  if(!v) return;
  buildDetails(v);
  highlightSelected();
  updateFocusedTrail(v);
  if(v.lat&&v.lon)
    map.flyTo({center:[v.lon,v.lat],zoom:Math.max(map.getZoom(),13),speed:1.2});
}
function buildDetails(v){
  const c=colorFor(v),e=iconFor(v);
  const gmap=v.lat&&v.lon?`https://maps.google.com/?q=${v.lat},${v.lon}`:'#';
  const gimg=`https://www.google.com/search?tbm=isch&q=${encodeURIComponent((v.name||'ship')+' vessel '+v.mmsi)}`;
  const photo=makeShipSVG(v);
  const html=`
    <div class="d-head">
      <div class="d-photo-wrap">
        <img class="d-photo" src="${photo}" alt=""/>
        <div class="d-photo-label">🎨 تصویر تولیدی</div>
      </div>
      <div class="d-ic" style="color:${c};border-color:${c}">${e}</div>
      <div class="d-name">${v.name||'نامشخص'}</div>
      <div class="d-type">${v.type_name||'نامشخص'}</div>
      <div>${v.country?`<div class="d-flag">🌍 ${v.country} ${v.country_code?('('+v.country_code+')'):''}</div>`:''}</div>
      <div class="d-badge" id="dv-nav">${v.nav_status||'—'}</div>
    </div>
    <div class="sec"><div class="sec-t">🆔 شناسه‌ها</div>
      <div class="row"><span class="lbl">🆔 MMSI</span><span class="val">${v.mmsi}</span></div>
      ${v.imo?`<div class="row"><span class="lbl">🔢 IMO</span><span class="val">${v.imo}</span></div>`:''}
      ${v.callsign?`<div class="row"><span class="lbl">📻 Callsign</span><span class="val">${v.callsign}</span></div>`:''}
      ${v.country?`<div class="row"><span class="lbl">🌍 کشور</span><span class="val">${v.country}</span></div>`:''}
    </div>
    <div class="sec"><div class="sec-t">🧭 ناوبری</div>
      <div class="compass"><div class="compass-n">N</div>
        <div class="compass-arrow" id="dv-compass"
          style="transform:translate(-50%,-100%) rotate(0deg)"></div>
      </div>
      <div class="row" style="margin-top:10px"><span class="lbl">⚡ سرعت</span>
        <span class="val green" id="dv-speed">—</span></div>
      <div class="speed-bar"><div class="speed-fill" id="dv-speedbar" style="width:0%"></div></div>
      <div class="row"><span class="lbl">🧭 COG</span><span class="val" id="dv-cog">—</span></div>
      <div class="row"><span class="lbl">🎯 HDG</span><span class="val" id="dv-hdg">—</span></div>
    </div>
    <div class="sec"><div class="sec-t">📍 موقعیت</div>
      <div class="row"><span class="lbl">Latitude</span><span class="val" id="dv-lat">—</span></div>
      <div class="row"><span class="lbl">Longitude</span><span class="val" id="dv-lon">—</span></div>
      <div class="row"><span class="lbl">🕒 زمان</span><span class="val" id="dv-time" style="font-size:11px">—</span></div>
      ${v.source?`<div class="row"><span class="lbl">📡 منبع</span><span class="val">${v.source}</span></div>`:''}
    </div>
    ${(v.destination||v.eta)?`<div class="sec"><div class="sec-t">🎯 سفر</div>
      ${v.destination?`<div class="row"><span class="lbl">🎯 مقصد</span><span class="val">${v.destination}</span></div>`:''}
      ${v.eta?`<div class="row"><span class="lbl">⏰ ETA</span><span class="val">${v.eta}</span></div>`:''}
    </div>`:''}
    <div class="sec"><div class="sec-t">📡 مسیر</div>
      <div class="row"><span class="lbl">📍 نقاط ثبت‌شده</span><span class="val" id="dv-trail">0</span></div>
    </div>
    <div class="actions">
      <a href="${gmap}" target="_blank" class="btn">🗺️ Google Maps</a>
      <a href="${gimg}" target="_blank" class="btn">🔍 عکس واقعی</a>
      <button class="btn" onclick="loadHistory('${v.mmsi}')">📜 تاریخچه</button>
    </div>`;
  document.getElementById('drawer-body').innerHTML=html;
  document.getElementById('drawer').classList.add('open');
  updateDetailsLive(v);
}
function updateDetailsLive(v){
  if(!v) return;
  const $=id=>document.getElementById(id);
  if(!$('dv-speed')) return;
  $('dv-speed').textContent=v.speed!=null?Number(v.speed).toFixed(1)+' kn':'—';
  $('dv-cog').textContent=v.course!=null?v.course+'°':'—';
  $('dv-hdg').textContent=(v.heading&&v.heading!=511)?v.heading+'°':'—';
  $('dv-lat').textContent=v.lat!=null?Number(v.lat).toFixed(6):'—';
  $('dv-lon').textContent=v.lon!=null?Number(v.lon).toFixed(6):'—';
  $('dv-time').textContent=v.time_utc||'—';
  $('dv-nav').textContent=v.nav_status||'—';
  $('dv-trail').textContent=(v.trail||[]).length;
  $('dv-speedbar').style.width=Math.min(100,((Number(v.speed)||0)/25)*100)+'%';
  const hdg=(v.heading&&v.heading!=511)?v.heading:(v.course||0);
  $('dv-compass').style.transform=`translate(-50%,-100%) rotate(${hdg}deg)`;
}
async function loadHistory(mmsi){
  const res=await fetch(`/api/history/${mmsi}?hours=24`);
  const data=await res.json();
  if(data.history&&data.history.length>1){
    const coords=data.history.map(h=>[h.lon,h.lat]);
    if(map.getSource('history')){map.removeLayer('history');map.removeSource('history');}
    map.addSource('history',{type:'geojson',data:{type:'Feature',
      geometry:{type:'LineString',coordinates:coords}}});
    map.addLayer({id:'history',type:'line',source:'history',
      paint:{'line-color':'#f59e0b','line-width':3,'line-opacity':0.6}});
    alert(`📜 ${data.history.length} نقطه بارگذاری شد`);
  } else alert('تاریخچه‌ای یافت نشد');
}
document.getElementById('drawer-close').onclick=()=>{
  document.getElementById('drawer').classList.remove('open');
  selectedMMSI=null;
  highlightSelected();
  updateFocusedTrail(null);
};
document.getElementById('btn-fit').onclick=()=>{
  const pts=Object.values(vessels).filter(withPosition).map(v=>[v.lon,v.lat]);
  if(pts.length){
    const b=pts.reduce((acc,p)=>acc.extend(p),new maplibregl.LngLatBounds(pts[0],pts[0]));
    map.fitBounds(b,{padding:60,maxZoom:8});
  }
};
document.getElementById('btn-trails').onclick=function(){
  showTrails=!showTrails;
  this.classList.toggle('on',showTrails);
  if(map.getLayer('trails')) map.setLayoutProperty('trails','visibility',showTrails?'visible':'none');
};
document.getElementById('btn-predict').onclick=function(){
  showPredict=!showPredict;
  this.classList.toggle('on',showPredict);
  updatePredictions();
  if(map.getLayer('predict')) map.setLayoutProperty('predict','visibility',showPredict?'visible':'none');
};
document.getElementById('btn-military').onclick=function(){
  activeFilter=activeFilter==='military'?'all':'military';
  document.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
  const target=activeFilter==='military'?'military':'all';
  document.querySelectorAll('.chip').forEach(c=>{
    if(c.dataset.filter===target) c.classList.add('active');
  });
  this.classList.toggle('on',activeFilter==='military');
  lastListKey=''; scheduleRender();
};
document.getElementById('btn-hormuz').onclick=function(){
  map.flyTo({center:[56.4,26.6],zoom:8,speed:1.5});
  this.classList.toggle('on');
};
document.getElementById('search').addEventListener('input',()=>{lastListKey='';renderList();});
function popupHTML(v){
  const e=iconFor(v);
  const rows=[];
  const add=(l,val)=>{if(val!=null&&val!=='') rows.push(
    `<div class="row"><span class="lbl">${l}</span><span class="val">${val}</span></div>`);};
  add('🏷️ نوع',v.type_name);
  add('🌍 کشور',v.country);
  add('🎯 مقصد',v.destination);
  add('⚡ سرعت',v.speed!=null?Number(v.speed).toFixed(1)+' kn':null);
  add('🧭 COG',v.course!=null?v.course+'°':null);
  add('📊 وضعیت',v.nav_status);
  return `<div style="direction:rtl;font-family:inherit">
    <div style="font-size:14px;font-weight:700;color:#38bdf8;margin-bottom:8px">
      ${e} ${v.name||'نامشخص'}</div>
    ${rows.join('')}
    <div style="text-align:center;margin-top:6px;font-size:9px;color:#475569">👻 Cyber Ghost</div>
  </div>`;
}
function setConn(ok,text){
  const s=document.getElementById('conn-status');
  s.classList.toggle('off',!ok);
  document.getElementById('conn-text').textContent=text;
}
function updateSourceUI(sources){
  for(const name of ['aisstream','datadocked','synthetic']){
    const el=document.getElementById('src-'+name);
    if(!el) continue;
    const s=sources[name]||{};
    el.className='src-dot';
    if(s.state==='running') el.classList.add('on');
    else if(['idle','starting','connecting','reconnecting','rate-limited'].includes(s.state)) el.classList.add('warn');
    else if(s.state==='error'||s.state==='no-key') el.classList.add('err');
    el.title=`${name}: ${s.state} | reports=${s.reports||0}${s.error?' | '+s.error:''}`;
  }
}
async function pollSources(){
  try{
    const res=await fetch('/api/sources');
    const data=await res.json();
    updateSourceUI(data.sources||{});
  }catch(e){}
}
setInterval(pollSources,5000);
pollSources();
function connectWS(){
  const proto=location.protocol==='https:'?'wss':'ws';
  ws=new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen=()=>setConn(true,'متصل');
  ws.onmessage=(ev)=>{
    const msg=JSON.parse(ev.data);
    if(msg.type==='initial'){
      msg.vessels.forEach(v=>{
        const m=String(v.mmsi);
        vessels[m]=v; knownMMSI.add(m);
      });
      lastListKey=''; scheduleRender();
    }
    else if(msg.type==='alerts_init'){
      alerts=msg.alerts||[];
      renderAlerts();
      updateAlertBadge();
    }
    else if(msg.type==='alert'){
      alerts.unshift(msg.data);
      if(alerts.length>200) alerts.pop();
      renderAlerts();
      updateAlertBadge();
      showToast(`🚨 ${msg.data.name} — ${msg.data.direction}`);
    }
    else if(msg.type==='batch'){
      msg.updates.forEach(u=>{
        const mmsi=String(u.mmsi);
        const isNew=!knownMMSI.has(mmsi);
        if(isNew){knownMMSI.add(mmsi);}
        vessels[mmsi]=Object.assign(vessels[mmsi]||{},u.data);
        if(u.trail) vessels[mmsi].trail=u.trail;
      });
      scheduleRender();
      if(selectedMMSI&&vessels[selectedMMSI])
        updateDetailsLive(vessels[selectedMMSI]);
    }
    else if(msg.type==='remove'){
      msg.mmsi.forEach(m=>{
        if(markers[m]){markers[m].remove();delete markers[m];}
        delete vessels[m]; knownMMSI.delete(m);
        if(selectedMMSI===m){selectedMMSI=null;updateFocusedTrail(null);}
      });
      lastListKey=''; scheduleRender();
    }
    const vs=Object.values(vessels);
    const wp=vs.filter(withPosition);
    document.getElementById('kpi-v').textContent=wp.length;
    document.getElementById('kpi-m').textContent=wp.filter(v=>v.speed&&Number(v.speed)>1).length;
    document.getElementById('kpi-a').textContent=wp.filter(v=>!v.speed||Number(v.speed)<=1).length;
    document.getElementById('kpi-mil').textContent=wp.filter(v=>v.category==='military').length;
    document.getElementById('kpi-alerts').textContent=alerts.length;
    document.getElementById('kpi-alerts-total').textContent=alerts.length;
    document.getElementById('last-upd').textContent=new Date().toLocaleTimeString('fa-IR');
  };
  ws.onclose=()=>{setConn(false,'قطع — تلاش مجدد...');setTimeout(connectWS,2000);};
  ws.onerror=()=>setConn(false,'خطا');
}
function updateAlertBadge(){
  const b=document.getElementById('alerts-badge');
  const n=alerts.length;
  if(n>0){b.textContent=n>99?'99+':n;b.classList.add('show');}
  else b.classList.remove('show');
}
function scheduleRender(){
  if(renderScheduled) return;
  renderScheduled=true;
  requestAnimationFrame(()=>{
    renderList();
    renderMarkers();
    updateTrails();
    updatePredictions();
    renderScheduled=false;
  });
}
connectWS();
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  ▶️ Entry Point
# ═══════════════════════════════════════════════════════════════
def print_banner():
    lan_ip = get_lan_ip()
    local_url = f"http://localhost:{PORT}"
    lan_url = f"http://{lan_ip}:{PORT}"

    lines = [
        "╔" + "═" * 66 + "╗",
        "║" + " " * 15 + "🛰️  AIS GLOBAL TRACKER v16.1  🛰️" + " " * 13 + "║",
        "║" + " " * 24 + "👻  Cyber Ghost  👻" + " " * 23 + "║",
        "╠" + "═" * 66 + "╣",
        f"║  👨‍💻  سازنده :  {CREATOR_NAME:<44} ║",
        f"║  🆔  آیدی    :  {CREATOR_ID:<44} ║",
        f"║  📢  کانال   :  {CREATOR_CHANNEL:<44} ║",
        f"║  🔖  نسخه    :  {VERSION:<44} ║",
        "╠" + "═" * 66 + "╣",
        f"║  🖥️  لوکال   :  {local_url:<44} ║",
        f"║  📱  شبکه    :  {lan_url:<44} ║",
        "╠" + "═" * 66 + "╣",
        "║  📡  منابع   :  Synthetic + AISStream + DataDocked       ║",
        "║  🚨  هشدار   :  تنگه هرمز فعال                             ║",
        "╠" + "═" * 66 + "╣",
        "║" + " " * 6 + "⚡  Powered by Cyber Ghost  |  @Cyber_Ghost_error_404" + " " * 6 + "║",
        "╚" + "═" * 66 + "╝",
    ]
    for line in lines:
        print(line, flush=True)
    print(flush=True)


if __name__ == "__main__":
    print_banner()

    def open_browser():
        time.sleep(4)
        import webbrowser
        try:
            webbrowser.open(f"http://localhost:{PORT}")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host=HOST, port=PORT,
                log_level="warning", use_colors=False, access_log=False)
