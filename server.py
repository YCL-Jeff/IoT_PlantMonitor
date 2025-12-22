import serial
import threading
import time
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from collections import deque
from flask import Flask, render_template, jsonify, request

# --- ★★★ HARDWARE CONFIG ★★★ ---
# 請確認這是你的正確 Port
SERIAL_PORT = '/dev/cu.usbserial-0001' 
BAUD_RATE = 115200
DB_FILE = 'plant_data.db'
SERVER_PORT = 5555
SERVER_START_TIME = time.time()

# 寫入資料庫限流 (秒) - 避免資料庫太大，每5秒存一次即可
CSV_WRITE_INTERVAL = 5 

app = Flask(__name__)

# --- 1. Database Handler (SQLite with WAL) ---
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        # 開啟 WAL 模式，避免寫入時讀取被鎖死 (卡頓主因之一)
        conn.execute('PRAGMA journal_mode=WAL;') 
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS readings 
                     (timestamp REAL PRIMARY KEY, temp REAL, humi REAL)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_time ON readings (timestamp)''')
        conn.commit()
        conn.close()
        print(">>> Database Initialized (WAL Mode).")
    except Exception as e:
        print(f">>> DB Init Failed: {e}")

def save_to_db(temp, humi):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=1) 
        c = conn.cursor()
        c.execute("INSERT INTO readings VALUES (?, ?, ?)", (time.time(), temp, humi))
        conn.commit()
        conn.close()
        return True
    except: return False

def get_stats_from_db():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        c = conn.cursor()
        one_day_ago = time.time() - 86400
        c.execute("SELECT MAX(temp), MIN(temp) FROM readings WHERE timestamp > ?", (one_day_ago,))
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None:
            return round(float(row[0]), 1), round(float(row[1]), 1)
    except: pass
    return "--", "--"

def get_history_from_db(hours):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        c = conn.cursor()
        start_time = time.time() - (hours * 3600)
        c.execute("SELECT timestamp, temp FROM readings WHERE timestamp > ? ORDER BY timestamp ASC", (start_time,))
        rows = c.fetchall()
        conn.close()
        
        times = []
        temps = []
        
        # 降採樣邏輯，避免長時間圖表點數過多導致瀏覽器卡頓
        total_points = len(rows)
        limit = 1500 
        step = 1
        if hours > 1 and total_points > limit:
            step = int(total_points / limit)
            
        for i in range(0, total_points, step):
            ts = rows[i][0]
            val = rows[i][1]
            dt_obj = datetime.fromtimestamp(ts)
            
            if hours <= 24: t_str = dt_obj.strftime('%H:%M')
            else: t_str = dt_obj.strftime('%m/%d %H:%M')
                
            times.append(t_str)
            temps.append(val)
            
        return times, temps
    except: return [], []

# --- 2. Logic Core ---
class PlantMonitor:
    def __init__(self):
        self.ewma_temp = None
        self.start_time = time.time()
        self.daily_swing = 0.0
        self.daily_max = None
        self.daily_min = None
        
        # 預設狀態設為 GOOD，避免剛啟動時 UI 沒顏色
        self.status_level = "GOOD"
        self.reason = "Initializing..."
        
        # ★ RAM 緩衝區：改存原始 Timestamp (float) 以便精準過濾 1H 數據
        self.ram_cache_ts = deque(maxlen=4000)
        self.ram_cache_temp = deque(maxlen=4000)

    def preload_data(self):
        """從資料庫回填最近的數據到 RAM，讓圖表重開機後不會空白"""
        try:
            if not os.path.exists(DB_FILE): return
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT timestamp, temp FROM readings ORDER BY timestamp DESC LIMIT 4000")
            rows = c.fetchall()
            conn.close()
            
            for r in reversed(rows):
                self.ram_cache_ts.append(r[0])
                self.ram_cache_temp.append(r[1])
                
            if rows:
                self.ewma_temp = rows[0][1]
                self._analyze_health()
            print(f">>> Preloaded {len(rows)} records.")
        except: pass

    def update_24h_stats(self):
        max_t, min_t = get_stats_from_db()
        if max_t != "--" and min_t != "--":
            self.daily_max = max_t
            self.daily_min = min_t
            self.daily_swing = round(self.daily_max - self.daily_min, 1)
        else:
            self.daily_swing = 0.0

    def add_reading(self, raw_temp):
        now_ts = time.time()
        
        # EWMA 濾波器 (Alpha 0.5)
        if self.ewma_temp is None: self.ewma_temp = raw_temp
        else: self.ewma_temp = (0.5 * raw_temp) + (0.5 * self.ewma_temp)
        
        # 存入 RAM
        self.ram_cache_ts.append(now_ts)
        self.ram_cache_temp.append(self.ewma_temp)
        
        self._analyze_health()
        return self.ewma_temp

    def _analyze_health(self):
        """核心健康判斷邏輯 - 對應前端 CSS class"""
        if (time.time() - self.start_time) < 5: 
            self.reason = "Sensor Ready"
            return
        curr = self.ewma_temp
        if curr is None: return

        # ★★★ 新版 6 級狀態判斷 ★★★
        if curr >= 28.0:
            self.status_level = "DANGER"
            self.reason = f"❌ DANGER! Too Hot (≥28°C)"
        elif curr >= 25.0:
            self.status_level = "WARN"
            self.reason = f"⚠️ Warning: Brief Only (25-27°C)"
        elif curr >= 23.0:
            self.status_level = "GOOD"
            self.reason = f"✅ Good Growth (23-24°C)"
        elif curr >= 20.0:
            self.status_level = "BEST"
            self.reason = f"⭐ Perfect Zone (20-22°C)"
        elif curr >= 16.0:
            self.status_level = "COLD"
            self.reason = f"❄️ Slow but Safe (16-19°C)"
        else:
            self.status_level = "FREEZE"
            self.reason = f"🧊 Almost Stopped (≤15°C)"

monitor = PlantMonitor()

# --- 3. Backend Variables ---
current_data = {
    "temp": 0.0, "humi": 0.0, "status": "Connecting...", 
    "last_update": "--", "max_24h": "--", "min_24h": "--", "swing_24h": "--",
    "swing_val": 0.0, 
    "uptime": "0m", "guard_level": "GOOD", "guard_msg": "",
    "ts": 0 
}

def get_uptime_str():
    seconds = int(time.time() - SERVER_START_TIME)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0: return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"

# --- Thread: 背景統計運算 ---
def stats_worker():
    time.sleep(2)
    while True:
        try:
            monitor.update_24h_stats()
            current_data["max_24h"] = monitor.daily_max if monitor.daily_max else "--"
            current_data["min_24h"] = monitor.daily_min if monitor.daily_min else "--"
            current_data["swing_24h"] = monitor.daily_swing
            current_data["swing_val"] = monitor.daily_swing
        except: pass
        time.sleep(10) 

# --- Thread: 讀取 Serial ---
def read_serial():
    global current_data
    print(f"Monitor Started: {SERIAL_PORT}")
    monitor.preload_data()
    last_write_time = 0
    
    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print(">>> Connected.")
            current_data["status"] = "Online"
            monitor.start_time = time.time()
            ser.reset_input_buffer()
            
            while True:
                if ser.in_waiting > 0:
                    try:
                        data_block = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                        lines = data_block.split('\n')
                        last_valid_line = None
                        for line in reversed(lines):
                            if "," in line:
                                try:
                                    p = line.strip().split(",")
                                    float(p[0]); float(p[1])
                                    last_valid_line = line
                                    break
                                except: continue
                        if not last_valid_line: continue

                        parts = last_valid_line.split(",")
                        raw_t = float(parts[0])
                        h = float(parts[1])

                        now = datetime.now()
                        smooth_t = monitor.add_reading(raw_t)

                        # 定時寫入 DB
                        if (time.time() - last_write_time) > CSV_WRITE_INTERVAL:
                            if save_to_db(smooth_t, h):
                                last_write_time = time.time()
                        
                        current_data.update({
                            "temp": round(smooth_t, 2), "humi": h, 
                            "last_update": now.strftime("%H:%M:%S"), "status": "Online",
                            "guard_level": monitor.status_level, "guard_msg": monitor.reason,
                            "uptime": get_uptime_str(),
                            "ts": time.time() 
                        })
                    except: continue
                time.sleep(0.05)
        except:
            current_data["status"] = "Reconnecting..."
            time.sleep(5)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return r

@app.route('/api/live')
def live_data(): return jsonify(current_data)

@app.route('/api/history')
def get_history():
    range_str = request.args.get('range', '1h')
    
    # ★★★ 1H 模式：嚴格時間過濾 ★★★
    if range_str == '1h':
        cutoff_time = time.time() - 3600 # 只取過去 3600 秒
        
        cached_ts = list(monitor.ram_cache_ts)
        cached_temp = list(monitor.ram_cache_temp)
        
        filtered_labels = []
        filtered_temp = []
        
        for ts, temp in zip(cached_ts, cached_temp):
            if ts > cutoff_time:
                # 轉成 "時:分:秒" 格式傳給前端
                dt_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                filtered_labels.append(dt_str)
                filtered_temp.append(round(temp, 2))
                
        return jsonify({
            "labels": filtered_labels,
            "temp": filtered_temp,
            "max_temp": 0
        })

    hours_map = {'1h': 1, '6h': 6, '12h': 12, '24h': 24, '7d': 168}
    hours = hours_map.get(range_str, 1)
    
    times, temps = get_history_from_db(hours)
    max_t = max(temps) if temps else 0
    
    return jsonify({ "labels": times, "temp": temps, "max_temp": max_t })

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    init_db()
    t = threading.Thread(target=stats_worker)
    t.daemon = True
    t.start()
    
    print(f"★★★ Plant Monitor v8.9 (Final Logic) Started ★★★")
    threading.Thread(target=read_serial, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)