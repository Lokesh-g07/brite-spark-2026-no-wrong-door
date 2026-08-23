"""
Configuration for the No Wrong Door unified API.

All tunable constants live here. Nothing is hardcoded in application code.
Values can be overridden via environment variables.
"""

import os


# ---------------------------------------------------------------------------
# Upstream service URLs
# ---------------------------------------------------------------------------
REST_BASE_URL: str = os.environ.get("REST_BASE_URL", "http://127.0.0.1:8081")
XML_BASE_URL: str = os.environ.get("XML_BASE_URL", "http://127.0.0.1:8082")

# ---------------------------------------------------------------------------
# Resilience — Benefits Register (XML service)
# ---------------------------------------------------------------------------
# Total attempts = 1 initial + (XML_MAX_ATTEMPTS - 1) retries
XML_MAX_ATTEMPTS: int = int(os.environ.get("XML_MAX_ATTEMPTS", "3"))
XML_TIMEOUT: float = float(os.environ.get("XML_TIMEOUT", "5.0"))        # seconds per attempt
XML_BACKOFF_BASE: float = float(os.environ.get("XML_BACKOFF_BASE", "0.3"))  # seconds, multiplied by attempt number

# ---------------------------------------------------------------------------
# Resilience — Resident Index (REST service)
# ---------------------------------------------------------------------------
REST_TIMEOUT: float = float(os.environ.get("REST_TIMEOUT", "10.0"))     # seconds for all pages

# ---------------------------------------------------------------------------
# Our API pagination defaults
# ---------------------------------------------------------------------------
DEFAULT_PAGE_SIZE: int = int(os.environ.get("DEFAULT_PAGE_SIZE", "50"))

# ---------------------------------------------------------------------------
# Circuit Breaker — Benefits Register
# ---------------------------------------------------------------------------
# Opens after this many consecutive adapter-level failures (each failure
# means all XML_MAX_ATTEMPTS retry attempts were exhausted).
CB_FAILURE_THRESHOLD: int = int(os.environ.get("CB_FAILURE_THRESHOLD", "3"))
# Seconds to stay OPEN before allowing a HALF_OPEN trial request.
CB_RECOVERY_DURATION: float = float(os.environ.get("CB_RECOVERY_DURATION", "30.0"))

