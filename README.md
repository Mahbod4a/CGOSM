# 🛰️ AIS Global Tracker

> **Real-time global ship tracking with AIS data, Strait of Hormuz alerts, and an always-on synthetic fleet.**
>
> 👻 Powered by **Cyber Ghost** · 📢 [Channel](https://t.me/cyber_ghost_error_404_chanel) · 🆔 [ID](https://t.me/Cyber_Ghost_error_404)

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-Realtime-010101?logo=websocket&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [🚀 Quick Start](#-quick-start)
- [🔑 API Keys — How to Get Them](#-api-keys--how-to-get-them)
- [⚙️ Configuration](#️-configuration)
- [📡 Data Sources](#-data-sources)
- [🗺️ Usage](#️-usage)
- [🐳 Docker](#-docker)
- [📁 Project Structure](#-project-structure)
- [❓ Troubleshooting](#-troubleshooting)
- [🤝 Contributing](#-contributing)
- [📜 License](#-license)
- [👻 Credits](#-credits)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🌍 **Global AIS Coverage** | Live vessel positions from AISStream (worldwide bounding box) |
| 🚨 **Strait of Hormuz Alerts** | Real-time alerts when vessels enter/exit the polygon zone |
| 🎭 **Synthetic Fleet Fallback** | 350 simulated vessels keep the map alive when AIS is down |
| 🗺️ **Interactive Map** | MapLibre GL with dark theme, trails, and course prediction |
| 📊 **SQLite History** | Stores positions locally (WAL mode, no external DB needed) |
| 🔌 **WebSocket Push** | Live updates pushed to browser without polling |
| 🎖️ **Military Filter** | Special highlighting for military vessels |
| 📈 **KPI Dashboard** | Active / moving / anchored / military counters |
| 🧭 **Vessel Drawer** | Detailed panel with navigation data, compass, and Google Maps link |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Server                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  AISStream   │  │  DataDocked  │  │    Synthetic     │  │
│  │  Collector   │  │   Poller     │  │  Fleet Generator │  │
│  │  (WebSocket) │  │   (REST)     │  │    (Simulated)   │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └────────────┬────┴────────────────────┘            │
│                      ▼                                      │
│              ┌───────────────┐                              │
│              │  Vessel State │  (in-memory dict + trail)    │
│              │  + SQLite DB  │                              │
│              └───────┬───────┘                              │
│                      ▼                                      │
│              ┌───────────────┐                              │
│              │  Broadcaster  │──── WebSocket ──▶ Browser   │
│              └───────────────┘                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **pip** and **venv**
- Two free API keys (see [API Keys](#-api-keys--how-to-get-them))

### Install & Run

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/ais-global-tracker.git
cd ais-global-tracker

# 2. Create virtual environment
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env from template
cp .env.example .env

# 5. Edit .env and paste your API keys (see below)

# 6. Run
python CGOSM.py
```

Then open **http://localhost:7999** in your browser.

---

## 🔑 API Keys — How to Get Them

> ⚠️ **Never hard-code API keys in source code.**
> Always use environment variables or a `.env` file (see [Configuration](#️-configuration)).

### 1️⃣ AISStream API Key (Required for live AIS)

AISStream provides **free** global AIS data over WebSocket.

| Step | Action | Link |
|:---:|---|---|
| 1 | Go to the AISStream website | https://aisstream.io |
| 2 | Sign up / log in | https://aisstream.io/authenticate |
| 3 | Open your **Account** page | https://aisstream.io/account |
| 4 | Click **"Create New API Key"** | — |
| 5 | **Copy the key immediately** — it is shown only once | — |

> 📌 **Important:** Existing keys are masked on the dashboard. If you lose the key, you must **disable** it and create a new one.

**Put the key in your `.env` file:**

```env
AISSTREAM_API_KEY=your_aisstream_key_here
```

**Where it's used in code:**

```python
# CGOSM.py — line ~38
AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()
```

The key is sent inside the WebSocket subscription payload:

```python
await ws.send(json.dumps({
    "APIKey": AISSTREAM_API_KEY,
    "BoundingBoxes": [[[-90.0, -180.0], [90.0, 180.0]]],
    "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
}))
```

---

### 2️⃣ DataDocked API Key (Optional — REST enrichment)

DataDocked provides vessel details, port calls, and historical data via REST.

| Step | Action | Link |
|:---:|---|---|
| 1 | Sign up (free, **20 credits instantly**, no credit card) | https://datadocked.com/signup |
| 2 | Verify your email | — |
| 3 | Go to **Dashboard → My Keys** | https://datadocked.com/dashboard/my_keys |
| 4 | **Copy your API key** — created automatically on signup | — |

> 📌 The API key is passed in the **`x-api-key`** header, **not** as a query parameter.

**Put the key in your `.env` file:**

```env
DATADOCKED_API_KEY=your_datadocked_key_here
```

**Where it's used in code:**

```python
# CGOSM.py — line ~43
DATADOCKED_API_KEY = os.environ.get("DATADOCKED_API_KEY", "").strip()
```

And in the REST request headers:

```python
headers = {
    "accept": "application/json",
    "x-api-key": DATADOCKED_API_KEY,
}
url = f"https://datadocked.com/api/vessels_operations/get-vessel-location?imo_or_mmsi={ident}"
```

---

### 📋 `.env.example` Template

Create a file named `.env.example` in your repo root:

```env
# ═══════════════════════════════════════════════════════════════
#  AIS Global Tracker — Environment Configuration
# ═══════════════════════════════════════════════════════════════

# ── API Keys (REQUIRED for live data) ──────────────────────────
# Get from https://aisstream.io/account
AISSTREAM_API_KEY=

# Get from https://datadocked.com/dashboard/my_keys
DATADOCKED_API_KEY=

# ── Server ─────────────────────────────────────────────────────
AIS_HOST=0.0.0.0
AIS_PORT=7999

# ── Data ───────────────────────────────────────────────────────
# Optional: custom data directory (default: ./AIS_Data)
# AIS_DATA_DIR=/var/lib/ais-tracker

# ── Security (optional) ────────────────────────────────────────
# Comma-separated allowed origins (default: *)
# AIS_ALLOWED_ORIGINS=http://localhost:7999,http://192.168.1.100:7999
```

### 🔒 `.gitignore` — Must Have

```gitignore
# Environment secrets
.env

# Data
AIS_Data/
*.db
*.db-shm
*.db-wal
*.log

# Python
__pycache__/
*.py[cod]
venv/
.venv/

# IDE
.vscode/
.idea/
*.swp
```

> 🚨 **CRITICAL:** If you already committed a real key, **revoke it immediately** on the provider's dashboard. Bots scan GitHub for leaked keys within minutes.

---

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `AISSTREAM_API_KEY` | `""` | AISStream API key (required for live AIS) |
| `DATADOCKED_API_KEY` | `""` | DataDocked API key (optional) |
| `AIS_HOST` | `0.0.0.0` | Bind address |
| `AIS_PORT` | `7999` | HTTP / WebSocket port |
| `AIS_DATA_DIR` | `./AIS_Data` | SQLite DB and log directory |
| `AIS_ALLOWED_ORIGINS` | `*` | CORS allowed origins |

---

## 📡 Data Sources

| Source | Type | Key Required | Status |
|---|---|---|---|
| **AISStream** | WebSocket (live AIS) | ✅ `AISSTREAM_API_KEY` | 🟢 Primary |
| **DataDocked** | REST (vessel details) | ✅ `DATADOCKED_API_KEY` | 🟡 Enrichment |
| **Synthetic Fleet** | Simulated | ❌ None | 🟢 Always on |

**Fallback logic:**

- If AISStream disconnects → automatic reconnect with exponential backoff
- If no live data at all → synthetic fleet keeps the map populated
- Synthetic vessels follow real shipping lanes (Persian Gulf, Suez, Malacca, etc.)

---

## 🗺️ Usage

### Web Interface

| URL | Description |
|---|---|
| `http://localhost:7999` | Main dashboard |
| `http://YOUR_LAN_IP:7999` | Access from other devices on your network |

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Server health + vessel count |
| `/api/metrics` | GET | Reports, alerts, WebSocket clients |
| `/api/sources` | GET | Status of each data source |
| `/api/alerts` | GET | Latest Hormuz alerts |
| `/api/history/{mmsi}` | GET | Position history (last N hours) |
| `/ws` | WebSocket | Real-time updates |

### Map Controls

| Button | Function |
|---|---|
| 🎯 | Fit all vessels in view |
| 〰️ | Toggle trail lines |
| 🔮 | Toggle course prediction |
| 🎖️ | Filter military vessels only |
| 🕌 | Fly to Strait of Hormuz |

---

## 🐳 Docker

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV AIS_DATA_DIR=/data
VOLUME /data
EXPOSE 7999

CMD ["python", "CGOSM.py"]
```

```bash
# Build
docker build -t ais-tracker .

# Run (pass keys via env)
docker run -d \
  --name ais-tracker \
  -p 7999:7999 \
  -e AISSTREAM_API_KEY=your_key \
  -e DATADOCKED_API_KEY=your_key \
  -v ais-data:/data \
  ais-tracker
```

### `requirements.txt`

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
websockets>=13.0
```

---

## 📁 Project Structure

```
ais-global-tracker/
├── CGOSM.py                 # Main application (single-file)
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
├── .gitignore               # Git ignore rules
├── Dockerfile               # Container definition
├── README.md                # This file
├── LICENSE                  # MIT License
└── AIS_Data/                # Created at runtime (gitignored)
    ├── ais_history.db       # SQLite database
    └── ais_tracker.log      # Application log
```

> 💡 **Tip:** For a cleaner structure, split `HTML_PAGE` into `templates/index.html` + `static/app.js` + `static/style.css` and use `Jinja2Templates`.

---

## ❓ Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| `HTTP 429` from AISStream | Rate limit | Wait 60–300s; code auto-retries |
| `AISSTREAM_API_KEY تنظیم نشده` | Key missing | Add key to `.env` |
| No vessels on map | AISStream down | Synthetic fleet will appear; check `/api/sources` |
| `403 Forbidden` (DataDocked) | Invalid key | Regenerate key in dashboard |
| Port already in use | Another process | Change `AIS_PORT` in `.env` |
| Map tiles not loading | Internet blocked | Check OSM tile access |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure your code follows **PEP 8** and includes appropriate comments.

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 👻 Credits

| | |
|---|---|
| **Creator** | Cyber Ghost |
| **Telegram ID** | [@Cyber_Ghost_error_404](https://t.me/Cyber_Ghost_error_404) |
| **Telegram Channel** | [@cyber_ghost_error_404_chanel](https://t.me/cyber_ghost_error_404_chanel) |
| **Version** | v16.1 — Ultimate Edition |

**Built with:** Python · FastAPI · WebSockets · MapLibre GL · SQLite

---

<p align="center">
  <b>🛰️ AIS Global Tracker</b><br>
  <i>Powered by Cyber Ghost</i><br>
  <a href="https://t.me/cyber_ghost_error_404_chanel">📢 Join the Channel</a>
</p>
