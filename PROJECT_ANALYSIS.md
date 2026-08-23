# PROJECT_ANALYSIS.md — Brite Spark 2026 · Problem 3: "No Wrong Door"

> **Status:** Pre-implementation analysis only. No architectural decisions made yet.

---

## Provided Services

| Service | File | Description |
|:--|:--|:--|
| **Resident Index** (REST/JSON) | `services/rest_service.py` | Paginated JSON service over resident data |
| **Benefits Register** (XML) | `services/xml_service.py` | Legacy XML service — intentionally slow & unreliable |
| Startup script | `services/run_both.sh` | Bash script that starts both services together |
| REST backing data | `services/_rest_data.json` | Raw JSON (620 records). Readable for analysis; must go through HTTP. |
| XML backing data | `services/_xml_data.json` | Raw JSON (540 records). Readable for analysis; must go through HTTP. |

**Runtime requirement:** Python 3, standard library only — nothing to install.

---

## Endpoints

### Service 1 — Resident Index · REST · `http://127.0.0.1:8081`

| Method | Path | Notes |
|:--|:--|:--|
| GET | `/residents?page=1&page_size=25` | Paginated list. `page_size` param is **ignored** — server hardcodes 25. |
| GET | `/residents/<id>` | Single record by `id` (e.g. `R-10234`). |
| GET | `/health` | Always fast, always HTTP 200. |

**Paginated list response shape:**
```json
{
  "page": 1,
  "page_size": 25,
  "total": 620,
  "has_more": true,
  "results": [ /* array of resident objects */ ]
}
```
`has_more` is `false` on the last page. Out-of-range pages return `"results": []`.

**Single record 404:**
```json
{ "error": "not_found", "id": "R-XXXXX" }
```

---

### Service 2 — Benefits Register · XML · `http://127.0.0.1:8082`

| Method | Path | Notes |
|:--|:--|:--|
| GET | `/records` | Returns ALL benefit records in one XML response (not paginated). |
| GET | `/records/<ref>` | Single record by ref (e.g. `NO/2019/4234`). Slashes in ref must be `%2F`-encoded. |
| GET | `/health` | **Exempt from delay and failure.** Always fast, always HTTP 200. |

**Successful response — list:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<BenefitsRegister>
  <Record>
    <Ref>NO/2019/4234</Ref>
    <Name>DELGADO, Maria</Name>
    <Born>1971-04-02</Born>
    <Addr>118 Cedar Avenue</Addr>
    <Town>Northgate</Town>
    <BenefitCode>HSP-B</BenefitCode>
    <ReviewDue>2026-05-14</ReviewDue>
  </Record>
  <!-- ... -->
</BenefitsRegister>
```

**HTTP 500 error body:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Fault><Code>SRV-500</Code><Message>Register temporarily unavailable. Retry.</Message></Fault>
```

**HTTP 404 error body (record not found or unknown path):**
```xml
<?xml version="1.0"?><Fault><Code>SRV-404</Code><Message>No such record</Message></Fault>
```

---

## Actual Data Structures

### REST — Resident record (as returned by the API; `_pid` stripped at startup)

```json
{
  "id":             "R-10234",
  "first_name":     "Maria",
  "last_name":      "Delgado",
  "date_of_birth":  "1971-04-02",
  "address_line":   "118 Cedar Ave",
  "city":           "Northgate",
  "phone":          "555-402-9911",
  "program_status": "Active",
  "last_contact":   "2025-11-30"
}
```

**Dataset stats (confirmed by inspection):**
- Total records: **620**
- `program_status` values: `Active` (360), `Suspended` (131), `Closed` (129)
- Cities: `Ash Hill`, `Calder Central`, `Northgate`, `Weybridge`

---

### XML — Benefit record (as returned by the API; `_pid` stripped at startup)

| XML Element | Example | Notes |
|:--|:--|:--|
| `Ref` | `NO/2019/4234` | Unique ref. Format: `CC/YYYY/NNNN`. |
| `Name` | `DELGADO, Maria` | Always `LASTNAME, Firstname` format. |
| `Born` | `1971-04-02` | YYYY-MM-DD |
| `Addr` | `118 Cedar Avenue` | Free text street address |
| `Town` | `Northgate` | One of four known towns |
| `BenefitCode` | `HSP-B` | See codes below |
| `ReviewDue` | `2026-05-14` | YYYY-MM-DD |

**Dataset stats (confirmed by inspection):**
- Total records: **540**
- Benefit codes: `HSP-A` (215), `HSP-B` (105), `HSP-C` (108), `TRN-1` (112)
- Towns: `Ash Hill`, `Calder Central`, `Northgate`, `Weybridge`

---

### No Shared Key

- REST `id` (`R-NNNNN`) and XML `Ref` (`CC/YYYY/NNNN`) are **completely unrelated** — assigned by different systems at different times.
- The raw backing files contain a `_pid` field that *does* link the two sources: ~340 people appear in both.
- **Both services strip `_pid` at startup** (`r.pop('_pid', None)`). It is **not accessible through the API**.
- Confirmed by inspection: `_pid=1` → REST `R-10001 / Ashley Kessler` and XML `CA/2016/4001 / KESSLER, Ashley` — same person, same DOB, same town — but no published link.

---

## Failure Behaviour

### REST Service (port 8081)
- **No artificial delay.** Responds immediately.
- **No random failures.** Always returns a valid response (or a structured 404/400).
- The only "failure mode" is intentional duplicate records across pages (see next section).

### XML Service (port 8082)

| Behaviour | Detail |
|:--|:--|
| **Always slow** | `time.sleep(random.uniform(0.7, 2.4))` before every non-health response |
| **Failure (Day-1)** | 15% of calls return HTTP 500 + XML Fault body |
| **Failure (Day-2)** | **40%** of calls return HTTP 500 — permanent, will not be fixed |
| **Order** | Sleep runs **before** the failure check — even failed requests cost 0.7–2.4 s |
| **Health endpoint** | `/health` is **exempt** from both delay and failure; always fast and HTTP 200 |

> **Python interpreter caveat (from README):** `xml.etree.ElementTree` may raise
> `"No module named expat"` if Python was built without `pyexpat`. This is a broken
> interpreter, not a broken service. Try a different Python before losing an hour on it.

---

## Pagination / Duplicate Behaviour

**Source (from `rest_service.py`):**
```python
def build_pages(records, size):
    rng = random.Random(97531)          # fixed seed → deterministic
    pages, i = [], 0
    while i < len(records):
        page = records[i:i + size]
        pages.append(page)
        step = size
        if i + size < len(records) and rng.random() < 0.60:
            step = size - rng.choice([1, 2, 3])   # cursor slips back 1–3 records
        i += step
    return pages
```

- **60% probability** at each page boundary that the cursor steps back 1, 2, or 3 records.
- Pages are **pre-computed once at startup** with a fixed seed — the duplicate pattern is **static and deterministic** across all requests.
- **Measured (confirmed):** 620 unique records → 661 records served across **27 pages** → **41 duplicate appearances**.
- Correct deduplication key: the `id` field (e.g. `R-10234`).
- `has_more: true` is a reliable signal to keep paging; `has_more: false` means stop.

---

## Mandatory Requirements

> "Nothing above the floor counts until every box below is ticked."

### 1. Graceful Degradation
- If one source is unavailable, return what you have **plus** a clear indication of what is missing and why.
- **Never** return a bare failure.
- **Never** silently pretend the missing source had nothing to say.

### 2. Retry-Safe and Idempotent
- The same request made twice must not produce a different or duplicated result.
- A retried write must not double anything.

### 3. Correct Deduplication
- The unified view must not contain the same source record twice.
- Must handle the REST service's intentional duplicate-across-pages behaviour.

### 4. Runs From a Clean Clone via README
- A reviewer must be able to clone the repo and get everything running from the README alone — including bringing the mock services up.

### Required Deliverables
| File | Requirement |
|:--|:--|
| `DECISIONS.md` | **Must** state the degradation policy explicitly: for each way a source can fail, what does the caller get and how do they know? |
| `AI-USAGE.md` | Required by competition rules |
| Running demo | Command-line is fine; no UI required |
| Real commit history | Not a single squash |

### Explicitly NOT Required
- Any user interface
- A database or persistence layer
- Authentication / authorisation
- Identity resolution across the two sources *(stretch goal — see below)*
- Handling any source other than the two provided

---

## Day-2 Change

**Source:** `3 - Surprise Challenge / 3 - No Wrong Door / READ ME FIRST.md`

> "The Benefits Register has degraded permanently. It now fails on roughly **40% of calls**, and it is not going to be fixed."

| | |
|:--|:--|
| **What changed** | XML failure rate: 15% → **40%** |
| **How to apply it** | `python3 services/xml_service.py --port 8082 --failure-rate 0.40` |
| **Scope** | Configuration only. No new data, no new endpoints. |
| **Floor status** | The full floor still applies **after** this change. A requirement met at 15% that breaks at 40% is a requirement no longer being met. |

**Required DECISIONS.md entry for Day-2:**
Add a section covering: what you changed, what you chose not to change, and what you would have done differently had you known this was coming in advance.

---

## Important Constraints

1. **Must go through HTTP** — raw data files are for reference only; the solution must call the services.
2. **`_pid` is invisible at runtime** — stripped by both services; identity matching cannot rely on it.
3. **Population overlap is invisible** — ~340 people appear in both sources, but nothing in the API reveals this.
4. **Identity matching is a stretch goal** — explicitly called a "rabbit hole." Do not sacrifice floor requirements for it.
5. **XML is always slow** — the sleep precedes the failure check; plan for async/concurrent requests and timeout budgets.
6. **`page_size` param is ignored by REST** — server always returns exactly 25 per page.
7. **Duplicate pattern is deterministic** — same 41 duplicates on every full traversal.
8. **`/health` is the only reliable liveness signal** for the XML service.
9. **XML refs contain `/`** — must be `%2F`-encoded in the URL path when calling `/records/<ref>`.

---

## Open Questions / Things We Should Verify

1. **What shape is the "unified view"?**
   The problem says "one call, one resident, everything known about them." Does this mean:
   - A list endpoint (all residents)?
   - A lookup endpoint (single resident by ID)?
   - Both?
   The problem permits a command-line demo but does not specify exact URL structure.

2. **What is the primary lookup key?**
   REST `id` (`R-NNNNN`) is the natural choice, but XML-only residents have no REST id.

3. **Is JSON mandated as the response format?**
   Implied by the REST-first framing, but not stated explicitly.

4. **What does "clear indication" mean in the graceful-degradation response?**
   Needs to be defined and documented in `DECISIONS.md`.

5. **What retry/timeout budget is acceptable at 40% failure?**
   - Each XML attempt costs 0.7–2.4 s (even on failure).
   - 3 retries → ~78% success probability; 5 retries → ~92%.
   - Maximum acceptable latency before returning partial data needs a decision.

6. **Is the integration purely read-only?**
   If so, idempotency is likely automatic and needs no special design.

7. **Caching strategy?** *(stretch goal)*
   Full `/records` dump vs. individual refs. What staleness window is defensible?

8. **Circuit breaker thresholds?** *(stretch goal)*
   Error rate window, open duration, probe behaviour via `/health`.

---

## Summary

| Topic | Finding |
|:--|:--|
| Services | 2: REST/JSON (reliable, port 8081) + XML/legacy (slow + flaky, port 8082) |
| REST records | 620 unique residents · 27 pages · 41 guaranteed duplicate appearances |
| XML records | 540 benefit records · single non-paginated XML dump |
| Cross-source link | ~340 people in both — but `_pid` linking field stripped by services at startup |
| REST failure modes | None (only intentional duplicate pagination) |
| XML failure modes | 0.7–2.4 s delay always · 15% HTTP 500 Day-1 · 40% HTTP 500 Day-2 |
| XML liveness oracle | `/health` — always fast, always succeeds |
| Floor (non-negotiable) | Graceful degradation · idempotency · dedup · clean-clone runnable · DECISIONS.md |
| Stretch goals | Identity matching (hard, rabbit hole) · caching · circuit breaking |
| Day-2 change | XML failure rate → 40%, permanent. Full floor still applies. |
| Identity matching constraint | `_pid` invisible at runtime — any matching must use fuzzy name/DOB/address heuristics |
