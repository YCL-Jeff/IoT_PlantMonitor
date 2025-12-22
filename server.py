import serial
import threading
import time
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from collections import deque
from flask import Flask, render_template_string, jsonify, request

# --- ★★★ HARDWARE CONFIG ★★★ ---
SERIAL_PORT = '/dev/cu.usbserial-0001' 
BAUD_RATE = 115200
DB_FILE = 'plant_data.db'
SERVER_PORT = 5555
SERVER_START_TIME = time.time()

# 寫入限流 (秒)
CSV_WRITE_INTERVAL = 5 

app = Flask(__name__)

# --- 1. Database Handler (SQLite with WAL) ---
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute('PRAGMA journal_mode=WAL;') # 開啟不卡頓模式
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
            # ★★★ 修正：強制取小數點後 1 位 ★★★
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
        self.status_level = "NORMAL"
        self.reason = "Initializing..."
        
        self.ram_cache_time = deque(maxlen=2000)
        self.ram_cache_temp = deque(maxlen=2000)

    def preload_data(self):
        try:
            if not os.path.exists(DB_FILE): return
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT timestamp, temp FROM readings ORDER BY timestamp DESC LIMIT 2000")
            rows = c.fetchall()
            conn.close()
            
            for r in reversed(rows):
                dt_str = datetime.fromtimestamp(r[0]).strftime('%H:%M')
                self.ram_cache_time.append(dt_str)
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
        now = datetime.now()
        # Alpha 0.5 高靈敏度
        if self.ewma_temp is None: self.ewma_temp = raw_temp
        else: self.ewma_temp = (0.5 * raw_temp) + (0.5 * self.ewma_temp)
        
        self.ram_cache_time.append(now.strftime('%H:%M'))
        self.ram_cache_temp.append(self.ewma_temp)
        
        self._analyze_health()
        return self.ewma_temp

    def _analyze_health(self):
        if (time.time() - self.start_time) < 5: 
            self.reason = "Sensor Ready"
            return
        curr = self.ewma_temp
        if curr is None: return

        if curr >= 26.5:
            self.status_level = "ALERT"
            self.reason = f"High Temp! Bacteria Risk (>26.5°C)"
        elif curr >= 24.0:
            self.status_level = "WARN"
            self.reason = f"Warm Area (>24°C)"
        elif curr < 17.0:
            self.status_level = "COLD"
            self.reason = f"Cold! Growth Slow (<17°C)"
        else:
            self.status_level = "NORMAL"
            self.reason = "Optimal Growth Zone"

monitor = PlantMonitor()

# --- 3. Backend Variables ---
current_data = {
    "temp": 0.0, "humi": 0.0, "status": "Connecting...", 
    "last_update": "--", "max_24h": "--", "min_24h": "--", "swing_24h": "--",
    "swing_val": 0.0, 
    "uptime": "0m", "guard_level": "NORMAL", "guard_msg": "",
    "ts": 0 # Unix Timestamp for frontend latency calc
}

def get_uptime_str():
    seconds = int(time.time() - SERVER_START_TIME)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0: return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"

# --- Background Stats Thread ---
def stats_worker():
    time.sleep(2)
    while True:
        try:
            # ★★★ 修正：每 10 秒更新一次 Max/Min，不用等 5 分鐘 ★★★
            monitor.update_24h_stats()
            current_data["max_24h"] = monitor.daily_max if monitor.daily_max else "--"
            current_data["min_24h"] = monitor.daily_min if monitor.daily_min else "--"
            current_data["swing_24h"] = monitor.daily_swing
            current_data["swing_val"] = monitor.daily_swing
        except: pass
        time.sleep(10) 

# --- Main Thread (Real-Time) ---
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
                        # Buffer Drain Strategy
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

                        if (time.time() - last_write_time) > CSV_WRITE_INTERVAL:
                            if save_to_db(smooth_t, h):
                                last_write_time = time.time()
                        
                        current_data.update({
                            "temp": round(smooth_t, 2), "humi": h, 
                            "last_update": now.strftime("%H:%M:%S"), "status": "Online",
                            "guard_level": monitor.status_level, "guard_msg": monitor.reason,
                            "uptime": get_uptime_str(),
                            "ts": time.time() # 傳送當下時間戳記
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
    
    if range_str == '1h':
        return jsonify({
            "labels": list(monitor.ram_cache_time),
            "temp": [round(x, 2) for x in list(monitor.ram_cache_temp)],
            "max_temp": 0
        })

    hours_map = {'1h': 1, '6h': 6, '12h': 12, '24h': 24, '7d': 168}
    hours = hours_map.get(range_str, 1)
    
    times, temps = get_history_from_db(hours)
    max_t = max(temps) if temps else 0
    
    return jsonify({ "labels": times, "temp": temps, "max_temp": max_t })

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

# --- 3. UI Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Plant Monitor v8.5</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;500;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { 
            --bg: #000000; 
            --glass-bg: rgba(28, 28, 30, 0.6);
            --text: #ffffff; 
            --sub: #8e8e93;
            --cold: #a0e1ff;  --cold-glow: rgba(160, 225, 255, 0.4);
            --safe: #30d158;  --safe-glow: rgba(48, 209, 88, 0.3);
            --warn: #ffd60a;  --warn-glow: rgba(255, 214, 10, 0.3);
            --alert: #ff453a; --alert-glow: rgba(255, 69, 58, 0.4);
            --info: #0a84ff;
        }
        body { font-family: 'Inter', -apple-system, sans-serif; background: radial-gradient(circle at 50% 0%, #1c1c1e 0%, #000000 100%); color: var(--text); margin: 0; padding: 20px; min-height: 100vh; }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 50px; }
        .card { border-radius: 30px; padding: 35px 25px; position: relative; margin-bottom: 20px; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.5s ease; }
        
        .card.level-COLD { background: linear-gradient(145deg, rgba(28,28,30,0.6), rgba(160,225,255,0.1)); box-shadow: 0 0 40px rgba(160,225,255,0.2), inset 0 0 20px rgba(160,225,255,0.05); border-color: rgba(160,225,255,0.4); }
        .card.level-COLD .temp-val { background: linear-gradient(180deg, #ffffff, #a0e1ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0 0 15px rgba(160,225,255,0.5)); }
        .card.level-NORMAL { background: linear-gradient(145deg, rgba(28,28,30,0.6), rgba(48,209,88,0.08)); box-shadow: 0 0 40px rgba(48, 209, 88, 0.15), inset 0 0 20px rgba(48, 209, 88, 0.05); border-color: rgba(48, 209, 88, 0.3); }
        .card.level-NORMAL .temp-val { background: linear-gradient(180deg, #30d158, #1c8538); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0 0 15px rgba(48,209,88,0.4)); }
        .card.level-WARN { background: linear-gradient(145deg, rgba(28,28,30,0.7), rgba(255,214,10,0.15)); box-shadow: 0 0 50px rgba(255, 214, 10, 0.3), inset 0 0 30px rgba(255, 214, 10, 0.1); border-color: var(--warn); animation: breathe 3s infinite ease-in-out; }
        .card.level-WARN .temp-val { background: linear-gradient(180deg, #ffd60a, #9e8405); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0 0 15px rgba(255,214,10,0.4)); }
        .card.level-ALERT { background: linear-gradient(145deg, rgba(40,10,10,0.8), rgba(255,69,58,0.2)); box-shadow: 0 0 60px rgba(255, 69, 58, 0.4), inset 0 0 40px rgba(255, 69, 58, 0.2); border-color: var(--alert); animation: pulse 1s infinite; }
        .card.level-ALERT .temp-val { background: linear-gradient(180deg, #ff453a, #94261f); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0 0 20px rgba(255,69,58,0.6)); }

        @keyframes breathe { 0%, 100% { opacity: 1; border-color: rgba(255,214,10,0.5); } 50% { opacity: 0.85; border-color: rgba(255,214,10,0.2); } }
        @keyframes pulse { 0% { transform: scale(1); border-color: var(--alert); } 50% { transform: scale(1.01); border-color: rgba(255,69,58,0.5); } 100% { transform: scale(1); border-color: var(--alert); } }

        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; opacity: 0.7; }
        .title { font-weight: 700; font-size: 0.8rem; letter-spacing: 1px; text-transform: uppercase; color: var(--sub); }
        .status-pill { font-size: 0.75rem; font-weight: 600; display: flex; align-items: center; gap: 6px; }
        .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--sub); }
        .dot.online { background: var(--safe); box-shadow: 0 0 8px var(--safe); }
        
        /* New Latency Text */
        .latency-msg { font-size: 0.65rem; color: #666; margin-left: 5px; font-weight: 400; }

        .main-display { display: flex; align-items: center; justify-content: center; gap: 30px; margin: 25px 0; }
        .temp-group { text-align: right; }
        .temp-val { font-size: 5.5rem; font-weight: 800; line-height: 1; letter-spacing: -3px; }
        .unit { font-size: 1.5rem; font-weight: 500; color: var(--sub); vertical-align: top; margin-left: 2px; }

        .extremes-stack { display: flex; flex-direction: column; gap: 15px; align-items: flex-start; }
        .ex-item { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.1; }
        .ex-label { font-size: 0.7rem; font-weight: 700; color: var(--sub); letter-spacing: 0.5px; margin-bottom: 2px; }
        .ex-val { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.5px; }
        .max-txt { color: var(--alert); text-shadow: 0 0 10px rgba(255, 69, 58, 0.4); }
        .min-txt { color: var(--info); text-shadow: 0 0 10px rgba(10, 132, 255, 0.4); }

        .msg-box { text-align: center; min-height: 1.2rem; font-size: 0.95rem; font-weight: 500; color: var(--sub); margin-bottom: 5px; letter-spacing: 0.3px; }
        .footer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 30px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1); }
        .stat-item { display: flex; flex-direction: column; align-items: center; }
        .stat-lbl { font-size: 0.65rem; color: var(--sub); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
        .stat-val { font-size: 1.1rem; font-weight: 600; color: #fff; }

        .swing-safe { color: var(--safe); text-shadow: 0 0 10px rgba(48, 209, 88, 0.3); }
        .swing-warn { color: var(--warn); text-shadow: 0 0 10px rgba(255, 214, 10, 0.3); }
        .swing-alert { color: var(--alert); text-shadow: 0 0 15px rgba(255, 69, 58, 0.5); }

        .chart-box { background: rgba(28, 28, 30, 0.6); border-radius: 24px; padding: 20px; box-shadow: 0 0 0 1px rgba(255,255,255,0.1); backdrop-filter: blur(20px); }
        .time-controls { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; background: rgba(118, 118, 128, 0.24); padding: 3px; border-radius: 10px; margin-bottom: 15px; }
        .time-btn { border: none; background: transparent; padding: 6px 0; font-size: 0.75rem; font-weight: 600; color: var(--sub); cursor: pointer; border-radius: 7px; transition: 0.2s; }
        .time-btn.active { background: rgba(99, 99, 102, 0.8); color: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
        .chart-container { position: relative; height: 300px; width: 100%; }
        .chart-footer { margin-top: 15px; text-align: center; font-size: 0.7rem; color: var(--sub); font-weight: 500; letter-spacing: 0.5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card level-NORMAL" id="mainCard">
            <div class="header">
                <div class="title">Plant Monitor</div>
                <div class="status-pill">
                    <div id="dot" class="dot"></div>
                    <span id="conn">Wait...</span>
                    <span id="latency" class="latency-msg"></span>
                </div>
            </div>
            <div id="guardMsg" class="msg-box">Loading...</div>
            <div class="main-display">
                <div class="temp-group"><span id="temp" class="temp-val">--</span><span class="unit">°C</span></div>
                <div class="extremes-stack">
                    <div class="ex-item"><span class="ex-label">MAX</span><span id="max24" class="ex-val max-txt">--</span></div>
                    <div class="ex-item"><span class="ex-label">MIN</span><span id="min24" class="ex-val min-txt">--</span></div>
                </div>
            </div>
            <div class="footer-grid">
                <div class="stat-item"><span class="stat-lbl">Humidity</span><span class="stat-val"><span id="humi">--</span>%</span></div>
                <div class="stat-item"><span class="stat-lbl">Daily Swing</span><span class="stat-val" id="swing24">--</span></div>
            </div>
        </div>
        <div class="chart-box">
            <div class="time-controls">
                <button onclick="changeRange('1h', this)" class="time-btn active">1H</button>
                <button onclick="changeRange('6h', this)" class="time-btn">6H</button>
                <button onclick="changeRange('12h', this)" class="time-btn">12H</button>
                <button onclick="changeRange('24h', this)" class="time-btn">24H</button>
                <button onclick="changeRange('7d', this)" class="time-btn">7D</button>
            </div>
            <div class="chart-container"><canvas id="chart"></canvas></div>
            <div class="chart-footer">Run Time: <span id="uptime">0m</span></div>
        </div>
    </div>
    <script>
        let chart; let currentRange = '1h'; let lastTs = 0;
        window.onload = function() { initChart(); loop(); setInterval(updateLatency, 1000); };
        
        function updateLatency() {
            if(lastTs === 0) return;
            const sec = Math.floor((Date.now()/1000) - lastTs);
            const el = document.getElementById('latency');
            el.innerText = sec + "s ago";
            // If data is stale (>10s), warn user visually
            if(sec > 10) el.style.color = '#ff453a'; else el.style.color = '#666';
        }

        function initChart() {
            const ctx = document.getElementById('chart').getContext('2d');
            chart = new Chart(ctx, { 
                type: 'line', 
                data: { labels: [], datasets: [{ 
                    label: 'Temp', 
                    data: [], 
                    borderColor: '#30d158', 
                    borderWidth: 2.5, 
                    pointRadius: 0, 
                    cubicInterpolationMode: 'monotone', 
                    fill: true, 
                    backgroundColor: 'rgba(48, 209, 88, 0.05)' 
                }] }, 
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: true, grid: { display: false }, ticks: { color: '#636366', font: { size: 9 }, maxTicksLimit: 6, maxRotation: 0 } }, y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8e8e93', font: { size: 10 } } } } } 
            });
        }
        async function loop() {
            try {
                const res = await fetch('/api/live?t=' + new Date().getTime()); const data = await res.json();
                document.getElementById('temp').innerText = data.temp;
                document.getElementById('humi').innerText = data.humi;
                document.getElementById('guardMsg').innerText = data.guard_msg;
                document.getElementById('max24').innerText = data.max_24h;
                document.getElementById('min24').innerText = data.min_24h;
                document.getElementById('uptime').innerText = data.uptime;
                
                // Update Timestamp
                if(data.ts) lastTs = data.ts;

                const swingElem = document.getElementById('swing24');
                swingElem.innerText = data.swing_24h + (data.swing_24h !== '--' ? '°C' : '');
                swingElem.className = 'stat-val';
                if (data.swing_24h !== '--') {
                    let s = parseFloat(data.swing_24h);
                    if (s >= 7.0) swingElem.classList.add('swing-alert');
                    else if (s >= 3.5) swingElem.classList.add('swing-warn');
                    else swingElem.classList.add('swing-safe');
                }
                const dot = document.getElementById('dot');
                if(data.status === "Online") { dot.classList.add('online'); document.getElementById('conn').innerText="Online"; } else { dot.classList.remove('online'); document.getElementById('conn').innerText=data.status; }
                const card = document.getElementById('mainCard');
                card.className = `card level-${data.guard_level}`;
                if(chart) {
                    let c = '#30d158'; let bg = 'rgba(48, 209, 88, 0.05)';
                    if(data.guard_level === 'ALERT') { c = '#ff453a'; bg = 'rgba(255, 69, 58, 0.1)'; }
                    else if(data.guard_level === 'WARN') { c = '#ffd60a'; bg = 'rgba(255, 214, 10, 0.1)'; }
                    else if(data.guard_level === 'COLD') { c = '#a0e1ff'; bg = 'rgba(160, 225, 255, 0.1)'; }
                    chart.data.datasets[0].borderColor = c;
                    chart.data.datasets[0].backgroundColor = bg;
                    chart.update('none');
                }
                updateChart();
            } catch(e) {}
            setTimeout(loop, 3000);
        }
        async function updateChart() {
            try {
                const hRes = await fetch(`/api/history?range=${currentRange}&t=` + new Date().getTime()); const hData = await hRes.json();
                if(chart) { chart.data.labels = hData.labels; chart.data.datasets[0].data = hData.temp; chart.update('none'); }
            } catch(e) {}
        }
        function changeRange(range, btn) { currentRange = range; document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); updateChart(); }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    init_db()
    t = threading.Thread(target=stats_worker)
    t.daemon = True
    t.start()
    
    print(f"★★★ Plant Monitor v8.5 (Live Debug) Started ★★★")
    threading.Thread(target=read_serial, daemon=True).start()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)