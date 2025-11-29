# System Architecture Documentation

## Table of Contents
1. [High-Level Architecture](#high-level-architecture)
2. [Component Architecture](#component-architecture)
3. [Data Models](#data-models)
4. [Network Architecture](#network-architecture)
5. [Security Considerations](#security-considerations)
6. [Scalability & Performance](#scalability--performance)
7. [Failure Modes & Recovery](#failure-modes--recovery)

## High-Level Architecture

### Architecture Pattern
This system implements a **Lambda Architecture** variant optimized for real-time stream processing:

- **Speed Layer**: Kafka + Spark Streaming for real-time processing
- **Serving Layer**: PostgreSQL for aggregated query results
- **Batch Layer**: Not implemented (could add historical batch processing)

### Design Principles

1. **Loose Coupling**: Components communicate through well-defined interfaces (Kafka topics, SQL schemas)
2. **Scalability**: Horizontal scaling through partitioning and worker nodes
3. **Fault Tolerance**: Kafka replication, Spark checkpointing, database transactions
4. **Idempotency**: UPSERT operations ensure consistent state despite retries
5. **Observability**: Comprehensive logging at each pipeline stage

## Component Architecture

### 1. Data Producer (producer.py)

**Technology**: Python 3.12 + Confluent Kafka Client

**Responsibilities**:
- Generate synthetic e-commerce transaction data
- Serialize transactions to JSON
- Publish messages to Kafka topic
- Handle delivery confirmations

**Key Design Decisions**:
- **Confluent Kafka over kafka-python**: Better performance and stability
- **Synchronous callbacks**: Ensure delivery before generating next event
- **UUID for transaction IDs**: Guaranteed uniqueness across distributed systems

**Configuration Parameters**:
```python
producer_config = {
    'bootstrap.servers': '127.0.0.1:9093',
    'client.id': 'python-producer',
    'security.protocol': 'PLAINTEXT',
    'acks': 'all'  # Wait for all replicas (if replication > 1)
}
```

**Data Generation Logic**:
- Random category selection from predefined list
- Timestamp: Current UTC time
- Amount: Random float between 10.00 and 999.99
- Product names mapped to categories

### 2. Apache Kafka

**Technology**: Confluent Platform 7.4.0

**Architecture**:
```
Zookeeper (Coordination)
    ↓
Kafka Broker
  ├── Topic: transactions
  │   └── Partition 0 (single partition for ordering)
  ├── Consumer Groups
  │   └── spark-streaming-group
  └── Offset Management
```

**Configuration Highlights**:

**Listeners**:
- `PLAINTEXT://0.0.0.0:29092` - Internal Docker network
- `PLAINTEXT_HOST://0.0.0.0:9092` - Host access (mapped to 9093)

**Advertised Listeners**:
- `PLAINTEXT://kafka:29092` - For Docker services
- `PLAINTEXT_HOST://127.0.0.1:9093` - For host applications

**Topic Configuration**:
- Partitions: 1 (maintains ordering)
- Replication Factor: 1 (single broker setup)
- Retention: Default (7 days)
- Compaction: Disabled (delete cleanup policy)

### 3. Apache Spark Streaming (spark_processor.py)

**Technology**: PySpark 3.5.0 with Structured Streaming

**Processing Pipeline**:

```
┌─────────────────────┐
│  Kafka Source       │
│  (transactions)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Parse JSON         │
│  Cast Types         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Watermarking       │
│  (1-min tolerance)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Window Aggregation │
│  (1-min tumbling)   │
└──────────┬──────────┘
           │
           ├──────────────┐
           │              │
           ▼              ▼
    ┌───────────┐  ┌──────────────┐
    │  Console  │  │  PostgreSQL  │
    │  (Debug)  │  │  (Persist)   │
    └───────────┘  └──────────────┘
```

**Key Configurations**:

**Kafka Source**:
```python
.option("kafka.bootstrap.servers", "127.0.0.1:9093")
.option("subscribe", "transactions")
.option("startingOffsets", "earliest")
.option("failOnDataLoss", "false")
.option("kafka.session.timeout.ms", "60000")
```

**Windowing**:
```python
window(col("timestamp"), "1 minute")  # Tumbling window
withWatermark("timestamp", "1 minute")  # Late data tolerance
```

**Output Modes**:
- Console: `update` mode (changed rows only)
- PostgreSQL: `update` mode with foreachBatch (UPSERT)

**Why UPSERT?**

Windowed aggregations in `update` mode emit multiple updates for the same window as new data arrives. Without UPSERT, we would get:
- Duplicate key errors (INSERT fails)
- Incorrect aggregation totals

UPSERT pattern:
```sql
INSERT INTO category_sales (window_start, window_end, category, total_sales, transaction_count)
VALUES (...)
ON CONFLICT (window_start, category)
DO UPDATE SET
    total_sales = EXCLUDED.total_sales,
    transaction_count = EXCLUDED.transaction_count;
```

### 4. PostgreSQL Database

**Technology**: PostgreSQL 15

**Schema**:

```sql
CREATE TABLE category_sales (
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    category VARCHAR(50) NOT NULL,
    total_sales DECIMAL(10, 2) NOT NULL,
    transaction_count INT NOT NULL,
    PRIMARY KEY (window_start, category)
);
```

**Indexes**:
- Primary Key Index: `(window_start, category)` - B-tree
- Implicit Index on window_start for time-series queries

**Query Patterns**:
1. Latest window: `ORDER BY window_start DESC LIMIT 1`
2. Category breakdown: `WHERE window_start = (SELECT MAX(window_start))`
3. Trend analysis: `ORDER BY window_start DESC LIMIT 100`

**Connection Pooling**:
Dashboard uses SQLAlchemy engine with default pool size (5 connections).

### 5. Streamlit Dashboard (dashboard.py)

**Technology**: Streamlit + Plotly

**Architecture**:
```
┌─────────────────────────┐
│  Streamlit Server       │
│  (Port 8501)            │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  SQLAlchemy Engine      │
│  (Connection Pool)      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  PostgreSQL             │
│  (Query Execution)      │
└─────────────────────────┘
```

**UI Components**:
1. **Metrics Row**: KPIs (Total Sales, Transactions, Latest Window)
2. **Bar Chart**: Sales by Category (current window)
3. **Line Chart**: Sales trend (last 100 windows)
4. **Data Table**: Raw aggregated data

**Refresh Mechanism**:
```python
while True:
    # Render dashboard
    display_metrics()
    display_charts()
    display_data()
    
    time.sleep(2)  # 2-second polling interval
    st.rerun()     # Force refresh
```

**Why 2 seconds?**
- Balance between real-time updates and database load
- Aggregation windows are 1 minute, so 2-second refresh captures changes quickly
- Avoids overwhelming the database with queries

## Data Models

### Transaction Event (Producer → Kafka)

```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_12345",
  "product_category": "Electronics",
  "product_name": "Smartphone X",
  "amount": 450.50,
  "timestamp": "2025-11-29 20:04:32",
  "payment_method": "credit_card"
}
```

**Field Specifications**:
- `transaction_id`: UUID v4 (36 chars)
- `user_id`: String (20 chars)
- `product_category`: Enum [Electronics, Fashion, Beauty, Home, Sports, Grocery]
- `product_name`: String (variable)
- `amount`: Float (2 decimal places, range 10.00-999.99)
- `timestamp`: ISO 8601 format
- `payment_method`: Enum [credit_card, debit_card, paypal]

### Aggregated Sales (Spark → PostgreSQL)

```
window_start: 2025-11-29 20:04:00
window_end:   2025-11-29 20:05:00
category:     Electronics
total_sales:  4250.75
transaction_count: 12
```

**Aggregation Logic**:
```python
SUM(amount) AS total_sales
COUNT(transaction_id) AS transaction_count
GROUP BY window(timestamp, '1 minute'), product_category
```

## Network Architecture

### Docker Network: real-timedata_default

**Type**: Bridge network

**Services & IPs** (Dynamic, assigned by Docker):
- Zookeeper: 172.18.0.2
- Kafka: 172.18.0.3
- PostgreSQL: 172.18.0.4
- Spark Master: 172.18.0.5
- Spark Worker: 172.18.0.6

**Port Mappings**:

| Service | Container Port | Host Port | Purpose |
|---------|---------------|-----------|---------|
| Zookeeper | 2181 | 2181 | Client connections |
| Kafka (Internal) | 29092 | - | Inter-broker |
| Kafka (External) | 9092 | 9093 | External producers/consumers |
| PostgreSQL | 5432 | 5432 | Database connections |
| Spark Master | 7077 | 7077 | Worker registration |
| Spark UI | 8080 | 8080 | Web interface |
| Streamlit | 8501 | 8501 | Dashboard |

**Communication Paths**:
1. Producer (host) → Kafka: `127.0.0.1:9093`
2. Spark (host) → Kafka: `127.0.0.1:9093`
3. Services (Docker) → Kafka: `kafka:29092`
4. Spark → PostgreSQL: `localhost:5432`
5. Dashboard → PostgreSQL: `localhost:5432`

## Security Considerations

### Current Security Posture

**⚠️ DEVELOPMENT ONLY - NOT PRODUCTION READY**

**Identified Risks**:
1. **No Authentication**: All services accept unauthenticated connections
2. **Plaintext Communication**: No TLS/SSL encryption
3. **Default Credentials**: PostgreSQL uses default user/password
4. **No Network Isolation**: All ports exposed to localhost
5. **No Input Validation**: Producer accepts any data
6. **No Rate Limiting**: No protection against DoS

### Production Security Recommendations

**1. Kafka Security**:
```yaml
# Enable SASL/SCRAM authentication
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: SASL_SSL:SASL_SSL
KAFKA_SASL_MECHANISM: SCRAM-SHA-256

# Enable TLS
KAFKA_SSL_KEYSTORE_LOCATION: /etc/kafka/secrets/broker.keystore.jks
KAFKA_SSL_TRUSTSTORE_LOCATION: /etc/kafka/secrets/broker.truststore.jks
```

**2. PostgreSQL Security**:
```yaml
# Enable SSL
POSTGRES_SSL_MODE: require
POSTGRES_SSL_CERT: /var/lib/postgresql/server.crt
POSTGRES_SSL_KEY: /var/lib/postgresql/server.key

# Use strong credentials
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD_SECRET}
```

**3. Network Security**:
- Use Docker secrets for credentials
- Implement network policies to restrict inter-service communication
- Use reverse proxy (nginx) for dashboard with authentication
- Enable firewall rules to restrict external access

**4. Application Security**:
- Implement input validation on producer
- Use parameterized queries (already done with psycopg2)
- Add API authentication for dashboard
- Implement audit logging

## Scalability & Performance

### Current Capacity

**Single Node Configuration**:
- Events: 1,000/sec sustained
- Latency: <5 seconds end-to-end
- Storage: ~100KB per 1-minute window (6 categories × ~16KB)
- Daily Data: ~140MB (assuming steady rate)

### Bottlenecks

1. **Single Kafka Partition**: Limits parallel consumption
2. **Single Spark Worker**: CPU-bound aggregation
3. **Single PostgreSQL Instance**: Write contention
4. **Dashboard Queries**: Full table scans without indices

### Horizontal Scaling Strategy

**Kafka Scaling**:
```bash
# Increase partitions
kafka-topics --alter --topic transactions --partitions 4

# Add more brokers (requires cluster setup)
```

**Spark Scaling**:
```yaml
# docker-compose.yml
spark-worker-2:
  image: apache/spark:3.4.0
  command: /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://spark-master:7077
  environment:
    - SPARK_WORKER_MEMORY=2G
    - SPARK_WORKER_CORES=2

spark-worker-3:
  # Similar configuration
```

**Database Scaling**:
1. **Read Replicas**: PostgreSQL streaming replication
2. **Partitioning**: Time-based table partitioning
3. **Caching**: Redis for dashboard queries
4. **Archival**: Move old windows to cold storage

### Vertical Scaling

**Spark Worker Resources**:
```yaml
environment:
  - SPARK_WORKER_MEMORY=4G  # Increase from 1G
  - SPARK_WORKER_CORES=4    # Increase from 1
```

**PostgreSQL Tuning**:
```
shared_buffers = 256MB  # 25% of RAM
work_mem = 16MB
maintenance_work_mem = 64MB
effective_cache_size = 1GB
```

## Failure Modes & Recovery

### Failure Scenarios

#### 1. Producer Failure

**Symptom**: No new data in Kafka

**Detection**:
```bash
# Check topic lag
kafka-consumer-groups --bootstrap-server localhost:9093 \
  --describe --group spark-streaming-group
```

**Recovery**:
1. Restart producer
2. Kafka retains messages (7-day retention)
3. No data loss if restarted within retention period

#### 2. Kafka Broker Failure

**Symptom**: Producer/Consumer connection errors

**Detection**:
```bash
docker compose ps kafka
docker compose logs kafka
```

**Recovery**:
```bash
docker compose restart kafka
# Wait 20-30 seconds for full startup
```

**Data Impact**: With replication-factor=1, potential data loss during downtime

#### 3. Spark Streaming Failure

**Symptom**: No database updates, stale dashboard

**Detection**:
```bash
# Check Spark Master UI
curl http://localhost:8080
```

**Recovery**:
1. Restart spark_processor.py
2. Spark reads from last committed Kafka offset
3. May reprocess some data (idempotent UPSERT prevents duplicates)

**Checkpoint Location**: `/tmp/temporary-*` (ephemeral, lost on termination)

**Production Recommendation**:
```python
.option("checkpointLocation", "/persistent/spark-checkpoints")
```

#### 4. PostgreSQL Failure

**Symptom**: Dashboard errors, Spark write failures

**Detection**:
```bash
docker compose logs postgres
docker exec postgres pg_isready
```

**Recovery**:
```bash
docker compose restart postgres
```

**Data Impact**: Volume mounted at `/var/lib/postgresql/data` persists data

#### 5. Dashboard Failure

**Symptom**: HTTP 500 errors, connection refused

**Impact**: Minimal - only affects visualization layer

**Recovery**: Restart Streamlit application

### High Availability Recommendations

**Kafka**:
- 3-node cluster with replication-factor=3
- Configure `min.insync.replicas=2`

**PostgreSQL**:
- Primary-replica setup with automatic failover
- Use Patroni for HA orchestration

**Spark**:
- Multiple worker nodes
- Persistent checkpoint location (HDFS or S3)

### Monitoring & Alerting

**Metrics to Monitor**:
1. Kafka lag (consumer group lag)
2. Spark processing rate (records/second)
3. Database connection pool utilization
4. Dashboard query latency
5. Error rates in logs

**Alert Thresholds**:
- Kafka lag > 1000 messages
- Spark processing rate < expected input rate
- Database connection pool > 80% utilization
- Dashboard query time > 1 second
- Error rate > 1%

**Tools**:
- Prometheus + Grafana for metrics
- ELK Stack for log aggregation
- PagerDuty for alerting

---

**Document Version**: 1.0  
**Last Updated**: November 2025  
**Author**: Data Engineering Team
