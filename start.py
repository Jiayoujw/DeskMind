"""
DeskMind - 统一启动入口
python start.py          # 启动全部服务（tracker + dashboard + alerter + 托盘）
python start.py --no-tray # 不使用系统托盘，直接在前台运行
"""

import subprocess
import sys
import time
from pathlib import Path

DESKMIND_DIR = Path(__file__).parent


def check_dependencies():
    """检查并安装缺失的依赖"""
    required = {
        "flask": "flask",
        "psutil": "psutil",
        "win32gui": "pywin32",
        "pynput": "pynput",
    }
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"[DeskMind] 安装缺失依赖: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + missing)
        print("[DeskMind] 依赖安装完成")


def main():
    check_dependencies()

    use_tray = "--no-tray" not in sys.argv

    if use_tray:
        # 尝试使用系统托盘模式
        try:
            import pystray
            from tray_app import run
            run()
            return
        except ImportError:
            print("[DeskMind] pystray 未安装，使用前台模式")
            print("[DeskMind] 运行 pip install pystray 可启用系统托盘模式")
        except Exception as e:
            print(f"[DeskMind] 托盘模式不可用: {e}，使用前台模式")

    # 前台模式：在当前终端启动 tracker，子进程启动 dashboard
    import tracker
    import threading

    # 子进程启动 dashboard
    dashboard_proc = subprocess.Popen(
        [sys.executable, str(DESKMIND_DIR / "dashboard.py")],
        cwd=str(DESKMIND_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    # 子进程启动 alerter
    alerter_proc = subprocess.Popen(
        [sys.executable, str(DESKMIND_DIR / "alerter.py")],
        cwd=str(DESKMIND_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    try:
        tracker.run_tracker()
    except KeyboardInterrupt:
        print("\n[DeskMind] 正在停止所有服务...")
        dashboard_proc.terminate()
        alerter_proc.terminate()
        print("[DeskMind] 已停止")


if __name__ == "__main__":
    main()
