"""
DeskMind - AI 分析引擎 v2
利用多维度数据（按键、idle、类别细分）做更精准的分析
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

DB_PATH = Path(__file__).parent / "deskmind.db"
OLLAMA_URL = "http://localhost:11434/api/chat"


def get_today_activity():
    """获取今天的行为数据"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM activity_log WHERE timestamp LIKE ? ORDER BY timestamp",
        (f"{today}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_date_range_activity(days=7):
    """获取最近 N 天的行为数据"""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM activity_log WHERE timestamp >= ? ORDER BY timestamp",
        (start,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_stats(records):
    """计算多维度统计数据"""
    if not records:
        return {"error": "没有数据，请先运行 tracker.py 采集数据"}

    INTERVAL = 5  # 秒
    app_time = defaultdict(float)
    category_time = defaultdict(float)
    hourly_dist = Counter()
    hourly_keys = defaultdict(int)      # 每小时总按键数
    hourly_clicks = defaultdict(int)    # 每小时总点击数
    hourly_idle = defaultdict(int)      # 每小时 idle 次数
    total_keys = 0
    total_clicks = 0
    idle_count = 0
    active_count = 0

    for r in records:
        is_idle = r.get("is_idle", 0)
        keys = r.get("key_count", 0)
        clicks = r.get("click_count", 0)

        if not is_idle:
            app_time[r["process_name"]] += INTERVAL
            category_time[r["category"]] += INTERVAL
            active_count += 1
        else:
            idle_count += 1

        total_keys += keys
        total_clicks += clicks
        hour = r["timestamp"].split("T")[1][:2]
        hourly_dist[hour] += 1
        if not is_idle:
            hourly_keys[hour] += keys
            hourly_clicks[hour] += clicks
        else:
            hourly_idle[hour] += 1

    # 转分钟
    app_minutes = {k: round(v / 60, 1) for k, v in sorted(app_time.items(), key=lambda x: -x[1])}
    cat_minutes = {k: round(v / 60, 1) for k, v in sorted(category_time.items(), key=lambda x: -x[1])}

    # 活跃率
    total = active_count + idle_count or 1
    active_ratio = round(active_count / total * 100, 1)

    # 按键强度（按键/分钟，只算活跃时间）
    active_minutes = active_count * INTERVAL / 60 or 1
    kpm = round(total_keys / active_minutes, 1)

    # 识别"高强度编码"时段（每分钟 > 20 次按键）
    focus_hours = [h for h, k in hourly_keys.items() if k / max(active_count / 24, 1) > 10]

    return {
        "total_records": len(records),
        "total_minutes": round((active_count + idle_count) * INTERVAL / 60, 1),
        "active_minutes": round(active_count * INTERVAL / 60, 1),
        "idle_minutes": round(idle_count * INTERVAL / 60, 1),
        "active_ratio": active_ratio,
        "total_keys": total_keys,
        "total_clicks": total_clicks,
        "keys_per_minute": kpm,
        "by_app": app_minutes,
        "by_category": cat_minutes,
        "hourly_distribution": dict(sorted(hourly_dist.items())),
        "hourly_keys": dict(sorted(hourly_keys.items())),
        "hourly_clicks": dict(sorted(hourly_clicks.items())),
        "hourly_idle": dict(sorted(hourly_idle.items())),
        "top_apps": list(app_minutes.items())[:10],
        "top_category": list(cat_minutes.items())[:8],
        "focus_hours": focus_hours,
    }


def build_analysis_prompt(stats):
    """构建利用多维度数据的 AI Prompt"""
    prompt = f"""你是个人效率分析 AI 助手"DeskMind"。根据以下多维度电脑使用数据，给出深度分析和可执行建议。

## 今日数据总览
- 总记录: {stats['total_records']} 条，追踪 {stats['total_minutes']} 分钟
- 活跃时间: {stats['active_minutes']} 分钟（占 {stats['active_ratio']}%）
- 空闲时间: {stats['idle_minutes']} 分钟
- 总按键: {stats['total_keys']} 次，总点击: {stats['total_clicks']} 次
- 平均按键强度: {stats['keys_per_minute']} 次/分钟（活跃时段）

## 按类别分布（分钟）
{json.dumps(stats['top_category'], ensure_ascii=False, indent=2)}

## 按应用分布 Top 10（分钟）
{json.dumps(stats['top_apps'], ensure_ascii=False, indent=2)}

## 每小时活跃度（按键数、点击数、idle 次数）
{json.dumps(stats['hourly_keys'], ensure_ascii=False, indent=2)}

## 高强度编码/输入时段
{stats['focus_hours'] if stats['focus_hours'] else '无'}

## 请分析（中文，简洁 Markdown）：

1. **行为模式**：根据按键强度和类别切换，识别出 2-3 个具体行为模式（如"上午集中编码 2 小时""下午频繁切换标签页"）
2. **效率评估**：productive（开发/办公/终端）vs 消耗（娱乐/无目的浏览）的实际比例；按键强度是否表明你在深度工作还是被动浏览
3. **注意力分析**：是否有频繁切换应用的情况？idle 分布说明什么？
4. **3 条具体可执行建议**：不要泛泛而谈，要基于数据给出具体动作（如"你 14-15 点按键强度仅 2 次/分但切换了 15 次窗口，建议集中处理一个任务"）
5. **学习/工具推荐**：基于你的实际使用模式，推荐 1-2 个能立即提升效率的具体工具或学习资源"""

    return prompt


def call_ollama(prompt, model="qwen2.5:1.5b"):
    """调用 Ollama 本地模型，带重试机制"""
    import urllib.request
    import urllib.error

    models_to_try = [model, "qwen2.5:3b", "qwen2.5-coder:3b"]

    for m in models_to_try:
        try:
            payload = json.dumps({
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 1500}
            }).encode("utf-8")

            req = urllib.request.Request(
                OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result.get("message", {}).get("content", "") or result.get("response", "")
                text = text.strip()
                if text:
                    return text
                continue

        except urllib.error.URLError:
            return "AI 分析失败：Ollama 服务未启动。请先运行 `ollama serve`"
        except Exception:
            continue

    return "AI 分析失败：所有模型均无响应。"


def analyze_today():
    """分析今天的数据并返回结果"""
    records = get_today_activity()
    stats = compute_stats(records)

    if "error" in stats:
        return stats

    prompt = build_analysis_prompt(stats)
    ai_response = call_ollama(prompt)

    return {
        "stats": stats,
        "ai_analysis": ai_response,
        "generated_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    print("[DeskMind] 正在分析今天的行为数据...")
    result = analyze_today()
    if "error" in result:
        print(f"[DeskMind] {result['error']}")
    else:
        print("\n" + "=" * 60)
        print("DeskMind AI 分析报告")
        print("=" * 60)
        s = result['stats']
        print(f"\n  活跃 {s['active_minutes']} 分钟 ({s['active_ratio']}%)  |  "
              f"空闲 {s['idle_minutes']} 分钟  |  "
              f"按键 {s['total_keys']} 次 ({s['keys_per_minute']} 次/分)")
        print(f"\n## 类别分布")
        for cat, mins in s['top_category']:
            print(f"  {cat:20s}: {mins} 分钟")
        print(f"\n## AI 分析")
        print(result['ai_analysis'])