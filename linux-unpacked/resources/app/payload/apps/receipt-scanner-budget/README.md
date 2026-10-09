# Receipt Scanner Budget

Photograph a receipt → extract merchant, amount, and category → reconcile
with bank CSV exports and forecast balances. Private-first: everything
stays on-device.

- **Stack:** web-app (single-file HTML/JS, localStorage; OCR backend later)
- **Run:** `python3 -m http.server 8000` in this folder, open http://localhost:8000
- **Idea source:** [cashlytics.online](https://cashlytics.online/) (batch 2, leader-approved)
- **Status:** scaffolded — skeleton has manual receipt entry + category tagging + monthly totals; wire OCR (e.g. tesseract) next

## Roadmap
- OCR: tesseract or an on-device vision model for merchant/amount extraction
- Bank CSV import + auto-reconciliation
- Balance forecasting and category budgets
