"""CHURN-54: CORS policy for the ChurnIQ API.

Only the deployed frontend and local development servers may call the API from
a browser. The list can be changed per deployment with the CORS_ALLOWED_ORIGINS
environment variable (comma-separated), without a code change.

Why credentials are off: the frontend never sends cookies. The one protected
endpoint, /send-email, uses an `Authorization: Bearer` header, which does not
need `Access-Control-Allow-Credentials`. Leaving credentials off means a
misconfigured origin list can never expose cookie-authenticated requests.
"""
from typing import Iterable, List, Optional
from urllib.parse import urlsplit

# Deployed frontend (Vercel). Recorded in backend/README.md.
PRODUCTION_FRONTEND_ORIGIN = 'https://churn-iq-frontend-five.vercel.app'

# Vite dev server (npm run dev) and preview server (npm run preview).
LOCAL_DEV_ORIGINS = (
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:4173',
    'http://127.0.0.1:4173',
)

DEFAULT_ALLOWED_ORIGINS = (PRODUCTION_FRONTEND_ORIGIN,) + LOCAL_DEV_ORIGINS

ALLOWED_METHODS = ['GET', 'POST']
ALLOWED_HEADERS = ['Content-Type', 'Authorization']
ALLOW_CREDENTIALS = False

ENV_VAR = 'CORS_ALLOWED_ORIGINS'


def normalise_origin(value: str) -> Optional[str]:
    """Return `scheme://host[:port]` (lower-case, no path or trailing slash),
    or None if the value is not a valid http(s) origin. A wildcard is
    rejected: it would allow any website to call the API."""
    v = (value or '').strip()
    if not v or '*' in v:
        return None
    parts = urlsplit(v)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return None
    if parts.path not in ('', '/') or parts.query or parts.fragment or parts.username:
        return None
    host = parts.hostname.lower()
    port = f':{parts.port}' if parts.port else ''
    return f'{parts.scheme}://{host}{port}'


def parse_allowed_origins(raw: Optional[str],
                          default: Iterable[str] = DEFAULT_ALLOWED_ORIGINS) -> List[str]:
    """Parse CORS_ALLOWED_ORIGINS. Unset or blank → the defaults. Invalid
    entries (including '*') are dropped; if nothing valid remains, the
    defaults are used rather than allowing every origin."""
    if raw is None or not raw.strip():
        return list(default)
    seen, out = set(), []
    for item in raw.split(','):
        origin = normalise_origin(item)
        if origin and origin not in seen:
            seen.add(origin)
            out.append(origin)
    return out or list(default)


def invalid_entries(raw: Optional[str]) -> List[str]:
    """Entries of CORS_ALLOWED_ORIGINS that were ignored (for a startup warning)."""
    if not raw:
        return []
    return [i.strip() for i in raw.split(',') if i.strip() and normalise_origin(i) is None]
