# DeskMind

**AI-powered personal productivity tracker — local, private, intelligent.**

Track your computer usage, measure real activity intensity (keystrokes, clicks, idle), and get AI-driven insights — all running locally on your machine.

## Why DeskMind?

Existing tools like [ActivityWatch](https://github.com/ActivityWatch/activitywatch) (13.5k stars) are powerful **data collection engines**, but they don't tell you what to do with the data. You have to write regex rules to classify apps, and there's zero intelligence or advice.

DeskMind takes a different approach:

| | ActivityWatch | RescueTime | **DeskMind** |
|---|---|---|---|
| Classification | Manual regex rules | Cloud-based | **AI auto-classification** |
| Insights | None | Cloud, paid | **Local AI, free, private** |
| Install | AppImage/pkg | Cloud agent | **`pip install`** |
| Architecture | 6+ processes, REST API | Cloud service | **Single Python process** |
| Privacy | Local | Data sent to cloud | **100% local (Ollama)** |
| Daily/Weekly Report | None | Yes (paid) | **Yes (local AI)** |
| Chinese app support | Partial | No | **Native support** |

## Features

### Multi-dimensional Tracking (v2)
- **Window monitoring** — active app, window title, auto-categorized (14 categories)
- **Keystroke intensity** — real-time key/click/move counting via `pynput` global hooks
- **Idle detection** — 60s inactivity threshold, separates real work from idle time
- **Smart categorization** — browsers are sub-categorized: tech reading (GitHub/StackOverflow), video (Bilibili/YouTube), AI chat (ChatGPT/Claude/Gemini), plus file manager, terminal, development, communication, office, entertainment

### Real-time Dashboard
- Active ratio, keystrokes per minute, total keys/clicks, focus hour detection
- Hourly keystroke + click intensity chart
- 24-hour heatmap timeline with focus hour highlighting
- Idle hot-spot analysis
- App usage ranking
- Category distribution (doughnut chart)

### AI Analysis (Ollama, local & private)
- **On-demand analysis** — click to analyze current day's data
- **Daily report** — auto-generates at 23:55, includes efficiency score (1-10), improvement suggestions, next-day plan
- **Weekly report** — 7-day trend analysis, pattern recognition, comparative insights
- Multi-model fallback (qwen2.5:1.5b → qwen2.5:3b → qwen2.5-coder:3b)

## Quick Start

### Prerequisites
- Python 3.8+
- [Ollama](https://ollama.ai) running locally with at least one model (e.g., `qwen2.5:1.5b`)
- Windows (uses `pywin32` for window detection)

### Install

```bash
git clone https://github.com/your-username/DeskMind.git
cd DeskMind
pip install -r requirements.txt
```

### Run

**Terminal 1 — Start tracking:**
```bash
python tracker.py
```

**Terminal 2 — Start dashboard:**
```bash
python dashboard.py
```

Open http://localhost:5000 in your browser.

### Reports

```bash
# Generate today's daily report
python reporter.py today

# Generate yesterday's report (default)
python reporter.py

# Generate weekly report
python reporter.py week

# Start auto-schedule mode (generates report daily at 23:55)
python reporter.py schedule
```

## Project Structure

```
DeskMind/
├── tracker.py        # Multi-dimensional behavior tracker (pynput hooks + window monitoring)
├── analyzer.py       # Statistics engine + AI analysis (Ollama)
├── reporter.py       # Daily/weekly report generation + scheduler
├── dashboard.py      # Flask web dashboard (Chart.js)
├── requirements.txt  # Python dependencies
└── .gitignore
```

## How It Works

```
┌─────────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐
│  tracker.py │────▶│  SQLite  │────▶│ analyzer  │────▶│ Ollama   │
│  (5s cycle) │     │ deskmind │     │  .py      │     │ (local)  │
│  pynput     │     │   .db    │     │ compute_  │     │          │
│  hooks      │     │          │     │ stats()   │     │          │
└─────────────┘     └──────────┘     └───────────┘     └──────────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │ dashboard.py │
                                        │  Flask+Chart │
                                        │  localhost:  │
                                        │    5000      │
                                        └──────────────┘
```

1. **tracker.py** installs global keyboard/mouse hooks via `pynput`, samples the active window every 5 seconds, and records keystrokes, clicks, idle status into SQLite
2. **analyzer.py** computes multi-dimensional stats (active ratio, KPM, focus hours) and sends structured prompts to Ollama for AI analysis
3. **reporter.py** generates daily/weekly reports and can auto-schedule at 23:55
4. **dashboard.py** serves a real-time web UI with Chart.js visualizations

## Tech Stack

| Component | Technology |
|---|---|
| Data Collection | Python + pynput + pywin32 + psutil |
| Storage | SQLite (single file, fully local) |
| Web UI | Flask + Chart.js 4 |
| AI Engine | Ollama (local LLM, any model) |
| Platform | Windows (extensible to macOS/Linux) |

## Roadmap

- [ ] AI auto-classification (replace rule-based categorization)
- [ ] Smart distraction alerts (context-aware, not just timers)
- [ ] Weekly trend charts in dashboard
- [ ] Browser extension for URL-level tracking
- [ ] macOS/Linux support
- [ ] System tray app with one-click start/stop
- [ ] Data export (JSON/CSV)
- [ ] Pomodoro integration based on focus detection

## Inspiration

- [ActivityWatch](https://github.com/ActivityWatch/activitywatch) — open-source time tracker
- [ulogme](https://github.com/karpathy/ulogme) — Karpathy's minimal usage logger
- [RescueTime](https://www.rescuetime.com/) — productivity tracking SaaS

## License

MIT