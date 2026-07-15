"""
DeskMind - 智能干扰提醒
基于窗口类别和 idle 状态，在非工作应用上停留过久时提醒
"""

import time
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent / "deskmind.db"

# 配置
CHECK_INTERVAL = 30          # 每 30 秒检查一次
DISTRACTION_THRESHOLD = 300  # 非工作应用连续 5 分钟触发提醒
COOLDOWN = 1800              # 同类提醒 30 分钟内不重复

# 非工作类别（在这些类别上长时间停留会被提醒）
NON_PRODUCTIVE = {"video", "entertainment", "browser", "other"}
# 轻度分心（阈值更高，15 分钟）
LIGHT_DISTRACTION = {"communication", "ai_chat"}

_last_alert = {}  # {category: timestamp}


def get_recent_category_streak():
    """
    查询最近一段时间内当前类别的连续停留时间
    返回 (category, duration_seconds, process_name)
    """
    try:
        import win32gui
        import win32process
        import psutil

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or "unknown"
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process_name = psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_name = f"pid_{pid}"

        # 查询最近 N 分钟内该进程的连续记录
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        # 查最近 30 分钟的记录，倒序
        cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
        rows = conn.execute(
            "SELECT category, timestamp, is_idle FROM activity_log WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,)
        ).fetchall()
        conn.close()

        if not rows:
            return None, 0, process_name

        current_cat = rows[0]["category"]
        streak_seconds = 0
        for r in rows:
            if r["category"] == current_cat and not r["is_idle"]:
                streak_seconds += 5  # 每条记录 5 秒
            else:
                break

        return current_cat, streak_seconds, process_name

    except Exception:
        return None, 0, ""


def _show_notification(title, message):
    """显示 Windows 桌面通知"""
    try:
        from ctypes import windll
        # 使用 Windows Toast 通知的简化版本
        # 通过 PowerShell 触发（兼容性最好）
        import subprocess
        ps_script = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("DeskMind").Show($toast)
        '''
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        # 降级：打印到控制台
        print(f"[DeskMind Alert] {title}: {message}")


def _check_and_alert():
    """检查是否需要提醒"""
    global _last_alert

    category, duration, process_name = get_recent_category_streak()
    if not category:
        return

    now = time.time()

    # 判断阈值
    if category in NON_PRODUCTIVE:
        threshold = DISTRACTION_THRESHOLD  # 5 分钟
    elif category in LIGHT_DISTRACTION:
        threshold = 900  # 15 分钟
    else:
        return  # 工作类应用不提醒

    # 检查冷却
    last = _last_alert.get(category, 0)
    if now - last < COOLDOWN:
        return

    if duration >= threshold:
        mins = int(duration / 60)
        _last_alert[category] = now

        # 根据类别生成不同提醒
        messages = {
            "video": f"你已经在视频平台上停留了 {mins} 分钟，休息一下眼睛或者切回工作？",
            "entertainment": f"娱乐时间已 {mins} 分钟，要不要回顾一下今天的待办？",
            "browser": f"无目的浏览已 {mins} 分钟，有具体的搜索目标吗？",
            "communication": f"通讯工具已使用 {mins} 分钟，如果有紧急事项处理完后可以回到专注模式",
            "ai_chat": f"AI 对话已 {mins} 分钟，是否可以把对话内容整理成笔记？",
            "other": f"当前应用已使用 {mins} 分钟，这是计划中的活动吗？",
        }
        msg = messages.get(category, f"你已在 {category} 上停留 {mins} 分钟")

        _show_notification("DeskMind 效率提醒", msg)
        print(f"[DeskMind Alert] [{category}] {msg}")


def run_alert_loop():
    """主循环"""
    print("[DeskMind Alerter] 智能提醒已启动")
    print(f"[DeskMind Alerter] 非工作应用阈值: {DISTRACTION_THRESHOLD//60} 分钟")
    print(f"[DeskMind Alerter] 检查间隔: {CHECK_INTERVAL} 秒")
    print(f"[DeskMind Alerter] 冷却时间: {COOLDOWN//60} 分钟")
    print("-" * 50)

    try:
        while True:
            _check_and_alert()
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        print("\n[DeskMind Alerter] 提醒服务已停止")


if __name__ == "__main__":
    run_alert_loop()
