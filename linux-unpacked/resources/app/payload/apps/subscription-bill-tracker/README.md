# Subscription & Recurring Bill Tracker

Track recurring payments (weekly/monthly/yearly), see what you must set
aside each month, and spot underfunded categories or forgotten services.

- **Stack:** web-app (single-file HTML/JS, localStorage)
- **Run:** `python3 -m http.server 8000` in this folder, open http://localhost:8000
- **Idea source:** [github.com/lancebramsay/hedgie](https://github.com/lancebramsay/hedgie) (batch 2, leader-approved)
- **Status:** scaffolded — skeleton has subscriptions CRUD + monthly set-aside projection

## Roadmap
- Auto-detect recurring payments from bank CSV
- Rainy-day buffer vs. income and underfunded-category warnings
- "Forgotten subscription" audit (last used, cancel suggestions)
