# 🤖 AI Job Monitor

Intelligent job tracking system with ML-based priority scoring and multi-channel alerts for principal/staff AI engineer roles.

[![Job Monitor](https://github.com/YOUR_USERNAME/ai-job-monitor/workflows/AI%20Job%20Monitor/badge.svg)](https://github.com/YOUR_USERNAME/ai-job-monitor/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 Features

- **🧠 Smart Priority Scoring** (0-100): role seniority × domain fit × location match
- **⚡ Multi-tier Alerts**:
  - 🔥 URGENT (80+): instant Telegram push notifications
  - 📊 HIGH/MEDIUM (40-79): daily email digest
  - 📈 LOW (<40): weekly summary
- **📡 20+ Companies** pre-configured
- **☁️ Serverless**: GitHub Actions cron
- **🔄 State Management**: git-backed, no duplicate alerts
- **🔒 Secure**: all credentials via GitHub Secrets

## 🏗️ Architecture

```
GitHub Actions (hourly cron)
  → Scrape career pages
  → Filter & score roles
  → Alert (Telegram) / Queue (email)
  → Commit job_state.json
```

## 🚀 Quick setup

1. Fork the repo (public recommended for Actions minutes).
2. Add GitHub Secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - Optional: `EMAIL_FROM`, `EMAIL_PASSWORD`
3. Enable Actions → run **AI Job Monitor** manually once.

## 🔧 Local run

```bash
pip install -r requirements.txt
cp config.template.json config.json
python job_monitor.py --once
python -m unittest test_job_monitor.py
```

## ⚙️ Customize

- **Companies**: edit `config.template.json`
- **Scoring**: adjust `calculate_job_score()` in `job_monitor.py`
- **Schedule**: edit `.github/workflows/monitor.yml` cron

## 🐛 Troubleshooting

- **No jobs found**: verify URLs in `config.template.json`
- **Telegram not sending**: check secrets + bot chat ID
- **State conflicts**: concurrent runs can race; next run will recover

## 📜 License

MIT — see `LICENSE`.