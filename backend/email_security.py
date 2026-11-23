"""CHURN-44 — protections for POST /send-email.

Three pieces, kept free of FastAPI so they can be unit-tested directly:

* ``check_bearer_token``  — constant-time check of ``Authorization: Bearer <token>``
  against the server-side ``EMAIL_API_TOKEN``.
* ``SlidingWindowLimiter`` — a small thread-safe in-memory rate limiter
  (no new dependency, no Redis). It is per process: see docs/api/README.md
  §"Email endpoint security" for the multi-worker limitation.
* ``is_valid_address``   — strict check of the configured sender/recipient
  addresses (no CR/LF, no whitespace, no display names, no header tricks).

Nothing here ever logs or returns the configured token.
"""
from __future__ import annotations

import hmac
import math
import re
import threading
import time
import unicodedata
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple

# Shortest EMAIL_API_TOKEN accepted. A shorter value is treated as "not
# configured" so a weak placeholder such as "test" can never unlock sending.
MIN_TOKEN_LENGTH = 16

# RFC 6750 bearer token characters (token68). Anything else is "malformed".
_BEARER_RE = re.compile(r'^Bearer ([A-Za-z0-9\-._~+/]+=*)$')

# Deliberately strict: one '@', no whitespace/control/quote/angle/comma chars,
# a dotted domain. Good enough for a configured demo inbox; we do not need to
# accept every RFC 5322 corner case, we need to reject header injection.
_ADDRESS_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}"
    r"@(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)

# Characters that end a line somewhere (str.splitlines) — all are rejected in
# single-line header values such as the subject.
_LINE_BREAKS = frozenset('\n\r\x0b\x0c\x1c\x1d\x1e\x85  ')


def configured_token(raw: Optional[str]) -> str:
    """Normalise EMAIL_API_TOKEN; '' when unset or too short to be safe."""
    token = (raw or '').strip()
    return token if len(token) >= MIN_TOKEN_LENGTH else ''


def check_bearer_token(authorization: Optional[str], expected: str) -> str:
    """Classify an Authorization header.

    Returns one of ``'ok'``, ``'missing'``, ``'malformed'``, ``'invalid'``.
    The comparison is constant-time (hmac.compare_digest), so response timing
    does not reveal how much of a guessed token was right.
    """
    if not authorization or not authorization.strip():
        return 'missing'
    match = _BEARER_RE.match(authorization.strip())
    if not match:
        return 'malformed'
    if not expected:                       # defensive: never match an empty secret
        return 'invalid'
    supplied = match.group(1).encode('utf-8')
    return 'ok' if hmac.compare_digest(supplied, expected.encode('utf-8')) else 'invalid'


def is_valid_address(address: Optional[str]) -> bool:
    """True for a plain ``local@domain.tld`` address that is safe in a header."""
    if not address or len(address) > 254:
        return False
    return bool(_ADDRESS_RE.match(address))


def has_line_break_or_control(value: str, allow: str = '') -> bool:
    """True if ``value`` contains a line break or control char not in ``allow``."""
    for ch in value:
        if ch in allow:
            continue
        if ch in _LINE_BREAKS or unicodedata.category(ch) == 'Cc':
            return True
    return False


class SlidingWindowLimiter:
    """At most ``max_requests`` hits per ``window_seconds`` for each key.

    Thread-safe (sync FastAPI endpoints run in a thread pool). Memory is
    bounded: empty buckets are dropped, and keys are pruned when the table
    grows past ``max_keys``.
    """

    def __init__(self, max_requests: int, window_seconds: float,
                 clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError('max_requests must be >= 1 and window_seconds > 0')
        self.max_requests = int(max_requests)
        self.window = float(window_seconds)
        self._clock = clock
        self._max_keys = max_keys
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> Tuple[bool, int]:
        """Record one attempt. Returns ``(allowed, retry_after_seconds)``.

        A rejected attempt is not recorded, so a client that keeps hammering
        regains access once its earlier attempts age out of the window.
        """
        now = self._clock()
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                if len(self._hits) >= self._max_keys:
                    self._prune(now)
                bucket = self._hits[key] = deque()
            cutoff = now - self.window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry = max(1, math.ceil(bucket[0] + self.window - now))
                return False, retry
            bucket.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        for k in [k for k, b in self._hits.items() if not b or b[-1] <= cutoff]:
            del self._hits[k]
        if len(self._hits) >= self._max_keys:       # still full: drop oldest
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])
            for k in oldest[: len(self._hits) - self._max_keys + 1]:
                del self._hits[k]


def env_int(environ, name: str, default: int, minimum: int = 1) -> int:
    """Read a positive int from the environment; fall back to ``default``."""
    raw = (environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default
