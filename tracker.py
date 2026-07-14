"""
DeskMind - 多维度电脑行为追踪器 v2
采集维度：窗口信息、按键频率、鼠标活动、idle 状态、浏览器 URL
"""

import sqlite3
import time
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

DB_PATH = Path(__file__).parent / "deskmind.db"
IDLE_TIMEOUT = 60  # 超过 60 秒无鼠标/键盘活动 = idle
TRACK_INTERVAL = 5  # 每 5 秒采集一次窗口信息

from classifier import classify as ai_classify


# ============ 事件计数器（线程安全） ============

class EventCounter:
    """累计一段时间内的按键和鼠标事件数"""
    def __init__(self):
        self._lock = threading.Lock()
        self._key_count = 0
        self._click_count = 0
        self._move_count = 0
        self._last_active_time = time.time()

    def record_key(self):
        with self._lock:
            self._key_count += 1
            self._last_active_time = time.time()

    def record_click(self):
        with self._lock:
            self._click_count += 1
            self._last_active_time = time.time()

    def record_move(self):
        with self._lock:
            self._move_count += 1
            self._last_active_time = time.time()

    def snapshot_and_reset(self):
        """获取当前计数并归零，返回 (keys, clicks, moves, seconds_since_last_activity)"""
        with self._lock:
            data = (
                self._key_count,
                self._click_count,
                self._move_count,
                round(time.time() - self._last_active_time, 1)
            )
            self._key_count = 0
            self._click_count = 0
            self._move_count = 0
            return data

    @property
    def is_idle(self):
        return (time.time() - self._last_active_time) > IDLE_TIMEOUT


counter = EventCounter()


# ============ 键盘/鼠标钩子 ============

def _setup_hooks():
    """安装全局键盘鼠标钩子"""
    try:
        from pynput import keyboard, mouse
    except ImportError:
        print("[DeskMind] 正在安装 pynput...")
        import subprocess
        subprocess.check_call(["pip", "install", "pynput", "-q"])
        from pynput import keyboard, mouse

    def on_key(event):
        # 忽略修饰键单独按下
        if hasattr(event, 'name') and event.name in ('shift', 'ctrl', 'alt', 'cmd'):
            return
        counter.record_key()

    def on_click(x, y, button, pressed):
        if pressed:
            counter.record_click()

    def on_move(x, y):
        counter.record_move()

    kb_listener = keyboard.Listener(on_press=on_key)
    ms_listener = mouse.Listener(on_click=on_click, on_move=on_move)
    kb_listener.daemon = True
    ms_listener.daemon = True
    kb_listener.start()
    ms_listener.start()
    print("[DeskMind] 键盘/鼠标钩子已安装")


# ============ 浏览器 URL 采集 ============

def get_chrome_url():
    """通过 Chrome DevTools Protocol 获取当前标签页 URL（需要 Chrome 以 debug 模式启动）"""
    try:
        import urllib.request
        import json as _json

        # 获取 Chrome debug 页面列表
        req = urllib.request.Request("http://localhost:9222/json", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            tabs = _json.loads(resp.read().decode())

        # 找到当前活跃标签
        for tab in tabs:
            if tab.get("type") == "page" and tab.get("url", "").startswith("http"):
                return tab["url"]
        return ""
    except Exception:
        return ""


def get_browser_url_from_title(process_name, window_title):
    """从窗口标题中提取 URL（降级方案，不需要 debug 模式）"""
    p = process_name.lower()
    if not any(x in p for x in ["chrome", "msedge", "firefox", "brave"]):
        return ""

    # Chrome/Edge 标题格式通常是 "网页标题 - Google Chrome"
    # 尝试从标题中提取域名信息
    if " - " in window_title:
        # 不是 URL，但可以提取有用信息
        return ""
    return ""


# ============ 数据库 ============

def init_db():
    """初始化/迁移数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    # 检查是否需要迁移（旧表没有新字段）
    cols = conn.execute("PRAGMA table_info(activity_log)").fetchall()
    col_names = [c[1] for c in cols]

    if col_names:
        if "key_count" not in col_names:
            conn.execute("ALTER TABLE activity_log ADD COLUMN key_count INTEGER DEFAULT 0")
        if "click_count" not in col_names:
            conn.execute("ALTER TABLE activity_log ADD COLUMN click_count INTEGER DEFAULT 0")
        if "is_idle" not in col_names:
            conn.execute("ALTER TABLE activity_log ADD COLUMN is_idle INTEGER DEFAULT 0")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            process_name TEXT NOT NULL,
            window_title TEXT NOT NULL,
            category TEXT DEFAULT 'uncategorized',
            key_count INTEGER DEFAULT 0,
            click_count INTEGER DEFAULT 0,
            is_idle INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON activity_log(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON activity_log(category)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            app_usage_json TEXT,
            total_active_minutes REAL DEFAULT 0,
            total_idle_minutes REAL DEFAULT 0,
            total_key_strokes INTEGER DEFAULT 0,
            total_clicks INTEGER DEFAULT 0,
            ai_analysis TEXT
        )
    """)
    conn.commit()
    conn.close()
    print(f"[DeskMind] 数据库已就绪: {DB_PATH}")


# ============ 窗口信息采集 ============

def get_active_window():
    """获取当前活动窗口信息"""
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return "unknown", "unknown"

    title = win32gui.GetWindowText(hwnd) or "unknown"
    _, pid = win32process.GetWindowThreadProcessId(hwnd)

    process_name = "unknown"
    try:
        import psutil
        proc = psutil.Process(pid)
        process_name = proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        process_name = f"pid_{pid}"

    return process_name, title


def categorize_app(process_name, window_title):
    """增强分类：浏览器、开发工具、通讯、办公、娱乐等"""
    p = process_name.lower()
    t = window_title.lower()

    # 浏览器 - 细分
    if any(x in p for x in ["chrome", "msedge", "firefox", "brave"]):
        if any(x in t for x in ["github", "stackoverflow", "csdn", "juejin", "zhihu"]):
            return "tech_reading"
        elif any(x in t for x in ["bilibili", "youtube", "netflix", "douyin", "tiktok"]):
            return "video"
        elif any(x in t for x in ["chatgpt", "claude", "gemini", "deepseek", "kimi"]):
            return "ai_chat"
        else:
            return "browser"

    # 开发工具 - 细分
    elif any(x in p for x in ["code", "cursor", "windsurf", "zed", "idea", "pycharm"]):
        return "development"
    elif any(x in p for x in ["terminal", "cmd", "powershell", "windowsterminal"]):
        return "terminal"
    elif "ollama" in p or "trae" in p:
        return "ai_tool"

    # 通讯
    elif any(x in p for x in ["wechat", "qq", "dingtalk", "feishu", "telegram", "discord"]):
        return "communication"

    # 办公
    elif any(x in p for x in ["word", "excel", "powerpnt", "wps", "notion"]):
        return "office"

    # 娱乐
    elif any(x in p for x in ["spotify", "cloudmusic", "steam"]):
        return "entertainment"

    # 文件管理
    elif "explorer" in p:
        return "file_manager"

    else:
        return "other"


# ============ 主追踪循环 ============

def log_activity():
    """采集一次完整的行为快照"""
    process_name, window_title = get_active_window()
    category = ai_classify(process_name, window_title, rule_based_fallback=categorize_app)
    is_idle = counter.is_idle
    keys, clicks, moves, idle_secs = counter.snapshot_and_reset()
    timestamp = datetime.now().isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """INSERT INTO activity_log 
           (timestamp, process_name, window_title, category, key_count, click_count, is_idle) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, process_name, window_title, category, keys, clicks, int(is_idle))
    )
    conn.commit()
    conn.close()

    return {
        "process": process_name,
        "title": window_title[:50],
        "category": category,
        "keys": keys,
        "clicks": clicks,
        "moves": moves,
        "idle_secs": idle_secs,
        "is_idle": is_idle,
    }


def run_tracker(interval=5):
    """持续追踪"""
    init_db()
    _setup_hooks()

    print(f"[DeskMind] 开始多维度追踪，每 {interval} 秒采样一次")
    print(f"[DeskMind] 采集维度: 窗口 | 按键频率 | 鼠标活动 | idle 检测")
    print(f"[DeskMind] idle 阈值: {IDLE_TIMEOUT} 秒无操作")
    print("-" * 70)
    print(f"{'时间':8s} {'类别':16s} {'按键':>4s} {'点击':>4s} {'空闲':>5s}  {'进程':20s}  {'标题'}")
    print("-" * 70)

    try:
        while True:
            data = log_activity()
            now = datetime.now().strftime("%H:%M:%S")
            idle_mark = "💤" if data["is_idle"] else "  "
            print(f"{now} {data['category']:16s} {data['keys']:4d} {data['clicks']:4d} {idle_mark} {data['idle_secs']:5.1f}s  {data['process']:20s}  {data['title']}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[DeskMind] 追踪已停止，数据已保存")


if __name__ == "__main__":
    run_tracker()