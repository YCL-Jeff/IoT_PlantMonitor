<div align="center">

# 🌿 IoT Plant Monitor
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

This specialized monitoring system is designed for plant and mycelium cultivation. By combining **ESP32** hardware with a **Python Flask** server, it eliminates data lag and write-blocking issues found in traditional systems, providing millisecond-level responsiveness.

### 📸 Showcase
<div align="center">
  <img src="https://github.com/user-attachments/assets/a669b270-cf96-4f16-8d8b-b727d93cb76f" alt="Plant Monitor Dashboard Preview" width="800">
  <p><em>Dynamic UI color shifts, real-time latency detection, and multi-timeframe trend charts.</em></p>
</div>

### ✨ Key Features
* **🚀 Extreme Performance**: SQLite **WAL Mode** for concurrent R/W; Multi-threaded architecture ensures 0 data loss even during heavy stats processing.
* **🧠 Smart Algorithms**: Built-in **EWMA Filter** (Alpha 0.5) for noise reduction; **Adaptive Logging** triggers immediate writes during rapid temp shifts (>0.2°C).
* **🎨 Interactive UI**: Modern Glassmorphism design with auto-background color shifts and live data "age" tracking (`2s ago`).

### 🔌 Hardware Setup
1.  **Wiring**: Connect DHT22/AHT10 DATA to ESP32 **GPIO 4**, along with VCC/GND.
2.  **Firmware**: Flash the code in the `firmware/` directory using Arduino IDE.

### 💻 Software Installation
1.  **Dependencies**: `pip install -r requirements.txt`
2.  **Config**: Update `SERIAL_PORT` in `server.py` to match your device (e.g., `COM3` or `/dev/cu.usbserial-xxx`).
3.  **Run**: `python server.py` (On Mac, use `caffeinate -i python server.py` to prevent sleep).

### 🌐 Remote Access (Cloudflare Tunnel)
Bypass firewalls and monitor your plants from anywhere:
bash
cloudflared tunnel --protocol http2 --url http://localhost:5555
<a name="繁體中文"></a>

## 繁體中文
v8.5 版本更新 | 高精度數據核心 • 專業抗噪演算法

本系統專為需要精準溫控的植物與菌絲培養環境設計。透過開啟資料庫 WAL 模式與多執行緒異步處理，解決了傳統監控軟體在長時間運行後容易產生的「數據卡頓」與「時空跳躍」問題。

### ✨ 核心功能
* **🚀 極致效能**：SQLite WAL 模式支援高併發讀寫；多執行緒架構分離數據接收與統計運算。
* **🧠 智慧演算法**：EWMA (Alpha 0.5) 濾波器過濾雜訊；自適應寫入 (Adaptive Logging) 捕捉劇烈溫變。
* **🎨 互動式 UI**：毛玻璃風格介面，背景隨溫度自動變色，支援即時延遲偵測 (`2s ago`)。

### 🔌 硬體架設
1.  **接線**：ESP32 GPIO 4 連接感測器 DATA，並接通 VCC/GND。
2.  **韌體**：使用 Arduino IDE 燒錄 `firmware/` 資料夾中的代碼。

### 💻 軟體安裝
1.  **依賴**：`pip install -r requirements.txt`
2.  **設定**：修改 `server.py` 中的 `SERIAL_PORT` 為您的連接埠。
3.  **啟動**：`python server.py` (Mac 建議使用 `caffeinate -i python server.py`)

### 🌐 遠端連線 (Cloudflare Tunnel)
執行以下指令穿透防火牆：
```bash
cloudflared tunnel --protocol http2 --url http://localhost:5555
```

📁 專案結構 / Structure

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
