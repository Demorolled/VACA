import datetime
import json

# Define the file path for the expenses data
EXPENSES_FILE = 'expenses.json'

# Load existing expenses from the file, if it exists
try:
    with open(EXPENSES_FILE, 'r') as file:
        expenses = json.load(file)
except FileNotFoundError:
    expenses = []

def save_expenses():
    """Save the current list of expenses to the file."""
    with open(EXPENSES_FILE, 'w') as file:
        json.dump(expenses, file, indent=4)

def add_expense(date, amount, description):
    """Add a new expense to the list."""
    expense = {
        'date': date,
        'amount': float(amount),
        'description': description
    }
    expenses.append(expense)
    save_expenses()
    print(f"Expense added: {date} - ${amount:.2f} - {description}")

def get_monthly_summary(year, month):
    """Return a summary of expenses for a given month and year."""
    month = int(month)
    year = int(year)
    total = 0
    summary = []
    for expense in expenses:
        expense_date = datetime.datetime.strptime(expense['date'], '%Y-%m-%d')
        if expense_date.year == year and expense_date.month == month:
            total += expense['amount']
            summary.append(expense)
    return {
        'total': total,
        'expenses': summary
    }

def list_expenses():
    """List all expenses."""
    if not expenses:
        print("No expenses found.")
        return
    for i, expense in enumerate(expenses, 1):
        print(f"{i}. {expense['date']} - ${expense['amount']:.2f} - {expense['description']}")

def main():
    while True:
        print("\nExpense Tracker")
        print("1. Add Expense")
        print("2. View Monthly Summary")
        print("3. List All Expenses")
        print("4. Exit")
        choice = input("Choose an option: ").strip()

        if choice == '1':
            date = input("Enter date (YYYY-MM-DD): ").strip()
            amount = input("Enter amount: ").strip()
            description = input("Enter description: ").strip()
            add_expense(date, amount, description)
        elif choice == '2':
            year = input("Enter year: ").strip()
            month = input("Enter month: ").strip()
            summary = get_monthly_summary(year, month)
            print(f"\nMonthly Summary for {year}-{month}:")
            print(f"Total: ${summary['total']:.2f}")
            print("Expenses:")
            for expense in summary['expenses']:
                print(f"{expense['date']} - ${expense['amount']:.2f} - {expense['description']}")
        elif choice == '3':
            list_expenses()
        elif choice == '4':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == '__main__':
    main()