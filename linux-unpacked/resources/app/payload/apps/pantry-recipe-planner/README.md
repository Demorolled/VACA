# Pantry-to-Recipe Shopping Planner

Paste a recipe or mark what's in your pantry → auto-build a shopping list
of what you're missing, grouped by store aisle.

- **Stack:** web-app (single-file HTML/JS, localStorage)
- **Run:** `python3 -m http.server 8000` in this folder, open http://localhost:8000
- **Idea source:** [lastlistapp.com](https://lastlistapp.com/) (batch 2, leader-approved)
- **Status:** scaffolded — skeleton has pantry + recipe + generated "missing" list; wire real recipe parsing and aisle mapping next

## Roadmap
- Parse recipe ingredients from pasted URLs/text
- Aisle ordering per store and live retailer price matching (see Grocery Price Radar)
- Share the list with family (link or copy-paste export)
