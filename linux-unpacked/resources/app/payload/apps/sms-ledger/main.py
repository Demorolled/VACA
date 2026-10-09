import os
import re
from datetime import datetime
from collections import defaultdict

# pdfplumber is optional: the app works fully for SMS parsing and degrades
# gracefully for PDF statements when it isn't installed (pip install pdfplumber).
try:
    import pdfplumber
    HAVE_PDFPLUMBER = True
except ImportError:
    HAVE_PDFPLUMBER = False

# Constants
SMS_DIR = 'sms'
STATEMENT_DIR = 'statements'
OUTPUT_DIR = 'output'
BUDGET_FILE = 'budgets.json'

# Ensure output directories exist
for _d in (SMS_DIR, STATEMENT_DIR, OUTPUT_DIR):
    os.makedirs(_d, exist_ok=True)

# Load budgets (simple JSON format for now)
def load_budgets():
    budgets = defaultdict(float)
    try:
        with open(BUDGET_FILE, 'r') as f:
            for line in f:
                category, amount = line.strip().split(',')
                budgets[category] = float(amount)
    except FileNotFoundError:
        pass
    return budgets

# Save budgets
def save_budgets(budgets):
    with open(BUDGET_FILE, 'w') as f:
        for category, amount in budgets.items():
            f.write(f"{category},{amount}\n")

# Parse SMS
def parse_sms(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    transactions = []
    for line in lines:
        # Example: "12/25 12:00 PM: Payment to XYZ: $12.34"
        match = re.match(r'(\d{2}/\d{2}) (\d{1,2}:\d{2} [AP]M): Payment to (.+?): \$(\d+\.\d{2})', line)
        if match:
            date_str, time_str, description, amount = match.groups()
            date = datetime.strptime(f"{date_str} {time_str}", "%m/%d %I:%M %p").replace(year=datetime.now().year)
            transactions.append({
                'type': 'sms',
                'date': date,
                'description': description,
                'amount': float(amount),
                'category': 'unknown'
            })
    return transactions

# Parse PDF statement
def parse_statement(file_path):
    if not HAVE_PDFPLUMBER:
        print(f"[skip] pdfplumber not installed — cannot parse {file_path} (pip install pdfplumber)")
        return []
    transactions = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # Example: "12/25 Payment to XYZ: $12.34"
            lines = text.split('\n')
            for line in lines:
                match = re.match(r'(\d{2}/\d{2}) (.+?): \$(\d+\.\d{2})', line)
                if match:
                    date_str, description, amount = match.groups()
                    date = datetime.strptime(date_str, "%m/%d").replace(year=datetime.now().year)
                    transactions.append({
                        'type': 'pdf',
                        'date': date,
                        'description': description,
                        'amount': float(amount),
                        'category': 'unknown'
                    })
    return transactions

# Categorize transactions
def categorize_transactions(transactions, budgets):
    categorized = []
    for tx in transactions:
        description = tx['description'].lower()
        category = 'unknown'
        for budget_item, _ in budgets.items():
            if budget_item in description:
                category = budget_item
                break
        categorized.append({**tx, 'category': category})
    return categorized

# Generate timeline
def generate_timeline(transactions):
    timeline = defaultdict(list)
    for tx in transactions:
        year = tx['date'].year
        month = tx['date'].month
        timeline[f"{year}-{month:02d}"].append(tx)
    return dict(timeline)

# Save timeline to JSON
def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def save_timeline(timeline, file_path):
    import json
    with open(file_path, 'w') as f:
        json.dump(timeline, f, indent=4, default=_json_default)

# Main entry point
def main():
    budgets = load_budgets()

    # Parse SMS
    sms_transactions = []
    for file_name in os.listdir(SMS_DIR):
        if file_name.endswith('.txt'):
            file_path = os.path.join(SMS_DIR, file_name)
            sms_transactions.extend(parse_sms(file_path))

    # Parse PDF statements
    pdf_transactions = []
    for file_name in os.listdir(STATEMENT_DIR):
        if file_name.endswith('.pdf'):
            file_path = os.path.join(STATEMENT_DIR, file_name)
            pdf_transactions.extend(parse_statement(file_path))

    # Combine and categorize transactions
    all_transactions = sms_transactions + pdf_transactions
    categorized_transactions = categorize_transactions(all_transactions, budgets)

    # Generate timeline
    timeline = generate_timeline(categorized_transactions)

    # Save timeline
    timeline_file = os.path.join(OUTPUT_DIR, 'timeline.json')
    save_timeline(timeline, timeline_file)

    print(f"Timeline saved to {timeline_file}")

if __name__ == '__main__':
    main()