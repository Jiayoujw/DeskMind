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
<title>DeskMind v2 - 多维度电脑行为分析</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; min-height: 100vh; }
  .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 20px 30px; border-bottom: 1px solid #2a2a4a; display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 24px; color: #7c8cf8; }
  .header p { color: #888; font-size: 14px; margin-top: 4px; }
  .header .version { background: #7c8cf822; color: #7c8cf8; padding: 4px 10px; border-radius: 12px; font-size: 12px; border: 1px solid #7c8cf844; }
  .container { max-width: 1300px; margin: 0 auto; padding: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .card { background: #1a1a2e; border-radius: 12px; padding: 20px; border: 1px solid #2a2a4a; }
  .card h2 { font-size: 15px; color: #7c8cf8; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
  .card h2 .icon { font-size: 18px; }

  /* 统计卡片 */
  .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; grid-column: 1 / -1; }
  .stat-item { background: #16213e; border-radius: 10px; padding: 18px 14px; text-align: center; position: relative; overflow: hidden; }
  .stat-item::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--accent, #7c8cf8); }
  .stat-item .value { font-size: 26px; font-weight: 700; color: var(--accent, #7c8cf8); margin-top: 4px; }
  .stat-item .label { font-size: 12px; color: #888; margin-top: 4px; }
  .stat-item .sub { font-size: 11px; color: #666; margin-top: 2px; }
  .stat-item.active-rate { --accent: #4caf50; }
  .stat-item.idle-time { --accent: #ff9800; }
  .stat-item.key-intensity { --accent: #e91e63; }
  .stat-item.focus-hours { --accent: #00bcd4; }

  /* 第二行统计 */
  .stat-grid-2 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; grid-column: 1 / -1; }
  .stat-grid-2 .stat-item { --accent: #7c8cf8; }

  .full-width { grid-column: 1 / -1; }
  .ai-section { grid-column: 1 / -1; background: linear-gradient(135deg, #1a1a2e 0%, #0d1b2a 100%); }
  .ai-content { white-space: pre-wrap; line-height: 1.8; font-size: 14px; color: #ccc; max-height: 500px; overflow-y: auto; }
  .ai-content h3 { color: #7c8cf8; margin: 12px 0 4px; }
  .ai-content strong { color: #a0a8ff; }
  .btn { background: #7c8cf8; color: #fff; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; transition: background 0.2s; }
  .btn:hover { background: #6b7bef; }
  .btn:disabled { background: #444; cursor: not-allowed; }
  .loading { text-align: center; padding: 40px; color: #888; }
  .loading::after { content: ''; animation: dots 1.5s infinite; }
  @keyframes dots { 0%,20% { content: '.'; } 40% { content: '..'; } 60%,100% { content: '...'; } }
  .app-list { list-style: none; }
  .app-list li { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #2a2a4a; font-size: 13px; }
  .app-list .bar { height: 5px; background: #2a2a4a; border-radius: 3px; margin-top: 4px; }
  .app-list .bar-fill { height: 100%; background: #7c8cf8; border-radius: 3px; transition: width 0.5s; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  .status-dot.active { background: #4caf50; box-shadow: 0 0 6px #4caf5088; }
  .status-dot.inactive { background: #666; }
  #ai-btn-row { margin-bottom: 12px; display: flex; gap: 10px; align-items: center; }

  /* 活跃度时间轴 */
  .timeline-bar { display: flex; gap: 2px; margin-top: 12px; flex-wrap: wrap; }
  .timeline-bar .hour-block { width: 28px; height: 32px; border-radius: 4px; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 10px; color: #aaa; background: #16213e; transition: background 0.3s; }
  .timeline-bar .hour-block.is-focus { background: #00bcd433; border: 1px solid #00bcd466; color: #00bcd4; }

  /* idle 标签 */
  .idle-tag { display: inline-block; background: #ff980022; color: #ff9800; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .focus-tag { display: inline-block; background: #00bcd422; color: #00bcd4; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }

  .report-card { background: #16213e; border-radius: 8px; padding: 14px; margin-bottom: 10px; border-left: 3px solid #7c8cf8; }
  .report-card .date { font-size: 13px; color: #7c8cf8; font-weight: 600; }
  .report-card .stats { font-size: 12px; color: #888; margin-top: 4px; }
  .report-card .ai-summary { font-size: 13px; color: #bbb; margin-top: 6px; line-height: 1.6; }
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>DeskMind</h1>
      <p>多维度电脑行为分析 — 按键 / idle / 焦点时段 / AI 洞察</p>
    </div>
    <span class="version">v2.0</span>
  </div>

  <div class="container">
    <!-- 第一行：核心指标 -->
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

    <!-- 第二行：基础指标 -->
    <div class="stat-grid-2">
      <div class="stat-item">
        <div class="label">今日追踪</div>
        <div class="value" id="total-minutes">--</div>
        <div class="sub">分钟</div>
      </div>
      <div class="stat-item">
        <div class="label">活动记录数</div>
        <div class="value" id="total-records">--</div>
        <div class="sub">条采样</div>
      </div>
      <div class="stat-item">
        <div class="label">效率指数</div>
        <div class="value" id="productive-ratio">--</div>
        <div class="sub">开发+办公+终端占比</div>
      </div>
    </div>

    <!-- 类别饼图 -->
    <div class="card">
      <h2><span class="icon">&#128202;</span> 时间分布（按类别）</h2>
      <canvas id="category-chart" height="250"></canvas>
    </div>

    <!-- 按键强度小时图 -->
    <div class="card">
      <h2><span class="icon">&#9000;</span> 每小时按键 / 点击强度</h2>
      <canvas id="intensity-chart" height="250"></canvas>
    </div>

    <!-- 小时活跃分布 -->
    <div class="card">
      <h2><span class="icon">&#128336;</span> 活跃时段分布</h2>
      <canvas id="hourly-chart" height="200"></canvas>
    </div>

    <!-- 焦点时段 + idle 分析 -->
    <div class="card">
      <h2><span class="icon">&#127919;</span> 焦点时段 & Idle 分析</h2>
      <div id="focus-info" style="font-size:14px; color:#aaa; margin-bottom:8px;">加载数据中...</div>
      <div class="timeline-bar" id="hourly-timeline"></div>
      <div class="tag-list" id="idle-tags"></div>
    </div>

    <!-- 应用排行 -->
    <div class="card">
      <h2><span class="icon">&#128187;</span> 应用使用排行</h2>
      <ul class="app-list" id="app-list"></ul>
    </div>

    <!-- AI 分析 -->
    <div class="card ai-section">
      <h2><span class="icon">&#129302;</span> AI 智能分析</h2>
      <div id="ai-btn-row">
        <button class="btn" id="analyze-btn" onclick="runAnalysis()">让 AI 深度分析我的行为</button>
        <span class="status-dot inactive" id="ollama-status"></span>
        <span id="status-text" style="color:#888;font-size:13px">检测 Ollama 状态...</span>
      </div>
      <div id="ai-result" class="ai-content" style="display:none;"></div>
      <div id="ai-loading" class="loading" style="display:none;">AI 正在多维度分析你的行为数据</div>
    </div>

    <!-- 周趋势 -->
    <div class="card full-width">
      <h2><span class="icon">&#128200;</span> 7 天趋势</h2>
      <canvas id="weekly-trend-chart" height="180"></canvas>
    </div>

    <!-- 历史报告 -->
    <div class="card full-width">
      <h2><span class="icon">&#128197;</span> 历史报告</h2>
      <div id="history-reports" style="font-size:14px; color:#888;">加载中...</div>
    </div>

    <!-- 底部工具栏 -->
    <div class="card full-width" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
      <div style="display:flex; gap:10px; align-items:center;">
        <button class="btn" onclick="exportData('json')" style="background:#4caf50;">导出 JSON</button>
        <button class="btn" onclick="exportData('csv')" style="background:#ff9800;">导出 CSV</button>
      </div>
      <div id="classifier-status" style="font-size:12px; color:#888;">分类器状态加载中...</div>
    </div>

    <!-- 番茄钟 -->
    <div class="card" style="grid-column: 1/2;">
      <h2><span class="icon">&#127813;</span> 番茄钟</h2>
      <div style="text-align:center; padding:20px 0;">
        <div id="pomo-circle" style="width:140px; height:140px; border-radius:50%; border:6px solid #2a2a4a; margin:0 auto 16px; display:flex; align-items:center; justify-content:center; position:relative; background:#16213e;">
          <div id="pomo-progress" style="position:absolute; top:-3px; left:-3px; width:calc(100% + 6px); height:calc(100% + 6px); border-radius:50%; border:6px solid transparent; border-top-color:#e91e63; transition:transform 0.5s;"></div>
          <div>
            <div id="pomo-time" style="font-size:32px; font-weight:700; color:#e0e0e0;">25:00</div>
            <div id="pomo-state" style="font-size:12px; color:#888;">未开始</div>
          </div>
        </div>
        <div style="display:flex; gap:8px; justify-content:center;">
          <button class="btn" id="pomo-start" onclick="pomoStart()" style="background:#e91e63;">开始工作</button>
          <button class="btn" id="pomo-stop" onclick="pomoStop()" style="display:none; background:#666;">停止</button>
          <button class="btn" id="pomo-break" onclick="pomoStartBreak()" style="display:none; background:#4caf50;">休息</button>
        </div>
        <div id="pomo-stats" style="margin-top:12px; font-size:12px; color:#666;">今日完成: 0 个番茄</div>
      </div>
    </div>

    <!-- 设置 -->
    <div class="card" style="grid-column: 2/3;">
      <h2><span class="icon">&#9881;</span> 设置</h2>
      <div style="display:grid; gap:14px;">
        <div>
          <label style="font-size:13px; color:#aaa; display:block; margin-bottom:4px;">追踪间隔（秒）</label>
          <input type="range" id="cfg-interval" min="3" max="30" step="1" value="5" oninput="updateSetting('tracker_interval', this.value); document.getElementById('cfg-interval-val').textContent=this.value+'s'">
          <span id="cfg-interval-val" style="font-size:12px; color:#7c8cf8;">5s</span>
        </div>
        <div>
          <label style="font-size:13px; color:#aaa; display:block; margin-bottom:4px;">Idle 超时（秒）</label>
          <input type="range" id="cfg-idle" min="30" max="300" step="10" value="60" oninput="updateSetting('idle_timeout', this.value); document.getElementById('cfg-idle-val').textContent=this.value+'s'">
          <span id="cfg-idle-val" style="font-size:12px; color:#7c8cf8;">60s</span>
        </div>
        <div>
          <label style="font-size:13px; color:#aaa; display:block; margin-bottom:4px;">分心提醒阈值（分钟）</label>
          <input type="range" id="cfg-distract" min="1" max="30" step="1" value="5" oninput="updateSetting('distraction_threshold', this.value*60); document.getElementById('cfg-distract-val').textContent=this.value+'min'">
          <span id="cfg-distract-val" style="font-size:12px; color:#7c8cf8;">5min</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <label style="font-size:13px; color:#aaa;">启用提醒</label>
          <input type="checkbox" id="cfg-alert" checked onchange="updateSetting('alert_enabled', this.checked)">
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <label style="font-size:13px; color:#aaa;">启用番茄钟</label>
          <input type="checkbox" id="cfg-pomo" onchange="updateSetting('pomodoro_enabled', this.checked)">
        </div>
        <div>
          <label style="font-size:13px; color:#aaa; display:block; margin-bottom:4px;">AI 模型</label>
          <select id="cfg-model" onchange="updateSetting('ollama_model', this.value)" style="background:#16213e; color:#e0e0e0; border:1px solid #2a2a4a; padding:6px 10px; border-radius:6px; font-size:13px;">
            <option value="qwen2.5:1.5b">qwen2.5:1.5b</option>
            <option value="qwen2.5:3b">qwen2.5:3b</option>
            <option value="qwen2.5-coder:3b">qwen2.5-coder:3b</option>
          </select>
        </div>
      </div>
    </div>
  </div>

<script>
// 类别颜色/标签映射 v2（含新类别）
const CATEGORY_COLORS = {
  browser: '#e91e63', tech_reading: '#8bc34a', video: '#f44336', ai_chat: '#7c8cf8',
  development: '#2196f3', terminal: '#9c27b0', ai_tool: '#00bcd4',
  communication: '#ff9800', office: '#4caf50', entertainment: '#ff5722',
  file_manager: '#795548', other: '#607d8b', uncategorized: '#455a64'
};
const CATEGORY_LABELS = {
  browser: '浏览器', tech_reading: '技术阅读', video: '视频', ai_chat: 'AI 对话',
  development: '开发工具', terminal: '终端', ai_tool: 'AI 工具',
  communication: '通讯工具', office: '办公软件', entertainment: '娱乐',
  file_manager: '文件管理', other: '其他', uncategorized: '未分类'
};

// 页面加载
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  checkOllama();
  setInterval(loadStats, 30000);
});

async function loadStats() {
  try {
    const resp = await fetch('/api/stats');
    const data = await resp.json();
    if (data.error) { console.log(data.error); return; }
    renderStats(data);
  } catch(e) { console.log('加载统计数据失败'); }
}

function renderStats(data) {
  // 核心指标
  document.getElementById('active-ratio').textContent = (data.active_ratio || 0) + '%';
  document.getElementById('active-detail').textContent =
    '活跃 ' + (data.active_minutes || 0) + ' / 空闲 ' + (data.idle_minutes || 0) + ' 分钟';
  document.getElementById('keys-per-min').textContent = data.keys_per_minute || 0;
  document.getElementById('total-keys').textContent = (data.total_keys || 0).toLocaleString();
  document.getElementById('total-clicks-sub').textContent = (data.total_clicks || 0).toLocaleString() + ' 次点击';
  document.getElementById('focus-count').textContent = (data.focus_hours || []).length;
  document.getElementById('focus-detail').textContent =
    (data.focus_hours || []).length > 0 ? '高强度编码/输入时段' : '暂无高强度时段';

  // 基础指标
  document.getElementById('total-minutes').textContent = data.total_minutes || 0;
  document.getElementById('total-records').textContent = (data.total_records || 0).toLocaleString();
  const productive = (data.by_category.development || 0) + (data.by_category.office || 0) + (data.by_category.terminal || 0);
  const total = data.total_minutes || 1;
  document.getElementById('productive-ratio').textContent = Math.round((productive / total) * 100) + '%';

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
  const colors = Object.keys(categories).map(k => CATEGORY_COLORS[k] || '#666');

  const ctx = document.getElementById('category-chart').getContext('2d');
  if (categoryChart) categoryChart.destroy();
  categoryChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
    options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#ccc', font: { size: 11 }, padding: 12 } } } }
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
    data: {
      labels,
      datasets: [
        { label: '按键数', data: keyData, backgroundColor: 'rgba(233,30,99,0.7)', borderRadius: 3 },
        { label: '点击数', data: clickData, backgroundColor: 'rgba(124,140,248,0.7)', borderRadius: 3 }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#ccc', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#888', maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, stacked: false },
        y: { ticks: { color: '#888' }, grid: { color: '#2a2a4a' }, stacked: false }
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
    data: {
      labels,
      datasets: [{
        label: '采样次数', data: values,
        borderColor: '#7c8cf8', backgroundColor: 'rgba(124,140,248,0.15)',
        fill: true, tension: 0.4, pointRadius: 2, pointHoverRadius: 5
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#888', maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
        y: { ticks: { color: '#888' }, grid: { color: '#2a2a4a' } }
      }
    }
  });
}

function renderAppList(apps) {
  const max = apps.length > 0 ? apps[0][1] : 1;
  const ul = document.getElementById('app-list');
  ul.innerHTML = apps.slice(0, 10).map(([name, mins]) => `
    <li>
      <span>${name}</span>
      <span>${mins} 分钟</span>
    </li>
    <li style="padding:0;border:none;">
      <div class="bar"><div class="bar-fill" style="width:${(mins/max)*100}%"></div></div>
    </li>
  `).join('');
}

function renderFocusSection(data) {
  const focusHours = data.focus_hours || [];
  const hourlyIdle = data.hourly_idle || {};
  const hourlyKeys = data.hourly_keys || {};

  // 信息文本
  const info = document.getElementById('focus-info');
  if (focusHours.length > 0) {
    info.innerHTML = '检测到 <strong style="color:#00bcd4">' + focusHours.length + '</strong> 个高强度输入时段：' +
      focusHours.map(h => '<span class="focus-tag">' + h + ':00</span>').join(' ');
  } else {
    info.textContent = '暂未检测到高强度输入时段（需积累更多数据）';
  }

  // 24 小时时间轴
  const timeline = document.getElementById('hourly-timeline');
  const hours = Array.from({length: 24}, (_, i) => i);
  const maxKeys = Math.max(...Object.values(hourlyKeys), 1);
  timeline.innerHTML = hours.map(h => {
    const hStr = h.toString().padStart(2, '0');
    const keys = hourlyKeys[hStr] || 0;
    const isFocus = focusHours.includes(hStr);
    const opacity = Math.max(0.15, keys / maxKeys);
    const bg = isFocus
      ? 'rgba(0,188,212,' + opacity + ')'
      : 'rgba(124,140,248,' + opacity + ')';
    return '<div class="hour-block' + (isFocus ? ' is-focus' : '') + '" style="background:' + bg + '" title="' + hStr + ':00 - ' + keys + ' 次按键">' + hStr + '</div>';
  }).join('');

  // idle 标签（显示 idle 最多的前 5 个小时）
  const idleTags = document.getElementById('idle-tags');
  const sortedIdle = Object.entries(hourlyIdle).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (sortedIdle.length > 0) {
    idleTags.innerHTML = '<span style="color:#888;font-size:12px;">高频 idle 时段：</span>' +
      sortedIdle.map(([h, count]) => '<span class="idle-tag">' + h + ':00 (' + count + '次)</span>').join('');
  }
}

async function checkOllama() {
  const dot = document.getElementById('ollama-status');
  const text = document.getElementById('status-text');
  try {
    const resp = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      dot.className = 'status-dot active';
      text.textContent = 'Ollama 已连接';
      text.style.color = '#4caf50';
    } else throw new Error();
  } catch(e) {
    dot.className = 'status-dot inactive';
    text.textContent = 'Ollama 未启动（AI 分析不可用）';
    text.style.color = '#666';
  }
}

async function runAnalysis() {
  const btn = document.getElementById('analyze-btn');
  const result = document.getElementById('ai-result');
  const loading = document.getElementById('ai-loading');
  btn.disabled = true;
  btn.textContent = '分析中...';
  loading.style.display = 'block';
  result.style.display = 'none';

  try {
    const resp = await fetch('/api/analyze');
    const data = await resp.json();
    loading.style.display = 'none';
    result.style.display = 'block';
    if (data.ai_analysis) {
      result.innerHTML = data.ai_analysis
        .replace(/### (.*)/g, '<h3>$1</h3>')
        .replace(/## (.*)/g, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/- (.*)/g, '&#8226; $1<br>')
        .replace(/\d+\.\s\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n\n/g, '<br><br>');
    } else if (data.error) {
      result.innerHTML = '<span style="color:#f44336">' + data.error + '</span>';
    }
  } catch(e) {
    loading.style.display = 'none';
    result.style.display = 'block';
    result.innerHTML = '<span style="color:#f44336">请求失败: ' + e.message + '</span>';
  }

  btn.disabled = false;
  btn.textContent = '重新分析';
}

// 7 天趋势
async function loadWeeklyTrend() {
  try {
    const resp = await fetch('/api/weekly-trend');
    const data = await resp.json();
    if (data.error) { return; }
    renderWeeklyTrend(data);
  } catch(e) {}
}

let weeklyTrendChart = null;
function renderWeeklyTrend(data) {
  const labels = data.dates.map(d => d.slice(5)); // MM-DD
  const ctx = document.getElementById('weekly-trend-chart').getContext('2d');
  if (weeklyTrendChart) weeklyTrendChart.destroy();
  weeklyTrendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: '活跃(分钟)', data: data.active_minutes, borderColor: '#4caf50', backgroundColor: 'rgba(76,175,80,0.1)', fill: true, tension: 0.3, pointRadius: 3 },
        { label: '按键强度(次/分)', data: data.kpm, borderColor: '#e91e63', backgroundColor: 'rgba(233,30,99,0.1)', fill: false, tension: 0.3, pointRadius: 3, yAxisID: 'y1' }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#ccc', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#888' }, grid: { color: '#2a2a4a' } },
        y: { type: 'linear', position: 'left', ticks: { color: '#4caf50' }, grid: { color: '#2a2a4a' }, title: { display: true, text: '分钟', color: '#4caf50' } },
        y1: { type: 'linear', position: 'right', ticks: { color: '#e91e63' }, grid: { drawOnChartArea: false }, title: { display: true, text: '次/分', color: '#e91e63' } }
      }
    }
  });
}

// 历史报告
async function loadHistoryReports() {
  try {
    const resp = await fetch('/api/reports');
    const data = await resp.json();
    const container = document.getElementById('history-reports');
    if (!data.length) {
      container.innerHTML = '<div style="color:#666;">暂无历史报告。运行 <code>python reporter.py today</code> 生成第一份报告。</div>';
      return;
    }
    container.innerHTML = data.map(r => {
      const aiText = (r.ai_analysis || '无 AI 分析').substring(0, 200);
      return '<div class="report-card">' +
        '<div class="date">' + r.date + '</div>' +
        '<div class="stats">活跃 ' + (r.total_active_minutes || 0) + ' 分钟 | 空闲 ' + (r.total_idle_minutes || 0) + ' 分钟 | 按键 ' + (r.total_key_strokes || 0) + ' 次</div>' +
        '<div class="ai-summary">' + aiText.replace(/\n/g, '<br>') + '...</div>' +
        '</div>';
    }).join('');
  } catch(e) {
    document.getElementById('history-reports').innerHTML = '<div style="color:#666;">加载失败</div>';
  }
}

// 数据导出
async function exportData(format) {
  try {
    const resp = await fetch('/api/export?format=' + format + '&days=7');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'deskmind_export_7d.' + format;
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) {
    alert('导出失败: ' + e.message);
  }
}

// 分类器状态
async function loadClassifierStatus() {
  try {
    const resp = await fetch('/api/classifier-status');
    const data = await resp.json();
    const el = document.getElementById('classifier-status');
    const aiLabel = data.ollama_available
      ? '<span style="color:#4caf50;">AI 分类已启用</span>'
      : '<span style="color:#ff9800;">AI 离线，使用规则分类</span>';
    el.innerHTML = aiLabel + ' | 缓存: ' + data.total_cached + ' 条 | ' +
      Object.entries(data.by_category || {}).map(([k,v]) => k + ':' + v).join(' ');
  } catch(e) {}
}

// 页面加载时也请求这些数据
document.addEventListener('DOMContentLoaded', () => {
  loadWeeklyTrend();
  loadHistoryReports();
  loadClassifierStatus();
});

// ===== 番茄钟 =====
let pomoInterval = null;
function pomoStart() {
  fetch('/api/pomodoro', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'start_work'})}).then(() => updatePomodoro());
}
function pomoStartBreak() {
  fetch('/api/pomodoro', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'start_break'})}).then(() => updatePomodoro());
}
function pomoStop() {
  fetch('/api/pomodoro', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'stop'})}).then(() => updatePomodoro());
}
function updatePomodoro() {
  fetch('/api/pomodoro').then(r=>r.json()).then(data => {
    const mins = Math.floor(data.remaining / 60);
    const secs = data.remaining % 60;
    document.getElementById('pomo-time').textContent = String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0');
    document.getElementById('pomo-state').textContent = {idle:'未开始',working:'工作中',break:'休息中'}[data.state] || data.state;
    
    // 旋转进度环
    const deg = data.progress * 360;
    document.getElementById('pomo-progress').style.transform = 'rotate(' + deg + 'deg)';
    document.getElementById('pomo-progress').style.borderTopColor = data.state === 'break' ? '#4caf50' : '#e91e63';
    
    // 按钮状态
    const isIdle = data.state === 'idle';
    const isWorking = data.state === 'working';
    document.getElementById('pomo-start').style.display = isIdle ? '' : 'none';
    document.getElementById('pomo-stop').style.display = isIdle ? 'none' : '';
    document.getElementById('pomo-break').style.display = (data.state === 'break') ? '' : 'none';
    
    // 自动转换检测
    if (isWorking && data.remaining <= 0) pomoStartBreak();
    if (data.state === 'break' && data.remaining <= 0) pomoStop();
    
    document.getElementById('pomo-stats').textContent = '今日完成: ' + data.completed_count + ' 个番茄';
  });
}
setInterval(updatePomodoro, 1000);
updatePomodoro();

// ===== 设置 =====
async function loadSettings() {
  try {
    const resp = await fetch('/api/settings');
    const data = await resp.json();
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
function updateSetting(key, value) {
  fetch('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key, value})});
}
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