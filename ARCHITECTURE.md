# ARCHITECTURE.md — Brite Spark 2026 · Problem 3: "No Wrong Door"

> **Status:** Implementation plan. No code written yet.

---

## 0. Design Goal

Build a single HTTP API that aggregates data from two upstream sources — the Resident
Index (REST/JSON, reliable) and the Benefits Register (XML, slow and unreliable) — and
returns a unified view. The design must satisfy all four mandatory floor requirements
**at both 15% and 40% XML failure rates** without any code changes, and must be simple
enough that one person can build, test, and demonstrate it in two days.

---

## 1. API Contract

### Technology choice for the unified API

**Python 3 + FastAPI + httpx + uvicorn.**

| Dependency | Why it is needed |
|:--|:--|
| **FastAPI** | Async-native HTTP framework. The XML service sleeps 0.7–2.4 s on every call; async lets us call both sources concurrently and retry the XML service without blocking. FastAPI also generates interactive API docs automatically — useful for a live demo. |
| **httpx** | Async HTTP client. Required to make concurrent, non-blocking calls to the upstream services. |
| **uvicorn** | ASGI server to run FastAPI. |

All three are installed via a single `pip install -r requirements.txt`.

**Why not Flask?** Flask is synchronous by default. To call two slow upstream services concurrently we would need `threading`, `gevent`, or `asyncio` wrappers — adding complexity that FastAPI removes by being async-native.

**Why not Python stdlib `http.server`?** It has no async support, no routing, and no request validation. The amount of boilerplate would exceed the amount of application code, and we would still need an HTTP client library.

**Why not Node.js / Express?** Would work equally well, but the mock services are Python 3 and the judges will already have Python on the machine. Staying in one language reduces the setup steps in the README.

---

### Endpoints

| Method | Path | Description |
|:--|:--|:--|
| `GET` | `/residents` | All residents from both sources, deduplicated, with source status. |
| `GET` | `/residents/{id}` | Single resident by REST id (`R-NNNNN`), with source status. |
| `GET` | `/benefits` | All benefit records from the XML source, with source status. |
| `GET` | `/benefits/{ref}` | Single benefit record by XML ref (`CC/YYYY/NNNN`), with source status. |
| `GET` | `/health` | Aggregated health of this API and both upstream services. |

**Why these five endpoints?**

The problem says "one call, one resident, everything known about them." At the floor
level (no identity matching), "everything known" from each source is independent. We
expose both collections through one API so a staff member only needs one place to look.
The single-record endpoints let a caller drill into a specific resident or benefit
record. The health endpoint gives operational visibility.

**Why separate `/residents` and `/benefits` instead of merging them into one list?**

Without identity matching (stretch goal, not floor), we have no reliable way to merge a
REST resident record with an XML benefit record. Presenting them as two clearly-labelled
collections in one response is honest: the caller sees exactly what each source knows.
A merged list would either require identity matching or would mix structurally different
records into one array, which is worse than useless — it pretends a merge happened when
it did not.

---

### Request Parameters

#### `GET /residents`

| Param | Type | Default | Description |
|:--|:--|:--|:--|
| `page` | int | `1` | Page number (1-indexed). Applied to our deduplicated result set, not to upstream pages. |
| `page_size` | int | `50` | Records per page. |

We re-paginate our own deduplicated output. This decouples our API contract from the
upstream REST service's hardcoded page size of 25 and its duplicate-producing pagination.

#### `GET /residents/{id}`

No query params. Path parameter `id` is the REST resident id (e.g. `R-10234`).

#### `GET /benefits`

No pagination. The XML source returns all 540 records in one call and is not paginated
upstream, so we return the full set. If we later add caching, this remains a single response.

#### `GET /benefits/{ref}`

Path parameter `ref` is the XML benefit ref (e.g. `NO/2019/4234`). Slashes are part of the
ref and must be URL-encoded in the path (`NO%2F2019%2F4234`).

#### `GET /health`

No params.

---

### Response Structure

Every response from this API follows a single envelope:

```json
{
  "data": { ... },
  "sources": {
    "resident_index": {
      "status": "ok | degraded | unavailable",
      "records_fetched": 620,
      "duplicates_removed": 41,
      "error": null,
      "attempts": 1
    },
    "benefits_register": {
      "status": "ok | degraded | unavailable",
      "records_fetched": 540,
      "error": "Service returned HTTP 500 on 3/3 attempts",
      "attempts": 3
    }
  }
}
```

**Why this envelope?**

Floor requirement 1 (graceful degradation) demands that when a source fails, the response
must include "a clear indication of what is missing and why." The `sources` block satisfies
this: every response tells the caller the state of each upstream source, including error
details and retry counts. The caller never has to guess whether an empty result means "no
records exist" or "the source was down."

Floor requirement 2 (never silently pretend the missing source had nothing to say) is
satisfied because the `status` field is always present and always reflects reality.

---

#### `GET /residents` — response `data` shape

```json
{
  "data": {
    "residents": [
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
    "page": 1,
    "page_size": 50,
    "total": 620,
    "has_more": true
  },
  "sources": { ... }
}
```

#### `GET /residents/{id}` — response `data` shape

```json
{
  "data": {
    "resident": { ... }
  },
  "sources": { ... }
}
```

Returns HTTP 404 with `"data": null` and `sources` status if the id is not found in the
Resident Index.

#### `GET /benefits` — response `data` shape

```json
{
  "data": {
    "benefits": [
      {
        "ref": "NO/2019/4234",
        "name": "DELGADO, Maria",
        "born": "1971-04-02",
        "addr": "118 Cedar Avenue",
        "town": "Northgate",
        "benefit_code": "HSP-B",
        "review_due": "2026-05-14"
      }
    ],
    "total": 540
  },
  "sources": { ... }
}
```

When the Benefits Register is unavailable after retries:
```json
{
  "data": {
    "benefits": [],
    "total": 0
  },
  "sources": {
    "benefits_register": {
      "status": "unavailable",
      "records_fetched": 0,
      "error": "HTTP 500 on all 3 attempts",
      "attempts": 3
    }
  }
}
```

#### `GET /benefits/{ref}` — response `data` shape

```json
{
  "data": {
    "benefit": { ... }
  },
  "sources": { ... }
}
```

#### `GET /health` — response shape

```json
{
  "status": "healthy | degraded | unhealthy",
  "upstreams": {
    "resident_index": { "reachable": true, "latency_ms": 4 },
    "benefits_register": { "reachable": true, "latency_ms": 2 }
  }
}
```

Calls each upstream's `/health` endpoint. Since the XML `/health` is exempt from delay
and failure, this always gives a true liveness signal.

---

### Degradation Matrix

This table documents every failure mode and what the caller gets. This is the core of
`DECISIONS.md`.

| Failure | What the caller gets | `sources` status |
|:--|:--|:--|
| REST healthy, XML healthy | Full data from both sources | `ok`, `ok` |
| REST healthy, XML returns 500 (retries succeed) | Full data from both sources | `ok`, `ok` (attempts > 1) |
| REST healthy, XML returns 500 (all retries fail) | Residents only; benefits array is empty | `ok`, `unavailable` |
| REST healthy, XML unreachable (connection refused) | Residents only; benefits array is empty | `ok`, `unavailable` |
| REST healthy, XML times out | Residents only; benefits array is empty | `ok`, `unavailable` |
| REST down, XML healthy | Benefits only; residents array is empty | `unavailable`, `ok` |
| Both down | Empty arrays for both; both marked unavailable | `unavailable`, `unavailable` |
| REST returns duplicates across pages | Deduplicated by `id`; duplicates_removed reported | `ok` |

**In no scenario does the API return a bare HTTP 500 or hide a source failure behind an empty result.**

---

## 2. Internal Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI Layer                     │
│              routes.py  (HTTP in/out)                │
│  Validates params, calls orchestrator, returns JSON  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                   Orchestrator                       │
│              orchestrator.py                         │
│  Calls adapters concurrently (asyncio.gather)        │
│  Assembles unified response with source status       │
│  Never throws — always returns partial + status      │
└──────┬───────────────────────────────┬──────────────┘
       │                               │
       ▼                               ▼
┌──────────────────────┐   ┌────────────────────────┐
│ Resident Index       │   │ Benefits Register      │
│ Adapter              │   │ Adapter                │
│ resident_adapter.py  │   │ benefits_adapter.py    │
│                      │   │                        │
│ • Pages through all  │   │ • Calls /records with  │
│   results            │   │   retry + backoff      │
│ • Deduplicates by id │   │ • Parses XML to dicts  │
│ • Fast, reliable     │   │ • Handles 500s, timeouts│
│ • Returns records +  │   │ • Returns records +    │
│   status             │   │   status               │
└──────┬───────────────┘   └──────┬─────────────────┘
       │                          │
       ▼                          ▼
  REST service              XML service
  port 8081                 port 8082
```

### Component Responsibilities

#### `config.py` — Configuration

Holds all tunable constants in one place. No magic numbers in application code.

```
REST_BASE_URL       = "http://127.0.0.1:8081"
XML_BASE_URL        = "http://127.0.0.1:8082"
XML_MAX_ATTEMPTS    = 3      (total attempts: 1 initial + 2 retries)
XML_TIMEOUT         = 5.0    (seconds per attempt)
XML_BACKOFF_BASE    = 0.3    (seconds; multiplied by attempt number)
REST_TIMEOUT        = 10.0   (seconds for all pages)
DEFAULT_PAGE_SIZE   = 50     (our API's page size, not upstream's)
```

**Why centralized config?** When the Day-2 failure rate increases, the only thing we may
need to touch is `XML_MAX_ATTEMPTS` — and it's in one obvious file. The problem explicitly
recommends "keeping each source adapter genuinely independent of the others and of the
assembly logic, so that the behaviour of one source can change without the rest of the
system caring." Central config is the simplest way to achieve this.

---

#### `models.py` — Data Models (Pydantic)

Defines the canonical internal representation. Each model maps directly to one source's
record format. We do not invent a merged model because identity matching is a stretch goal.

```python
class Resident:            # From REST service
    id: str
    first_name: str
    last_name: str
    date_of_birth: str
    address_line: str
    city: str
    phone: str
    program_status: str
    last_contact: str

class BenefitRecord:       # From XML service
    ref: str
    name: str
    born: str
    addr: str
    town: str
    benefit_code: str
    review_due: str

class SourceStatus:
    status: str            # "ok" | "degraded" | "unavailable"
    records_fetched: int
    duplicates_removed: int | None
    error: str | None
    attempts: int
```

**Why Pydantic?** FastAPI uses Pydantic natively for request/response validation and
serialization. Adding it costs zero extra dependencies (it ships with FastAPI) and gives
us type-safe, self-documenting models.

**Why not one merged "Person" model?** That would require identity matching to populate,
which is a stretch goal. The floor says "a unified view" — meaning one API that aggregates
— not "a merged record." Keeping the models source-specific means we are honest about what
we know.

---

#### `resident_adapter.py` — Resident Index Adapter

**Responsibility:** Fetch all residents from the REST service, handling pagination and
deduplication. Returns `(list[Resident], SourceStatus)`.

**Algorithm:**
```
1. Start at page = 1.
2. GET /residents?page={page}
3. For each record in results:
      if record.id not in seen_ids:
          add to output list
          add record.id to seen_ids
      else:
          increment duplicates_removed counter
4. If has_more is true, increment page and go to step 2.
5. Return (output list, SourceStatus with counts).
```

**Why sequential pagination, not concurrent?**
We do not know the total number of pages upfront. The `total` field reports 620 records
and `page_size` is 25, which implies `ceil(620/25) = 25` pages — but the actual page
count is 27 because duplicates expand the total. We cannot safely pre-calculate page
numbers. Sequential pagination following `has_more` is the only correct approach.

**Why deduplicate here, not in the orchestrator?**
Deduplication is a source-specific concern caused by this specific service's pagination
behaviour. The orchestrator should not need to know about REST pagination quirks. This
keeps the adapter self-contained and independently testable.

**Error handling:**
The REST service is reliable (no random failures, no delay), so we use a simple timeout
and treat any failure as the source being unavailable. No retry logic — it's not needed
for a service that does not randomly fail.

---

#### `benefits_adapter.py` — Benefits Register Adapter

**Responsibility:** Fetch all benefit records from the XML service, handling retries,
timeouts, and XML parsing. Returns `(list[BenefitRecord], SourceStatus)`.

**Attempt semantics:**

- **Maximum 3 total attempts** per Benefits Register request.
  - Attempt 1 = the initial request.
  - Attempts 2 and 3 = retries (only executed if the previous attempt failed).
- **Bounded linear backoff** between attempts: `XML_BACKOFF_BASE × attempt_number`
  (0.3 s, 0.6 s). This avoids tight retry loops without compounding the latency of a
  service that already takes 0.7–2.4 s per call.
- After all 3 attempts are exhausted, the adapter returns an empty list and a
  `SourceStatus` with `status: "unavailable"`, the error message from the last attempt,
  and `attempts: 3`.

**Algorithm:**
```
1. attempt = 0
2. While attempt < XML_MAX_ATTEMPTS:             # XML_MAX_ATTEMPTS = 3
      attempt += 1
      try:
          GET /records with timeout = XML_TIMEOUT
          if HTTP 200:
              parse XML body into list of BenefitRecord
              return (records, SourceStatus(status="ok", attempts=attempt))
          if HTTP 500:
              record error message
              if attempt < XML_MAX_ATTEMPTS:
                  sleep XML_BACKOFF_BASE * attempt
              continue
      except timeout/connection error:
              record error
              if attempt < XML_MAX_ATTEMPTS:
                  sleep XML_BACKOFF_BASE * attempt
              continue
3. Return ([], SourceStatus(status="unavailable", error=last_error, attempts=attempt))
```

**Theoretical probability at 40% failure rate (Day-2):**

If each attempt fails independently with probability 0.4:

| Total attempts | P(all fail) | P(at least one succeeds) | Worst-case time |
|:--|:--|:--|:--|
| 1 (no retry) | 40.0% | 60.0% | ~2.4 s |
| 2 (1 retry) | 16.0% | 84.0% | ~5.1 s |
| **3 (2 retries)** | **6.4%** | **93.6%** | **~7.8 s** |
| 4 (3 retries) | 2.6% | 97.4% | ~10.5 s |

Worst-case time = attempts × (max_delay + backoff).

**Important caveat:** The 93.6% figure is a theoretical probability assuming failures are
independent and identically distributed with exactly P(fail) = 0.4 per attempt. In
practice, failures may be correlated or persistent — for example, if the upstream service
is experiencing sustained load or a network partition, all three attempts may fail
together. Retries improve recovery from *transient, independent* failures but cannot
guarantee recovery from *persistent or correlated* upstream failures. When all attempts
are exhausted, the system falls back to graceful degradation: it returns a partial
response containing whatever data it could obtain, with explicit failure information for
the Benefits source.

**Decision: 3 total attempts (1 initial + 2 retries).** At 40% independent failure rate,
this gives a reasonable chance of success within ~8 seconds worst case. This is acceptable
for a service whose users are currently copy-pasting between browser tabs. If testing at
40% shows this is insufficient, bumping `XML_MAX_ATTEMPTS` to 4 in `config.py` is a
one-line config change.

**Why not more attempts?** Beyond 3, the latency grows but the marginal probability gain
shrinks. A staff member waiting 13 seconds for a small improvement over 8 seconds is a
poor trade. Better to return partial data quickly and let the caller decide whether to
retry at the API level.

**Why retry at all instead of returning partial data immediately?**
Because the service _does_ work — it just fails intermittently. Retries improve recovery
from transient, independent failures at the cost of a few seconds of latency. For
persistent failures, the graceful degradation path (partial response + source status)
ensures the caller is never left with a bare error or misleading silence.

**XML parsing:**
Use `xml.etree.ElementTree` (stdlib). Parse the `<BenefitsRegister>` root, iterate
`<Record>` children, extract text from each known element. Unknown elements are ignored
(forward-compatible).

---

#### `orchestrator.py` — Aggregation Layer

**Responsibility:** Call both adapters concurrently and assemble the unified response.
Never raises an exception — always returns a response with source status.

**Failure isolation requirement:** Each adapter's result must be captured independently.
An exception or failure from one adapter must not cancel, suppress, or hide the
successful result from the other adapter. The four possible outcomes are:

| Resident Adapter | Benefits Adapter | Orchestrator Response |
|:--|:--|:--|
| Succeeds | Succeeds | Full unified response, both sources `ok` |
| Succeeds | Fails | Resident data returned; Benefits status = `unavailable` with error detail |
| Fails | Succeeds | Benefits data returned; Resident status = `unavailable` with error detail |
| Fails | Fails | Valid degraded response; both sources = `unavailable` with error details |

All four outcomes produce a valid HTTP 200 response with the standard envelope. The
caller always receives a `sources` block that honestly reports what happened to each
upstream.

**Algorithm for `get_all()`:**
```python
results = await asyncio.gather(
    resident_adapter.fetch_all(),
    benefits_adapter.fetch_all(),
    return_exceptions=True
)

# Process each result independently:
# - If the result is a (records, status) tuple → use it directly.
# - If the result is an Exception → convert it to ([], SourceStatus(unavailable, error)).
# Neither result depends on or is affected by the other.

resident_records, resident_status = unpack_or_fail(results[0], "resident_index")
benefit_records, benefit_status   = unpack_or_fail(results[1], "benefits_register")

# Build and return UnifiedResponse with whatever data we have + both statuses.
```

**Why `asyncio.gather` with `return_exceptions=True`?**

`asyncio.gather` runs both adapter calls concurrently, so total latency is
`max(REST, XML)` instead of `REST + XML`. The `return_exceptions=True` flag is critical:
without it, if one adapter raises an exception, `gather` cancels the other task and
propagates the exception — which would violate the failure isolation requirement. With
`return_exceptions=True`, a raised exception is returned as a value in the result list,
so the orchestrator can inspect each result independently and convert exceptions to
unavailable status without losing the other adapter's successful result.

**Algorithm for `get_resident(id)`:**
```python
# Only calls the REST adapter — XML has no ID lookup capability for REST ids
resident = await resident_adapter.fetch_one(id)
# Return with source status
```

**Algorithm for `get_benefits()` and `get_benefit(ref)`:**
```python
# Only calls the XML adapter — these are benefit-specific endpoints
```

---

#### `routes.py` — API Routes

**Responsibility:** HTTP interface. Validates request parameters, calls the orchestrator,
serializes the response. No business logic.

Each route is ~5 lines:
```
parse params → call orchestrator → return JSON envelope
```

No try/except in routes — the orchestrator guarantees it never raises.

---

## 3. How the Architecture Handles Each Failure Mode

### REST pagination duplicates

**Handled by:** `resident_adapter.py`

The adapter maintains a `seen_ids: set[str]` during pagination. Every record's `id` field
is checked before being added to the output. Duplicates are counted and reported in
`SourceStatus.duplicates_removed`. This satisfies floor requirement 3 (correct
deduplication).

**Why deduplicate during pagination rather than after?**
Memory-equivalent, but deduplicating during traversal means we never hold a list
containing duplicates. It also makes the count accurate — we know exactly how many were
skipped.

---

### XML failures (HTTP 500)

**Handled by:** `benefits_adapter.py`

Up to 3 total attempts (1 initial + 2 retries) with bounded linear backoff
(`0.3s × attempt_number`). After all attempts are exhausted, the adapter returns an empty
list and a `SourceStatus` with `status: "unavailable"`, the error message from the last
attempt, and the total number of attempts made.

Retries improve recovery from transient, independent failures. If the upstream failure is
persistent or correlated (e.g. sustained overload), all attempts may fail, and the system
falls back to graceful degradation. The orchestrator passes the status through to the
response envelope. The caller sees exactly what happened.

---

### XML latency (0.7–2.4 s per call)

**Handled by:** async concurrency in `orchestrator.py` + per-request timeout in
`benefits_adapter.py`

The orchestrator runs both adapters concurrently via `asyncio.gather`. The XML adapter
sets `timeout=XML_TIMEOUT` (5 s) on each individual HTTP request, which is generous
(max service delay is 2.4 s). If a request times out, it counts as a failed attempt and
triggers a retry.

---

### Retries

**Handled by:** `benefits_adapter.py` only

The REST service does not need retries (it is reliable). The XML adapter retries on
HTTP 500 and on connection/timeout errors, up to a maximum of 3 total attempts (1 initial
+ 2 retries). Backoff is bounded and linear (`0.3 × attempt_number`: 0.3 s, 0.6 s).

Retries are designed to recover from transient, independent failures. They do not
guarantee recovery — persistent or correlated upstream failures will exhaust all attempts,
at which point graceful degradation takes over.

**Why linear backoff instead of exponential?**
The service is always slow (0.7–2.4 s). Exponential backoff would add seconds on top of
a service that already takes seconds. Linear backoff adds 0.3 s, 0.6 s — enough to avoid
tight retry loops without doubling the latency budget.

---

### Timeouts

| Component | Timeout | Rationale |
|:--|:--|:--|
| REST per-page request | 5 s | Generous; REST responds in milliseconds |
| REST total (all pages) | 30 s | 27 pages × generous margin |
| XML per-attempt | 5 s | Max delay is 2.4 s; allows for network jitter |
| XML total (all attempts) | ~16 s | 3 attempts × (5 s timeout) + backoff (0.3 + 0.6 s) |
| Orchestrator overall | 30 s | Protects against the entire aggregation hanging |

---

### Repeated identical requests (idempotency)

**Handled by:** the architecture being entirely read-only

Every endpoint is a `GET`. No state is created, modified, or deleted. No database. No
side effects. The same request always produces the same response shape with the same data
(modulo the XML service's random failures — but the retry logic and source status reporting
make the caller's experience deterministic in kind, if not in exact timing).

This satisfies floor requirement 2 (retry-safe and idempotent) automatically. Adding a
cache (stretch goal) would make it deterministic in content too.

---

### Partial data

**Handled by:** the response envelope

Every response always includes the `sources` block. A caller can check
`sources.benefits_register.status` to distinguish "no benefits exist for anyone" from
"the benefits register was unavailable." This is the core of the graceful degradation
guarantee.

---

### Day-2 (40% failure rate)

**Handled by:** no code changes required

The adapter makes up to 3 total attempts (1 initial + 2 retries). At 40% independent
failure rate, the theoretical probability that all 3 attempts fail is 6.4% — but this
assumes failures are independent, which may not hold in practice. Persistent or correlated
failures (e.g. sustained service degradation) could cause higher actual failure rates.

Regardless of whether retries succeed, the response envelope always reports the exact
status of each source. If all attempts fail, the response contains partial data with a
clear explanation of what is missing and why.

The Day-2 README says "Your demo still has to work." It does, because:
- The REST source is unaffected.
- Retries improve recovery from transient XML failures.
- When retries do not recover, the response returns partial data with explicit source
  failure information — which is exactly the graceful degradation the floor requires.
- If testing at 40% shows the current attempt budget is insufficient, increasing
  `XML_MAX_ATTEMPTS` in `config.py` is a one-line change.

---

## 4. Floor vs. Enhancement

### Mandatory for the Floor (implement first)

| Item | Floor Requirement |
|:--|:--|
| Response envelope with `sources` status | Graceful degradation |
| Timeouts on all upstream calls | Graceful degradation |
| Bounded retry (3 total attempts) for XML adapter | Graceful degradation at 40% |
| Partial response with explicit source failure info | Graceful degradation |
| Pagination traversal with `id`-based dedup | Correct deduplication |
| All endpoints are GET-only, no state | Idempotency |
| README with setup instructions | Clean-clone runnable |
| DECISIONS.md with degradation policy | Required deliverable |
| AI-USAGE.md | Required deliverable |
| Test suite covering 40% failure rate | Day-2 validation |

### Implementation priority within the floor

1. Timeouts on all upstream HTTP calls
2. Bounded retry (3 total attempts) with backoff for the Benefits adapter
3. Graceful degradation (partial response + source status envelope)
4. Deduplication of REST pagination artifacts
5. Testing under Day-2 40% failure rate
6. README, DECISIONS.md, AI-USAGE.md

### Enhancements (only after floor is complete and tested at 40%)

| Item | Category | Rationale for postponing |
|:--|:--|:--|
| Identity matching across sources | Stretch goal | Explicitly called a "rabbit hole" by the problem. Requires fuzzy matching on name, DOB, address. High risk of false positives. |
| In-memory caching of XML records | Stretch goal | Reduces latency and failure impact. Needs a defensible expiry policy. |
| Circuit breaker for XML service | Post-testing evaluation | Not implemented in the initial MVP. After the floor is complete and tested under the Day-2 40% failure rate, evaluate whether a circuit breaker provides meaningful benefit. If testing shows that the bounded retry strategy handles 40% failure adequately, a circuit breaker adds complexity without clear value. If testing reveals that sustained failures cause unacceptable latency across many requests, a circuit breaker (using `/health` to probe recovery) becomes worthwhile. |
| Re-pagination of REST results | Nice-to-have | Expose configurable page_size on our API. Low priority. |
| Request logging / metrics | Operational | Useful for demo but not a floor requirement. |

---

## 5. Project Folder Structure

```
brite/
├── README.md                  # Setup + run instructions (floor req 4)
├── DECISIONS.md               # Degradation policy (floor deliverable)
├── AI-USAGE.md                # AI usage disclosure (required deliverable)
├── PROJECT_ANALYSIS.md        # Pre-implementation analysis (already written)
├── ARCHITECTURE.md            # This document
├── requirements.txt           # Python dependencies (fastapi, httpx, uvicorn)
│
├── services/                  # Provided mock services (copied from data pack)
│   ├── rest_service.py
│   ├── xml_service.py
│   ├── _rest_data.json
│   ├── _xml_data.json
│   └── run_both.sh
│
├── app/                       # Application code
│   ├── __init__.py
│   ├── main.py                # FastAPI app entrypoint, app factory
│   ├── config.py              # All tunable constants
│   ├── models.py              # Pydantic data models
│   ├── routes.py              # API route handlers (thin layer)
│   ├── orchestrator.py        # Aggregation logic (calls adapters concurrently)
│   └── adapters/
│       ├── __init__.py
│       ├── resident_adapter.py   # REST pagination + deduplication
│       └── benefits_adapter.py   # XML retry + parsing
│
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── conftest.py            # Shared fixtures (mock HTTP responses, test client)
│   ├── test_resident_adapter.py
│   ├── test_benefits_adapter.py
│   ├── test_orchestrator.py
│   ├── test_routes.py
│   └── test_dedup.py
│
└── demo.sh                    # One-command demo script (starts services + API)
```

**Why flat `app/` instead of nested packages?**

Six files. Nesting them into `app/api/v1/endpoints/` would add cognitive overhead with
zero benefit at this scale. If the project grew, we'd refactor — but it won't, because
the scope is fixed.

**Why `adapters/` is the only subdirectory?**

Adapters are the components most likely to change independently (Day-2 proved this). A
subdirectory signals "these are isolated, substitutable modules." Everything else (one
orchestrator, one routes file, one config, one models file) is at the top level because
there's only one of each.

---

## 6. Testing Strategy

### Test Dependencies

`pytest` + `pytest-asyncio` + `httpx` (already in main requirements for its test client).

### Test Categories

#### A. Adapter Unit Tests (mock HTTP responses, no real services)

**`test_resident_adapter.py`:**

| Test | What it verifies |
|:--|:--|
| Fetches all pages following `has_more` | Pagination traversal is correct |
| Deduplicates records with same `id` | Floor requirement 3 |
| Reports correct `duplicates_removed` count | Source status accuracy |
| Handles connection error → returns unavailable status | Graceful degradation |
| Handles non-200 response → returns unavailable status | Graceful degradation |

**`test_benefits_adapter.py`:**

| Test | What it verifies |
|:--|:--|
| Parses valid XML into BenefitRecord list | Basic correctness |
| Retries on HTTP 500, succeeds on 2nd attempt | Retry logic works |
| Retries on HTTP 500, all attempts fail → unavailable | Degradation after retry exhaustion |
| Retries on timeout, succeeds on retry | Timeout recovery |
| All retries fail → returns empty list + error in status | Never raises, always returns |
| Handles malformed XML → returns unavailable | Defensive parsing |
| Reports correct `attempts` count | Source status accuracy |

#### B. Deduplication Tests

**`test_dedup.py`:**

| Test | What it verifies |
|:--|:--|
| Input with no duplicates → output unchanged | Baseline correctness |
| Input with duplicates at page boundaries → exactly one copy kept | Core dedup logic |
| Duplicate count matches expected (41 for real data) | Accuracy |
| Deduplication key is `id`, not position or other field | Correct key |

#### C. Orchestrator Tests (mock adapters, no real services)

**`test_orchestrator.py`:**

| Test | What it verifies |
|:--|:--|
| Both adapters succeed → full response with `ok`/`ok` status | Happy path |
| REST ok, XML fails → partial response with `ok`/`unavailable` | Graceful degradation |
| XML ok, REST fails → partial response with `unavailable`/`ok` | Graceful degradation |
| Both fail → empty data with `unavailable`/`unavailable` | Worst case |
| Adapter raises exception → caught, treated as unavailable | Never-crash guarantee |

#### D. API Route Tests (FastAPI test client, mock orchestrator)

**`test_routes.py`:**

| Test | What it verifies |
|:--|:--|
| `GET /residents` returns correct envelope shape | Contract compliance |
| `GET /residents/R-10001` returns single resident | Single-record lookup |
| `GET /residents/R-99999` returns 404 with source status | Not-found handling |
| `GET /benefits` returns correct envelope shape | Contract compliance |
| `GET /health` returns aggregated upstream status | Health endpoint |
| Response always includes `sources` block | Degradation visibility |

#### E. Integration Tests (real mock services, full stack)

Run with the actual mock services on localhost. These are slow (XML latency) so they
run separately from the fast unit tests.

| Test | What it verifies |
|:--|:--|
| Full paginated fetch produces exactly 620 unique residents | End-to-end dedup |
| XML at 15% failure rate: multiple calls all return data | Retry works in practice |
| XML at 40% failure rate: repeated calls, most return data | Day-2 resilience |
| XML at 40% failure rate: source status reports attempts | Degradation visibility |
| Kill XML service, call API → get residents + unavailable status | Full degradation path |

### Testing the Day-2 Change Specifically

```bash
# Start REST normally
python3 services/rest_service.py --port 8081 &

# Start XML at 40% failure rate
python3 services/xml_service.py --port 8082 --failure-rate 0.40 &

# Hit the API 20 times, count successes vs degraded responses
for i in $(seq 1 20); do
  curl -s http://127.0.0.1:8000/benefits | python3 -c "
    import json, sys
    r = json.load(sys.stdin)
    s = r['sources']['benefits_register']
    print(f\"Status: {s['status']}, Attempts: {s['attempts']}, Records: {s.get('records_fetched', 0)}\")
  "
done
```

Expected: most calls return `status: ok` (retries recover from transient failures).
Some calls may return `status: unavailable` with `attempts: 3` and a clear error.
The exact ratio depends on whether failures are transient or correlated — the purpose
of this test is to verify that both outcomes produce valid, informative responses.

---

## 7. Why Each Decision Was Made (Summary Table)

| Decision | Chosen | Rejected alternative | Why |
|:--|:--|:--|:--|
| Language | Python 3 | Node.js, Go | Mock services are Python; single-language reduces README setup steps |
| Framework | FastAPI | Flask, stdlib http.server | Native async (XML is slow); auto-docs for demo; Pydantic built in |
| HTTP client | httpx | requests, aiohttp, urllib | Async-native; pairs with FastAPI; familiar requests-like API |
| Deduplication location | Inside REST adapter | In orchestrator | Source-specific concern; keeps adapter self-contained and testable |
| Dedup key | `id` field | Hash of all fields | `id` is the unique identifier; full-record hash is fragile if fields change |
| Retry strategy | 3 total attempts (1+2 retries), linear backoff | Exponential backoff, no retries | Linear is simpler; service is already slow so exponential adds too much latency |
| Attempt count | 3 total (configurable) | 1, 5 | 3 balances recovery probability vs latency; 5 costs ~13 s worst case for diminishing returns |
| Response envelope | Always includes `sources` | Omit sources on success | Floor says "never silently pretend"; always showing sources costs nothing |
| Separate /residents + /benefits | Two collections | One merged list | No identity matching = no way to merge honestly |
| No database | In-memory only | SQLite, Redis | Problem says "not required"; adds setup complexity; data is read-only |
| No caching (floor) | No cache | TTL cache | Postponed to stretch goal; floor works without it |
| No identity matching (floor) | Not attempted | Fuzzy matching | Explicitly warned as "rabbit hole, not the floor" |

---

## Summary

The architecture is a thin Python API (FastAPI + httpx) with four layers: **routes** handle
HTTP, the **orchestrator** runs two adapters concurrently and assembles the response, and
each **adapter** encapsulates the quirks of its upstream source — REST pagination and
deduplication in one, XML retry logic and parsing in the other. Every response carries a
`sources` status block that tells the caller exactly what succeeded, what failed, and how
many attempts were made, so the system never returns a bare error and never silently hides
a failure.

The Resident Index adapter pages through all 27 pages, deduplicates the 41 duplicate
records by `id`, and reports the count. The Benefits Register adapter makes up to 3 total
attempts (1 initial request + 2 retries) with bounded linear backoff on HTTP 500 or
timeout, then returns whatever it has (full data or empty) with a clear status. The
orchestrator captures each adapter's result independently — an exception or failure from
one adapter never cancels or hides the other's successful result. Because the adapters run
concurrently via `asyncio.gather`, total latency is dominated by the XML service
(~2–8 seconds) rather than being additive.

The design handles the Day-2 change (40% failure rate) without code modifications. Retries
improve recovery from transient, independent failures — but they do not guarantee recovery.
When the upstream failure is persistent or correlated, all attempts may fail, and the
system falls back to graceful degradation: a partial response with explicit source failure
information. If testing at 40% shows the current attempt budget is insufficient, increasing
`XML_MAX_ATTEMPTS` in `config.py` is a one-line change.

Identity matching and caching are deferred as stretch goals. A circuit breaker is not
implemented in the initial MVP but will be evaluated after testing the system under the
Day-2 40% failure rate — it is only worthwhile if testing shows that sustained failures
cause unacceptable latency across many requests. The adapter/orchestrator separation means
any of these can be added later without structural changes. That is the same property that
makes the Day-2 change survivable: each source's behaviour can change without the rest of
the system caring.
