import os
import time
import csv
from collections import deque

# ===== 可調參數 =====
CSV_PATH = "temp.csv"     # 你的檔名
POLL_S = 1.0              # 每秒檢查一次檔案有沒有新增
SAMPLE_PERIOD_S = 5       # 你的取樣週期（預期 5 秒一筆）

# 門檻：更偏「保護菌絲」的設定
DT_5S_MAX = 0.4           # 5秒內跳變
DT_15S_MAX = 0.7          # 15秒內跳變
SLOPE_1M_WARM = 1.0       # °C/min
SLOPE_1M_COOL = -0.8      # °C/min
SLOPE_3M_WARM = 0.6       # °C/min
SLOPE_3M_COOL = -0.5      # °C/min
DELTA_1M_MAX = 2.0        # 1分鐘總變化
DELTA_3M_MAX = 3.5        # 3分鐘總變化

# 平滑（避免感測器抖動誤報）
EWMA_ALPHA = 0.2


def parse_row(row: dict):
    """
    允許兩種 CSV 欄位：
      1) ts,temp
      2) temp
    """
    if "temp" not in row:
        raise ValueError("CSV 必須有 'temp' 欄位")

    temp = float(row["temp"])

    ts = None
    if "ts" in row and row["ts"].strip():
        # 允許 "YYYY-mm-dd HH:MM:SS"
        # 若你要更自由格式，可以改成 dateutil parser，但這裡先保持純標準庫
        from datetime import datetime
        ts = datetime.strptime(row["ts"].strip(), "%Y-%m-%d %H:%M:%S").timestamp()
    else:
        ts = time.time()

    return ts, temp


class TempMonitor:
    def __init__(self):
        self.buf = deque()  # (ts, temp_smoothed)
        self.temp_ewma = None

    def _push(self, ts, temp):
        # EWMA 平滑
        if self.temp_ewma is None:
            self.temp_ewma = temp
        else:
            self.temp_ewma = EWMA_ALPHA * temp + (1 - EWMA_ALPHA) * self.temp_ewma

        self.buf.append((ts, self.temp_ewma))

        # 保留 3 分鐘資料
        cutoff = ts - 180
        while self.buf and self.buf[0][0] < cutoff:
            self.buf.popleft()

    def _get_at_or_after(self, cutoff_ts):
        for ts, t in self.buf:
            if ts >= cutoff_ts:
                return ts, t
        return None

    def _rate_and_delta(self, window_s):
        if len(self.buf) < 2:
            return None
        ts_now, t_now = self.buf[-1]
        start = self._get_at_or_after(ts_now - window_s)
        if not start:
            return None
        ts0, t0 = start
        dt = ts_now - ts0
        if dt < window_s * 0.7:
            return None
        delta = t_now - t0
        slope = (delta / dt) * 60.0
        return slope, delta

    def update(self, ts, temp_raw):
        self._push(ts, temp_raw)

        alerts = []

        # 瞬間跳變：5s, 15s（用最接近的點）
        ts_now, t_now = self.buf[-1]

        def delta_over(sec):
            start = self._get_at_or_after(ts_now - sec)
            if not start:
                return None
            _, t0 = start
            return t_now - t0

        d5 = delta_over(5)
        d15 = delta_over(15)

        if d5 is not None and abs(d5) > DT_5S_MAX:
            alerts.append(f"[WARN] 5秒跳變過大 ΔT={d5:+.2f}°C (>{DT_5S_MAX})")
        if d15 is not None and abs(d15) > DT_15S_MAX:
            alerts.append(f"[ALERT] 15秒跳變過大 ΔT={d15:+.2f}°C (>{DT_15S_MAX})")

        # 1m / 3m 斜率與總變化
        r1 = self._rate_and_delta(60)
        if r1:
            slope1, delta1 = r1
            if abs(delta1) > DELTA_1M_MAX:
                alerts.append(f"[WARN] 1分鐘總變化過大 ΔT={delta1:+.2f}°C (>{DELTA_1M_MAX})")
            if slope1 > SLOPE_1M_WARM:
                alerts.append(f"[WARN] 1分鐘升溫太快 slope={slope1:+.2f}°C/min (>{SLOPE_1M_WARM})")
            if slope1 < SLOPE_1M_COOL:
                alerts.append(f"[WARN] 1分鐘降溫太快 slope={slope1:+.2f}°C/min (<{SLOPE_1M_COOL})")

        r3 = self._rate_and_delta(180)
        if r3:
            slope3, delta3 = r3
            if abs(delta3) > DELTA_3M_MAX:
                alerts.append(f"[ALERT] 3分鐘總變化過大 ΔT={delta3:+.2f}°C (>{DELTA_3M_MAX})")
            if slope3 > SLOPE_3M_WARM:
                alerts.append(f"[ALERT] 3分鐘升溫太快 slope={slope3:+.2f}°C/min (>{SLOPE_3M_WARM})")
            if slope3 < SLOPE_3M_COOL:
                alerts.append(f"[ALERT] 3分鐘降溫太快 slope={slope3:+.2f}°C/min (<{SLOPE_3M_COOL})")

        return self.buf[-1][1], alerts


def follow_csv_new_lines(path):
    """
    像 tail -f 一樣追蹤 CSV 新增行。
    1) 檔案不存在就等
    2) 檔案被覆寫(大小變小)就自動從頭讀
    """
    last_size = 0
    f = None

    while True:
        if not os.path.exists(path):
            print(f"[INFO] 找不到檔案：{path}，等待中...")
            time.sleep(1)
            continue

        size = os.path.getsize(path)

        # 檔案第一次開 / 被覆寫
        if f is None or size < last_size:
            if f:
                f.close()
            f = open(path, "r", newline="", encoding="utf-8")
            reader = csv.DictReader(f)
            # 先把舊資料讀完（你也可以改成只讀最後N行）
            for _ in reader:
                pass
            print(f"[INFO] 開始追蹤 {path}（欄位：{reader.fieldnames}）")
            last_size = os.path.getsize(path)

        # 讀新增資料
        where = f.tell()
        line = f.readline()
        if not line:
            f.seek(where)
            time.sleep(POLL_S)
            last_size = os.path.getsize(path)
            continue

        # DictReader 需要用它的方式解析，所以我們把該行用 csv 解析成 dict
        # 這裡用同一個 header
        f.seek(where)
        chunk = f.readline()
        # 用 DictReader 的 header 解析單行
        header = None
        # 重新讀 header（最簡單穩）
        f2 = open(path, "r", newline="", encoding="utf-8")
        reader2 = csv.DictReader(f2)
        header = reader2.fieldnames
        f2.close()

        values = next(csv.reader([chunk.strip()]))
        if header and len(values) == len(header):
            yield dict(zip(header, values))
        else:
            print(f"[WARN] CSV 行格式不對：{chunk.strip()}")
        last_size = os.path.getsize(path)


def main():
    mon = TempMonitor()
    last_ts = 0

    for row in follow_csv_new_lines(CSV_PATH):
        try:
            ts, temp = parse_row(row)
        except Exception as e:
            print(f"[ERROR] 解析失敗：{e} row={row}")
            continue

        # 基本 sanity：避免同一筆重複或時間倒退
        if ts <= last_ts:
            ts = time.time()
        last_ts = ts

        t_smooth, alerts = mon.update(ts, temp)
        print(f"T_raw={temp:.2f}C  T_smooth={t_smooth:.2f}C")

        for a in alerts:
            print("  " + a)


if __name__ == "__main__":
    main()
