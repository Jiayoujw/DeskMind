"""
DeskMind - 数据导出模块
支持 JSON 和 CSV 格式导出
"""

import sqlite3
import json
import csv
import io
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "deskmind.db"


def get_activity_records(days=7):
    """获取最近 N 天的活动记录"""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM activity_log WHERE timestamp >= ? ORDER BY timestamp",
        (start,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_reports(days=7):
    """获取最近 N 天的日报"""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM daily_summary WHERE date >= ? ORDER BY date",
        (start,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_json(days=7, include_ai_analysis=True):
    """导出为 JSON 格式"""
    records = get_activity_records(days)
    result = {
        "exported_at": datetime.now().isoformat(),
        "period_days": days,
        "total_records": len(records),
        "activity_log": records,
    }
    if include_ai_analysis:
        reports = get_daily_reports(days)
        # 不导出原始 AI 文本（太大），只导出结构化数据
        result["daily_summaries"] = [
            {k: v for k, v in r.items() if k != "ai_analysis"}
            for r in reports
        ]
    return json.dumps(result, ensure_ascii=False, indent=2)


def export_csv(days=7):
    """导出为 CSV 格式"""
    records = get_activity_records(days)
    if not records:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "timestamp", "process_name", "window_title",
        "category", "key_count", "click_count", "is_idle"
    ])
    writer.writeheader()
    for r in records:
        writer.writerow({k: r.get(k, "") for k in [
            "id", "timestamp", "process_name", "window_title",
            "category", "key_count", "click_count", "is_idle"
        ]})
    return output.getvalue()


if __name__ == "__main__":
    import sys
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    days = 7
    fmt = "json"

    for arg in args:
        if arg.startswith("--days="):
            days = int(arg.split("=")[1])
        elif arg in ("json", "csv"):
            fmt = arg

    if fmt == "csv":
        content = export_csv(days)
        filename = f"deskmind_export_{days}d.csv"
    else:
        content = export_json(days)
        filename = f"deskmind_export_{days}d.json"

    filepath = Path(__file__).parent / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"[DeskMind Export] 已导出 {len(get_activity_records(days))} 条记录到 {filepath}")