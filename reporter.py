"""
DeskMind - 每日自动报告生成模块
生成日报和周报，支持定时自动触发
"""

import sqlite3
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from analyzer import compute_stats, call_ollama, get_date_range_activity

DB_PATH = Path(__file__).parent / "deskmind.db"


# ============ 数据库查询 ============

def get_activity_by_date(date_str):
    """查询指定日期的所有 activity_log 记录"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM activity_log WHERE timestamp LIKE ? ORDER BY timestamp",
        (f"{date_str}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_summaries(days=7):
    """获取最近 N 天的 daily_summary 记录"""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM daily_summary WHERE date >= ? ORDER BY date",
        (start,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_daily_summary(date_str, stats, ai_analysis):
    """将日报结果存入 daily_summary 表"""
    conn = sqlite3.connect(str(DB_PATH))
    # 构建应用使用数据 JSON（按应用分布）
    app_usage_json = json.dumps(stats.get("by_app", {}), ensure_ascii=False)

    # 使用 INSERT OR REPLACE 覆盖同一天的记录
    conn.execute("""
        INSERT OR REPLACE INTO daily_summary
            (date, app_usage_json, total_active_minutes, total_idle_minutes,
             total_key_strokes, total_clicks, ai_analysis)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        date_str,
        app_usage_json,
        stats.get("active_minutes", 0),
        stats.get("idle_minutes", 0),
        stats.get("total_keys", 0),
        stats.get("total_clicks", 0),
        ai_analysis,
    ))
    conn.commit()
    conn.close()


# ============ 日报 ============

def build_daily_report_prompt(stats, date_str):
    """构建日报专用的 AI Prompt（与 analyzer.py 中的不同）"""
    # 类别分布 Top 5
    top_categories = stats.get("top_category", [])[:5]
    cat_lines = "\n".join(f"  {i+1}. {cat} — {mins} 分钟" for i, (cat, mins) in enumerate(top_categories)) or "  无数据"

    # 焦点时段
    focus_hours = stats.get("focus_hours", [])
    focus_desc = ", ".join(focus_hours) + ":00" if focus_hours else "无高强度时段"

    prompt = f"""你是个人效率分析 AI 助手 "DeskMind"。请根据以下 {date_str} 的电脑使用数据，生成一份简洁的每日工作报告。

## 数据总览
- 活跃时间: {stats['active_minutes']} 分钟（活跃率 {stats['active_ratio']}%）
- 空闲时间: {stats['idle_minutes']} 分钟
- 按键强度: {stats['keys_per_minute']} 次/分钟（活跃时段平均）
- 总按键: {stats['total_keys']} 次，总点击: {stats['total_clicks']} 次

## 类别分布 Top 5
{cat_lines}

## 焦点时段
{focus_desc}

## 每小时活跃度（按键数）
{json.dumps(stats.get('hourly_keys', {}), ensure_ascii=False, indent=2)}

## 请按以下格式输出（中文，简洁 Markdown）：

### 行为模式总结
简要概括今天的主要工作模式和节奏（2-3 句话）

### 效率评分
给出 1-10 的效率评分，并简要说明理由（一句话）

### 改进建议
给出 3 条基于数据的具体改进建议，每条不超过两句话，要有针对性

### 明日计划建议
基于今天的数据模式，给出 2-3 条明日工作安排建议，帮助提升效率"""

    return prompt


def generate_daily_report(date_str=None):
    """
    生成指定日期的日报

    参数:
        date_str: 日期字符串，格式 "YYYY-MM-DD"。为 None 时使用昨天的日期

    返回:
        dict: 包含 date, stats, ai_analysis, generated_at 的完整报告
    """
    # 确定目标日期
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"[DeskMind Reporter] 正在生成 {date_str} 的日报...")

    # 查询指定日期的活动记录
    records = get_activity_by_date(date_str)

    if not records:
        print(f"[DeskMind Reporter] {date_str} 无活动记录，跳过日报生成")
        return {"date": date_str, "error": "该日期无活动记录"}

    # 计算统计
    stats = compute_stats(records)

    if "error" in stats:
        print(f"[DeskMind Reporter] 统计计算失败: {stats['error']}")
        return {"date": date_str, "error": stats["error"]}

    # 构建日报专用 prompt
    prompt = build_daily_report_prompt(stats, date_str)

    # 调用 AI 分析
    ai_analysis = call_ollama(prompt)

    # 存入数据库
    save_daily_summary(date_str, stats, ai_analysis)

    report = {
        "date": date_str,
        "stats": stats,
        "ai_analysis": ai_analysis,
        "generated_at": datetime.now().isoformat(),
    }

    print(f"[DeskMind Reporter] {date_str} 日报已生成并存入数据库")
    return report


# ============ 周报 ============

def build_weekly_report_prompt(daily_summaries):
    """构建周报 AI Prompt"""
    # 汇总每天的数据
    summary_lines = []
    for item in daily_summaries:
        date = item["date"]
        active = item.get("total_active_minutes", 0)
        idle = item.get("total_idle_minutes", 0)
        keys = item.get("total_key_strokes", 0)
        clicks = item.get("total_clicks", 0)
        ai = item.get("ai_analysis", "无分析") or "无分析"
        summary_lines.append(
            f"### {date}\n"
            f"- 活跃: {active} 分钟, 空闲: {idle} 分钟\n"
            f"- 按键: {keys} 次, 点击: {clicks} 次\n"
            f"- AI 分析摘要: {ai[:200]}..."
        )

    daily_text = "\n".join(summary_lines)

    prompt = f"""你是个人效率分析 AI 助手 "DeskMind"。请根据以下最近 7 天的每日报告数据，生成一份周趋势分析报告。

## 每日数据摘要

{daily_text}

## 请按以下格式输出（中文，简洁 Markdown）：

### 本周整体趋势
总结这一周的工作效率变化趋势（是否有提升/下降，整体节奏如何）

### 数据对比
比较不同日期的关键指标（活跃时间、按键强度），找出最高效和最低效的日子并分析原因

### 模式洞察
识别本周反复出现的行为模式（如固定的高效时段、经常分心的时段等）

### 本周效率评分
给出 1-10 的周效率评分及简要理由

### 下周改进建议
给出 3 条基于本周趋势的具体改进建议"""

    return prompt


def generate_weekly_report():
    """
    生成周报

    查询最近 7 天的 daily_summary：
    - 如果每天的 summary 都存在，用 AI 做周趋势分析
    - 如果某些天缺失，用 get_date_range_activity(7) 兜底重新计算

    返回:
        dict: 包含 report_type, period, daily_summaries, ai_analysis, generated_at 的周报
    """
    print("[DeskMind Reporter] 正在生成周报...")

    # 检查最近 7 天是否有完整的 daily_summary
    daily_summaries = get_daily_summaries(days=7)

    # 检查是否 7 天都有数据
    existing_dates = {item["date"] for item in daily_summaries}
    expected_dates = set()
    for i in range(7, 0, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        expected_dates.add(d)

    missing_dates = expected_dates - existing_dates

    # 如果有缺失的天数，兜底：从原始 activity_log 重新生成
    if missing_dates:
        print(f"[DeskMind Reporter] 发现缺失日报的日期: {missing_dates}，正在从原始数据补生成...")
        fallback_records = get_date_range_activity(7)
        fallback_stats = compute_stats(fallback_records)

        if "error" in fallback_stats:
            return {
                "report_type": "weekly",
                "period": f"{min(expected_dates)} ~ {max(expected_dates)}",
                "error": "数据不足，无法生成周报",
            }

        # 为缺失的日期补生成日报（基于兜底统计的整体数据）
        # 注意：兜底模式下无法精确到单日，直接用整体统计构建简化周报
        prompt = f"""你是个人效率分析 AI 助手 "DeskMind"。由于部分日报缺失，请根据最近 7 天的整体统计数据生成一份简化周报。

## 7 天整体数据
- 总记录: {fallback_stats['total_records']} 条
- 活跃时间: {fallback_stats['active_minutes']} 分钟
- 空闲时间: {fallback_stats['idle_minutes']} 分钟
- 按键强度: {fallback_stats['keys_per_minute']} 次/分钟
- 类别分布: {json.dumps(fallback_stats.get('top_category', [])[:5], ensure_ascii=False)}
- 焦点时段: {fallback_stats.get('focus_hours', [])}

已有的每日 AI 分析：
{chr(10).join(f"- {item['date']}: {(item.get('ai_analysis') or '无')[:150]}" for item in daily_summaries)}

## 请按以下格式输出（中文，简洁 Markdown）：
### 本周整体趋势
### 关键数据指标
### 模式洞察
### 效率评分（1-10）
### 下周改进建议"""

        ai_analysis = call_ollama(prompt)
    else:
        # 数据完整，正常生成周报
        prompt = build_weekly_report_prompt(daily_summaries)
        ai_analysis = call_ollama(prompt)

    # 计算汇总指标
    total_active = sum(item.get("total_active_minutes", 0) for item in daily_summaries)
    total_idle = sum(item.get("total_idle_minutes", 0) for item in daily_summaries)
    total_keys = sum(item.get("total_key_strokes", 0) for item in daily_summaries)
    total_clicks = sum(item.get("total_clicks", 0) for item in daily_summaries)

    period_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    period_end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    report = {
        "report_type": "weekly",
        "period": f"{period_start} ~ {period_end}",
        "days_with_data": len(daily_summaries),
        "total_active_minutes": total_active,
        "total_idle_minutes": total_idle,
        "total_key_strokes": total_keys,
        "total_clicks": total_clicks,
        "daily_summaries": [
            {
                "date": item["date"],
                "active_minutes": item.get("total_active_minutes", 0),
                "idle_minutes": item.get("total_idle_minutes", 0),
                "key_strokes": item.get("total_key_strokes", 0),
                "clicks": item.get("total_clicks", 0),
            }
            for item in daily_summaries
        ],
        "ai_analysis": ai_analysis,
        "generated_at": datetime.now().isoformat(),
    }

    print(f"[DeskMind Reporter] 周报已生成（{period_start} ~ {period_end}）")
    return report


# ============ 定时任务 ============

def schedule_daily_report():
    """
    用 threading.Timer 实现每天 23:55 自动触发生成日报
    首次运行后，每 24 小时重复触发
    """
    def _run_and_reschedule():
        print("[DeskMind Reporter] 定时任务触发，开始生成日报...")
        report = generate_daily_report()
        if "error" not in report:
            print(f"[DeskMind Reporter] 定时日报已生成: {report['date']}")
        else:
            print(f"[DeskMind Reporter] 定时日报生成失败: {report.get('error', '未知错误')}")

        # 计算下一次触发时间：明天 23:55
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(hour=23, minute=55, second=0, microsecond=0)
        delay_seconds = (tomorrow - now).total_seconds()
        print(f"[DeskMind Reporter] 下次日报生成时间: {tomorrow.strftime('%Y-%m-%d %H:%M:%S')}")

        timer = threading.Timer(delay_seconds, _run_and_reschedule)
        timer.daemon = True
        timer.start()

    # 计算距离今天 23:55 的秒数
    now = datetime.now()
    target = now.replace(hour=23, minute=55, second=0, microsecond=0)

    # 如果当前时间已过 23:55，则目标设为明天
    if now >= target:
        target += timedelta(days=1)

    delay_seconds = (target - now).total_seconds()
    print(f"[DeskMind Reporter] 定时任务已启动，首次触发时间: {target.strftime('%Y-%m-%d %H:%M:%S')}")

    timer = threading.Timer(delay_seconds, _run_and_reschedule)
    timer.daemon = True
    timer.start()

    # 保持主线程运行
    try:
        print("[DeskMind Reporter] 按 Ctrl+C 停止定时任务...")
        timer.join()
    except KeyboardInterrupt:
        print("\n[DeskMind Reporter] 定时任务已停止")


# ============ 命令行入口 ============

if __name__ == "__main__":
    import sys

    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if "schedule" in args:
        # 启动定时任务模式
        schedule_daily_report()
    elif "week" in args:
        # 生成周报
        report = generate_weekly_report()
        if "error" in report:
            print(f"[DeskMind Reporter] {report['error']}")
        else:
            print("\n" + "=" * 60)
            print(f"DeskMind 周报（{report['period']}）")
            print("=" * 60)
            print(f"  覆盖天数: {report['days_with_data']}")
            print(f"  总活跃: {report['total_active_minutes']} 分钟")
            print(f"  总空闲: {report['total_idle_minutes']} 分钟")
            print(f"  总按键: {report['total_key_strokes']} 次")
            print(f"  总点击: {report['total_clicks']} 次")
            print(f"\n## AI 周报分析")
            print(report["ai_analysis"])
    elif "today" in args:
        # 生成今天的日报
        today = datetime.now().strftime("%Y-%m-%d")
        report = generate_daily_report(date_str=today)
        if "error" in report:
            print(f"[DeskMind Reporter] {report['error']}")
        else:
            print("\n" + "=" * 60)
            print(f"DeskMind 日报（{report['date']}）")
            print("=" * 60)
            s = report["stats"]
            print(f"  活跃 {s['active_minutes']} 分钟 ({s['active_ratio']}%)  |  "
                  f"空闲 {s['idle_minutes']} 分钟  |  "
                  f"按键 {s['total_keys']} 次 ({s['keys_per_minute']} 次/分)")
            print(f"\n## AI 日报分析")
            print(report["ai_analysis"])
    else:
        # 默认：生成昨天的日报
        report = generate_daily_report()
        if "error" in report:
            print(f"[DeskMind Reporter] {report['error']}")
        else:
            print("\n" + "=" * 60)
            print(f"DeskMind 日报（{report['date']}）")
            print("=" * 60)
            s = report["stats"]
            print(f"  活跃 {s['active_minutes']} 分钟 ({s['active_ratio']}%)  |  "
                  f"空闲 {s['idle_minutes']} 分钟  |  "
                  f"按键 {s['total_keys']} 次 ({s['keys_per_minute']} 次/分)")
            print(f"\n## AI 日报分析")
            print(report["ai_analysis"])
