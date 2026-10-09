# Grocery List Price Optimizer

Build your weekly basket → see which single store is cheapest, or the
cheapest split-trip with a route (which items to buy where).

- **Stack:** web-app (single-file HTML/JS, localStorage)
- **Run:** `python3 -m http.server 8000` in this folder, open http://localhost:8000
- **Idea source:** [grocerychop.com](https://grocerychop.com/) (batch 2, leader-approved)
- **Status:** scaffolded — skeleton has stores, items, per-store prices, and a greedy cheapest-store picker

## Roadmap
- Live price feeds per chain (pair with Grocery Price Radar + Price Watcher)
- Split-trip optimizer (per-item cheapest store) with route ordering by aisle
- Savings estimate per basket vs. shopping at one store
