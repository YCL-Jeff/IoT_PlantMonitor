<div align="center">

# 🌿 IoT Plant Monitor ─ BOTANIC
### High-Precision Environmental Monitoring System

[![GitHub release](https://img.shields.io/badge/Release-v8.5-brightgreen.svg)](https://github.com/YCL-Jeff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

[**English**](#english) | [**繁體中文**](#繁體中文)

</div>

---

<a name="english"></a>
## English

> **v8.5 Release** | High Precision • Non-Blocking Architecture • Real-time Visualization

This specialized monitoring system is designed for high-precision plant cultivation and environmental monitoring. By combining **ESP32** hardware with a **Python Flask** server, it eliminates data lag and write-blocking issues found in traditional systems, providing millisecond-level responsiveness.

### 📸 Showcase
<div align="center">
  <img src="https://github.com/user-attachments/assets/409fec77-cf11-4398-8f25-260af3fc9a30" alt="Plant Monitor Dashboard Preview" width="380">
  <p><em>Dynamic UI color shifts, real-time latency detection, and multi-timeframe trend charts.</em></p>
</div>


### ✨ Key Features
* **🚀 Extreme Performance**: SQLite **WAL Mode** for concurrent R/W; Multi-threaded architecture ensures 0 data loss even during heavy stats processing.
* **🧠 Smart Algorithms**: Built-in **EWMA Filter** (Alpha 0.5) for noise reduction; **Adaptive Logging** triggers immediate writes during rapid temp shifts (>0.2°C).
* **🎨 Interactive UI**: Modern Glassmorphism design with auto-background color shifts and live data "age" tracking (`2s ago`).

### 🔌 Hardware Setup
1. **Wiring**: Connect DHT22/AHT10 DATA to ESP32 **GPIO 4**, along with VCC/GND.
2. **Firmware**: Flash the code in the `firmware/` directory using Arduino IDE.

### 💻 Software Installation
1. **Dependencies**: `pip install -r requirements.txt`
2. **Config**: Update `SERIAL_PORT` in `server.py` to match your device (e.g., `COM3` or `/dev/cu.usbserial-xxx`).
3. **Run**: `python server.py` (On Mac, use `caffeinate -i python server.py` to prevent sleep).

### 🌐 Remote Access (Cloudflare Tunnel)
Bypass firewalls and monitor your plants from anywhere:

cloudflared tunnel --protocol http2 --url http://localhost:5555

<a name="繁體中文"></a>

<div align="center">

# 🌿 IoT Plant Monitor ─ BOTANIC
### 高精度植物環境監控系統

[![GitHub release](https://img.shields.io/badge/Release-v8.5-brightgreen.svg)](https://github.com/YCL-Jeff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

</div>

---

> **v8.5 版本更新** | 高精度數據 • 抗噪演算法 • 即時數據視覺化

本系統專為需要精準環境監控與植物栽培設計。結合 **ESP32** 硬體與 **Python Flask** 後端伺服器，透過開啟資料庫 WAL 模式與多執行緒異步處理，解決了傳統監控軟體在長時間運行後容易產生的數據卡頓與寫入阻塞問題，提供毫秒級的即時響應。

### 📸 介面展示
<div align="center">
  <img src="https://github.com/user-attachments/assets/409fec77-cf11-4398-8f25-260af3fc9a30" alt="Plant Monitor Dashboard Preview" width="380">
  <p><em>動態 UI 色彩變化、即時延遲偵測與多時間軸趨勢圖表。</em></p>
</div>

### ✨ 核心功能
* **🚀 極致效能**：SQLite **WAL 模式**支援高併發讀寫；多執行緒架構分離數據接收與統計運算，高負載下資料不遺失。
* **🧠 智慧演算法**：內建 **EWMA (Alpha 0.5)** 濾波器過濾訊號雜訊；**自適應寫入 (Adaptive Logging)** 在溫溼度劇烈變化時（>0.2°C）立即觸發儲存。
* **🎨 互動式 UI**：現代毛玻璃風格介面，背景顏色隨溫度自動轉變，並支援資料更新時間追蹤（如 `2s ago`）。

### 🔌 硬體架設
1. **接線方式**：將 DHT22/AHT10 的 DATA 引腳連接至 ESP32 **GPIO 4**，並接通 VCC 與 GND。
2. **韌體燒錄**：使用 Arduino IDE 將 `firmware/` 資料夾內的程式碼燒錄至 ESP32。

### 💻 軟體安裝與執行
1. **安裝依賴套件**：
   ```bash
   pip install -r requirements.txt

```text

.
├── firmware/          # ESP32 Firmware (C++)
├── server.py          # Python Core (Flask + SQLite)
├── requirements.txt   # Dependencies List
├── .gitignore         # Git ignore rules (Excluded venv & db)
└── README.md          # Documentation
```

📝 License
Distributed under the MIT License. See LICENSE for more information.
