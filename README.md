# No Wrong Door — Unified Resident API

> Brite Spark 2026 · Problem 3

A single, resilient API that aggregates the Calder County **Resident Index** (REST/JSON)
and **Benefits Register** (XML) into one unified view.

---

## Prerequisites

- **Python 3.10+** (3.11, 3.12, 3.13, or 3.14)
- **pip** (ships with Python)

No database, Redis, Docker, or external infrastructure is needed.

## Tech Stack

- **Framework:** FastAPI (Native async support and OpenAPI docs)
- **HTTP Client:** HTTPX (Non-blocking concurrent requests)
- **Data Validation:** Pydantic (Type-safe response envelopes)
- **Server:** Uvicorn (ASGI web server)
- **Testing:** Pytest & Pytest-Asyncio

---

## Functional Capabilities

**Core Endpoints & Processing**
- **Unified `GET /search` Endpoint:** Aggregates both data sources concurrently.
- **Liveness `/health` Endpoint:** Returns orchestrator health status.
- **Idempotent Operations:** Strictly read-only GET behaviour.
- **Resident Index Pagination:** Traverses all pages automatically.
- **In-Memory Deduplication:** Safely filters the 661 raw fetched records down to 620 unique residents by removing 41 duplicates.
- **Benefits Register XML Parsing:** Correctly handles legacy PascalCase XML schemas.

**Resilience & Isolation**
- **Independent Source Failure Isolation:** `asyncio.gather(return_exceptions=True)` ensures one failing source never crashes the other.
- **Graceful Degradation:** A source failure returns intact data from the healthy source alongside explicit `unavailable` status metadata.
- **Bounded Linear Backoff:** Transient XML errors trigger retries with linear backoff.
- **Strict Attempt Budgets:** Exactly 3 TOTAL XML attempts (1 initial + 2 retries) before declaring the service unavailable.
- **Timeouts:** Both REST and XML sources have configurable HTTP timeouts.

**Sustained Outage Protection (Circuit Breaker)**
- **Singleton Circuit Breaker:** Protects against total XML outages without stalling the API.
- **State Machine:** Implements `CLOSED` (normal), `OPEN` (fail-fast), and `HALF_OPEN` (testing) states.
- **Recovery Period:** Configurable duration before allowing a trial request.

**Observability & Safety**
- **Production Application Logging:** Emits structured logs for circuit transitions, exhausted retries, and errors.
- **Configuration Validation:** Validates all environment variables on startup (preventing negative timeouts or invalid retries).

---

## Quick Start

### 1. Clone and enter the project

```bash
git clone https://github.com/Lokesh-g07/brite-spark-2026-no-wrong-door.git
cd brite
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Windows (cmd)
.\.venv\Scripts\activate.bat

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Start the mock upstream services

Open a **separate terminal** (activate the venv there too if needed):

```bash
# Terminal 2 — Resident Index (REST, port 8081)
python services/rest_service.py --port 8081

# Terminal 3 — Benefits Register (XML, port 8082)
python services/xml_service.py --port 8082
```

Or on macOS / Linux in one terminal:

```bash
bash services/run_both.sh
```

### 4. Start the unified API

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Verify it works

#### Liveness Health Check
```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{"status": "healthy", "service": "no-wrong-door"}
```

#### Unified Resident Search
Search for a resident across both systems with a single call:

```bash
curl "http://127.0.0.1:8000/search?last_name=Delgado"
```

Example response:
```json
{
  "data": {
    "query": {
      "first_name": null,
      "last_name": "Delgado",
      "date_of_birth": null
    },
    "resident_index_matches": [
      {
        "id": "R-10234",
        "first_name": "Maria",
        "last_name": "Delgado",
        "date_of_birth": "1971-04-02",
        "address_line": "118 Cedar Ave",
        "city": "Northgate",
        "phone": "555-402-9911",
        "program_status": "Active",
        "last_contact": "2025-11-30"
      }
    ],
    "benefits_register_matches": [
      {
        "ref": "NO/2019/4234",
        "name": "DELGADO, Maria",
        "born": "1971-04-02",
        "addr": "118 Cedar Avenue",
        "town": "Northgate",
        "benefit_code": "HSP-B",
        "review_due": "2026-05-14"
      }
    ]
  },
  "sources": {
    "resident_index": {
      "status": "ok",
      "records_fetched": 661,
      "duplicates_removed": 41,
      "error": null,
      "attempts": 1
    },
    "benefits_register": {
      "status": "ok",
      "records_fetched": 540,
      "duplicates_removed": null,
      "error": null,
      "attempts": 1
    }
  }
}
```

Interactive OpenAPI documentation is available at: http://127.0.0.1:8000/docs

---

## Running Tests

Run the complete test suite:

```bash
python -m pytest tests/ -v
```

---

## Day-2 Change (40% XML Failure Rate)

**Day 1:** Normal upstream operation with occasional latency.
**Day 2:** The Benefits Register permanently operates at an approximately 40% failure rate.

Restart the Benefits Register with the increased failure rate to test this:
```bash
python services/xml_service.py --port 8082 --failure-rate 0.40
```

The unified API is architected to handle this automatically without crashing or stalling. Here is exactly how the system responds:

1. A single request reaches both upstream sources concurrently.
2. A transient Benefits Register failure triggers bounded retries (up to 3 total attempts) with linear backoff.
3. A successful retry recovers normally and seamlessly returns all data.
4. Exhausted failures gracefully produce an explicit `unavailable` status in the response metadata.
5. Resident Index data is fully isolated and is still returned even if the XML service fails completely.
6. Repeated sustained Benefits Register failures eventually open the Circuit Breaker.
7. An OPEN circuit fails fast instead of repeatedly hitting the failing service, protecting the caller from stalling.
8. After the recovery duration (`CB_RECOVERY_DURATION`), a HALF_OPEN state permits exactly one trial request.
9. A successful trial instantly closes the circuit and resumes normal operations.
10. A failed trial immediately returns the circuit to OPEN.

**Production logging** surfaces all exact failure points and circuit state transitions for observability.

---

## Configuration

All settings can be overridden via environment variables:

| Variable | Default | Description |
|:--|:--|:--|
| `REST_BASE_URL` | `http://127.0.0.1:8081` | Resident Index base URL |
| `XML_BASE_URL` | `http://127.0.0.1:8082` | Benefits Register base URL |
| `XML_MAX_ATTEMPTS` | `3` | Total attempts (1 initial + 2 retries) for XML calls |
| `XML_TIMEOUT` | `5.0` | Seconds per XML attempt |
| `XML_BACKOFF_BASE` | `0.3` | Backoff multiplier between XML retries (`0.3s * attempt`) |
| `REST_TIMEOUT` | `10.0` | Seconds for REST calls |
| `CB_FAILURE_THRESHOLD` | `3` | Consecutive failures before the circuit opens |
| `CB_RECOVERY_DURATION` | `30.0` | Seconds the circuit stays OPEN before allowing a HALF_OPEN trial |
| `DEFAULT_PAGE_SIZE` | `50` | Default page size for API endpoints |

---

## Project Structure

```
brite/
├── README.md
├── ARCHITECTURE.md
├── DECISIONS.md
├── PROJECT_ANALYSIS.md
├── AI-USAGE.md
├── requirements.txt
├── .gitignore
│
├── services/              # Provided mock services (unmodified)
│   ├── rest_service.py
│   ├── xml_service.py
│   ├── _rest_data.json
│   ├── _xml_data.json
│   └── run_both.sh
│
├── app/                   # Application code
│   ├── __init__.py
│   ├── main.py            # FastAPI app + structured logging
│   ├── config.py          # Centralised config + startup validation
│   ├── circuit_breaker.py # Singleton in-memory circuit breaker
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py      # /search and /health API endpoints
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── resident_adapter.py   # REST pagination & deduplication
│   │   └── benefits_adapter.py   # XML parsing, retries & circuit integration
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py      # Pydantic schemas & response envelopes
│   └── services/
│       ├── __init__.py
│       └── orchestrator.py# Concurrent aggregation, search & failure isolation
│
└── tests/
    ├── __init__.py
    ├── test_health.py           # Health endpoint verification
    ├── test_orchestrator.py     # Parsing, degradation, retry, dedup & search tests
    ├── test_circuit_breaker.py  # Unit and integration tests for state transitions
    └── test_config.py           # Configuration validation tests
```
