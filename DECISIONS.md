# Architecture Decisions

This document summarizes the key architectural decisions, degradation policies, and trade-offs for the Brite Spark 2026 Problem 3 mandatory MVP.

## 1. Unified Search Interface
**Decision:** We expose a single `GET /search` endpoint that accepts common resident traits (`first_name`, `last_name`, `date_of_birth`).
**Trade-off:** Because the upstream systems do not support filtering by name or DOB, the API fetches all records from both sources concurrently, and filters them in-memory. This is viable at the current scale (~1,000 records total), but would require caching or an indexed persistence layer if the scale grew significantly.

## 2. Separate Result Sets (Deferred Identity Matching)
**Decision:** The `/search` endpoint returns matches from the Resident Index and Benefits Register as two separate arrays within the single unified JSON response (`resident_index_matches` and `benefits_register_matches`).
**Trade-off:** The challenge explicitly identifies cross-system identity matching (without a shared key) as a "rabbit hole" stretch goal. Instead of risking false-positive merges based on heuristic parsing of names, the API honors the floor requirement ("one call, one resident, everything known about them") by retrieving all records that match the query criteria side-by-side. The human caller retains the final judgment on whether `Maria Delgado` in one array is `DELGADO, Maria` in the other.

## 3. Asynchronous Aggregation & Failure Isolation
**Decision:** We use FastAPI and `httpx` with `asyncio.gather(..., return_exceptions=True)` in the orchestrator.
**Trade-off:** Adds slight complexity compared to a synchronous Flask/requests app, but reduces worst-case latency from `REST + XML` to `max(REST, XML)`. Crucially, `return_exceptions=True` ensures that an exception raised by one adapter never cancels or corrupts the other adapter's response.

## 4. Retry Policy (Bounded Linear Backoff)
**Decision:** The Benefits Register XML adapter implements a maximum of 3 total attempts (1 initial + 2 retries) with a linear backoff (`0.3s * attempt`).
**Trade-off:** Exponential backoff would increase latency beyond reasonable limits for an already slow service (0.7–2.4s base latency). Linear backoff limits the worst-case time to ~8 seconds, offering a strong theoretical recovery rate (93.6% for independent 40% failures) without stalling the user. Real-world persistent failures exhaust retries and gracefully degrade.

## 5. Deduplication and Idempotency
**Decision:** Deduplication of Resident Index records occurs during pagination in `resident_adapter.py` by maintaining a `seen_ids: set[str]`. Duplicates are omitted from output and tracked in `duplicates_removed`. Because all endpoints are read-only HTTP `GET` requests returning deterministic slices of static data, the API is inherently idempotent and retry-safe.
**Trade-off:** Deduplicating in the adapter keeps upstream pagination quirks localized, preventing downstream contamination.

## 6. Explicit Source Status Envelope
**Decision:** Every API response wraps data inside a standard envelope containing a `sources` dictionary detailing the status of every upstream dependency (`resident_index` and `benefits_register`).
**Trade-off:** Adds minimal envelope overhead in exchange for eliminating ambiguity: callers can unequivocally distinguish between "no records match query" vs "source was down".

---

## 7. Explicit Degradation Policy Matrix

The table below documents the exact system behavior for every possible upstream condition.

| Failure Mode / Upstream Condition | Retries Occur? | Caller Receives | `sources.resident_index` | `sources.benefits_register` | How Caller Knows Data Is Unavailable |
|:---|:---:|:---|:---|:---|:---|
| **Resident Index Success** | No (1 attempt) | Matching resident records | `status: "ok"`, `records_fetched: 661`, `duplicates_removed: 41`, `error: null` | Dependent on Benefits source | Source status is `"ok"`. Duplicates removed count is reported. |
| **Resident Index HTTP Non-200** | No | `resident_index_matches: []` + intact Benefits matches | `status: "unavailable"`, `records_fetched: 0`, `error: "HTTP <code>: <msg>"` | Dependent on Benefits source | `status: "unavailable"`, `error` contains HTTP status and body text. |
| **Resident Index Timeout** | No | `resident_index_matches: []` + intact Benefits matches | `status: "unavailable"`, `records_fetched: 0`, `error: "Connection/Timeout error: ..."` | Dependent on Benefits source | `status: "unavailable"`, `error` contains timeout exception details. |
| **Resident Index Connection Failure** | No | `resident_index_matches: []` + intact Benefits matches | `status: "unavailable"`, `records_fetched: 0`, `error: "Connection/Timeout error: ..."` | Dependent on Benefits source | `status: "unavailable"`, `error` reports connection refusal or network error. |
| **Benefits Register Success (1st Attempt)** | No (1 attempt) | Intact Resident matches + matching Benefits records | Dependent on Resident source | `status: "ok"`, `records_fetched: 540`, `attempts: 1`, `error: null` | Source status is `"ok"`. |
| **Benefits Register HTTP 500 (Recovers on Retry)** | Yes (attempt 2 or 3) | Intact Resident matches + matching Benefits records | Dependent on Resident source | `status: "ok"`, `records_fetched: 540`, `attempts: 2` or `3`, `error: null` | Source status is `"ok"`. `attempts` reflects retry count (>1). |
| **Benefits Register Timeout (Recovers on Retry)** | Yes (attempt 2 or 3) | Intact Resident matches + matching Benefits records | Dependent on Resident source | `status: "ok"`, `records_fetched: 540`, `attempts: 2` or `3`, `error: null` | Source status is `"ok"`. `attempts` reflects retry count (>1). |
| **Benefits Register Connection Failure (Recovers)** | Yes (attempt 2 or 3) | Intact Resident matches + matching Benefits records | Dependent on Resident source | `status: "ok"`, `records_fetched: 540`, `attempts: 2` or `3`, `error: null` | Source status is `"ok"`. `attempts` reflects retry count (>1). |
| **Benefits Register Retry Exhaustion (All 3 Fail)** | Yes (3 total attempts) | Intact Resident matches + `benefits_register_matches: []` | Dependent on Resident source | `status: "unavailable"`, `records_fetched: 0`, `attempts: 3`, `error: "<last attempt error>"` | `status: "unavailable"`, `attempts: 3`, `error` describes the persistent failure reason. |
| **Both Sources Fail** | Yes (1 REST attempt, 3 XML attempts) | `resident_index_matches: []`, `benefits_register_matches: []` (HTTP 200 response) | `status: "unavailable"`, `records_fetched: 0`, `error: "<rest error>"` | `status: "unavailable"`, `records_fetched: 0`, `attempts: 3`, `error: "<xml error>"` | Both statuses report `"unavailable"`; response envelope returns clean HTTP 200 with complete error logs for both sources. |

### Degradation Guarantees
1. **Never a bare HTTP 500:** The API never crashes or returns an unhandled HTTP 500 due to upstream service failures.
2. **Never silent failure:** An unavailable service is never represented as an empty result with `status: "ok"`. The `status: "unavailable"` and `error` fields explicitly explain what happened.
3. **Failure Isolation:** A failure in one source does not suppress, delay, or discard data obtained from the healthy source.
