# 🛒 Marketplace & E-Commerce Platforms

> Reference for building two-sided marketplaces and e-commerce platforms — listings, payments, trust/safety, logistics, and platform economics.
> Extracted from The Programming Bible's Marketplace & Sharing Economy and E-Commerce levels.

---

## 1. Marketplace Architecture

### Two-Sided Platform Design

```
┌────────────────────────────────────────────────────┐
│                  MARKETPLACE                        │
│                                                      │
│  ┌─────────────┐              ┌─────────────┐      │
│  │  Seller Side │              │  Buyer Side │      │
│  │              │              │             │      │
│  │ • Listings   │              │ • Search    │      │
│  │ • Inventory  │              │ • Browse    │      │
│  │ • Orders     │    Matching   │ • Compare   │      │
│  │ • Analytics  │◄───────────►│ • Purchase  │      │
│  │ • Payouts    │              │ • Reviews   │      │
│  └──────┬───────┘              └──────┬──────┘      │
│         │                            │              │
└─────────┼────────────────────────────┼──────────────┘
          │                            │
┌─────────▼────────────────────────────▼──────────────┐
│              CROSS-CUTTING SERVICES                  │
│  Payments  │  Trust & Safety  │  Disputes  │  Tax    │
│  Messaging │  Recommendations │  Analytics │  Fraud  │
└──────────────────────────────────────────────────────┘
```

### Key Metrics

| Metric | Definition | Target |
|---|---|---|
| **GMV** | Gross Merchandise Value | Revenue driver |
| **Take Rate** | Platform commission % | 10-30% |
| **Liquidity** | Buyers per seller per day | >1.0 |
| **Conversion** | Searches → purchases | 2-10% |
| **NPS** | Net Promoter Score | >50 |
| **CAC** | Customer Acquisition Cost | < LTV/3 |

---

## 2. Listing & Search

### Product Catalog Schema

```typescript
// Marketplace listing data model
interface Listing {
    id: string;
    sellerId: string;
    title: string;
    description: string;
    price: Money;
    category: string;
    condition: 'new' | 'like-new' | 'good' | 'fair';
    location: GeoPoint;
    images: string[];
    attributes: Record<string, string>;  // Dynamic per category
    status: 'active' | 'reserved' | 'sold' | 'inactive';
    createdAt: Date;
    updatedAt: Date;
}

interface Money {
    amount: number;       // In smallest unit (cents)
    currency: string;     // ISO 4217
}

interface GeoPoint {
    lat: number;
    lng: number;
    radius?: number;      // Search radius in meters
}

// Category-specific attributes
const CATEGORY_SCHEMAS: Record<string, Record<string, string>> = {
    electronics: {
        brand: 'string',
        model: 'string',
        storage: 'enum:64GB,128GB,256GB,512GB,1TB',
        color: 'string',
        warranty_months: 'number',
    },
    vehicles: {
        make: 'string',
        model: 'string',
        year: 'number',
        mileage: 'number',
        fuel_type: 'enum:gasoline,diesel,electric,hybrid',
        transmission: 'enum:automatic,manual',
    },
    real_estate: {
        property_type: 'enum:apartment,house,condo,land',
        bedrooms: 'number',
        bathrooms: 'number',
        sqft: 'number',
        year_built: 'number',
    },
};
```

### Geo-Search with Filtering

```typescript
// Location-based listing search
interface SearchFilters {
    query?: string;
    category?: string;
    minPrice?: number;
    maxPrice?: number;
    location?: GeoPoint;
    attributes?: Record<string, string>;
    sort?: 'relevance' | 'price_asc' | 'price_desc' | 'newest' | 'distance';
    cursor?: string;
    limit?: number;
}

class MarketplaceSearch {
    constructor(
        private searchEngine: SearchEngine,
        private geoIndex: GeoIndex,
    ) {}

    async search(filters: SearchFilters): Promise<{
        results: Listing[];
        total: number;
        nextCursor?: string;
    }> {
        const must = [];
        const filter = [];

        // Text search
        if (filters.query) {
            must.push({
                multi_match: {
                    query: filters.query,
                    fields: ['title^3', 'description', 'category'],
                },
            });
        }

        // Category filter
        if (filters.category) {
            filter.push({ term: { category: filters.category } });
        }

        // Price range
        if (filters.minPrice || filters.maxPrice) {
            const range: Record<string, number> = {};
            if (filters.minPrice) range.gte = filters.minPrice;
            if (filters.maxPrice) range.lte = filters.maxPrice;
            filter.push({ range: { 'price.amount': range } });
        }

        // Geo filter
        if (filters.location) {
            filter.push({
                geo_distance: {
                    distance: `${filters.location.radius || 50000}m`,
                    location: {
                        lat: filters.location.lat,
                        lon: filters.location.lng,
                    },
                },
            });
        }

        // Attribute filters
        if (filters.attributes) {
            for (const [key, value] of Object.entries(filters.attributes)) {
                filter.push({ term: { [`attributes.${key}`]: value } });
            }
        }

        return this.searchEngine.search({
            query: { bool: { must, filter } },
            sort: this.buildSort(filters.sort, filters.location),
            size: filters.limit || 20,
            search_after: filters.cursor,
        });
    }
}
```

---

## 3. Payments & Escrow

### Marketplace Payment Flow

```
Buyer places order
    │
    ▼
Authorization hold on payment method
    │
    ▼
Platform holds funds in escrow
    │
    ▼
Seller fulfills order
    │
    ▼
Buyer confirms receipt (or dispute window expires)
    │
    ▼
Funds released to seller (minus platform fee)
    │
    ▼
Payout to seller's bank account (daily/weekly batch)
```

### Escrow Implementation

```typescript
// Marketplace escrow service
interface EscrowTransaction {
    id: string;
    orderId: string;
    buyerId: string;
    sellerId: string;
    amount: Money;
    platformFee: Money;
    status: 'held' | 'released' | 'refunded' | 'disputed';
    createdAt: Date;
    releaseAt?: Date;    // Auto-release after N days
}

class EscrowService {
    private readonly HOLD_DAYS = 3;     // Auto-release after 3 days
    private readonly PLATFORM_FEE_RATE = 0.10;  // 10% take rate

    async createEscrow(order: Order): Promise<EscrowTransaction> {
        const platformFee = {
            amount: Math.round(order.total.amount * this.PLATFORM_FEE_RATE),
            currency: order.total.currency,
        };

        // 1. Authorization hold on buyer's payment method
        await this.paymentGateway.authorize({
            amount: order.total,
            metadata: { orderId: order.id, type: 'escrow_hold' },
        });

        // 2. Create escrow record
        const escrow: EscrowTransaction = {
            id: crypto.randomUUID(),
            orderId: order.id,
            buyerId: order.buyerId,
            sellerId: order.sellerId,
            amount: {
                amount: order.total.amount - platformFee.amount,
                currency: order.total.currency,
            },
            platformFee,
            status: 'held',
            createdAt: new Date(),
            releaseAt: new Date(Date.now() + this.HOLD_DAYS * 86400000),
        };

        await this.db.escrows.insert(escrow);

        // 3. Schedule auto-release
        await this.scheduler.schedule(escrow.releaseAt, () =>
            this.releaseEscrow(escrow.id));

        return escrow;
    }

    async releaseEscrow(escrowId: string): Promise<void> {
        const escrow = await this.db.escrows.findById(escrowId);
        if (!escrow || escrow.status !== 'held') return;

        // 1. Capture payment
        await this.paymentGateway.capture(escrow.amount);

        // 2. Process payout to seller
        await this.payoutService.payout(escrow.sellerId, {
            amount: escrow.amount.amount,
            currency: escrow.amount.currency,
        });

        // 3. Record platform revenue
        await this.revenueService.record({
            amount: escrow.platformFee,
            source: 'escrow_fee',
            orderId: escrow.orderId,
        });

        // 4. Update status
        await this.db.escrows.update(escrowId, {
            status: 'released',
            releasedAt: new Date(),
        });
    }

    async dispute(escrowId: string): Promise<void> {
        await this.db.escrows.update(escrowId, { status: 'disputed' });
        // Notify both parties, assign mediator
    }
}
```

---

## 4. Trust & Safety

### Fraud Detection Patterns

| Pattern | Description | Detection |
|---|---|---|
| **Fake listings** | Non-existent items | Image reverse search, review analysis, seller history |
| **Shill bidding** | Fake bids to drive up price | Bidder-seller network analysis |
| **Payment fraud** | Stolen cards, chargebacks | AVS, 3DS, velocity checks |
| **Review manipulation** | Fake reviews | Review pattern analysis, verified purchase only |
| **Account takeover** | Stolen accounts | Login anomaly, device fingerprinting |
| **Incentive abuse** | Coupon stacking, referral fraud | Rate limiting, unique constraint |

### Review & Rating System

```typescript
// Trusted review system
interface Review {
    id: string;
    listingId: string;
    reviewerId: string;
    orderId: string;           // Must have completed order
    rating: number;            // 1-5
    content: string;
    images?: string[];
    verified: boolean;         // Verified purchase
    createdAt: Date;
}

interface SellerRating {
    sellerId: string;
    averageRating: number;
    totalReviews: number;
    distribution: Record<number, number>;  // {1: 5, 2: 3, ...}
    responseRate: number;     // % of reviews responded to
    responseTime: number;     // Avg hours to respond
}

class ReviewService {
    async createReview(userId: string, review: Partial<Review>): Promise<Review> {
        // 1. Verify purchase
        const order = await this.db.orders.findById(review.orderId);
        if (!order || order.buyerId !== userId) {
            throw new Error('Must complete purchase to review');
        }

        // 2. Check for existing review
        const existing = await this.db.reviews.findOne({
            orderId: review.orderId,
            reviewerId: userId,
        });
        if (existing) throw new Error('Already reviewed this purchase');

        // 3. Validate content
        if (review.content && review.content.length > 5000) {
            throw new Error('Review too long');
        }
        if (review.rating < 1 || review.rating > 5) {
            throw new Error('Rating must be 1-5');
        }

        // 4. Check for fraud signals
        const fraudScore = await this.fraudDetector.analyzeReview({
            reviewerId: userId,
            sellerId: order.sellerId,
            rating: review.rating,
            timeSinceOrder: Date.now() - order.createdAt.getTime(),
        });
        if (fraudScore > 0.9) {
            throw new Error('Review flagged for manual review');
        }

        // 5. Save
        const saved = await this.db.reviews.insert({
            ...review,
            reviewerId: userId,
            verified: true,
            createdAt: new Date(),
        });

        // 6. Update seller rating
        await this.updateSellerRating(order.sellerId);

        return saved;
    }
}
```

---

## 5. Logistics & Fulfillment

### Order Fulfillment States

```
Pending → Confirmed → Processing → Shipped → Delivered → Completed
  │          │            │                      │
  │          ▼            ▼                      │
  └──→ Cancelled    Return Requested              │
                              │                   │
                              ▼                   ▼
                          Refunded         Review Opened
```

### Multi-Warehouse Inventory

```typescript
// Inventory management with multi-warehouse support
interface InventoryItem {
    sku: string;
    listingId: string;
    warehouses: Map<string, number>;  // warehouseId → quantity
    reserved: Map<string, number>;    // orderId → quantity
    backorderLimit: number;
    restockingDate?: Date;
}

class InventoryService {
    async checkAvailability(
        listingId: string,
        quantity: number,
        nearLocation?: GeoPoint,
    ): Promise<{ available: boolean; warehouse?: string }> {
        const item = await this.db.inventory.findByListing(listingId);
        if (!item) return { available: false };

        // Check total available (stock - reserved)
        const totalAvailable = Array.from(item.warehouses.values())
            .reduce((a, b) => a + b, 0) -
            Array.from(item.reserved.values())
            .reduce((a, b) => a + b, 0);

        if (totalAvailable < quantity) return { available: false };

        // Find nearest warehouse with stock
        if (nearLocation) {
            const closest = await this.findNearestWarehouse(
                nearLocation, item, quantity
            );
            if (closest) {
                return { available: true, warehouse: closest };
            }
        }

        return { available: true };
    }

    async reserveStock(
        listingId: string,
        orderId: string,
        quantity: number,
    ): Promise<void> {
        const item = await this.db.inventory.findByListing(listingId);

        // Find and reserve from a warehouse
        for (const [warehouseId, stock] of item.warehouses) {
            const currentReserved = item.reserved.get(orderId) || 0;
            const available = stock - currentReserved;

            if (available >= quantity) {
                item.reserved.set(orderId, currentReserved + quantity);
                item.warehouses.set(warehouseId, stock - quantity);
                await this.db.inventory.update(item);
                return;
            }
        }

        throw new Error('Insufficient stock');
    }
}
```

---

## Quick Reference: Marketplace by Node Type

| Node Type | Marketplace Mapping |
|---|---|
| **Input** | Product upload, search query, order placement, review submission |
| **Logic** | Search ranking, price calculation, escrow logic, fraud detection, dispute resolution |
| **Database** | Listings index, order ledger, user ratings, inventory, escrow records |
| **UI** | Product page, search results, seller dashboard, checkout flow, messaging |
| **API** | Payment gateway (Stripe Connect), shipping APIs, tax calculation (TaxJar), SMS/email |

---

*For deeper marketplace concepts, see Bible levels `41-marketplace-sharing-economy/`, `38-fintech-insurance/`, `26-enterprise-systems/`, and `36-search-recs-personalization/`.*
