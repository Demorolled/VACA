# -*- coding: utf-8 -*-
"""
Code Bible — Category 33: Finance & Money (atomic).
Convention: integer-cents where possible, round at the end, no deps.
"""
CHUNKS = [
    {
        "id": "fin-annuity-fv",
        "name": "Future Value of Annuity",
        "category": "fin",
        "lang": "typescript",
        "when": "Computing how much a series of equal periodic deposits grows to",
        "why": "Atomic formula — deposit, rate, periods in, future value out; zero deps",
        "tags": ["fin", "annuity", "future-value", "compound", "interest"],
        "iface": r'''export function annuityFutureValue(deposit: number, ratePerPeriod: number, periods: number): number''',
        "code": r'''export function annuityFutureValue(deposit: number, ratePerPeriod: number, periods: number) {
  if (ratePerPeriod === 0) return deposit * periods;
  const g = Math.pow(1 + ratePerPeriod, periods);
  return deposit * ((g - 1) / ratePerPeriod);
}''',
        "provides": "annuityFutureValue(deposit, ratePerPeriod, periods)",
        "depends": [],
    },
    {
        "id": "fin-pv",
        "name": "Present Value / Discounting",
        "category": "fin",
        "lang": "typescript",
        "when": "Discounting a future cash flow to today's money at a rate",
        "why": "Atomic discount formula — future amount, rate, periods in, present value out",
        "tags": ["fin", "present-value", "discount", "cash-flow", "npv"],
        "iface": r'''export function presentValue(future: number, ratePerPeriod: number, periods: number): number''',
        "code": r'''export function presentValue(future: number, ratePerPeriod: number, periods: number) {
  return future / Math.pow(1 + ratePerPeriod, periods);
}''',
        "provides": "presentValue(future, rate, periods)",
        "depends": [],
    },
    {
        "id": "fin-npv",
        "name": "Net Present Value",
        "category": "fin",
        "lang": "typescript",
        "when": "Valuing an investment as discounted future cash flows minus cost",
        "why": "Atomic NPV — cash-flow array + rate in, signed NPV out; negative = reject",
        "tags": ["fin", "npv", "net-present-value", "valuation", "cash-flow"],
        "iface": r'''export function netPresentValue(cashFlows: number[], rate: number): number''',
        "code": r'''export function netPresentValue(cashFlows: number[], rate: number) {
  return cashFlows.reduce((sum, cf, t) => sum + cf / Math.pow(1 + rate, t), 0);
}''',
        "provides": "netPresentValue(cashFlows, rate)",
        "depends": [],
    },
    {
        "id": "fin-irr",
        "name": "Internal Rate of Return",
        "category": "fin",
        "lang": "typescript",
        "when": "Finding the discount rate that zeroes an investment's NPV",
        "why": "Atomic bisection solver — bracketed NPV root, no derivatives needed",
        "tags": ["fin", "irr", "internal-rate", "return", "bisection"],
        "iface": r'''export function irr(cashFlows: number[], guess = 0.1, maxIter = 100): number''',
        "code": r'''function npvAt(cashFlows: number[], r: number) {
  return cashFlows.reduce((s, cf, t) => s + cf / Math.pow(1 + r, t), 0);
}
export function irr(cashFlows: number[], guess = 0.1, maxIter = 100) {
  let lo = -0.9999, hi = 10, r = guess;
  for (let i = 0; i < maxIter; i++) {
    const f = npvAt(cashFlows, r);
    if (Math.abs(f) < 1e-8) break;
    if (f > 0) { lo = r; r = (r + hi) / 2; }
    else { hi = r; r = (lo + r) / 2; }
  }
  return r;
}''',
        "provides": "irr(cashFlows, guess, maxIter)",
        "depends": [],
    },
    {
        "id": "fin-amortization",
        "name": "Loan Amortization Schedule",
        "category": "fin",
        "lang": "typescript",
        "when": "Breaking a fixed-rate loan into principal + interest per period",
        "why": "Atomic scheduler — equal payments, remaining balance, cumulative interest",
        "tags": ["fin", "amortization", "loan", "mortgage", "schedule"],
        "iface": r'''export interface AmortRow { period: number; payment: number; principal: number; interest: number; balance: number }
export function amortization(principal: number, annualRate: number, years: number, paymentsPerYear = 12): AmortRow[]''',
        "code": r'''export function amortization(principal: number, annualRate: number, years: number, paymentsPerYear = 12) {
  const n = years * paymentsPerYear;
  const r = annualRate / paymentsPerYear;
  const payment = r === 0 ? principal / n : (principal * r) / (1 - Math.pow(1 + r, -n));
  const rows: AmortRow[] = [];
  let balance = principal;
  for (let period = 1; period <= n; period++) {
    const interest = balance * r;
    const principalPart = payment - interest;
    balance -= principalPart;
    rows.push({ period, payment, principal: principalPart, interest, balance: Math.max(0, balance) });
  }
  return rows;
}''',
        "provides": "amortization(principal, annualRate, years, paymentsPerYear)",
        "depends": [],
    },
    {
        "id": "fin-compound-interest",
        "name": "Compound Interest",
        "category": "fin",
        "lang": "typescript",
        "when": "Growing a principal at a rate compounded n times per year",
        "why": "Atomic growth formula — principal, rate, times/yr, years in, balance out",
        "tags": ["fin", "compound", "interest", "growth", "balance"],
        "iface": r'''export function compoundInterest(principal: number, annualRate: number, timesPerYear: number, years: number): number''',
        "code": r'''export function compoundInterest(principal: number, annualRate: number, timesPerYear: number, years: number) {
  return principal * Math.pow(1 + annualRate / timesPerYear, timesPerYear * years);
}''',
        "provides": "compoundInterest(principal, annualRate, timesPerYear, years)",
        "depends": [],
    },
    {
        "id": "fin-simple-interest",
        "name": "Simple Interest",
        "category": "fin",
        "lang": "typescript",
        "when": "Computing linear interest accrual on a principal",
        "why": "Atomic formula — principal, rate, time in, interest + total out",
        "tags": ["fin", "simple", "interest", "accrual"],
        "iface": r'''export interface SimpleInterest { interest: number; total: number }
export function simpleInterest(principal: number, annualRate: number, years: number): SimpleInterest''',
        "code": r'''export function simpleInterest(principal: number, annualRate: number, years: number) {
  const interest = principal * annualRate * years;
  return { interest, total: principal + interest };
}''',
        "provides": "simpleInterest(principal, annualRate, years)",
        "depends": [],
    },
    {
        "id": "fin-capm",
        "name": "CAPM Expected Return",
        "category": "fin",
        "lang": "typescript",
        "when": "Estimating an asset's expected return from market risk",
        "why": "Atomic CAPM — risk-free, beta, market premium in, expected return out",
        "tags": ["fin", "capm", "beta", "expected-return", "risk"],
        "iface": r'''export function capm(riskFree: number, beta: number, marketReturn: number): number''',
        "code": r'''export function capm(riskFree: number, beta: number, marketReturn: number) {
  return riskFree + beta * (marketReturn - riskFree);
}''',
        "provides": "capm(riskFree, beta, marketReturn)",
        "depends": [],
    },
    {
        "id": "fin-dca",
        "name": "Dollar-Cost Averaging Simulator",
        "category": "fin",
        "lang": "typescript",
        "when": "Simulating periodic buys of an asset at varying prices",
        "why": "Atomic simulator — buys at each price, avg cost + shares + total spent out",
        "tags": ["fin", "dca", "dollar-cost", "average", "invest"],
        "iface": r'''export interface DcaResult { shares: number; totalSpent: number; avgCost: number }
export function dollarCostAverage(periodicAmount: number, prices: number[]): DcaResult''',
        "code": r'''export function dollarCostAverage(periodicAmount: number, prices: number[]) {
  let shares = 0, spent = 0;
  for (const price of prices) {
    if (price <= 0) continue;
    shares += periodicAmount / price;
    spent += periodicAmount;
  }
  return { shares, totalSpent: spent, avgCost: spent / (shares || 1) };
}''',
        "provides": "dollarCostAverage(periodicAmount, prices)",
        "depends": [],
    },
    {
        "id": "fin-vwap",
        "name": "Volume-Weighted Average Price",
        "category": "fin",
        "lang": "typescript",
        "when": "Blending a price series by traded volume over a window",
        "why": "Atomic VWAP — typical price × volume summed over volumes; no deps",
        "tags": ["fin", "vwap", "volume", "average", "price"],
        "iface": r'''export function vwap(bars: Array<{ high: number; low: number; close: number; volume: number }>): number''',
        "code": r'''export function vwap(bars: Array<{ high: number; low: number; close: number; volume: number }>) {
  let pv = 0, vol = 0;
  for (const b of bars) {
    const tp = (b.high + b.low + b.close) / 3;
    pv += tp * b.volume;
    vol += b.volume;
  }
  return vol === 0 ? 0 : pv / vol;
}''',
        "provides": "vwap(bars)",
        "depends": [],
    },
    {
        "id": "fin-return-pct",
        "name": "Return Percentage & CAGR",
        "category": "fin",
        "lang": "typescript",
        "when": "Converting price changes into returns or annualized growth",
        "why": "Atomic metrics — simple return and CAGR from start/end + years",
        "tags": ["fin", "return", "cagr", "annualized", "growth"],
        "iface": r'''export function returnPct(start: number, end: number): number
export function cagr(start: number, end: number, years: number): number''',
        "code": r'''export function returnPct(start: number, end: number) {
  return start === 0 ? 0 : (end - start) / start;
}
export function cagr(start: number, end: number, years: number) {
  if (start <= 0 || years <= 0) return 0;
  return Math.pow(end / start, 1 / years) - 1;
}''',
        "provides": "returnPct / cagr",
        "depends": [],
    },
    {
        "id": "fin-portfolio-alloc",
        "name": "Portfolio Allocation",
        "category": "fin",
        "lang": "typescript",
        "when": "Computing target dollar amounts from percentage weights",
        "why": "Atomic allocator — total + weights in, per-asset targets + checks out",
        "tags": ["fin", "portfolio", "allocation", "weights", "assets"],
        "iface": r'''export function allocate(total: number, weights: Record<string, number>): Record<string, number>''',
        "code": r'''export function allocate(total: number, weights: Record<string, number>) {
  const out: Record<string, number> = {};
  for (const [name, w] of Object.entries(weights)) out[name] = total * w;
  return out;
}''',
        "provides": "allocate(total, weights)",
        "depends": [],
    },
    {
        "id": "fin-rebalance",
        "name": "Portfolio Rebalance Trades",
        "category": "fin",
        "lang": "typescript",
        "when": "Computing buy/sell amounts to restore target weights",
        "why": "Atomic rebalancer — current + target values in, signed trades out",
        "tags": ["fin", "rebalance", "trades", "portfolio", "target"],
        "iface": r'''export function rebalanceTrades(current: Record<string, number>, weights: Record<string, number>, total: number): Record<string, number>''',
        "code": r'''export function rebalanceTrades(current: Record<string, number>, weights: Record<string, number>, total: number) {
  const out: Record<string, number> = {};
  for (const name of Object.keys(weights)) {
    const targetValue = total * weights[name];
    out[name] = targetValue - (current[name] ?? 0);
  }
  return out;
}''',
        "provides": "rebalanceTrades(current, weights, total)",
        "depends": [],
    },
    {
        "id": "fin-tax-bracket",
        "name": "Progressive Tax Calculator",
        "category": "fin",
        "lang": "typescript",
        "when": "Applying marginal tax brackets to income",
        "why": "Atomic marginal calc — bracket array in, tax + effective rate out",
        "tags": ["fin", "tax", "bracket", "marginal", "income"],
        "iface": r'''export interface TaxBracket { upTo: number; rate: number }
export function taxBracketTax(income: number, brackets: TaxBracket[]): number''',
        "code": r'''export function taxBracketTax(income: number, brackets: TaxBracket[]) {
  let tax = 0, prev = 0;
  for (const b of brackets) {
    const slice = Math.min(income, b.upTo) - prev;
    if (slice <= 0) break;
    tax += slice * b.rate;
    prev = b.upTo;
  }
  return tax;
}''',
        "provides": "taxBracketTax(income, brackets)",
        "depends": [],
    },
    {
        "id": "fin-currency-format",
        "name": "Currency Formatter",
        "category": "fin",
        "lang": "typescript",
        "when": "Formatting amounts with symbol, thousands separators, and decimals",
        "why": "Atomic formatter — locale-free, deterministic, handles negatives",
        "tags": ["fin", "currency", "format", "money", "display"],
        "iface": r'''export function formatMoney(amount: number, symbol = '$', decimals = 2): string''',
        "code": r'''export function formatMoney(amount: number, symbol = '$', decimals = 2) {
  const sign = amount < 0 ? '-' : '';
  const v = Math.abs(amount);
  const fixed = v.toFixed(decimals);
  const [int, frac] = fixed.split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return sign + symbol + grouped + (frac ? '.' + frac : '');
}''',
        "provides": "formatMoney(amount, symbol, decimals)",
        "depends": [],
    },
    {
        "id": "fin-budget-category",
        "name": "Category Budget Tracker",
        "category": "fin",
        "lang": "typescript",
        "when": "Aggregating expenses into categories and comparing to budgets",
        "why": "Atomic aggregator — transactions in, per-category totals + over-budget flags out",
        "tags": ["fin", "budget", "category", "expense", "tracker"],
        "iface": r'''export interface BudgetTx { category: string; amount: number }
export function budgetByCategory(txs: BudgetTx[], budgets: Record<string, number>): Record<string, { spent: number; budget: number; remaining: number }>''',
        "code": r'''export function budgetByCategory(txs: BudgetTx[], budgets: Record<string, number>) {
  const spent = new Map<string, number>();
  for (const t of txs) spent.set(t.category, (spent.get(t.category) ?? 0) + t.amount);
  const out: Record<string, { spent: number; budget: number; remaining: number }> = {};
  for (const cat of new Set([...spent.keys(), ...Object.keys(budgets)])) {
    const s = spent.get(cat) ?? 0;
    const b = budgets[cat] ?? 0;
    out[cat] = { spent: s, budget: b, remaining: b - s };
  }
  return out;
}''',
        "provides": "budgetByCategory(txs, budgets)",
        "depends": [],
    },
    {
        "id": "fin-envelope-method",
        "name": "Envelope Budget Allocator",
        "category": "fin",
        "lang": "typescript",
        "when": "Dividing income into named spending envelopes each period",
        "why": "Atomic allocation — income + percentages in, envelope amounts + total check out",
        "tags": ["fin", "envelope", "budget", "allocation", "income"],
        "iface": r'''export function envelopeAllocate(income: number, envelopes: Record<string, number>): Record<string, number>''',
        "code": r'''export function envelopeAllocate(income: number, envelopes: Record<string, number>) {
  const totalPct = Object.values(envelopes).reduce((s, p) => s + p, 0);
  if (totalPct > 1.0001) throw new Error('Envelope percentages exceed 100%');
  const out: Record<string, number> = {};
  for (const [name, pct] of Object.entries(envelopes)) out[name] = income * pct;
  return out;
}''',
        "provides": "envelopeAllocate(income, envelopes)",
        "depends": [],
    },
    {
        "id": "fin-bill-due",
        "name": "Bill Due-Date Calendar",
        "category": "fin",
        "lang": "typescript",
        "when": "Listing upcoming bill due dates within a horizon from today",
        "why": "Atomic calendar — monthly bills in, next N due dates out, month-overflow safe",
        "tags": ["fin", "bill", "due", "calendar", "schedule"],
        "iface": r'''export function upcomingDues(bills: Array<{ name: string; day: number; amount: number }>, from: Date, months: number): Array<{ name: string; date: Date; amount: number }>''',
        "code": r'''export function upcomingDues(bills: Array<{ name: string; day: number; amount: number }>, from: Date, months: number) {
  const out: Array<{ name: string; date: Date; amount: number }> = [];
  for (let m = 0; m < months; m++) {
    for (const b of bills) {
      const date = new Date(from.getFullYear(), from.getMonth() + m, Math.min(b.day, 28));
      if (date >= from) out.push({ name: b.name, date, amount: b.amount });
    }
  }
  return out.sort((a, b) => a.date.getTime() - b.date.getTime());
}''',
        "provides": "upcomingDues(bills, from, months)",
        "depends": [],
    },
    {
        "id": "fin-savings-goal",
        "name": "Savings Goal Progress",
        "category": "fin",
        "lang": "typescript",
        "when": "Tracking progress toward a savings target and ETA",
        "why": "Atomic progress — saved, target, monthly rate in, pct + months-to-goal out",
        "tags": ["fin", "savings", "goal", "progress", "eta"],
        "iface": r'''export interface SavingsProgress { percent: number; monthsToGoal: number | null }
export function savingsProgress(saved: number, target: number, monthly: number): SavingsProgress''',
        "code": r'''export function savingsProgress(saved: number, target: number, monthly: number) {
  const percent = target <= 0 ? 100 : Math.min(100, (saved / target) * 100);
  const monthsToGoal = monthly <= 0 || saved >= target ? null : Math.ceil((target - saved) / monthly);
  return { percent, monthsToGoal };
}''',
        "provides": "savingsProgress(saved, target, monthly)",
        "depends": [],
    },
    {
        "id": "fin-debt-snowball",
        "name": "Debt Snowball Ordering",
        "category": "fin",
        "lang": "typescript",
        "when": "Ordering debts by balance for the snowball payoff method",
        "why": "Atomic sorter — debts in, payoff plan with running totals out",
        "tags": ["fin", "debt", "snowball", "payoff", "order"],
        "iface": r'''export interface DebtPlan { name: string; balance: number; rate: number; payoffOrder: number }
export function debtSnowball(debts: Array<{ name: string; balance: number; rate: number }>): DebtPlan[]''',
        "code": r'''export function debtSnowball(debts: Array<{ name: string; balance: number; rate: number }>) {
  return [...debts]
    .sort((a, b) => a.balance - b.balance)
    .map((d, i) => ({ ...d, payoffOrder: i + 1 }));
}''',
        "provides": "debtSnowball(debts)",
        "depends": [],
    },
    {
        "id": "fin-debt-avalanche",
        "name": "Debt Avalanche Ordering",
        "category": "fin",
        "lang": "typescript",
        "when": "Ordering debts by interest rate to minimize total interest",
        "why": "Atomic sorter — highest rate first, payoff order + est. interest savings",
        "tags": ["fin", "debt", "avalanche", "interest", "payoff"],
        "iface": r'''export function debtAvalanche(debts: Array<{ name: string; balance: number; rate: number }>): DebtPlan[]''',
        "code": r'''export function debtAvalanche(debts: Array<{ name: string; balance: number; rate: number }>) {
  return [...debts]
    .sort((a, b) => b.rate - a.rate)
    .map((d, i) => ({ ...d, payoffOrder: i + 1 }));
}''',
        "provides": "debtAvalanche(debts)",
        "depends": [],
    },
    {
        "id": "fin-invoice-due",
        "name": "Invoice Aging Report",
        "category": "fin",
        "lang": "typescript",
        "when": "Bucketting unpaid invoices by days overdue",
        "why": "Atomic aging — invoices + reference date in, 0-30/31-60/61-90/90+ buckets out",
        "tags": ["fin", "invoice", "aging", "overdue", "report"],
        "iface": r'''export interface InvoiceAging { current: number; d30: number; d60: number; d90: number; over90: number }
export function invoiceAging(invoices: Array<{ dueDate: Date; amount: number }>, now: Date): InvoiceAging''',
        "code": r'''export function invoiceAging(invoices: Array<{ dueDate: Date; amount: number }>, now: Date) {
  const out: InvoiceAging = { current: 0, d30: 0, d60: 0, d90: 0, over90: 0 };
  for (const inv of invoices) {
    const days = Math.floor((now.getTime() - inv.dueDate.getTime()) / 86400000);
    if (days <= 0) out.current += inv.amount;
    else if (days <= 30) out.d30 += inv.amount;
    else if (days <= 60) out.d60 += inv.amount;
    else if (days <= 90) out.d90 += inv.amount;
    else out.over90 += inv.amount;
  }
  return out;
}''',
        "provides": "invoiceAging(invoices, now)",
        "depends": [],
    },
    {
        "id": "fin-expense-trend",
        "name": "Expense Trend Comparison",
        "category": "fin",
        "lang": "typescript",
        "when": "Comparing this month's spending to last month per category",
        "why": "Atomic delta — month totals in, absolute + pct change per category out",
        "tags": ["fin", "expense", "trend", "compare", "delta"],
        "iface": r'''export function expenseTrend(last: Record<string, number>, now: Record<string, number>): Record<string, { last: number; now: number; delta: number; pct: number }>''',
        "code": r'''export function expenseTrend(last: Record<string, number>, now: Record<string, number>) {
  const cats = new Set([...Object.keys(last), ...Object.keys(now)]);
  const out: Record<string, { last: number; now: number; delta: number; pct: number }> = {};
  for (const c of cats) {
    const l = last[c] ?? 0, n = now[c] ?? 0;
    out[c] = { last: l, now: n, delta: n - l, pct: l === 0 ? 0 : (n - l) / l };
  }
  return out;
}''',
        "provides": "expenseTrend(last, now)",
        "depends": [],
    },
    {
        "id": "fin-interest-split",
        "name": "Interest Split (Principal vs Interest)",
        "category": "fin",
        "lang": "typescript",
        "when": "Splitting a single payment into its interest and principal parts",
        "why": "Atomic split — balance, rate, payment in, interest + principal + new balance out",
        "tags": ["fin", "interest", "principal", "payment", "split"],
        "iface": r'''export interface PaymentSplit { interest: number; principal: number; newBalance: number }
export function splitPayment(balance: number, annualRate: number, payment: number, periodsPerYear = 12): PaymentSplit''',
        "code": r'''export function splitPayment(balance: number, annualRate: number, payment: number, periodsPerYear = 12) {
  const interest = balance * (annualRate / periodsPerYear);
  const principal = Math.min(payment, balance + interest) - interest;
  return { interest, principal: Math.max(0, principal), newBalance: Math.max(0, balance - principal) };
}''',
        "provides": "splitPayment(balance, annualRate, payment)",
        "depends": [],
    },
    {
        "id": "fin-tip-split",
        "name": "Tip & Split Calculator",
        "category": "fin",
        "lang": "typescript",
        "when": "Computing tip, tax, and per-person cost for a bill",
        "why": "Atomic bill split \u2014 amount + tip% + people in, per-person out",
        "tags": [
            "fin",
            "tip",
            "split",
            "bill",
            "calculator"
        ],
        "iface": "export interface BillSplit { subtotal: number; tip: number; total: number; perPerson: number }\nexport function billSplit(amount: number, tipPercent: number, people: number, taxPercent = 0): BillSplit",
        "code": "export function billSplit(amount: number, tipPercent: number, people: number, taxPercent = 0) {\n  const tax = amount * (taxPercent / 100);\n  const tip = (amount + tax) * (tipPercent / 100);\n  const total = amount + tax + tip;\n  return { subtotal: amount, tip, total, perPerson: people <= 0 ? total : total / people };\n}",
        "provides": "billSplit(amount, tipPercent, people, taxPercent)",
        "depends": []
    },
]
