# 📊 Data Engineering & Analytics

> Reference for data engineering — ETL pipelines, stream processing, data warehousing, and analytics infrastructure.
> Extracted from The Programming Bible's Data Engineering level.

---

## 1. Data Pipeline Architecture

```
Data Sources
    │
    ▼
┌──────────────────────┐
│    Ingestion Layer    │  Collect from sources (APIs, DBs, files, streams)
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Processing Layer   │  Transform, clean, enrich, aggregate
│  (Batch / Streaming)  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Storage Layer      │  Data Lake, Warehouse, Lakehouse
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│   Consumption Layer   │  Analytics, BI, ML, Reports
└──────────────────────┘
```

### Batch vs Streaming

| Aspect | Batch | Streaming |
|---|---|---|
| **Latency** | Minutes to hours | Sub-second to minutes |
| **Data** | Bounded (known size) | Unbounded (continuous) |
| **Processing** | Scheduled intervals | Event-driven, continuous |
| **Complexity** | Lower | Higher |
| **Use Case** | Daily reports, ETL | Real-time dashboards, alerts |
| **Tools** | Airflow, dbt, Spark | Kafka, Flink, Spark Streaming |

---

## 2. ETL/ELT Pipeline Design

### Pipeline Orchestration (Airflow)

```python
"""ETL pipeline DAG — Apache Airflow example."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.postgres_operator import PostgresOperator
from airflow.providers.http.sensors.http import HttpSensor
import requests
import json

default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

dag = DAG(
    'etl_customer_pipeline',
    default_args=default_args,
    description='Daily customer data ETL',
    schedule_interval='0 3 * * *',  # Daily at 3 AM
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['etl', 'customer'],
)

def extract_api(**context) -> str:
    """Extract data from source API."""
    response = requests.get(
        'https://api.example.com/v1/customers',
        params={'updated_since': context['ds']},
        headers={'Authorization': 'Bearer ${API_KEY}'},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    # Save to staging
    file_path = f'/data/raw/customers/{context["ds"]}.json'
    with open(file_path, 'w') as f:
        json.dump(data, f)

    return file_path

def validate_data(**context) -> bool:
    """Validate extracted data quality."""
    file_path = context['ti'].xcom_pull(task_ids='extract')
    with open(file_path, 'r') as f:
        data = json.load(f)

    checks = {
        'non_empty': len(data) > 0,
        'has_required_fields': all(
            all(k in record for k in ['id', 'email', 'created_at'])
            for record in data
        ),
        'valid_emails': all('@' in r['email'] for r in data),
    }

    if not all(checks.values()):
        failed = [k for k, v in checks.items() if not v]
        raise ValueError(f'Validation failed: {failed}')

    return True

def transform_aggregate(**context) -> str:
    """Transform and aggregate data for warehouse."""
    file_path = context['ti'].xcom_pull(task_ids='extract')
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Transform
    transformed = []
    for record in data:
        transformed.append({
            'customer_id': record['id'],
            'email': record['email'].lower(),
            'full_name': f"{record.get('first_name', '')} {record.get('last_name', '')}".strip(),
            'signup_date': record['created_at'][:10],
            'country': record.get('address', {}).get('country', 'unknown'),
            'total_orders': record.get('order_count', 0),
            'ltv': record.get('lifetime_value', 0.0),
        })

    # Write transformed data
    output_path = f'/data/processed/customers/{context["ds"]}.parquet'
    # In production: use pandas/polars to write parquet
    with open(output_path.replace('.parquet', '.json'), 'w') as f:
        json.dump(transformed, f)

    return output_path

# Define DAG tasks
check_api = HttpSensor(
    task_id='check_api_available',
    http_conn_id='source_api',
    endpoint='/health',
    timeout=30,
    dag=dag,
)

extract = PythonOperator(
    task_id='extract',
    python_callable=extract_api,
    dag=dag,
)

validate = PythonOperator(
    task_id='validate',
    python_callable=validate_data,
    dag=dag,
)

transform = PythonOperator(
    task_id='transform',
    python_callable=transform_aggregate,
    dag=dag,
)

load_warehouse = PostgresOperator(
    task_id='load_to_warehouse',
    postgres_conn_id='data_warehouse',
    sql="""
        INSERT INTO fact_customers
        SELECT * FROM staging.customers
        ON CONFLICT (customer_id) DO UPDATE SET
            email = EXCLUDED.email,
            total_orders = EXCLUDED.total_orders,
            ltv = EXCLUDED.ltv,
            updated_at = NOW();
    """,
    dag=dag,
)

check_api >> extract >> validate >> transform >> load_warehouse
```

### Data Quality Checks

```python
# Data quality validation patterns
import pandera as pa
from datetime import datetime

# Schema validation with pandera
class CustomerSchema(pa.DataFrameModel):
    customer_id: int = pa.Field(unique=True, nullable=False)
    email: str = pa.Field(regex=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    full_name: str = pa.Field(nullable=True)
    signup_date: datetime = pa.Field()
    country: str = pa.Field(isin=['US', 'UK', 'CA', 'AU', 'DE', 'FR'])
    total_orders: int = pa.Field(ge=0)
    ltv: float = pa.Field(ge=0.0)

# Anomaly detection
def detect_anomalies(dataframe):
    alerts = []

    # Volume anomaly
    if len(dataframe) < expected_min_records:
        alerts.append(f"Low record count: {len(dataframe)} < {expected_min_records}")

    # Null checks
    for col in required_columns:
        null_pct = dataframe[col].isnull().mean()
        if null_pct > threshold:
            alerts.append(f"High null rate for {col}: {null_pct:.1%}")

    # Freshness
    max_date = dataframe['signup_date'].max()
    days_old = (datetime.now() - max_date).days
    if days_old > 1:
        alerts.append(f"Data is {days_old} days old — pipeline may be stale")

    return alerts
```

---

## 3. Stream Processing

### Time Domains

| Time Type | Definition | Example |
|---|---|---|
| **Event Time** | When the event actually occurred | Sensor reading timestamp |
| **Processing Time** | When the system observes the event | Current server time |
| **Ingestion Time** | When the event enters the streaming system | Kafka broker timestamp |

### Watermarks & Windowing

```python
# Stream processing with watermarks (conceptual)
from dataclasses import dataclass
from typing import Generator
from datetime import datetime, timedelta

@dataclass
class Event:
    event_time: datetime
    value: float
    key: str

class WatermarkTracker:
    """Tracks watermark progress for event-time processing."""

    def __init__(self, max_lateness: timedelta = timedelta(seconds=60)):
        self.max_lateness = max_lateness
        self.watermark: datetime | None = None

    def observe_event(self, event: Event) -> None:
        event_watermark = event.event_time - self.max_lateness
        if self.watermark is None or event_watermark > self.watermark:
            self.watermark = event_watermark

    def is_late(self, event: Event) -> bool:
        """Check if event is too late for the current window."""
        return self.watermark is not None and event.event_time < self.watermark

class TumblingWindow:
    """Fixed-size, non-overlapping time windows."""

    def __init__(self, size_seconds: int = 60):
        self.size = timedelta(seconds=size_seconds)
        self.buckets: dict[tuple[str, datetime], list[Event]] = {}

    def get_window_start(self, event_time: datetime) -> datetime:
        seconds = int(event_time.timestamp()) // self.size.seconds * self.size.seconds
        return datetime.fromtimestamp(seconds)

    def add_event(self, event: Event) -> None:
        window_start = self.get_window_start(event.event_time)
        key = (event.key, window_start)
        if key not in self.buckets:
            self.buckets[key] = []
        self.buckets[key].append(event)

    def close_window(self, key: str, window_start: datetime) -> dict:
        """Finalize a window and return aggregation."""
        events = self.buckets.pop((key, window_start), [])
        if not events:
            return {}

        values = [e.value for e in events]
        return {
            'key': key,
            'window_start': window_start.isoformat(),
            'count': len(values),
            'sum': sum(values),
            'avg': sum(values) / len(values),
            'min': min(values),
            'max': max(values),
        }
```

---

## 4. Data Warehouse Design

### Star Schema vs Snowflake

| Aspect | Star Schema | Snowflake |
|---|---|---|
| **Normalization** | Denormalized dimensions | Normalized dimensions |
| **Query Performance** | Faster (fewer joins) | Slower (more joins) |
| **Storage** | More (duplicated data) | Less (no duplication) |
| **Maintenance** | Simpler | More complex |
| **Use Case** | BI, reporting, analytics | Complex data governance |

### Fact Table Pattern

```sql
-- Star schema example: Sales fact table
CREATE TABLE fact_sales (
    sale_id BIGINT PRIMARY KEY,
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key INTEGER NOT NULL REFERENCES dim_product(product_key),
    customer_key INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    store_key INTEGER NOT NULL REFERENCES dim_store(store_key),
    -- Metrics (additive)
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    total_amount DECIMAL(10,2) NOT NULL,
    cost_amount DECIMAL(10,2) NOT NULL,
    profit_amount DECIMAL(10,2) GENERATED ALWAYS AS (total_amount - cost_amount) STORED,
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
PARTITION BY RANGE (date_key);

-- Common dimension table
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL,
    year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    week INTEGER NOT NULL,
    day_of_week SMALLINT NOT NULL,
    day_name VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_holiday BOOLEAN NOT NULL
);

-- Analytics queries
SELECT
    d.year,
    d.quarter,
    p.category,
    SUM(f.total_amount) as revenue,
    COUNT(DISTINCT f.customer_key) as unique_customers,
    SUM(f.quantity) as units_sold
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key
JOIN dim_product p ON f.product_key = p.product_key
WHERE d.year = 2024
GROUP BY d.year, d.quarter, p.category
ORDER BY d.year, d.quarter, revenue DESC;
```

---

## 5. Data Lakehouse Pattern

```
┌──────────────────────────────────────────────┐
│            CONSUMPTION LAYER                   │
│  BI Tools   ML Models   SQL Engines   Apps     │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│          CATALOG & GOVERNANCE LAYER            │
│  Unity Catalog   HMS   Data Lineage   Audit    │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│          STORAGE OPTIMIZATION LAYER            │
│  Delta Lake   Iceberg   Hudi   (ACID on Lake)  │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│              STORAGE LAYER                     │
│  S3 / ADLS / GCS   (Parquet / Avro / ORC)     │
└──────────────────────────────────────────────┘
```

---

## Quick Reference: Data Engineering by Node Type

| Node Type | Data Engineering Mapping |
|---|---|
| **Input** | Data source connectors, file ingestion, API polling, CDC listeners |
| **Logic** | Transform logic, data quality checks, aggregation, enrichment |
| **Database** | Data warehouse, data lake, OLAP cube, materialized views |
| **UI** | Dashboards, BI reports, data catalog browser, lineage graph |
| **API** | Data service APIs, metadata catalog, SQL query endpoints |

---

*For deeper data engineering concepts, see Bible level `27-data-engineering/` — data warehousing, streaming, data governance, analytics, and BI systems.*
