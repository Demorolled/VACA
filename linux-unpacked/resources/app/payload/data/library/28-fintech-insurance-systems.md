# 💰 Fintech & Insurance Systems

> Reference for building fintech and insurance applications — payment processing, core banking, ledger systems, insurance lifecycle, and regulatory compliance.
> Extracted from The Programming Bible's Fintech & Insurance level.

---

## 1. Payment Processing

### Payment Gateway Architecture

```
Merchant App
    │
    ▼
┌──────────────────────┐
│   Payment Gateway     │  Authorization, Capture, Refund
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│   Payment Processor   │  Routes to card networks
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│   Card Networks       │  Visa, Mastercard, Amex
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│   Issuing Bank        │  Customer's bank
└──────────────────────┘
```

### Transaction States

```
    ┌──────────┐
    │  Init    │
    └────┬─────┘
         ▼
    ┌──────────┐
    │ Pending  │
    └────┬─────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌────────┐
│ Author- │ │Failed  │
│  ized   │ └────────┘
└────┬───┘
     │
┌────┴────┐
│         │
▼         ▼
┌────────┐ ┌────────┐
│Capture │ │ Void   │
└────┬───┘ └────────┘
     │
     ▼
┌──────────┐     ┌──────────┐
│Settled   │────▶│Refunded  │
└──────────┘     └──────────┘
                    │
                    ▼
               ┌──────────┐
               │Partial   │
               │Chargeback│
               └──────────┘
```

### Payment Integration Pattern

```typescript
// Stripe-style payment integration
interface PaymentIntent {
  id: string;
  amount: number;        // In cents
  currency: string;
  status: 'requires_payment_method' | 'requires_confirmation' | 'succeeded' | 'failed';
  customerId: string;
  metadata: Record<string, string>;
}

class PaymentService {
  constructor(
    private apiKey: string,
    private webhookSecret: string,
  ) {}

  async createPayment(amount: number, currency: string, customerId: string): Promise<PaymentIntent> {
    const response = await fetch('https://api.stripe.com/v1/payment_intents', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        amount: String(amount),
        currency: currency.toLowerCase(),
        customer: customerId,
        'automatic_payment_methods[enabled]': 'true',
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(`Payment failed: ${error.error.message}`);
    }

    return response.json();
  }

  async capturePayment(paymentIntentId: string): Promise<PaymentIntent> {
    const response = await fetch(
      `https://api.stripe.com/v1/payment_intents/${paymentIntentId}/capture`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      },
    );

    return response.json();
  }

  async refundPayment(paymentIntentId: string, amount?: number): Promise<void> {
    const body: Record<string, string> = { payment_intent: paymentIntentId };
    if (amount) body.amount = String(amount);

    await fetch('https://api.stripe.com/v1/refunds', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams(body),
    });
  }

  // Webhook handler for async events
  async handleWebhook(payload: string, signature: string): Promise<void> {
    // Verify webhook signature
    const event = this.verifyWebhookSignature(payload, signature);

    switch (event.type) {
      case 'payment_intent.succeeded':
        await this.onPaymentSucceeded(event.data.object);
        break;
      case 'payment_intent.payment_failed':
        await this.onPaymentFailed(event.data.object);
        break;
      case 'charge.refunded':
        await this.onRefundProcessed(event.data.object);
        break;
      case 'charge.dispute.created':
        await this.onChargebackCreated(event.data.object);
        break;
    }
  }
}
```

### PCI DSS Compliance Levels

| Level | Transaction Volume | Requirements |
|---|---|---|
| **SAQ A** | Fully outsourced | Minimal — no direct handling |
| **SAQ A-EP** | E-commerce, outsourced | Validation of iframe/redirect |
| **SAQ B** | Imprint/terminal only | Physical terminal security |
| **SAQ B-IP** | E-commerce, terminal | Terminal + basic web controls |
| **SAQ C-VT** | Virtual terminal | Web-based manual entry |
| **SAQ D** | Full responsibility | Most rigorous — 326 controls |

---

## 2. Core Banking & Ledger Systems

### Double-Entry Accounting

```
Accounting Equation: Assets = Liabilities + Equity

Every transaction:
- Debits MUST equal Credits
- At least two accounts affected
- Audit trail preserved forever

Example: Customer deposits $100
  Debit: Cash (asset) +$100
  Credit: Customer Deposit (liability) +$100
```

### Account Types

| Account | Type | Normal Balance | Examples |
|---|---|---|---|
| **Asset** | Balance Sheet | Debit | Cash, Accounts Receivable, Loans |
| **Liability** | Balance Sheet | Credit | Deposits, Accounts Payable |
| **Equity** | Balance Sheet | Credit | Retained Earnings, Capital |
| **Revenue** | P&L | Credit | Interest Income, Fees |
| **Expense** | P&L | Debit | Salaries, Rent, Interest |

### Ledger Implementation

```typescript
// Core ledger transaction
interface LedgerTransaction {
  id: string;
  date: Date;
  description: string;
  entries: LedgerEntry[];
  metadata: Record<string, string>;
}

interface LedgerEntry {
  accountId: string;
  amount: number;         // Always positive — sign determined by debit/credit
  direction: 'debit' | 'credit';
  currency: string;
}

class DoubleEntryLedger {
  private transactions: LedgerTransaction[] = [];

  postTransaction(tx: LedgerTransaction): void {
    // 1. Validate balanced
    const totalDebits = tx.entries
      .filter(e => e.direction === 'debit')
      .reduce((sum, e) => sum + e.amount, 0);
    const totalCredits = tx.entries
      .filter(e => e.direction === 'credit')
      .reduce((sum, e) => sum + e.amount, 0);

    if (Math.abs(totalDebits - totalCredits) > 0.001) {
      throw new Error(`Unbalanced transaction: debits=${totalDebits}, credits=${totalCredits}`);
    }

    // 2. Check sufficient balance for debited accounts
    for (const entry of tx.entries) {
      if (entry.direction === 'debit') {
        const balance = this.getAccountBalance(entry.accountId);
        if (balance < entry.amount) {
          throw new Error(`Insufficient balance in account ${entry.accountId}`);
        }
      }
    }

    // 3. Post (immutable — append only)
    this.transactions.push(tx);
  }

  getAccountBalance(accountId: string): number {
    let balance = 0;
    for (const tx of this.transactions) {
      for (const entry of tx.entries) {
        if (entry.accountId === accountId) {
          balance += entry.direction === 'debit' ? -entry.amount : entry.amount;
        }
      }
    }
    return balance;
  }

  getAccountStatement(accountId: string, from: Date, to: Date): LedgerTransaction[] {
    return this.transactions.filter(tx =>
      tx.entries.some(e => e.accountId === accountId) &&
      tx.date >= from && tx.date <= to
    );
  }
}
```

### Balance Types

| Balance | Definition | Logic |
|---|---|---|
| **Current Balance** | End-of-day book balance | Sum of all posted transactions |
| **Available Balance** | Usable funds | Current - holds - pending |
| **Ledger Balance** | Total posted | Sum of all entries in GL |
| **Collected Balance** | Cleared funds | Excluding uncollected deposits |

---

## 3. Insurance Lifecycle

```
Product Design → Rating → Underwriting → Policy Admin → Billing → Claims → Reinsurance
     │              │           │             │          │        │           │
     ▼              ▼           ▼             ▼          ▼        ▼           ▼
  Coverages     Premium    Risk         Policy         Premium  Claim      Risk
  Terms         Calc       Selection    Issuance       Collect  Adjudicate Transfer
```

### Policy Data Model

```typescript
interface InsurancePolicy {
  id: string;
  policyNumber: string;
  productType: 'auto' | 'home' | 'life' | 'health' | 'commercial';
  status: 'active' | 'lapsed' | 'cancelled' | 'expired';

  // Parties
  policyHolder: Party;
  insured: Party[];
  beneficiaries?: Party[];

  // Coverage
  coverages: Coverage[];
  premium: Premium;
  deductibles: Deductible[];

  // Dates
  effectiveDate: Date;
  expirationDate: Date;
  cancellationDate?: Date;
}

interface Coverage {
  code: string;          // e.g., 'LIAB', 'COLL', 'COMP'
  name: string;          // e.g., 'Liability', 'Collision'
  limit: number;
  deductible: number;
}

interface Premium {
  total: number;
  base: number;
  taxes: number;
  fees: number;
  discounts: Discount[];
  surcharges: Surcharge[];
  billingFrequency: 'monthly' | 'quarterly' | 'semi-annual' | 'annual';
}

// Claims processing
interface InsuranceClaim {
  id: string;
  policyId: string;
  lossDate: Date;
  reportDate: Date;
  status: 'filed' | 'investigating' | 'estimating' | 'approved' | 'denied' | 'paid';
  lossType: string;
  description: string;
  estimatedAmount: number;
  paidAmount: number;
  reserve: number;       // Amount set aside for this claim
  adjusterId: string;
}
```

---

## 4. Digital Banking API Layer

### Open Banking API Pattern

```typescript
// Standard banking API resources
interface BankAccount {
  id: string;
  accountNumber: string;     // Masked
  type: 'checking' | 'savings' | 'credit_card' | 'loan' | 'investment';
  status: 'active' | 'frozen' | 'closed';
  balances: {
    current: number;
    available: number;
    ledger: number;
  };
  currency: string;
  openedAt: Date;
}

interface BankTransaction {
  id: string;
  accountId: string;
  amount: number;
  direction: 'credit' | 'debit';
  description: string;
  category: string;        // MCC code or custom
  status: 'pending' | 'posted' | 'reversed';
  postingDate: Date;
  transactionDate: Date;
  merchantName?: string;
  reference: string;
}

// Banking API client
class BankingAPI {
  constructor(private baseUrl: string, private clientId: string, private clientSecret: string) {}

  private async getAccessToken(): Promise<string> {
    // OAuth2 client credentials flow
    const response = await fetch(`${this.baseUrl}/oauth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'client_credentials',
        client_id: this.clientId,
        client_secret: this.clientSecret,
        scope: 'accounts transactions payments',
      }),
    });
    const data = await response.json();
    return data.access_token;
  }

  async getAccounts(token: string): Promise<BankAccount[]> {
    const response = await fetch(`${this.baseUrl}/open-banking/v3.1/accounts`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    return response.json();
  }

  async getTransactions(token: string, accountId: string, from?: Date, to?: Date): Promise<BankTransaction[]> {
    const params = new URLSearchParams();
    if (from) params.set('fromDate', from.toISOString());
    if (to) params.set('toDate', to.toISOString());

    const response = await fetch(
      `${this.baseUrl}/open-banking/v3.1/accounts/${accountId}/transactions?${params}`,
      { headers: { 'Authorization': `Bearer ${token}` } },
    );
    return response.json();
  }

  async initiatePayment(token: string, payment: {
    sourceAccountId: string;
    destinationIBAN: string;
    amount: number;
    reference: string;
  }): Promise<{ paymentId: string; status: string }> {
    const response = await fetch(`${this.baseUrl}/open-banking/v3.1/payments`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payment),
    });
    return response.json();
  }
}
```

---

## Quick Reference: Fintech by Node Type

| Node Type | Fintech/Insurance Mapping |
|---|---|
| **Input** | Payment form, claim submission, KYC document upload, transaction import |
| **Logic** | Underwriting rules engine, premium calculation, fraud detection, payment reconciliation |
| **Database** | Ledger (immutable), policy store, claims DB, audit trail |
| **UI** | Payment checkout, banking dashboard, claims portal, policy management |
| **API** | Payment gateway, open banking APIs, credit bureau integration, regulatory reporting |

---

*For deeper fintech concepts, see Bible level `38-fintech-insurance/` — payments, core banking, lending, insurance tech, digital banking, and regulatory compliance.*
