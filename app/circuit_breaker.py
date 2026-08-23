"""
Circuit breaker for the Benefits Register upstream.

Sits OUTSIDE the retry loop: a request only counts as a circuit-breaker
failure after the adapter has exhausted all 3 retry attempts and returned
status="unavailable". Successful requests (even those that required retries)
reset the consecutive failure counter.

State model:
  CLOSED    — normal operation, all requests forwarded to upstream.
  OPEN      — upstream considered persistently down, fail fast.
  HALF_OPEN — after recovery_duration, allow one trial request through.

This is an in-memory, single-process implementation appropriate for
a hackathon demo. State is lost on restart (which is fine — the circuit
resets to CLOSED, which is the safe default).
"""
import time


class BenefitsCircuitBreaker:
    """In-memory circuit breaker for the Benefits Register."""

    # States
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 3,
                 recovery_duration: float = 30.0):
        """
        Args:
            failure_threshold: Number of consecutive adapter-level failures
                (i.e. retry-exhausted unavailable responses) before the
                circuit opens. Default 3 means: 3 consecutive requests
                where all 3 retry attempts failed = 9 total failed HTTP
                calls before the circuit opens.
            recovery_duration: Seconds to wait in OPEN state before
                transitioning to HALF_OPEN for a trial request.
        """
        self.failure_threshold = failure_threshold
        self.recovery_duration = recovery_duration
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> str:
        """Current circuit state, accounting for time-based transitions."""
        if self._state == self.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_duration:
                self._state = self.HALF_OPEN
        return self._state

    def should_allow_request(self) -> bool:
        """Whether the circuit allows a request to proceed."""
        current = self.state
        if current == self.CLOSED:
            return True
        if current == self.HALF_OPEN:
            return True  # Allow exactly one trial
        # OPEN
        return False

    def record_success(self) -> None:
        """Record a successful adapter response (status="ok")."""
        self._consecutive_failures = 0
        self._state = self.CLOSED

    def record_failure(self) -> None:
        """Record a failed adapter response (status="unavailable"
        after all retries exhausted)."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._state = self.OPEN
            self._opened_at = time.monotonic()

    def time_remaining_open(self) -> float:
        """Seconds remaining in OPEN state. 0 if not OPEN."""
        if self._state != self.OPEN:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        remaining = self.recovery_duration - elapsed
        return max(0.0, remaining)

    def reset(self) -> None:
        """Reset circuit to CLOSED (for testing)."""
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0


# Module-level singleton for the Benefits Register circuit breaker.
# Imported by benefits_adapter.py.
from app.config import CB_FAILURE_THRESHOLD, CB_RECOVERY_DURATION

benefits_circuit = BenefitsCircuitBreaker(
    failure_threshold=CB_FAILURE_THRESHOLD,
    recovery_duration=CB_RECOVERY_DURATION
)
