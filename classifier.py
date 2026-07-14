"""
DeskMind - AI 自动分类器
用 Ollama 本地模型替代规则分类，支持缓存 + 降级
"""

import sqlite3
import json
import time
import threading
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent / "deskmind.db"
OLLAMA_URL = "http://localhost:11434/api/chat"

# 所有合法类别
VALID_CATEGORIES = [
    "development", "terminal", "ai_tool", "ai_chat",
    "tech_reading", "browser", "video",
    "communication", "office", "entertainment",
    "file_manager", "other"
]

CATEGORY_LABELS_ZH = {
    "development": "开发工具", "terminal": "终端", "ai_tool": "AI 工具", "ai_chat": "AI 对话",
    "tech_reading": "技术阅读", "browser": "浏览器", "video": "视频",
    "communication": "通讯工具", "office": "办公软件", "entertainment": "娱乐",
    "file_manager": "文件管理", "other": "其他"
}

_cache = {}  # 内存缓存 (process_name, title_prefix) -> category
_cache_lock = threading.Lock()
_ollama_available = True  # AI 是否可用
_last_ollama_check = 0


def _init_db():
    """确保分类缓存表存在"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS category_cache (
            process_name TEXT NOT NULL,
            title_prefix TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (process_name, title_prefix)
        )
    """)
    conn.commit()
    conn.close()


def _load_cache():
    """启动时从数据库加载缓存到内存"""
    global _cache
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT process_name, title_prefix, category FROM category_cache"
    ).fetchall()
    conn.close()
    with _cache_lock:
        for proc, title, cat in rows:
            _cache[(proc, title)] = cat
    if _cache:
        print(f"[DeskMind Classifier] 已加载 {len(_cache)} 条分类缓存")


def _check_ollama_available():
    """检查 Ollama 是否可用（每 60 秒最多检查一次）"""
    global _ollama_available, _last_ollama_check
    now = time.time()
    if now - _last_ollama_check < 60:
        return _ollama_available
    _last_ollama_check = now
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                _ollama_available = True
            else:
                _ollama_available = False
    except Exception:
        _ollama_available = False
    return _ollama_available


def _call_ollama_classify(process_name, window_title):
    """调用 Ollama 进行分类，使用极简 prompt 以获得快速响应"""
    import urllib.request
    import urllib.error

    prompt = f"""将以下电脑应用分类到唯一一个类别中。

进程名: {process_name}
窗口标题: {window_title}

可选类别: {', '.join(VALID_CATEGORIES)}

只输出类别名，不要输出其他任何内容。"""

    payload = json.dumps({
        "model": "qwen2.5:1.5b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 20}
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result.get("message", {}).get("content", "") or result.get("response", "")
            text = text.strip().lower()
            # 提取有效类别
            for cat in VALID_CATEGORIES:
                if cat in text:
                    return cat
            return None
    except Exception:
        return None


def _save_to_cache(process_name, title_prefix, category):
    """保存分类结果到数据库和内存缓存"""
    with _cache_lock:
        _cache[(process_name, title_prefix)] = category
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO category_cache (process_name, title_prefix, category, created_at) VALUES (?, ?, ?, ?)",
            (process_name, title_prefix, category, time.time())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def classify(process_name, window_title, rule_based_fallback=None):
    """
    对应用进行 AI 分类。

    参数:
        process_name: 进程名
        window_title: 窗口标题
        rule_based_fallback: 降级用的规则分类函数（即 tracker.py 的 categorize_app）

    返回:
        category 字符串
    """
    # 生成缓存 key（标题取前 30 字符）
    title_prefix = window_title[:30]
    cache_key = (process_name, title_prefix)

    # 1. 查内存缓存
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    # 2. 如果 Ollama 不可用，直接降级
    if not _check_ollama_available():
        if rule_based_fallback:
            return rule_based_fallback(process_name, window_title)
        return "other"

    # 3. 调用 AI 分类
    category = _call_ollama_classify(process_name, window_title)

    if category and category in VALID_CATEGORIES:
        _save_to_cache(process_name, title_prefix, category)
        return category

    # 4. AI 失败，降级到规则
    if rule_based_fallback:
        return rule_based_fallback(process_name, window_title)
    return "other"


def get_cache_stats():
    """获取缓存统计"""
    with _cache_lock:
        cat_counts = defaultdict(int)
        for _, cat in _cache.items():
            cat_counts[cat] += 1
        return {
            "total_cached": len(_cache),
            "by_category": dict(sorted(cat_counts.items(), key=lambda x: -x[1])),
            "ollama_available": _ollama_available
        }


def clear_cache():
    """清空分类缓存"""
    global _cache
    with _cache_lock:
        _cache.clear()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM category_cache")
    conn.commit()
    conn.close()
    print("[DeskMind Classifier] 缓存已清空")


# 模块加载时初始化
_init_db()
_load_cache()