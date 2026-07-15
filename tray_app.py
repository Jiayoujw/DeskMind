"""
DeskMind - 系统托盘启动器
一键启动/停止 tracker + dashboard，最小化到系统托盘
"""

import subprocess
import threading
import time
import webbrowser
import sys
from pathlib import Path
from PIL import Image, ImageDraw

DESKMIND_DIR = Path(__file__).parent

_tracker_process = None
_dashboard_process = None
_alert_process = None


def _create_icon():
    """生成托盘图标（蓝色圆形 + D 字母）"""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(124, 140, 248, 255))
    draw.text((18, 14), "D", fill=(255, 255, 255, 255))
    return img


def _start_tracker():
    """启动 tracker 子进程"""
    global _tracker_process
    if _tracker_process and _tracker_process.poll() is None:
        return  # 已在运行
    _tracker_process = subprocess.Popen(
        [sys.executable, "-u", str(DESKMIND_DIR / "tracker.py")],
        cwd=str(DESKMIND_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _stop_tracker():
    """停止 tracker 子进程"""
    global _tracker_process
    if _tracker_process and _tracker_process.poll() is None:
        _tracker_process.terminate()
        _tracker_process = None


def _start_dashboard():
    """启动 dashboard 子进程"""
    global _dashboard_process
    if _dashboard_process and _dashboard_process.poll() is None:
        return
    _dashboard_process = subprocess.Popen(
        [sys.executable, str(DESKMIND_DIR / "dashboard.py")],
        cwd=str(DESKMIND_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _stop_dashboard():
    """停止 dashboard 子进程"""
    global _dashboard_process
    if _dashboard_process and _dashboard_process.poll() is None:
        _dashboard_process.terminate()
        _dashboard_process = None


def _start_alert():
    """启动智能提醒子进程"""
    global _alert_process
    if _alert_process and _alert_process.poll() is None:
        return
    _alert_process = subprocess.Popen(
        [sys.executable, str(DESKMIND_DIR / "alerter.py")],
        cwd=str(DESKMIND_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _stop_alert():
    """停止智能提醒子进程"""
    global _alert_process
    if _alert_process and _alert_process.poll() is None:
        _alert_process.terminate()
        _alert_process = None


def _open_dashboard(icon, item):
    """打开浏览器看板"""
    webbrowser.open("http://localhost:5000")


def _toggle_tracker(icon, item):
    """切换 tracker 状态"""
    global _tracker_process
    if _tracker_process and _tracker_process.poll() is None:
        _stop_tracker()
        icon.title = "DeskMind - Tracker 已停止"
    else:
        _start_tracker()
        icon.title = "DeskMind - 运行中"


def _toggle_alert(icon, item):
    """切换智能提醒状态"""
    global _alert_process
    if _alert_process and _alert_process.poll() is None:
        _stop_alert()
    else:
        _start_alert()


def _quit(icon, item):
    """退出所有服务"""
    _stop_tracker()
    _stop_dashboard()
    _stop_alert()
    icon.stop()


def run():
    """启动 DeskMind 系统托盘应用"""
    import pystray

    # 自动启动所有服务
    _start_tracker()
    time.sleep(1)  # 等 tracker 初始化完成
    _start_dashboard()
    _start_alert()

    menu = pystray.Menu(
        pystray.MenuItem("打开看板", _open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Tracker: 运行中", _toggle_tracker, checked=lambda item: _tracker_process and _tracker_process.poll() is None),
        pystray.MenuItem("智能提醒: 开启", _toggle_alert, checked=lambda item: _alert_process and _alert_process.poll() is None),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _quit),
    )

    icon = pystray.Icon(
        name="DeskMind",
        icon=_create_icon(),
        title="DeskMind - 运行中",
        menu=menu,
    )

    icon.run()


if __name__ == "__main__":
    print("[DeskMind] 启动系统托盘应用...")
    print("[DeskMind] 右键托盘图标可控制服务")
    print("[DeskMind] 双击托盘图标打开看板")
    run()
