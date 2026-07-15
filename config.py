"""
DeskMind - 配置管理模块
所有用户可配置项的持久化存储和读取
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "deskmind.db"

# 默认配置
DEFAULTS = {
    "tracker_interval": 5,          # 追踪间隔（秒）
    "idle_timeout": 60,             # idle 超时（秒）
    "distraction_threshold": 300,   # 非工作应用提醒阈值（秒）
    "light_distraction_threshold": 900,  # 轻度分心阈值（秒）
    "alert_cooldown": 1800,         # 提醒冷却时间（秒）
    "alert_enabled": True,          # 是否启用提醒
    "ollama_model": "qwen2.5:1.5b", # 默认 AI 模型
    "pomodoro_work": 25,            # 番茄钟工作时间（分钟）
    "pomodoro_break": 5,            # 番茄钟休息时间（分钟）
    "pomodoro_enabled": False,      # 是否启用番茄钟
}

# 内存缓存
_cache = {}


def _init_db():
    """确保配置表存在"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    # 插入缺失的默认值
    for k, v in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (k, json.dumps(v))
        )
    conn.commit()
    conn.close()


def get(key, default=None):
    """获取配置项"""
    if default is None:
        default = DEFAULTS.get(key)
    if key in _cache:
        return _cache[key]
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        if row:
            val = json.loads(row[0])
            _cache[key] = val
            return val
    except Exception:
        pass
    return default


def set(key, value):
    """设置配置项"""
    _cache[key] = value
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_all():
    """获取所有配置"""
    result = dict(DEFAULTS)
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        for k, v in rows:
            result[k] = json.loads(v)
    except Exception:
        pass
    return result


def reset(key=None):
    """重置配置为默认值"""
    global _cache
    if key:
        _cache.pop(key, None)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(DEFAULTS[key]))
        )
        conn.commit()
        conn.close()
    else:
        _cache.clear()
        conn = sqlite3.connect(str(DB_PATH))
        for k, v in DEFAULTS.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (k, json.dumps(v))
            )
        conn.commit()
        conn.close()


# 模块加载时初始化
_init_db()
