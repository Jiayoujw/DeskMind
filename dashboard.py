"""
DeskMind - Web 看板 v2
展示多维度行为数据：活跃率、按键强度、idle 分析、焦点时段
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from flask import Flask, render_template_string, jsonify, request

from analyzer import compute_stats, analyze_today, get_date_range_activity
from export import export_json, export_csv
from config import get as config_get, set as config_set, get_all as config_get_all
from pomodoro import pomodoro, get_pomodoro_stats

app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"))
DB_PATH = Path(__file__).parent / "deskmind.db"

# ============ HTML 模板 ============
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DeskMind — 认知驾驶舱</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {
    --bg-primary: #080b1a;
    --bg-card: #0f1328;
    --bg-card-hover: #141933;
    --border-subtle: rgba(59,130,246,0.12);
    --border-glow: rgba(59,130,246,0.3);
    --accent-blue: #3b82f6;
    --accent-pink: #f472b6;
    --accent-emerald: #34d399;
    --accent-amber: #f59e0b;
    --accent-coral: #fb7185;
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #475569;
    --radius: 14px;
    --font-display: 'Bricolage Grotesque', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: var(--font-display);
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse at 20% 20%, rgba(59,130,246,0.06) 0%, transparent 50%),
      radial-gradient(ellipse at 80% 80%, rgba(244,114,182,0.05) 0%, transparent 50%),
      linear-gradient(rgba(59,130,246,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(59,130,246,0.03) 1px, transparent 1px);
    background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
    background-position: 0 0, 0 0, -1px -1px, -1px -1px;
  }

  /* ===== 头部 ===== */
  .header {
    position: sticky; top: 0; z-index: 100;
    background: rgba(8,11,26,0.85);
    backdrop-filter: blur(20px) saturate(1.5);
    border-bottom: 1px solid var(--border-subtle);
    padding: 16px 32px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .header-brand { display: flex; align-items: center; gap: 14px; }
  .header-logo {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-pink));
    display: flex; align-items: center; justify-content: center;
    font-family: var(--font-mono); font-weight: 700; font-size: 18px;
    color: #fff; box-shadow: 0 0 20px rgba(59,130,246,0.3);
  }
  .header h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.02em; }
  .header h1 span { color: var(--accent-pink); }
  .header p { font-size: 12px; color: var(--text-secondary); margin-top: 1px; }
  .header-badge {
    font-family: var(--font-mono); font-size: 11px; padding: 4px 12px;
    border-radius: 20px; background: rgba(59,130,246,0.1);
    border: 1px solid var(--border-subtle); color: var(--accent-blue);
  }

  /* ===== 容器 ===== */
  .container {
    max-width: 1360px; margin: 0 auto; padding: 24px 32px 48px;
    display: grid; grid-template-columns: 1fr 1fr; gap: 18px;
  }
  .full-width { grid-column: 1 / -1; }

  /* ===== 卡片 ===== */
  .card {
    background: var(--bg-card);
    border-radius: var(--radius);
    padding: 20px;
    border: 1px solid var(--border-subtle);
    position: relative;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: cardIn 0.5s ease-out both;
  }
  .card:hover { border-color: var(--border-glow); box-shadow: 0 0 30px rgba(59,130,246,0.06); }
  .card h2 {
    font-size: 13px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-secondary);
    margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
  }
  .card h2 .icon { font-size: 15px; }

  @keyframes cardIn {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .card:nth-child(1) { animation-delay: 0.02s; }
  .card:nth-child(2) { animation-delay: 0.06s; }
  .card:nth-child(3) { animation-delay: 0.10s; }
  .card:nth-child(4) { animation-delay: 0.14s; }

  /* ===== 指标卡片 ===== */
  .stat-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
    grid-column: 1 / -1;
  }
  .stat-grid-2 {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
    grid-column: 1 / -1;
  }
  .stat-item {
    background: var(--bg-card);
    border-radius: var(--radius);
    padding: 18px 16px;
    border: 1px solid var(--border-subtle);
    text-align: center;
    position: relative; overflow: hidden;
    transition: all 0.3s ease;
    animation: cardIn 0.5s ease-out both;
  }
  .stat-item:hover { border-color: var(--border-glow); transform: translateY(-2px); }
  .stat-item::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: var(--accent);
  }
  .stat-item .label { font-size: 11px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
  .stat-item .value { font-family: var(--font-mono); font-size: 28px; font-weight: 600; color: var(--accent); margin-top: 6px; }
  .stat-item .sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
  .stat-item.active-rate { --accent: var(--accent-emerald); }
  .stat-item.idle-time { --accent: var(--accent-amber); }
  .stat-item.key-intensity { --accent: var(--accent-coral); }
  .stat-item.focus-hours { --accent: var(--accent-blue); }

  .stat-item:nth-child(1) { animation-delay: 0.02s; }
  .stat-item:nth-child(2) { animation-delay: 0.05s; }
  .stat-item:nth-child(3) { animation-delay: 0.08s; }
  .stat-item:nth-child(4) { animation-delay: 0.11s; }

  /* ===== 按钮 ===== */
  .btn {
    font-family: var(--font-display); font-size: 13px; font-weight: 600;
    padding: 8px 20px; border-radius: 8px; border: none;
    cursor: pointer; transition: all 0.2s ease;
    background: var(--accent-blue); color: #fff;
    letter-spacing: 0.01em;
  }
  .btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  .btn-export { background: transparent; border: 1px solid var(--border-subtle); color: var(--text-secondary); }
  .btn-export:hover { border-color: var(--accent-blue); color: var(--accent-blue); background: rgba(59,130,246,0.08); }
  .btn-pomo { background: var(--accent-coral); }
  .btn-pomo-stop { background: transparent; border: 1px solid var(--text-muted); color: var(--text-secondary); }
  .btn-pomo-break { background: var(--accent-emerald); }

  /* ===== AI 分析 ===== */
  .ai-section {
    background: linear-gradient(135deg, #0f1328, #0a0e1f);
    border: 1px solid var(--border-subtle);
  }
  .ai-content {
    font-family: var(--font-display);
    white-space: pre-wrap; line-height: 1.8; font-size: 14px;
    color: var(--text-secondary); max-height: 500px; overflow-y: auto;
  }
  .ai-content h3 { color: var(--accent-blue); margin: 14px 0 6px; font-size: 15px; }
  .ai-content strong { color: var(--accent-pink); }
  #ai-btn-row { margin-bottom: 14px; display: flex; gap: 12px; align-items: center; }
  .loading { text-align: center; padding: 40px; color: var(--text-muted); }

  /* ===== 应用列表 ===== */
  .app-list { list-style: none; }
  .app-list li { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--border-subtle); font-size: 13px; }
  .app-list li:last-child { border-bottom: none; }
  .app-list .bar { height: 4px; background: rgba(59,130,246,0.08); border-radius: 2px; margin-top: 3px; }
  .app-list .bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent-blue), var(--accent-pink)); border-radius: 2px; transition: width 0.5s ease; }

  /* ===== 状态点 ===== */
  .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  .status-dot.active { background: var(--accent-emerald); box-shadow: 0 0 8px rgba(52,211,153,0.5); }
  .status-dot.inactive { background: var(--text-muted); }

  /* ===== 时间轴 ===== */
  .timeline-bar { display: flex; gap: 2px; margin-top: 12px; flex-wrap: wrap; }
  .hour-block {
    width: 28px; height: 34px; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--font-mono); font-size: 9px;
    color: var(--text-muted); background: #0c0f22;
    transition: all 0.2s ease; cursor: default;
  }
  .hour-block:hover { transform: scale(1.15); z-index: 2; }
  .hour-block.is-focus { border: 1px solid var(--accent-blue); color: var(--accent-blue); }

  /* ===== 标签 ===== */
  .idle-tag, .focus-tag {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-family: var(--font-mono); font-size: 11px;
  }
  .idle-tag { background: rgba(245,158,11,0.1); color: var(--accent-amber); }
  .focus-tag { background: rgba(59,130,246,0.1); color: var(--accent-blue); }
  .tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }

  /* ===== 报告卡片 ===== */
  .report-card {
    background: #0c0f22; border-radius: 10px; padding: 14px 16px;
    margin-bottom: 10px; border-left: 3px solid var(--accent-blue);
    transition: all 0.2s ease;
  }
  .report-card:hover { border-left-color: var(--accent-pink); background: var(--bg-card-hover); }
  .report-card .date { font-family: var(--font-mono); font-size: 12px; color: var(--accent-blue); font-weight: 600; }
  .report-card .stats { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
  .report-card .ai-summary { font-size: 13px; color: var(--text-secondary); margin-top: 6px; line-height: 1.6; }

  /* ===== 番茄钟 ===== */
  .pomo-ring {
    width: 140px; height: 140px; border-radius: 50%;
    border: 4px solid rgba(59,130,246,0.1);
    margin: 0 auto 16px;
    display: flex; align-items: center; justify-content: center;
    position: relative; background: #0c0f22;
  }
  .pomo-ring svg { position: absolute; transform: rotate(-90deg); }
  .pomo-ring .pomo-bg { fill: none; stroke: rgba(59,130,246,0.08); stroke-width: 4; }
  .pomo-ring .pomo-progress {
    fill: none; stroke: var(--accent-coral); stroke-width: 4;
    stroke-linecap: round; transition: stroke-dashoffset 0.8s ease;
  }
  .pomo-ring.break .pomo-progress { stroke: var(--accent-emerald); }
  #pomo-time { font-family: var(--font-mono); font-size: 30px; font-weight: 600; }
  #pomo-state { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  #pomo-stats { font-size: 12px; color: var(--text-muted); margin-top: 12px; }

  /* ===== 设置滑块 ===== */
  .setting-group { margin-bottom: 14px; }
  .setting-group label { font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 6px; }
  .setting-group .val { font-family: var(--font-mono); font-size: 12px; color: var(--accent-blue); margin-left: 8px; }
  input[type="range"] {
    -webkit-appearance: none; width: 100%; height: 4px;
    border-radius: 2px; background: rgba(59,130,246,0.1);
    outline: none; margin: 4px 0;
  }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none; width: 14px; height: 14px;
    border-radius: 50%; background: var(--accent-blue);
    cursor: pointer; box-shadow: 0 0 10px rgba(59,130,246,0.3);
  }
  .toggle-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .toggle-row label { font-size: 12px; color: var(--text-muted); }
  .toggle-row input[type="checkbox"] { width: 36px; height: 20px; accent-color: var(--accent-blue); }
  select.style-select {
    background: #0c0f22; color: var(--text-primary);
    border: 1px solid var(--border-subtle); padding: 7px 12px;
    border-radius: 8px; font-family: var(--font-mono); font-size: 12px;
    width: 100%; cursor: pointer;
  }
  select.style-select:focus { border-color: var(--accent-blue); outline: none; }

  /* ===== 底部工具栏 ===== */
  .toolbar {
    display: flex; justify-content: space-between; align-items: center;
    flex-wrap: wrap; gap: 12px;
  }
  .toolbar-left { display: flex; gap: 8px; align-items: center; }
  #classifier-status { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }

  /* ===== 滚动条 ===== */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--text-muted); border-radius: 3px; }
</style>
</head>
<body>
  <div class="header">
    <div class="header-brand">
      <div class="header-logo">D</div>
      <div>
        <h1>Desk<span>Mind</span></h1>
        <p>认知驾驶舱 · 行为分析 · AI 洞察</p>
      </div>
    </div>
    <span class="header-badge">v2.0</span>
  </div>

  <div class="container">
    <!-- 核心指标 -->
    <div class="stat-grid">
      <div class="stat-item active-rate">
        <div class="label">活跃率</div>
        <div class="value" id="active-ratio">--</div>
        <div class="sub" id="active-detail">活跃 -- / 空闲 -- 分钟</div>
      </div>
      <div class="stat-item key-intensity">
        <div class="label">按键强度</div>
        <div class="value" id="keys-per-min">--</div>
        <div class="sub">次/分钟（活跃时段）</div>
      </div>
      <div class="stat-item idle-time">
        <div class="label">总按键 / 点击</div>
        <div class="value" id="total-keys">--</div>
        <div class="sub" id="total-clicks-sub">-- 次点击</div>
      </div>
      <div class="stat-item focus-hours">
        <div class="label">焦点时段</div>
        <div class="value" id="focus-count">--</div>
        <div class="sub" id="focus-detail">高强度编码/输入</div>
      </div>
    </div>

    <!-- 基础指标 -->
    <div class="stat-grid-2">
      <div class="stat-item" style="--accent:var(--accent-blue);">
        <div class="label">今日追踪</div>
        <div class="value" id="total-minutes">--</div>
        <div class="sub">分钟</div>
      </div>
      <div class="stat-item" style="--accent:var(--accent-blue);">
        <div class="label">活动记录数</div>
        <div class="value" id="total-records">--</div>
        <div class="sub">条采样</div>
      </div>
      <div class="stat-item" style="--accent:var(--accent-blue);">
        <div class="label">效率指数</div>
        <div class="value" id="productive-ratio">--</div>
        <div class="sub">开发+办公+终端占比</div>
      </div>
    </div>

    <!-- 类别饼图 + 强度柱图 -->
    <div class="card">
      <h2><span class="icon">&#9679;</span> 时间分布（按类别）</h2>
      <canvas id="category-chart" height="250"></canvas>
    </div>
    <div class="card">
      <h2><span class="icon">&#9000;</span> 每小时按键 / 点击强度</h2>
      <canvas id="intensity-chart" height="250"></canvas>
    </div>

    <!-- 活跃时段 + 焦点分析 -->
    <div class="card">
      <h2><span class="icon">&#128336;</span> 活跃时段分布</h2>
      <canvas id="hourly-chart" height="200"></canvas>
    </div>
    <div class="card">
      <h2><span class="icon">&#9733;</span> 焦点时段 & Idle 分析</h2>
      <div id="focus-info" style="font-size:13px; color:var(--text-muted); margin-bottom:10px;">加载数据中...</div>
      <div class="timeline-bar" id="hourly-timeline"></div>
      <div class="tag-list" id="idle-tags"></div>
    </div>

    <!-- 应用排行 -->
    <div class="card">
      <h2><span class="icon">&#128187;</span> 应用使用排行</h2>
      <ul class="app-list" id="app-list"></ul>
    </div>

    <!-- 周趋势 -->
    <div class="card full-width">
      <h2><span class="icon">&#128200;</span> 7 天趋势</h2>
      <canvas id="weekly-trend-chart" height="180"></canvas>
    </div>

    <!-- AI 分析 -->
    <div class="card ai-section full-width">
      <h2><span class="icon">&#9889;</span> AI 智能分析</h2>
      <div id="ai-btn-row">
        <button class="btn" id="analyze-btn" onclick="runAnalysis()">&#9654; 让 AI 深度分析我的行为</button>
        <span class="status-dot inactive" id="ollama-status"></span>
        <span id="status-text" style="color:var(--text-muted);font-size:12px;">检测 Ollama 状态...</span>
      </div>
      <div id="ai-result" class="ai-content" style="display:none;"></div>
      <div id="ai-loading" class="loading" style="display:none;">AI 正在多维度分析你的行为数据...</div>
    </div>

    <!-- 历史报告 -->
    <div class="card full-width">
      <h2><span class="icon">&#128197;</span> 历史报告</h2>
      <div id="history-reports" style="font-size:13px; color:var(--text-muted);">加载中...</div>
    </div>

    <!-- 番茄钟 -->
    <div class="card">
      <h2><span class="icon">&#127813;</span> 番茄钟</h2>
      <div style="text-align:center; padding:10px 0;">
        <div class="pomo-ring" id="pomo-ring">
          <svg width="148" height="148" viewBox="0 0 148 148">
            <circle class="pomo-bg" cx="74" cy="74" r="68"/>
            <circle class="pomo-progress" id="pomo-progress" cx="74" cy="74" r="68"
              stroke-dasharray="427.26" stroke-dashoffset="0"/>
          </svg>
          <div>
            <div id="pomo-time">25:00</div>
            <div id="pomo-state">未开始</div>
          </div>
        </div>
        <div style="display:flex; gap:8px; justify-content:center;">
          <button class="btn btn-pomo" id="pomo-start" onclick="pomoStart()">&#9654; 开始工作</button>
          <button class="btn btn-pomo-stop" id="pomo-stop" onclick="pomoStop()" style="display:none;">&#9632; 停止</button>
          <button class="btn btn-pomo-break" id="pomo-break" onclick="pomoStartBreak()" style="display:none;">&#9632; 休息</button>
        </div>
        <div id="pomo-stats">今日完成: 0 个番茄</div>
      </div>
    </div>

    <!-- 设置 -->
    <div class="card">
      <h2><span class="icon">&#9881;</span> 设置</h2>
      <div class="setting-group">
        <label>追踪间隔 <span class="val" id="cfg-interval-val">5s</span></label>
        <input type="range" id="cfg-interval" min="3" max="30" step="1" value="5"
          oninput="updateSetting('tracker_interval', this.value); document.getElementById('cfg-interval-val').textContent=this.value+'s'">
      </div>
      <div class="setting-group">
        <label>Idle 超时 <span class="val" id="cfg-idle-val">60s</span></label>
        <input type="range" id="cfg-idle" min="30" max="300" step="10" value="60"
          oninput="updateSetting('idle_timeout', this.value); document.getElementById('cfg-idle-val').textContent=this.value+'s'">
      </div>
      <div class="setting-group">
        <label>分心提醒阈值 <span class="val" id="cfg-distract-val">5min</span></label>
        <input type="range" id="cfg-distract" min="1" max="30" step="1" value="5"
          oninput="updateSetting('distraction_threshold', this.value*60); document.getElementById('cfg-distract-val').textContent=this.value+'min'">
      </div>
      <div class="toggle-row">
        <input type="checkbox" id="cfg-alert" checked onchange="updateSetting('alert_enabled', this.checked)">
        <label for="cfg-alert">启用提醒</label>
      </div>
      <div class="toggle-row">
        <input type="checkbox" id="cfg-pomo" onchange="updateSetting('pomodoro_enabled', this.checked)">
        <label for="cfg-pomo">启用番茄钟</label>
      </div>
      <div class="setting-group">
        <label>AI 模型</label>
        <select id="cfg-model" class="style-select" onchange="updateSetting('ollama_model', this.value)">
          <option value="qwen2.5:1.5b">qwen2.5:1.5b</option>
          <option value="qwen2.5:3b">qwen2.5:3b</option>
          <option value="qwen2.5-coder:3b">qwen2.5-coder:3b</option>
        </select>
      </div>
    </div>

    <!-- 底部工具栏 -->
    <div class="card full-width">
      <div class="toolbar">
        <div class="toolbar-left">
          <button class="btn btn-export" onclick="exportData('json')">&#128230; 导出 JSON</button>
          <button class="btn btn-export" onclick="exportData('csv')">&#128230; 导出 CSV</button>
        </div>
        <div id="classifier-status">分类器状态加载中...</div>
      </div>
    </div>
  </div>

<script>
// 类别颜色/标签映射
const CATEGORY_COLORS = {
  browser: '#f472b6', tech_reading: '#34d399', video: '#fb7185', ai_chat: '#3b82f6',
  development: '#60a5fa', terminal: '#a78bfa', ai_tool: '#22d3ee',
  communication: '#f59e0b', office: '#34d399', entertainment: '#f97316',
  file_manager: '#a8a29e', other: '#64748b', uncategorized: '#475569'
};
const CATEGORY_LABELS = {
  browser: '浏览器', tech_reading: '技术阅读', video: '视频', ai_chat: 'AI 对话',
  development: '开发工具', terminal: '终端', ai_tool: 'AI 工具',
  communication: '通讯工具', office: '办公软件', entertainment: '娱乐',
  file_manager: '文件管理', other: '其他', uncategorized: '未分类'
};

// 页面加载
document.addEventListener('DOMContentLoaded', () => {
  loadStats(); checkOllama();
  loadWeeklyTrend(); loadHistoryReports(); loadClassifierStatus();
  setInterval(loadStats, 30000);
  updatePomodoro();
});

// ===== 统计 =====
async function loadStats() {
  try {
    const resp = await fetch('/api/stats');
    const data = await resp.json();
    if (data.error) { console.log(data.error); return; }
    renderStats(data);
  } catch(e) { console.log('加载统计数据失败'); }
}

function renderStats(data) {
  document.getElementById('active-ratio').textContent = (data.active_ratio || 0) + '%';
  document.getElementById('active-detail').textContent = '活跃 ' + (data.active_minutes || 0) + ' / 空闲 ' + (data.idle_minutes || 0) + ' 分钟';
  document.getElementById('keys-per-min').textContent = data.keys_per_minute || 0;
  document.getElementById('total-keys').textContent = (data.total_keys || 0).toLocaleString();
  document.getElementById('total-clicks-sub').textContent = (data.total_clicks || 0).toLocaleString() + ' 次点击';
  document.getElementById('focus-count').textContent = (data.focus_hours || []).length;
  document.getElementById('focus-detail').textContent = (data.focus_hours || []).length > 0 ? '高强度编码/输入时段' : '暂无高强度时段';
  document.getElementById('total-minutes').textContent = data.total_minutes || 0;
  document.getElementById('total-records').textContent = (data.total_records || 0).toLocaleString();
  const productive = (data.by_category.development || 0) + (data.by_category.office || 0) + (data.by_category.terminal || 0);
  document.getElementById('productive-ratio').textContent = Math.round((productive / (data.total_minutes || 1)) * 100) + '%';
  renderCategoryChart(data.by_category);
  renderIntensityChart(data.hourly_keys, data.hourly_clicks);
  renderHourlyChart(data.hourly_distribution);
  renderAppList(data.top_apps);
  renderFocusSection(data);
}

let categoryChart = null;
function renderCategoryChart(categories) {
  const labels = Object.keys(categories).map(k => CATEGORY_LABELS[k] || k);
  const values = Object.values(categories);
  const colors = Object.keys(categories).map(k => CATEGORY_COLORS[k] || '#64748b');
  const ctx = document.getElementById('category-chart').getContext('2d');
  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
    options: { responsive: true, cutout: '65%',
      plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 }, padding: 12, usePointStyle: true, pointStyle: 'circle' } } }
    }
  });
}

let intensityChart = null;
function renderIntensityChart(hourlyKeys, hourlyClicks) {
  const hours = Array.from({length: 24}, (_, i) => i);
  const labels = hours.map(h => h.toString().padStart(2, '0') + ':00');
  const keyData = hours.map(h => hourlyKeys[h.toString().padStart(2, '0')] || 0);
  const clickData = hours.map(h => hourlyClicks[h.toString().padStart(2, '0')] || 0);
  const ctx = document.getElementById('intensity-chart').getContext('2d');
  if (intensityChart) intensityChart.destroy();
  intensityChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [
      { label: '按键数', data: keyData, backgroundColor: 'rgba(244,114,182,0.7)', borderRadius: 4, borderSkipped: false },
      { label: '点击数', data: clickData, backgroundColor: 'rgba(59,130,246,0.7)', borderRadius: 4, borderSkipped: false }
    ]},
    options: { responsive: true,
      plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 }, usePointStyle: true } } },
      scales: {
        x: { ticks: { color: '#475569', maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
        y: { ticks: { color: '#475569' }, grid: { color: 'rgba(59,130,246,0.06)' } }
      }
    }
  });
}

let hourlyChart = null;
function renderHourlyChart(hourly) {
  const hours = Array.from({length: 24}, (_, i) => i);
  const labels = hours.map(h => h.toString().padStart(2, '0') + ':00');
  const values = hours.map(h => hourly[h.toString().padStart(2, '0')] || 0);
  const ctx = document.getElementById('hourly-chart').getContext('2d');
  if (hourlyChart) hourlyChart.destroy();
  hourlyChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label: '采样次数', data: values, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, tension: 0.4, pointRadius: 2, pointHoverRadius: 5 }]},
    options: { responsive: true, plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#475569', maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { display: false } },
        y: { ticks: { color: '#475569' }, grid: { color: 'rgba(59,130,246,0.06)' } }
      }
    }
  });
}

function renderAppList(apps) {
  const max = apps.length > 0 ? apps[0][1] : 1;
  document.getElementById('app-list').innerHTML = apps.slice(0, 10).map(([name, mins]) =>
    '<li><span>' + name + '</span><span style="font-family:var(--font-mono);color:var(--text-muted);">' + mins + ' 分钟</span></li>' +
    '<li style="padding:0;border:none;"><div class="bar"><div class="bar-fill" style="width:' + (mins/max)*100 + '%"></div></div></li>'
  ).join('');
}

function renderFocusSection(data) {
  const focusHours = data.focus_hours || [];
  const hourlyIdle = data.hourly_idle || {};
  const hourlyKeys = data.hourly_keys || {};
  const info = document.getElementById('focus-info');
  if (focusHours.length > 0) {
    info.innerHTML = '检测到 <strong style="color:var(--accent-blue)">' + focusHours.length + '</strong> 个高强度输入时段：' +
      focusHours.map(h => '<span class="focus-tag">' + h + ':00</span>').join(' ');
  } else {
    info.textContent = '暂未检测到高强度输入时段（需积累更多数据）';
  }
  const timeline = document.getElementById('hourly-timeline');
  const hours = Array.from({length: 24}, (_, i) => i);
  const maxKeys = Math.max(...Object.values(hourlyKeys), 1);
  timeline.innerHTML = hours.map(h => {
    const hStr = h.toString().padStart(2, '0');
    const keys = hourlyKeys[hStr] || 0;
    const isFocus = focusHours.includes(hStr);
    const opacity = Math.max(0.15, keys / maxKeys);
    return '<div class="hour-block' + (isFocus ? ' is-focus' : '') + '" style="background:rgba(59,130,246,' + opacity + ')" title="' + hStr + ':00 - ' + keys + ' 次按键">' + hStr + '</div>';
  }).join('');
  const idleTags = document.getElementById('idle-tags');
  const sortedIdle = Object.entries(hourlyIdle).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (sortedIdle.length > 0) {
    idleTags.innerHTML = '<span style="color:var(--text-muted);font-size:11px;">高频 idle 时段：</span>' +
      sortedIdle.map(([h, count]) => '<span class="idle-tag">' + h + ':00 (' + count + '次)</span>').join('');
  }
}

// ===== Ollama 状态 =====
async function checkOllama() {
  const dot = document.getElementById('ollama-status');
  const text = document.getElementById('status-text');
  try {
    const resp = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(3000) });
    if (resp.ok) { dot.className = 'status-dot active'; text.textContent = 'Ollama 已连接'; text.style.color = '#34d399'; }
    else throw new Error();
  } catch(e) { dot.className = 'status-dot inactive'; text.textContent = 'Ollama 未启动'; text.style.color = '#475569'; }
}

// ===== AI 分析 =====
async function runAnalysis() {
  const btn = document.getElementById('analyze-btn');
  const result = document.getElementById('ai-result');
  const loading = document.getElementById('ai-loading');
  btn.disabled = true; btn.textContent = '分析中...';
  loading.style.display = 'block'; result.style.display = 'none';
  try {
    const resp = await fetch('/api/analyze');
    const data = await resp.json();
    loading.style.display = 'none'; result.style.display = 'block';
    if (data.ai_analysis) {
      result.innerHTML = data.ai_analysis
        .replace(/### (.*)/g, '<h3>$1</h3>').replace(/## (.*)/g, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/- (.*)/g, '&#8226; $1<br>')
        .replace(/\d+\.\s\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n\n/g, '<br><br>');
    } else if (data.error) { result.innerHTML = '<span style="color:var(--accent-coral)">' + data.error + '</span>'; }
  } catch(e) { loading.style.display = 'none'; result.style.display = 'block'; result.innerHTML = '<span style="color:var(--accent-coral)">请求失败</span>'; }
  btn.disabled = false; btn.textContent = '重新分析';
}

// ===== 周趋势 =====
async function loadWeeklyTrend() {
  try { const resp = await fetch('/api/weekly-trend'); const data = await resp.json(); if (!data.error) renderWeeklyTrend(data); } catch(e) {}
}
let weeklyTrendChart = null;
function renderWeeklyTrend(data) {
  const labels = data.dates.map(d => d.slice(5));
  const ctx = document.getElementById('weekly-trend-chart').getContext('2d');
  if (weeklyTrendChart) weeklyTrendChart.destroy();
  weeklyTrendChart = new Chart(ctx, {
    type: 'line', data: { labels, datasets: [
      { label: '活跃(分钟)', data: data.active_minutes, borderColor: '#34d399', backgroundColor: 'rgba(52,211,153,0.08)', fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: '#34d399' },
      { label: '按键强度(次/分)', data: data.kpm, borderColor: '#f472b6', backgroundColor: 'rgba(244,114,182,0.08)', fill: false, tension: 0.3, pointRadius: 3, pointBackgroundColor: '#f472b6', yAxisID: 'y1' }
    ]},
    options: { responsive: true, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 }, usePointStyle: true } } },
      scales: {
        x: { ticks: { color: '#475569' }, grid: { display: false } },
        y: { ticks: { color: '#475569' }, grid: { color: 'rgba(59,130,246,0.06)' }, title: { display: true, text: '分钟', color: '#475569' } },
        y1: { position: 'right', ticks: { color: '#475569' }, grid: { drawOnChartArea: false }, title: { display: true, text: '次/分', color: '#475569' } }
      }
    }
  });
}

// ===== 历史报告 =====
async function loadHistoryReports() {
  try {
    const resp = await fetch('/api/reports'); const data = await resp.json();
    const container = document.getElementById('history-reports');
    if (!data.length) { container.innerHTML = '<div style="color:var(--text-muted);">暂无历史报告。运行 <code style="background:#0c0f22;padding:2px 6px;border-radius:4px;">python reporter.py today</code> 生成第一份报告。</div>'; return; }
    container.innerHTML = data.map(r => {
      const aiText = (r.ai_analysis || '无 AI 分析').substring(0, 200);
      return '<div class="report-card"><div class="date">' + r.date + '</div><div class="stats">活跃 ' + (r.total_active_minutes || 0) + ' 分钟 | 空闲 ' + (r.total_idle_minutes || 0) + ' 分钟 | 按键 ' + (r.total_key_strokes || 0) + ' 次</div><div class="ai-summary">' + aiText.replace(/\n/g, '<br>') + '...</div></div>';
    }).join('');
  } catch(e) { document.getElementById('history-reports').innerHTML = '<div style="color:var(--text-muted);">加载失败</div>'; }
}

// ===== 导出 =====
async function exportData(format) {
  try {
    const resp = await fetch('/api/export?format=' + format + '&days=7');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'deskmind_export_7d.' + format; a.click(); URL.revokeObjectURL(url);
  } catch(e) { alert('导出失败'); }
}

// ===== 分类器状态 =====
async function loadClassifierStatus() {
  try {
    const resp = await fetch('/api/classifier-status'); const data = await resp.json();
    const el = document.getElementById('classifier-status');
    el.innerHTML = (data.ollama_available ? '<span style="color:#34d399;">AI 分类</span>' : '<span style="color:#f59e0b;">规则分类</span>') +
      ' | 缓存 ' + data.total_cached + ' 条';
  } catch(e) {}
}

// ===== 番茄钟 =====
function pomoStart() { fetch('/api/pomodoro', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'start_work'})}).then(() => updatePomodoro()); }
function pomoStartBreak() { fetch('/api/pomodoro', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'start_break'})}).then(() => updatePomodoro()); }
function pomoStop() { fetch('/api/pomodoro', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'stop'})}).then(() => updatePomodoro()); }
function updatePomodoro() {
  fetch('/api/pomodoro').then(r=>r.json()).then(data => {
    const mins = Math.floor(data.remaining / 60);
    const secs = data.remaining % 60;
    document.getElementById('pomo-time').textContent = String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0');
    document.getElementById('pomo-state').textContent = {idle:'未开始',working:'工作中',break:'休息中'}[data.state] || data.state;
    const circumference = 68 * 2 * Math.PI;
    document.getElementById('pomo-progress').style.strokeDashoffset = circumference * (1 - data.progress);
    document.getElementById('pomo-ring').className = 'pomo-ring' + (data.state === 'break' ? ' break' : '');
    document.getElementById('pomo-start').style.display = data.state === 'idle' ? '' : 'none';
    document.getElementById('pomo-stop').style.display = data.state === 'idle' ? 'none' : '';
    document.getElementById('pomo-break').style.display = data.state === 'break' ? '' : 'none';
    if (data.state === 'working' && data.remaining <= 0) pomoStartBreak();
    if (data.state === 'break' && data.remaining <= 0) pomoStop();
    document.getElementById('pomo-stats').textContent = '今日完成: ' + data.completed_count + ' 个番茄';
  });
}
setInterval(updatePomodoro, 1000);

// ===== 设置 =====
async function loadSettings() {
  try {
    const resp = await fetch('/api/settings'); const data = await resp.json();
    document.getElementById('cfg-interval').value = data.tracker_interval || 5;
    document.getElementById('cfg-interval-val').textContent = (data.tracker_interval || 5) + 's';
    document.getElementById('cfg-idle').value = data.idle_timeout || 60;
    document.getElementById('cfg-idle-val').textContent = (data.idle_timeout || 60) + 's';
    document.getElementById('cfg-distract').value = (data.distraction_threshold || 300) / 60;
    document.getElementById('cfg-distract-val').textContent = ((data.distraction_threshold || 300) / 60) + 'min';
    document.getElementById('cfg-alert').checked = data.alert_enabled !== false;
    document.getElementById('cfg-pomo').checked = !!data.pomodoro_enabled;
    document.getElementById('cfg-model').value = data.ollama_model || 'qwen2.5:1.5b';
  } catch(e) {}
}
function updateSetting(key, value) { fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key, value})}); }
document.addEventListener('DOMContentLoaded', loadSettings);
</script>
</body>
</html>
"""


# ============ API 路由 ============

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/stats")
def api_stats():
    """返回今日统计数据"""
    from analyzer import get_today_activity
    records = get_today_activity()
    stats = compute_stats(records)
    return jsonify(stats)


@app.route("/api/analyze")
def api_analyze():
    """调用 AI 分析"""
    result = analyze_today()
    if "error" in result and "stats" not in result:
        return jsonify({"error": result["error"]})
    return jsonify(result)


@app.route("/api/available-models")
def api_models():
    """返回 Ollama 可用模型列表"""
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return jsonify({"models": models})
    except:
        return jsonify({"models": [], "error": "Ollama 未启动"})


@app.route("/api/weekly-trend")
def api_weekly_trend():
    """返回最近 7 天的每日活跃时间趋势"""
    try:
        from analyzer import get_date_range_activity
        records = get_date_range_activity(7)
        
        # 按天分组统计
        daily = defaultdict(lambda: {"active": 0, "idle": 0, "keys": 0, "clicks": 0, "active_count": 0})
        for r in records:
            date = r["timestamp"][:10]
            if r.get("is_idle", 0):
                daily[date]["idle"] += 5
            else:
                daily[date]["active"] += 5
                daily[date]["active_count"] += 1
                daily[date]["keys"] += r.get("key_count", 0)
                daily[date]["clicks"] += r.get("click_count", 0)
        
        # 生成连续 7 天的数据
        dates = []
        active_minutes = []
        kpm = []
        for i in range(6, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            dates.append(d)
            data = daily[d]
            active_minutes.append(round(data["active"] / 60, 1))
            active_mins = data["active"] / 60 or 1
            kpm.append(round(data["keys"] / active_mins, 1))
        
        return jsonify({
            "dates": dates,
            "active_minutes": active_minutes,
            "kpm": kpm,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/reports")
def api_reports():
    """返回历史日报列表"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT date, total_active_minutes, total_idle_minutes, total_key_strokes, total_clicks, ai_analysis FROM daily_summary ORDER BY date DESC LIMIT 14"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/export")
def api_export():
    """数据导出 API"""
    from flask import Response
    fmt = request.args.get("format", "json")
    days = int(request.args.get("days", 7))
    
    if fmt == "csv":
        content = export_csv(days)
        return Response(content, mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=deskmind_export.csv"})
    else:
        content = export_json(days)
        return Response(content, mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=deskmind_export.json"})


@app.route("/api/classifier-status")
def api_classifier_status():
    """返回 AI 分类器状态"""
    try:
        from classifier import get_cache_stats
        return jsonify(get_cache_stats())
    except:
        return jsonify({"total_cached": 0, "by_category": {}, "ollama_available": False})


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """获取所有配置"""
    return jsonify(config_get_all())


@app.route("/api/settings", methods=["POST"])
def api_set_setting():
    """设置单个配置项"""
    data = request.get_json()
    key = data.get("key")
    value = data.get("value")
    if key:
        # 数值类型转换
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        config_set(key, value)
    return jsonify({"ok": True})


@app.route("/api/pomodoro", methods=["GET"])
def api_pomodoro_status():
    """获取番茄钟状态"""
    return jsonify(pomodoro.to_dict())


@app.route("/api/pomodoro", methods=["POST"])
def api_pomodoro_action():
    """番茄钟操作"""
    data = request.get_json()
    action = data.get("action", "")
    if action == "start_work":
        work = config_get("pomodoro_work", 25)
        brk = config_get("pomodoro_break", 5)
        pomodoro.configure(work, brk)
        pomodoro.start_work()
    elif action == "start_break":
        pomodoro.start_break()
    elif action == "stop":
        pomodoro.stop()
    return jsonify(pomodoro.to_dict())


# ============ 启动 ============

if __name__ == "__main__":
    print("=" * 50)
    print("  DeskMind Web Dashboard v2")
    print("  打开浏览器访问: http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)