"""
DeskMind - 番茄钟模块
与焦点检测联动，在检测到高强度编码时段自动开始计时
"""

import time
import threading
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "deskmind.db"
OLLAMA_URL = "http://localhost:11434/api/chat"


class PomodoroTimer:
    """番茄钟状态机"""

    # 状态常量
    IDLE = "idle"           # 未开始
    WORKING = "working"     # 工作中
    BREAK = "break"         # 休息中

    def __init__(self):
        self._state = self.IDLE
        self._start_time = None
        self._remaining = 0
        self._work_duration = 25 * 60    # 默认 25 分钟
        self._break_duration = 5 * 60    # 默认 5 分钟
        self._completed_pomodoros = 0
        self._lock = threading.Lock()
        self._on_state_change = None     # 回调函数

    def configure(self, work_min=25, break_min=5):
        """配置番茄钟时长"""
        with self._lock:
            self._work_duration = work_min * 60
            self._break_duration = break_min * 60

    def set_callback(self, callback):
        """设置状态变化回调 callback(state, remaining_seconds)"""
        self._on_state_change = callback

    @property
    def state(self):
        return self._state

    @property
    def remaining(self):
        """剩余秒数"""
        if self._state == self.IDLE or self._start_time is None:
            return 0
        elapsed = time.time() - self._start_time
        return max(0, self._remaining - elapsed)

    @property
    def progress(self):
        """进度 0.0 ~ 1.0"""
        if self._state == self.IDLE:
            return 0
        total = self._work_duration if self._state == self.WORKING else self._break_duration
        return min(1.0, 1.0 - (self.remaining / total)) if total > 0 else 0

    @property
    def completed_count(self):
        return self._completed_pomodoros

    def start_work(self):
        """开始一个工作番茄"""
        with self._lock:
            self._state = self.WORKING
            self._start_time = time.time()
            self._remaining = self._work_duration
        self._notify()

    def start_break(self):
        """开始休息"""
        with self._lock:
            self._state = self.BREAK
            self._start_time = time.time()
            self._remaining = self._break_duration
        self._notify()

    def stop(self):
        """停止当前番茄"""
        with self._lock:
            self._state = self.IDLE
            self._start_time = None
            self._remaining = 0
        self._notify()

    def check_auto_transition(self):
        """检查是否需要自动转换状态，返回新状态或 None"""
        if self._state == self.WORKING and self.remaining <= 0:
            with self._lock:
                self._completed_pomodoros += 1
                self._save_pomodoro()
            return self.BREAK
        elif self._state == self.BREAK and self.remaining <= 0:
            return self.IDLE
        return None

    def to_dict(self):
        return {
            "state": self._state,
            "remaining": round(self.remaining),
            "progress": round(self.progress, 2),
            "completed_count": self._completed_pomodoros,
            "work_duration": self._work_duration,
            "break_duration": self._break_duration,
        }

    def _notify(self):
        if self._on_state_change:
            try:
                self._on_state_change(self._state, self.remaining)
            except Exception:
                pass

    def _save_pomodoro(self):
        """保存完成的番茄钟记录"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pomodoro_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL
                )
            """)
            end = datetime.now()
            start = end - timedelta(seconds=self._work_duration)
            conn.execute(
                "INSERT INTO pomodoro_log (start_time, end_time, duration_minutes) VALUES (?, ?, ?)",
                (start.isoformat(), end.isoformat(), self._work_duration // 60)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# 全局单例
pomodoro = PomodoroTimer()


def get_pomodoro_stats(days=7):
    """获取最近 N 天的番茄钟统计"""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    # 确保表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pomodoro_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL
        )
    """)
    rows = conn.execute(
        "SELECT date(start_time) as d, COUNT(*) as count, SUM(duration_minutes) as total_min FROM pomodoro_log WHERE start_time >= ? GROUP BY d ORDER BY d",
        (start,)
    ).fetchall()
    conn.close()
    return [{"date": r[0], "count": r[1], "total_minutes": r[2]} for r in rows]
