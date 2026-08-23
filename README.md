# No Wrong Door — Unified Resident API

> Brite Spark 2026 · Problem 3

A single, resilient API that aggregates the Calder County **Resident Index** (REST/JSON)
and **Benefits Register** (XML) into one unified view.

---

## Prerequisites

- **Python 3.10+** (3.11, 3.12, 3.13, or 3.14)
- **pip** (ships with Python)

No database, Redis, Docker, or external infrastructure is needed.

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

Restart the Benefits Register with the increased failure rate:

```bash
python services/xml_service.py --port 8082 --failure-rate 0.40
```

The unified API handles this automatically:
- **Bounded linear retries** (up to 3 total attempts) recover from intermittent failures.
- A singleton **Circuit Breaker** protects the API from stalling during sustained outages.
- If all 3 attempts fail, the API gracefully degrades, returning resident data and explicit failure status without crashing.
- **Production logging** surfaces exact failure points and circuit state transitions.

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
