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


def compute_efficiency_score(stats):
    """
    计算每日综合效率评分 (0-100)

    评分维度：
    1. 活跃率 (0-20): 活跃时间占比
    2. 生产力占比 (0-30): 开发/终端/办公/技术阅读/AI 工具占比
    3. 按键强度 (0-20): 平均 KPM 反映深度工作程度
    4. 专注连续性 (0-15): 高强度时段数量
    5. 低干扰 (0-15): 娱乐/视频时间少
    """
    if "error" in stats:
        return {"score": 0, "breakdown": {}, "grade": "N/A"}

    total_min = stats.get("total_minutes", 0)
    if total_min < 5:
        return {"score": 0, "breakdown": {"note": "数据不足（<5分钟）"}, "grade": "N/A"}

    breakdown = {}

    # 1. 活跃率 (0-20)
    active_ratio = stats.get("active_ratio", 0)
    # 80%+ → 满分, 50% → 12分, 20% → 3分, 0% → 0
    s1 = min(20, round(active_ratio / 80 * 20, 1))
    breakdown["活跃率"] = {"value": f"{active_ratio}%", "score": s1, "max": 20}

    # 2. 生产力占比 (0-30)
    cat = stats.get("by_category", {})
    productive_cats = ["development", "terminal", "office", "tech_reading", "ai_tool", "ai_chat"]
    productive_min = sum(cat.get(c, 0) for c in productive_cats)
    active_min = stats.get("active_minutes", 1) or 1
    prod_ratio = productive_min / active_min * 100
    # 80%+ → 30, 50% → 20, 20% → 8, 0% → 0
    s2 = min(30, round(prod_ratio / 80 * 30, 1))
    breakdown["生产力占比"] = {"value": f"{round(prod_ratio)}%", "score": s2, "max": 30}

    # 3. 按键强度 (0-20)
    kpm = stats.get("keys_per_minute", 0)
    # 15+ KPM → 20 (深度编码), 8 → 12, 3 → 5, 0 → 0
    s3 = min(20, round(kpm / 15 * 20, 1))
    breakdown["按键强度"] = {"value": f"{kpm} 次/分", "score": s3, "max": 20}

    # 4. 专注连续性 (0-15)
    focus_hours = stats.get("focus_hours", [])
    # 5+ 个高强度时段 → 15, 2 → 8, 0 → 0
    s4 = min(15, round(len(focus_hours) / 5 * 15, 1))
    breakdown["专注时段"] = {"value": f"{len(focus_hours)} 个", "score": s4, "max": 15}

    # 5. 低干扰 (0-15) — 娱乐+视频占比越低分越高
    waste_cats = ["entertainment", "video"]
    waste_min = sum(cat.get(c, 0) for c in waste_cats)
    waste_ratio = waste_min / active_min * 100
    # 0% → 15, 10% → 12, 30% → 6, 60%+ → 0
    s5 = max(0, round((1 - waste_ratio / 60) * 15, 1))
    s5 = min(15, s5)
    breakdown["低干扰"] = {"value": f"娱乐 {round(waste_ratio)}%", "score": s5, "max": 15}

    total_score = round(sum(b["score"] for b in breakdown.values()), 0)

    # 评级
    if total_score >= 85:
        grade = "S"
    elif total_score >= 70:
        grade = "A"
    elif total_score >= 55:
        grade = "B"
    elif total_score >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": int(total_score),
        "breakdown": breakdown,
        "grade": grade,
    }


def save_efficiency_score(stats):
    """计算并保存今日效率评分到数据库"""
    result = compute_efficiency_score(stats)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(str(DB_PATH))
    # 确保表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS efficiency_scores (
            date TEXT PRIMARY KEY,
            score INTEGER,
            grade TEXT,
            breakdown TEXT,
            active_minutes REAL,
            productive_ratio REAL,
            kpm REAL,
            focus_hours INTEGER,
            created_at TEXT
        )
    """)
    # Upsert
    conn.execute("""
        INSERT OR REPLACE INTO efficiency_scores (date, score, grade, breakdown, active_minutes, productive_ratio, kpm, focus_hours, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today,
        result["score"],
        result["grade"],
        json.dumps(result["breakdown"], ensure_ascii=False),
        stats.get("active_minutes", 0),
        stats.get("productive_ratio", 0) if "productive_ratio" in stats else 0,
        stats.get("keys_per_minute", 0),
        len(stats.get("focus_hours", [])),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()
    return result


def get_efficiency_history(days=30):
    """获取最近 N 天的效率评分历史"""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT date, score, grade, breakdown, active_minutes, kpm FROM efficiency_scores WHERE date >= ? ORDER BY date",
        (start,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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