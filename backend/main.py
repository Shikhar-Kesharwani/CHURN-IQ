
#   ChurnIQ Pro — FILE 2: FastAPI Backend + Gemini AI
#   ─────────────────────────────────────────────────────────
#   What this file does:
#
#   PART A — STARTUP
#     Loads trained XGBoost model (.pkl) and datasets on server start
#     Configures Gemini API key
#
#   PART B — HELPER FUNCTIONS
#     Feature engineering (same as ML pipeline — must match exactly)
#     Plain-English SHAP reason formatting
#     CLV calculation and segmentation
#
#   PART C — API ENDPOINTS
#     GET  /                   → Health check
#     GET  /customers          → Full risk table + KPI summary
#     GET  /customer/{id}      → Single customer detail + SHAP reasons
#     POST /whatif             → Live what-if simulation (sliders)
#     GET  /retention/{id}     → Gemini AI retention email + actions
#     GET  /segments           → Churn stats by plan/device/tenure/genre
#     GET  /dashboard/summary  → All KPIs in one call
#
#   ─────────────────────────────────────────────────────────
#   PREREQUISITES:
#     Run churniq_ml_pipeline.py first to generate:
#       churniq_model.pkl
#       feature_names.pkl
#       ott_churn_dataset.csv
#       customer_predictions.csv
#
#   SETUP:
#     pip install fastapi uvicorn google-generativeai
#                 pandas numpy scikit-learn xgboost python-multipart
#
#   ADD YOUR GEMINI KEY:
#     Get free key from: https://aistudio.google.com
#     Set it below in the GEMINI_API_KEY variable (line ~120)
#
#   RUN:
#     uvicorn main:app --reload --port 8000
#
#   TEST:
#     Open http://localhost:8000/docs  ← interactive Swagger UI
#     Try every endpoint directly in the browser — no Postman needed!
#
#   DEPLOY TO RENDER (free):
#     1. Push project to GitHub
#     2. Go to render.com → New Web Service
#     3. Connect repo → Build: pip install -r requirements.txt
#     4. Start: uvicorn main:app --host 0.0.0.0 --port $PORT
#     5. Add env variable: GEMINI_API_KEY = your_key
# =============================================================================

# ─── IMPORTS ──────────────────────────────────────────────────────────────────

# FastAPI — the web framework that turns Python functions into REST API endpoints
# Uvicorn — the ASGI server that runs FastAPI (async capable, much faster than Flask)
from fastapi import Depends, FastAPI, HTTPException, Query, Path, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Pydantic — data validation library
# CONCEPT: Pydantic models define the SHAPE of request/response data.
# FastAPI uses them to:
#   - Automatically validate incoming JSON (wrong type = auto 422 error)
#   - Generate API documentation at /docs
#   - Serialize Python dicts to JSON responses
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from typing import Annotated, Any, Dict, List, Optional

# Standard Python
import pickle          # Deserialize saved .pkl model and feature names
import pandas as pd
import numpy as np
import os
import json
import re
import warnings
import sys
import html
import logging
import traceback
import uuid
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from customer_similarity import CustomerSimilarityEngine
import churniq_core

warnings.filterwarnings('ignore')

# ── Logging (CHURN-21) ───────────────────────────────────────────────────────
# Server-side diagnostics go to the 'churniq.api' logger. Clients only ever see
# a short message, an error code and a request_id that matches the log line.
logger = logging.getLogger("churniq.api")
logger.setLevel(logging.INFO)
if not logger.handlers and not logging.getLogger().handlers:
    # Only our own logger gets a handler — global/library logging is untouched.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)

# Google Gemini API — for AI-generated retention emails
# CONCEPT: We use Gemini to translate ML/SHAP output into human-readable
# personalized retention strategies. This is the "AI layer" of ChurnIQ Pro.
import google.generativeai as genai


# =============================================================================
#   PART A — STARTUP: Load All Required Files
# =============================================================================
# CONCEPT: Load heavy resources ONCE at startup, not on every request.
# Loading a .pkl model takes ~200-500ms. If loaded per request:
#   → Every API call is 500ms slower
#   → Under 10 concurrent users → server is constantly reloading
# Loading at startup: done once → all requests share same loaded object
#
# VIVA TIP:
#   "We use FastAPI's module-level loading pattern — the model is loaded
#    into memory when the server starts. All incoming requests share the
#    same model object. This is thread-safe for inference (read-only)."
# =============================================================================

print("=" * 60)
print("  ChurnIQ Pro API — Initializing...")
print("=" * 60)

def find_file(filename: str) -> str:
    """
    Search common locations for a required file.
    Checks current directory, subdirectories, and outputs folder.
    Raises FileNotFoundError with helpful message if not found.
    """
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',   filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs', filename),
        os.path.join('/mnt/user-data/outputs', filename),
        filename,   # Absolute path (if passed directly)
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"Cannot find '{filename}'.\n"
        f"Make sure you ran churniq_ml_pipeline.py first.\n"
        f"Searched in: {candidates}"
    )

class ArtifactLoadError(RuntimeError):
    """A required model/data artifact is missing or unreadable (CHURN-21).

    Raised at import time so the server refuses to start with a clear,
    single-line reason instead of serving requests with a half-loaded model.
    """


def load_required_artifact(filename: str, loader, what: str):
    """Locate and load a required startup artifact, failing with a clear message."""
    try:
        path = find_file(filename)
    except FileNotFoundError as e:
        logger.error("Startup failed: required artifact %s (%s) is missing. %s", filename, what, e)
        raise ArtifactLoadError(
            f"Required artifact '{filename}' ({what}) was not found. "
            f"Run churniq_ml_pipeline.py / generate_predictions.py to create it."
        ) from e
    try:
        return loader(path)
    except Exception as e:
        logger.error("Startup failed: could not load %s (%s) from %s: %s: %s",
                     filename, what, path, type(e).__name__, e)
        raise ArtifactLoadError(
            f"Required artifact '{filename}' ({what}) could not be loaded "
            f"({type(e).__name__}). Regenerate it with the ML pipeline."
        ) from e


def _load_pickle(path):
    with open(path, 'rb') as f:
        return pickle.load(f)


# ── Load XGBoost Model ──────────────────────────────────────────────────────
print("\n[1/4] Loading XGBoost model...")
MODEL = load_required_artifact('churniq_model.pkl', _load_pickle, 'production XGBoost model')
print("  ✓ Model loaded")

# ── Load Feature Names ──────────────────────────────────────────────────────
# CRITICAL: Feature names define the exact order and set of columns
# the model expects. ANY mismatch = wrong predictions.
print("[2/4] Loading feature names...")
FEATURE_NAMES = load_required_artifact('feature_names.pkl', _load_pickle, 'model feature order')
print(f"  ✓ {len(FEATURE_NAMES)} feature names loaded")

# ── Load Predictions CSV ─────────────────────────────────────────────────────
# Pre-computed by ML pipeline — contains churn_prob + SHAP reasons per customer
# We load this so /customers and /customer/{id} endpoints are FAST
# (no live SHAP computation needed — that's already done)
print("[3/4] Loading predictions...")
PREDICTIONS_DF = load_required_artifact('customer_predictions.csv', pd.read_csv,
                                        'pre-computed customer predictions')
print(f"  ✓ {len(PREDICTIONS_DF)} customer predictions loaded")

# ── Load Raw Dataset ──────────────────────────────────────────────────────────
# Needed for: customer profiles, segment analysis, what-if defaults
print("[4/4] Loading raw dataset...")
DATASET_DF = load_required_artifact('ott_churn_dataset.csv', pd.read_csv, 'customer dataset')
print(f"  ✓ {len(DATASET_DF)} customers loaded")

# ── Merge Predictions into Dataset ──────────────────────────────────────────
# CONCEPT: SQL-style JOIN on customer_id
# Result: each customer row has both profile data AND churn predictions
# suffixes=('_raw', '') → if column exists in both, predictions version wins
FULL_DF = DATASET_DF.merge(
    PREDICTIONS_DF[['customer_id', 'churn_prob', 'risk_level',
                    'top_reason_1', 'top_reason_2', 'top_reason_3', 'clv_score',
                    'prediction_source', 'fold']],
    on='customer_id',
    how='left',
    suffixes=('_raw', '')
)

# ── CLV tier consistency (CHURN-16) ──────────────────────────────────────────
# The dataset's clv_segment was computed from the GENERATOR's true churn
# probability, while clv_score above comes from the MODEL's probability.
# Re-derive the tier from the model CLV so /segments, /dashboard/summary and
# /customer/{id} all agree. Unscored customers get 'Unknown' (below).
_has_model_clv = FULL_DF['clv_score'].notna()
FULL_DF.loc[_has_model_clv, 'clv_segment'] = (
    FULL_DF.loc[_has_model_clv, 'clv_score'].map(churniq_core.get_clv_segment)
)
print(f"\n  Merged dataset shape: {FULL_DF.shape}")

# ── Model feature matrix per customer (CHURN-15) ─────────────────────────────
# The exact feature values the model saw, used to phrase SHAP reasons
# truthfully ("tenure of 18 months" vs "short tenure").
FEATURE_MATRIX = churniq_core.encode_features(DATASET_DF, FEATURE_NAMES)
FEATURE_MATRIX.index = DATASET_DF['customer_id'].values

# ── Out-of-fold models (CHURN-37) ────────────────────────────────────────────
# customer_predictions.csv (generate_predictions.py) covers every eligible
# customer. Training-split customers are scored out-of-fold: their probability
# comes from the fold model that did NOT see them. Live what-if calls must use
# that same fold model — the production MODEL is in-sample for them
# (over-confident), so mixing the two would recreate a train/serve mismatch.
# Held-out test and demo customers use the production MODEL.
FOLD_MODELS = None
try:
    with open(find_file('oof_fold_models.pkl'), 'rb') as f:
        _oof = pickle.load(f)
    # CHURN-21: an explicit check (not `assert`, which `python -O` strips).
    # A mismatched bundle disables out-of-fold what-if; it is NEVER replaced
    # by the production MODEL, which is in-sample for these customers.
    if list(_oof['feature_names']) != list(FEATURE_NAMES):
        raise ValueError('fold model feature names do not match feature_names.pkl')
    FOLD_MODELS = _oof['models']
    print(f"  ✓ {len(FOLD_MODELS)} out-of-fold models loaded")
except FileNotFoundError:
    print("  ⚠ oof_fold_models.pkl not found — what-if unavailable for out-of-fold customers")
    logger.warning("oof_fold_models.pkl not found — /whatif returns 409 for out-of-fold customers")
except Exception as e:
    FOLD_MODELS = None
    print("  ⚠ oof_fold_models.pkl could not be used — what-if unavailable for out-of-fold customers")
    logger.error("oof_fold_models.pkl unusable (%s: %s) — /whatif returns 409 for "
                 "out-of-fold customers", type(e).__name__, e)


def model_for(row):
    """The model that produced this customer's displayed probability, or None."""
    if row.get('prediction_source') == 'cv_out_of_fold':
        fold = row.get('fold')
        if FOLD_MODELS is None or fold is None or pd.isna(fold):
            return None
        return FOLD_MODELS[int(fold)]
    return MODEL


# ── Unscored customers (CHURN-37 fallback) ───────────────────────────────────
# Every eligible customer now has a prediction. Records that fail
# churniq_core.validate_raw_record (or are absent from the predictions file)
# remain explicitly NOT_SCORED / Unknown — never 0 % risk or ₹0 CLV, and never
# the generator's true-probability tier.
NOT_SCORED        = 'NOT_SCORED'
NOT_SCORED_TEXT   = 'Not scored'
NOT_SCORED_REASON = 'Not scored — no out-of-sample model prediction is available for this customer'
FULL_DF.loc[FULL_DF['churn_prob'].isna(), 'clv_segment'] = 'Unknown'
SCORED_COUNT   = int(FULL_DF['churn_prob'].notna().sum())
UNSCORED_COUNT = int(FULL_DF['churn_prob'].isna().sum())
print(f"  ✓ {SCORED_COUNT} customers scored, {UNSCORED_COUNT} not scored")


def model_prob(row):
    """The model's churn probability for a FULL_DF row, or None if not scored."""
    v = row.get('churn_prob')
    return None if v is None or pd.isna(v) else float(v)


def _mean_or_none(series):
    """Mean of the non-null values, or None when there are none (avoids NaN in JSON)."""
    v = series.mean()
    return None if v is None or pd.isna(v) else float(v)


def _json_safe(records):
    """Replace NaN/inf in list-of-dict records with None (JSON has no NaN)."""
    return [{k: (None if isinstance(v, float) and not np.isfinite(v) else v)
             for k, v in r.items()} for r in records]

# ── Load/Initialize Customer Similarity Engine (KNN) ─────────────────────────
print("\n[5/5] Loading Customer Similarity Engine (KNN)...")
# CHURN-21: the similarity engine is an optional feature. If it cannot be
# loaded or fitted, the rest of the API still starts and the similarity
# endpoints answer 503 with a clear message.
try:
    SIMILARITY_ENGINE = CustomerSimilarityEngine(data_df=DATASET_DF)
    if not SIMILARITY_ENGINE.load(data_df=DATASET_DF):
        print("  Artifacts not found, fitting Customer Similarity Engine...")
        SIMILARITY_ENGINE.fit(DATASET_DF)
        SIMILARITY_ENGINE.save()
    print("  ✓ Customer Similarity Engine ready")
except Exception as e:
    SIMILARITY_ENGINE = None
    print("  ⚠ Customer Similarity Engine unavailable — similarity endpoints return 503")
    logger.error("Customer Similarity Engine failed to initialise: %s: %s", type(e).__name__, e)


# =============================================================================
#   CONFIGURE GEMINI API
# =============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#   ⚠️  IMPORTANT: Replace 'YOUR_GEMINI_API_KEY' with your actual key!
#   Get a free key at: https://aistudio.google.com/app/apikey
#   Takes 2 minutes — no credit card required
#   Or set as environment variable: export GEMINI_API_KEY="your_key_here"
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# The model actually called. /retention reports this name in `generated_by`.
# Override with the GEMINI_MODEL_NAME environment variable; an unset or blank
# value falls back to the default. (gemini-2.5-flash returns 404 for the
# project's API key; gemini-3.5-flash is the working default.)
GEMINI_MODEL_NAME = (
    os.environ.get("GEMINI_MODEL_NAME", "gemini-3.5-flash").strip()
    or "gemini-3.5-flash"
)
# Upper bound on one Gemini call so a slow upstream cannot hang a request.
try:
    GEMINI_TIMEOUT_SECONDS = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "20"))
except ValueError:
    GEMINI_TIMEOUT_SECONDS = 20.0
GEMINI_MODEL   = None
GEMINI_ENABLED = False

if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY":
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_MODEL   = genai.GenerativeModel(GEMINI_MODEL_NAME)
        GEMINI_ENABLED = True
        print(f"  ✓ Gemini API configured — model {GEMINI_MODEL_NAME} (AI retention emails enabled)")
    except Exception as e:
        # Never log the exception text verbatim: it may echo the key.
        logger.error("Gemini configuration failed (%s) — /retention uses rule-based fallback",
                     type(e).__name__)
        print("  ⚠ Gemini configuration failed — /retention endpoint uses rule-based fallback")
else:
    print("  ⚠ Gemini API key not set — /retention endpoint uses rule-based fallback")
    print("    Set key: export GEMINI_API_KEY='your_key'")

print("\n" + "=" * 60)
print("  Startup complete! All systems ready.")
print("  Docs: http://localhost:8000/docs")
print("=" * 60)

# =============================================================================
# ChurnIQ Pro — Email Sending Code
# =============================================================================
# Yeh code main.py mein add karo:
#
#   PART 1 → Top pe (imports ke baad, FastAPI app se pehle)
#   PART 2 → Bottom pe (last endpoint ke baad)
# =============================================================================
 
 
# ─────────────────────────────────────────────────────────────
# PART 1 — Yeh code main.py mein TOP pe add karo
#           (existing imports ke baad, app = FastAPI() se pehle)
# ─────────────────────────────────────────────────────────────
 
import smtplib
import json
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart
 
# Load Gmail config from email_config.json
# CONCEPT: Credentials ko code mein hardcode karna dangerous hai
# Agar galti se GitHub pe push ho gaya → credentials leak!
# Isliye alag JSON file mein rakha — .gitignore se protected
 
# Load Gmail config from environment variables (SECURE) or fallback to local email_config.json
GMAIL_SENDER   = os.environ.get('GMAIL_SENDER', '')
GMAIL_APP_PASS = os.environ.get('GMAIL_APP_PASS', '')
DEMO_RECEIVER  = os.environ.get('DEMO_RECEIVER', '')

if not (GMAIL_SENDER and GMAIL_APP_PASS):
    try:
        with open('email_config.json') as f:
            _cfg = json.load(f)
        GMAIL_SENDER   = GMAIL_SENDER or _cfg.get('GMAIL_SENDER', '')
        GMAIL_APP_PASS = GMAIL_APP_PASS or _cfg.get('GMAIL_APP_PASS', '')
        DEMO_RECEIVER  = DEMO_RECEIVER or _cfg.get('DEMO_RECEIVER', '')
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

EMAIL_ENABLED = bool(GMAIL_SENDER and GMAIL_APP_PASS)
if EMAIL_ENABLED:
    print("  ✓ Gmail config loaded (email sending enabled)")
else:
    print("  ⚠ Gmail not configured — set GMAIL_SENDER and GMAIL_APP_PASS env variables")

# ── /send-email protection (CHURN-44) ────────────────────────────────────────
# EMAIL_API_TOKEN: server-side shared secret. Callers must send
#   Authorization: Bearer <EMAIL_API_TOKEN>
# Unset (or shorter than 16 chars) → /send-email is disabled (503), fail closed.
# EMAIL_RATE_LIMIT_MAX per EMAIL_RATE_LIMIT_WINDOW_SECONDS, per client IP,
# counted for every authenticated attempt (valid or not) and, separately, for
# every failed authentication attempt. In-memory: per process (see docs).
import email_security as esec

EMAIL_API_TOKEN                 = esec.configured_token(os.environ.get('EMAIL_API_TOKEN'))
EMAIL_RATE_LIMIT_MAX            = esec.env_int(os.environ, 'EMAIL_RATE_LIMIT_MAX', 5)
EMAIL_RATE_LIMIT_WINDOW_SECONDS = esec.env_int(os.environ, 'EMAIL_RATE_LIMIT_WINDOW_SECONDS', 600)
EMAIL_SEND_LIMITER   = esec.SlidingWindowLimiter(EMAIL_RATE_LIMIT_MAX, EMAIL_RATE_LIMIT_WINDOW_SECONDS)
EMAIL_AUTH_FAIL_LIMITER = esec.SlidingWindowLimiter(EMAIL_RATE_LIMIT_MAX, EMAIL_RATE_LIMIT_WINDOW_SECONDS)

if EMAIL_API_TOKEN:
    print(f"  ✓ /send-email protected: bearer token + {EMAIL_RATE_LIMIT_MAX} requests "
          f"per {EMAIL_RATE_LIMIT_WINDOW_SECONDS}s per client")
elif (os.environ.get('EMAIL_API_TOKEN') or '').strip():
    print(f"  ⚠ EMAIL_API_TOKEN is shorter than {esec.MIN_TOKEN_LENGTH} characters — "
          "ignored; /send-email is disabled")
else:
    print("  ⚠ EMAIL_API_TOKEN not set — /send-email is disabled (returns 503)")
if esec.env_int(os.environ, 'WEB_CONCURRENCY', 1) > 1:
    print("  ⚠ WEB_CONCURRENCY > 1: the /send-email rate limit is per worker process, "
          "so the effective limit is multiplied by the number of workers")
# =============================================================================
#   FASTAPI APP INITIALIZATION
# =============================================================================
# CONCEPT: FastAPI creates a web application where Python functions become
# REST API endpoints. Each endpoint is a Python function decorated with
# @app.get(), @app.post() etc.
#
# FastAPI automatically:
#   → Parses incoming JSON request bodies
#   → Validates data types (int, str, float etc.)
#   → Serializes Python dicts/lists to JSON responses
#   → Generates interactive docs at /docs (Swagger UI)
#   → Generates schema at /openapi.json
#
# FASTAPI vs FLASK:
#   Flask: older, synchronous, manual validation
#   FastAPI: async-first, automatic validation via Pydantic, auto docs
#   In 2025, FastAPI is the industry standard for new Python APIs

app = FastAPI(
    title="ChurnIQ Pro API",
    description=(
        "AI-powered OTT customer churn prediction and retention intelligence. "
        "Predicts churn probability, explains reasons via SHAP, scores CLV, "
        "and generates personalized retention emails via Gemini AI."
    ),
    version="1.0.0",
    docs_url="/docs",       # Swagger UI at /docs
    redoc_url="/redoc",     # ReDoc UI at /redoc
)

# ── /send-email gate (CHURN-44) ──────────────────────────────────────────────
# Runs BEFORE routing and body parsing, so authentication and rate limiting
# apply to every request — including malformed or invalid bodies, which can
# therefore neither probe the endpoint unauthenticated nor bypass the limit.
# Registered before CORSMiddleware so CORS stays the outermost layer and the
# browser can read 401/429 responses.
EMAIL_PROTECTED_PATHS = ('/send-email', '/send-email/')
EMAIL_UNAUTHORIZED_MESSAGE = ("Missing or invalid email API token. "
                              "Send the header 'Authorization: Bearer <token>'.")


def _client_key(request: Request) -> str:
    # request.client is the direct peer. X-Forwarded-For is NOT trusted here
    # (it is client-controlled); run uvicorn with --proxy-headers and
    # --forwarded-allow-ips behind a trusted proxy to get real client IPs.
    return request.client.host if request.client else 'unknown'


def _rate_limited_response(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=_error_body(429, 'rate_limited',
                            f"Too many email requests. Try again in {retry_after} seconds."),
        headers={'Retry-After': str(retry_after)})


@app.middleware('http')
async def email_endpoint_gate(request: Request, call_next):
    if request.url.path not in EMAIL_PROTECTED_PATHS or request.method == 'OPTIONS':
        return await call_next(request)

    if not EMAIL_API_TOKEN:
        return JSONResponse(status_code=503, content=_error_body(
            503, 'email_auth_not_configured',
            "Email sending is disabled: no API token is configured on the server."))

    client = _client_key(request)
    verdict = esec.check_bearer_token(request.headers.get('authorization'), EMAIL_API_TOKEN)
    if verdict != 'ok':
        # Failed attempts have their own bucket: brute-forcing the token is
        # throttled, but cannot use up the quota of legitimate callers.
        allowed, retry = EMAIL_AUTH_FAIL_LIMITER.hit(client)
        logger.warning("/send-email rejected: %s credentials (client %s)", verdict, client)
        if not allowed:
            return _rate_limited_response(retry)
        return JSONResponse(status_code=401,
                            content=_error_body(401, 'unauthorized', EMAIL_UNAUTHORIZED_MESSAGE),
                            headers={'WWW-Authenticate': 'Bearer'})

    # Authenticated: every attempt counts, valid or not.
    allowed, retry = EMAIL_SEND_LIMITER.hit(client)
    if not allowed:
        logger.warning("/send-email rate limit exceeded (client %s)", client)
        return _rate_limited_response(retry)
    return await call_next(request)


# ── CORS Middleware ──────────────────────────────────────────────────────────
# CONCEPT: Browsers enforce CORS (Cross-Origin Resource Sharing) policy.
# A React app at localhost:5173 CANNOT call an API at localhost:8000
# by default — different ports = different "origins" = blocked by browser.
#
# CORS middleware adds headers to every response:
#   Access-Control-Allow-Origin: *
#   Access-Control-Allow-Methods: GET, POST, ...
#
# This tells the browser: "Yes, this API is intentionally accessible cross-origin"
# In production → replace "*" with your actual frontend URL for security:
#   allow_origins=["https://churniq.vercel.app"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Allow ALL origins (dev mode)
    allow_credentials=True,
    allow_methods=["*"],        # Allow all HTTP methods
    allow_headers=["*"],        # Allow all headers
)


# =============================================================================
#   ERROR HANDLING (CHURN-21)
# =============================================================================
# Every error response — 4xx and 5xx, raised by our code, by FastAPI's request
# validation or by an unexpected crash — has the same JSON shape:
#
#   {
#     "detail":      "Human-readable message",     # always a string
#     "error":       "machine_readable_code",      # e.g. not_found, validation_error
#     "status_code": 404,
#     "errors":      [{"field": ..., "message": ..., "type": ...}],  # 422 only
#     "request_id":  "3f2c..."                     # 500 only; matches the server log
#   }
#
# `detail` stays a string so the frontend's `data?.detail` keeps working
# (FastAPI's default 422 put a list there, which React cannot render).
# Stack traces, exception text, file paths and API keys are logged server-side
# only (redacted), never returned to the client.

DEFAULT_ERROR_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 413: "payload_too_large",
    422: "validation_error", 429: "rate_limited", 500: "internal_error",
    502: "bad_gateway", 503: "service_unavailable", 504: "gateway_timeout",
}


class APIError(HTTPException):
    """HTTPException carrying a stable machine-readable error code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.code = code


class ErrorResponse(BaseModel):
    """Shape of every error response (documented in /docs)."""
    detail:      str
    error:       str
    status_code: int
    errors:      Optional[List[Dict[str, Any]]] = None
    request_id:  Optional[str] = None


_SECRET_PATTERNS = [
    re.compile(r'AIza[0-9A-Za-z_\-]{20,}'),                     # Google API keys
    re.compile(r'(?i)(api[_-]?key|key|token|password|pass)=([^&\s]+)'),
]


def redact(text) -> str:
    """Remove configured secrets and key-like tokens from a log message."""
    text = str(text)
    for secret in (GEMINI_API_KEY, os.environ.get('GMAIL_APP_PASS', ''), GMAIL_APP_PASS,
                   EMAIL_API_TOKEN, os.environ.get('EMAIL_API_TOKEN', '')):
        if secret and len(secret) >= 4:
            text = text.replace(secret, '[REDACTED]')
    text = _SECRET_PATTERNS[0].sub('[REDACTED]', text)
    return _SECRET_PATTERNS[1].sub(lambda m: f'{m.group(1)}=[REDACTED]', text)


def log_exception(exc: BaseException, message: str, *args) -> None:
    """logger.error with a REDACTED traceback (logger.exception would leak raw text)."""
    tb = redact(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    logger.error(message + "\n%s", *args, tb)


def _error_body(status_code: int, code: str, message: str, **extra) -> dict:
    body = {"detail": message, "error": code, "status_code": status_code}
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = getattr(exc, 'code', None) or DEFAULT_ERROR_CODES.get(exc.status_code, 'http_error')
    message = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, default=str)
    if exc.status_code >= 500:
        logger.warning("%s %s -> %s %s: %s", request.method, request.url.path,
                       exc.status_code, code, redact(message))
    return JSONResponse(status_code=exc.status_code,
                        content=_error_body(exc.status_code, code, message),
                        headers=getattr(exc, 'headers', None))


def _field_name(loc) -> str:
    parts = [str(p) for p in loc if p not in ('body', 'query', 'path', 'header')]
    return '.'.join(parts) if parts and not all(p.isdigit() for p in parts) else (
        str(loc[0]) if loc else 'request')


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # The offending input values are deliberately NOT echoed back.
    errors = [{"field": _field_name(e.get('loc', ())),
               "message": e.get('msg', 'Invalid value'),
               "type": e.get('type', 'value_error')} for e in exc.errors()]
    summary = '; '.join(f"{e['field']}: {e['message']}" for e in errors[:5])
    return JSONResponse(status_code=422, content=_error_body(
        422, 'validation_error', f"Invalid request — {summary}", errors=errors))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = uuid.uuid4().hex[:12]
    # The traceback is formatted here so it can be redacted too (exc_info=
    # would print the raw exception message, which may contain a key).
    tb = redact(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    logger.error("Unhandled error request_id=%s %s %s: %s: %s\n%s", request_id, request.method,
                 request.url.path, type(exc).__name__, redact(exc), tb)
    return JSONResponse(status_code=500, content=_error_body(
        500, 'internal_error',
        "An unexpected server error occurred. Quote the request_id when reporting it.",
        request_id=request_id))


ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Customer not found"},
    422: {"model": ErrorResponse, "description": "Malformed or out-of-range input"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
}


# =============================================================================
#   PYDANTIC REQUEST/RESPONSE MODELS
# =============================================================================
# CONCEPT: Pydantic models are Python classes that define data schemas.
# They serve three purposes in FastAPI:
#   1. Request validation → wrong type = automatic 422 Unprocessable Entity
#   2. Response documentation → shown in /docs so frontend knows what to expect
#   3. Type safety → your IDE gives autocomplete for these fields
#
# Optional fields = not required. If not sent, they default to None.
# The what-if endpoint uses Optional because user might only change 1 slider.

# ── Input validation rules (CHURN-20) ─────────────────────────────────────────
# Customer IDs: 1-32 characters of letters, digits, '_' or '-', surrounding
# whitespace ignored. Well-formed but unknown IDs → 404; malformed IDs → 422.
CUSTOMER_ID_PATTERN = r'^[A-Za-z0-9_-]{1,32}$'
_CUSTOMER_ID_RE     = re.compile(CUSTOMER_ID_PATTERN)
CUSTOMER_ID_RULE    = ("1-32 characters: letters, digits, '_' or '-' (e.g. CUST00001)")

# What-if bounds: physically/commercially plausible values. They are wider
# than the training data range (shown in brackets) so analysts can explore,
# but XGBoost does not extrapolate — beyond the training range the prediction
# stays flat at the edge value. NaN / ±Infinity and wrong types are rejected.
WHATIF_BOUNDS = {
    #  field                   (min, max)     training range
    'watch_hours_per_week': (0.0, 168.0),   # [0.5, 40]  — 168 = hours in a week
    'tenure_months':        (1, 240),       # [1, 72]
    'payment_failures_3m':  (0, 20),        # [0, 4]
    'support_tickets':      (0, 100),       # [0, 5]
    'logins_last_30_days':  (0, 300),       # [1, 26]
    'monthly_charge':       (1, 5000),      # {199, 499, 799}
}
MAX_SIMILAR_NEIGHBORS = 50
MAX_CUSTOMERS_LIMIT   = 10000
CUSTOMERS_SORT_FIELDS = ('churn_prob', 'clv_score', 'monthly_charge', 'tenure_months',
                         'watch_hours_per_week', 'logins_last_30_days', 'payment_failures_3m',
                         'support_tickets', 'customer_id', 'name', 'plan_type', 'risk_level')


def normalize_customer_id(value) -> str:
    """Strip whitespace and check the ID format; raise ValueError if malformed."""
    if not isinstance(value, str):
        raise ValueError('customer_id must be a string')
    value = value.strip()
    if not _CUSTOMER_ID_RE.match(value):
        raise ValueError(f'customer_id must be {CUSTOMER_ID_RULE}')
    return value


def _bounded(field, kind=float):
    lo, hi = WHATIF_BOUNDS[field]
    if kind is float:
        return Optional[Annotated[float, Field(strict=True, ge=lo, le=hi, allow_inf_nan=False)]]
    return Optional[Annotated[StrictInt, Field(ge=lo, le=hi)]]


class _CustomerIdModel(BaseModel):
    @field_validator('customer_id', mode='before', check_fields=False)
    @classmethod
    def _check_customer_id(cls, v):
        return normalize_customer_id(v)


class WhatIfRequest(_CustomerIdModel):
    """
    Request body for POST /whatif (What-If Simulator).

    Frontend sends the customer_id + any features the user changed via sliders.
    Only send the fields that changed — unchanged fields stay at customer's actual values.
    `null` (or omitting a field) keeps the customer's actual value.

    Validation (CHURN-20): unknown fields, wrong types, NaN/Infinity and values
    outside WHATIF_BOUNDS are rejected with 422.

    Example request body:
    {
        "customer_id": "CUST01033",
        "payment_failures_3m": 0,
        "watch_hours_per_week": 8.5
    }
    """
    model_config = ConfigDict(extra='forbid')

    customer_id:            str
    watch_hours_per_week:   _bounded('watch_hours_per_week')       = None   # Slider: 0.5 - 40 hrs/week
    tenure_months:          _bounded('tenure_months', int)         = None   # Slider: 1 - 72 months
    payment_failures_3m:    _bounded('payment_failures_3m', int)   = None   # Slider: 0 - 4 failures
    support_tickets:        _bounded('support_tickets', int)       = None   # Slider: 0 - 5 tickets
    logins_last_30_days:    _bounded('logins_last_30_days', int)   = None   # Slider: 0 - 30 logins
    monthly_charge:         _bounded('monthly_charge', int)        = None   # Dropdown: 199 / 499 / 799


class WhatIfResponse(BaseModel):
    """Response from POST /whatif — shows before and after churn probabilities."""
    customer_id:          str
    original_churn_prob:  float    # Before slider change
    new_churn_prob:       float    # After slider change
    change:               float    # Positive = got riskier, Negative = improved
    change_percent:       str      # Formatted: "+3.2%" or "-8.5%"
    original_risk:        str      # HIGH / MEDIUM / LOW
    new_risk:             str      # HIGH / MEDIUM / LOW
    improved:             bool     # True if change is negative (risk went down)


class CustomerSimilarityRequest(_CustomerIdModel):
    """Request body for POST /api/customer-similarity.

    n_neighbors: 1-50 (default 5; null → 5). Values outside the range are
    rejected with 422 instead of being silently replaced (CHURN-20/23).
    """
    model_config = ConfigDict(extra='forbid')

    customer_id: str
    n_neighbors: Optional[Annotated[StrictInt, Field(ge=1, le=MAX_SIMILAR_NEIGHBORS)]] = 5


class SimilarCustomerDetail(BaseModel):
    """Details of a single similar historical customer."""
    customer_id: str
    name: str
    similarity_score: float
    distance: float
    similarity_explanation: str
    historical_churn: Optional[int] = None
    historical_outcome: str
    churn_prob: Optional[float] = None   # None = not scored by the model (Bug A)
    churn_percent: str
    risk_level: str
    plan_type: str
    monthly_charge: int
    tenure_months: int
    watch_hours_per_week: float
    logins_last_30_days: int
    last_login_days_ago: int
    payment_failures_3m: int
    support_tickets: int
    device_type: str
    preferred_genre: str
    payment_method: str
    num_profiles: int
    age: int


class CustomerSimilarityResponse(BaseModel):
    """Response payload for customer similarity search."""
    selected_customer: dict
    similar_customers: List[SimilarCustomerDetail]
    count: int
    insights: List[str]


# ── Response contracts (CHURN-19) ─────────────────────────────────────────────
# These document and enforce the JSON the frontend already consumes. Field
# names are unchanged; Optional marks fields that are null for NOT_SCORED
# customers. FastAPI validates every response against them, so a type drift
# becomes a test failure rather than a silent frontend bug.

class CustomerRow(BaseModel):
    customer_id:    str
    name:           str
    plan_type:      str
    monthly_charge: int
    tenure_months:  int
    scored:         bool
    churn_prob:     Optional[float]
    churn_percent:  str
    risk_level:     str
    clv_score:      Optional[float]
    clv_segment:    str
    top_reason_1:   str
    device_type:    str
    watch_hours:    float


class CustomersSummary(BaseModel):
    total_customers:           int
    high_risk_count:           int
    medium_risk_count:         int
    low_risk_count:            int
    unscored_count:            int
    scored_customers:          int
    avg_churn_probability:     Optional[float]
    avg_churn_percent:         str
    revenue_at_risk_monthly:   float
    revenue_at_risk_formatted: str


class CustomersResponse(BaseModel):
    summary:         CustomersSummary
    customers:       List[CustomerRow]
    count:           int
    filters_applied: Dict[str, Optional[str]]


class ClvBreakdown(BaseModel):
    monthly_charge:   int
    tenure_months:    int
    retention_factor: Optional[float]
    formula:          str


class CustomerDetailResponse(BaseModel):
    scored:               bool
    prediction_source:    Optional[str]
    customer_id:          str
    name:                 str
    age:                  int
    gender:               str
    country:              str
    plan_type:            str
    monthly_charge:       int
    tenure_months:        int
    tenure_display:       str
    watch_hours_per_week: float
    logins_last_30_days:  int
    last_login_days_ago:  int
    payment_failures_3m:  int
    support_tickets:      int
    num_profiles:         int
    device_type:          str
    payment_method:       str
    preferred_genre:      str
    churn_prob:           Optional[float]
    churn_percent:        str
    risk_level:           str
    top_reason_1:         str
    top_reason_2:         str
    top_reason_3:         str
    clv_score:            Optional[float]
    clv_segment:          str
    clv_formatted:        str
    clv_breakdown:        ClvBreakdown


class RetentionResponse(BaseModel):
    """GET /retention/{id}. `ai_generated` is True only for genuine Gemini output."""
    customer_id:     str
    name:            str
    churn_prob:      float           # 0-1, like every other endpoint (was 0-100)
    churn_percent:   str             # e.g. "87.3%"
    risk_level:      str
    generated_by:    str             # GEMINI_MODEL_NAME or "rule-based-fallback"
    ai_generated:    bool
    fallback_reason: Optional[str]   # null when ai_generated is True
    subject:         str
    email:           str
    actions:         List[str]
    priority:        str
    suggested_offer: str
    top_reasons:     List[str]
    clv_score:       float


class SendEmailResponse(BaseModel):
    success:     bool
    message:     str
    customer_id: str
    customer:    str
    subject:     str
    sent_to:     str


class EmailStatusResponse(BaseModel):
    email_enabled:   bool
    sender:          str
    demo_receiver:   str
    message:         str
    auth_configured: bool   # CHURN-44: is EMAIL_API_TOKEN set? (never the token itself)
    rate_limit:      str    # CHURN-44: e.g. "5 requests per 600 seconds per client"


class DashboardKpis(BaseModel):
    total_customers:           int
    high_risk_count:           int
    medium_risk_count:         int
    low_risk_count:            int
    unscored_count:            int
    scored_customers:          int
    high_risk_pct:             float
    avg_churn_probability:     Optional[float]
    avg_churn_percent:         str
    revenue_at_risk_monthly:   float
    revenue_at_risk_formatted: str
    high_value_at_risk:        int


class PriorityCustomer(BaseModel):
    customer_id: str
    name:        str
    churn_prob:  float
    churn_pct:   str
    clv_score:   float
    plan_type:   str
    risk_level:  str


class DashboardResponse(BaseModel):
    kpis:                    DashboardKpis
    churn_reasons_breakdown: Dict[str, int]
    priority_customers:      List[PriorityCustomer]


class SegmentsOverall(BaseModel):
    total_customers:       int
    scored_customers:      int
    unscored_count:        int
    avg_churn_rate_pct:    Optional[float]
    total_revenue_at_risk: float


class SegmentsResponse(BaseModel):
    by_plan:       List[Dict[str, Any]]
    by_device:     List[Dict[str, Any]]
    by_tenure:     List[Dict[str, Any]]
    by_genre:      List[Dict[str, Any]]
    by_clv:        List[Dict[str, Any]]
    monthly_trend: List[Dict[str, Any]]
    overall:       SegmentsOverall


class HealthResponse(BaseModel):
    status:             str
    version:            str
    model_loaded:       bool
    fold_models_loaded: bool
    similarity_ready:   bool
    total_customers:    int
    high_risk_count:    int
    gemini_enabled:     bool
    email_enabled:      bool
    endpoints:          Dict[str, str]


# =============================================================================
#   PART B — HELPER FUNCTIONS
# =============================================================================

def get_risk_level(prob: float) -> str:
    """
    Convert churn probability to risk label.
    Thresholds:
      HIGH   (≥70%): Immediate action required
      MEDIUM (40-70%): Monitor and prepare retention
      LOW    (<40%):  Healthy customer
    Implemented in churniq_core so the pipeline and API share thresholds.
    """
    return churniq_core.get_risk_level(prob)


def calc_clv(monthly_charge: float, tenure: int, churn_prob: float):
    """
    Customer Lifetime Value = monthly_charge × max(tenure, 6) × (1 − churn_probability)
    Returns None when an input is missing; raises ValueError on invalid input.
    Implemented in churniq_core (shared with the ML pipeline).
    """
    return churniq_core.calc_clv(monthly_charge, tenure, churn_prob)


def get_clv_segment(clv: float) -> str:
    """Segment customers by CLV: High (>8000) / Medium (>3000) / Low; Unknown if missing."""
    return churniq_core.get_clv_segment(clv)


def reason_feature_value(customer_id: str, reason_str: str):
    """Look up the customer's actual model-feature value for a raw SHAP reason string."""
    if not isinstance(reason_str, str) or '(impact' not in reason_str:
        return None
    feature = reason_str.split(' (impact')[0].strip()
    if customer_id not in FEATURE_MATRIX.index or feature not in FEATURE_MATRIX.columns:
        return None
    return FEATURE_MATRIX.at[customer_id, feature]


def explain_reason(customer_id: str, reason_str) -> str:
    """format_reason() using the customer's real feature value (CHURN-15)."""
    reason_str = str(reason_str)
    return format_reason(reason_str, reason_feature_value(customer_id, reason_str))


def format_reason(reason_str: str, value=None) -> str:
    """
    Convert raw SHAP feature string to plain-English business language.

    Input:  'friction_score (impact: +2.17)'
    Output: 'High friction score — payment failures + support issues [SHAP: +2.17]'

    WHY THIS MATTERS: Business teams cannot act on "friction_score = 7".
    They CAN act on "Customer has had 7 combined payment failures and support tickets."
    This translation is what makes ChurnIQ Pro actionable.
    """
    if not isinstance(reason_str, str) or reason_str in ('N/A', '', 'nan'):
        return "No significant risk factor identified"

    # Map feature names to plain English descriptions
    plain_map = {
        'friction_score':           'High friction score — payment failures + support issues',
        'watch_hours_per_week':     'Very low content engagement — watching very few hours',
        'tenure_months':            'Short subscription tenure — still in high-risk early phase',
        'is_new_customer':          'New customer — within the high-churn 0-6 month window',
        'engagement_score':         'Low overall engagement score (watch hours × login frequency)',
        'logins_last_30_days':      'Infrequent logins — rarely opening the app',
        'last_login_days_ago':      'Has not logged in recently — going inactive',
        'payment_failures_3m':      'Recent payment failures — billing friction',
        'support_tickets':          'Multiple support tickets — experiencing service issues',
        'inactivity_flag':          'Customer has gone inactive — 14+ days without login',
        'monthly_charge':           'High monthly charge relative to engagement level',
        'num_profiles':             'Low profile usage — subscription underutilized',
        'age':                      'Age demographic associated with higher churn risk',
    }

    # Extract feature name (before ' (impact:')
    feature     = reason_str.split(' (impact')[0].strip()
    impact_part = ''
    if '(impact:' in reason_str:
        impact_part = ' [SHAP: ' + reason_str.split('(impact:')[1].replace(')', '').strip() + ']'

    # CHURN-15: when the customer's actual value is known, use a description
    # that is true for that value. The static plain_map above made claims
    # such as "Short subscription tenure" for 24-month customers or
    # "Low profile usage" for customers with 2-5 profiles.
    described = churniq_core.describe_reason(feature, value) if value is not None else None
    plain = described or plain_map.get(feature, feature.replace('_', ' ').title())
    return f"{plain}{impact_part}"


def build_feature_row(customer_data: dict) -> pd.DataFrame:
    """
    Rebuild the exact feature vector the model needs for a new prediction.
    CRITICAL: Must apply the EXACT same transformations as the ML pipeline.
    Any difference = wrong predictions.

    Steps (shared with churniq_ml_pipeline.py via churniq_core.encode_features):
      1. Compute engineered features
      2. Label encode plan_type
      3. One-hot encode categorical columns against the TRAINING category levels
      4. Reindex to match training feature order (fill missing with 0)

    BUG FIXED (CHURN-13): this previously called pd.get_dummies(drop_first=True)
    on a single row, which dropped every customer's own category and left all
    19 one-hot columns at 0. A no-change /whatif call then moved churn
    probability by 0.157 on average and changed the risk tier for 327/1000
    test customers. See docs/ml/01-pipeline-review.md.

    Args:
        customer_data: dict of raw customer features (can include overrides)
    Returns:
        DataFrame with exactly FEATURE_NAMES columns in correct order
    """
    # Defaults for missing raw values (kept from the original implementation)
    defaults = {
        'watch_hours_per_week': 5.0, 'logins_last_30_days': 10,
        'payment_failures_3m': 0,   'support_tickets': 0,
        'tenure_months': 12,        'last_login_days_ago': 3,
        'plan_type': 'Basic',
    }
    row = dict(customer_data)
    for key, default in defaults.items():
        if key not in row or row[key] is None or (isinstance(row[key], float) and np.isnan(row[key])):
            row[key] = default
    # Unknown plan names fall back to Basic, as before
    if row['plan_type'] not in churniq_core.PLAN_ORDER:
        row['plan_type'] = 'Basic'

    return churniq_core.encode_features(pd.DataFrame([row]), FEATURE_NAMES)


def get_customer_row(customer_id) -> pd.Series:
    """
    The FULL_DF row for a customer ID, with uniform validation (CHURN-20):
      malformed ID → 422 validation_error, unknown ID → 404 not_found.
    Surrounding whitespace is ignored on every endpoint (previously only the
    similarity endpoint stripped it).
    """
    try:
        cid = normalize_customer_id(customer_id)
    except ValueError as e:
        raise APIError(422, 'validation_error', str(e))
    row = FULL_DF[FULL_DF['customer_id'] == cid]
    if row.empty:
        raise APIError(404, 'customer_not_found',
                       f"Customer '{cid}' not found. Total customers: {len(FULL_DF)}. "
                       f"Example valid ID: {FULL_DF['customer_id'].iloc[0]}")
    return row.iloc[0]


def not_scored_error(customer_id: str, what: str) -> APIError:
    """409 for customers with no out-of-sample prediction (Bug A / CHURN-37 behaviour)."""
    return APIError(409, 'customer_not_scored',
                    f"Customer '{customer_id}' has no out-of-sample churn prediction "
                    f"(not scored by the model), so {what}.")


def _mask_email(address: str) -> str:
    """'someone@gmail.com' → 's*****e@gmail.com' (the API is unauthenticated)."""
    if not address or '@' not in address:
        return 'not configured' if not address else '***'
    local, domain = address.split('@', 1)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


# =============================================================================
#   PART C — API ENDPOINTS
# =============================================================================
# CONCEPT: In REST APIs:
#   GET  → Read data (no side effects) — use for fetching information
#   POST → Send data to server for processing — use for simulations/calculations
#   PUT  → Update existing resource
#   DELETE → Remove resource
#
# URL path parameters: /customer/{customer_id}  → customer_id is a variable
# Query parameters:    /customers?risk_level=HIGH → filter param in URL
# Request body:        POST /whatif with JSON body → for complex input data
#
# HTTP Status Codes:
#   200 OK          → success
#   404 Not Found   → customer_id doesn't exist
#   422 Unprocessable → wrong data type in request
#   500 Server Error → something crashed server-side


# ── ENDPOINT 1: Health Check ─────────────────────────────────────────────────
# WHY NEEDED:
#   Deployment platforms (Render, Railway) ping this to check if server is alive
#   If this returns non-200, the platform restarts the server
#   Frontend can also call this to show "API Status: Connected ✓" indicator
@app.get("/", tags=["System"], response_model=HealthResponse)
def health_check():
    """
    Health check endpoint. Returns server status and basic stats.
    Used by deployment platforms to verify the server is alive.

    model_loaded is always true here: the server refuses to start without the
    production model (ArtifactLoadError). Optional components report their state.
    """
    high_risk = len(FULL_DF[FULL_DF['risk_level'] == 'HIGH'])
    return {
        "status":           "✓ ChurnIQ Pro API is running",
        "version":          "1.0.0",
        "model_loaded":     MODEL is not None,
        "fold_models_loaded": FOLD_MODELS is not None,
        "similarity_ready": SIMILARITY_ENGINE is not None,
        "total_customers":  len(FULL_DF),
        "high_risk_count":  high_risk,
        "gemini_enabled":   GEMINI_ENABLED,
        "email_enabled":    EMAIL_ENABLED,
        "endpoints": {
            "customers":        "GET  /customers",
            "customer_detail":  "GET  /customer/{id}",
            "what_if":          "POST /whatif",
            "customer_similarity": "POST /api/customer-similarity",
            "retention":        "GET  /retention/{id}",
            "segments":         "GET  /segments",
            "dashboard":        "GET  /dashboard/summary",
            "docs":             "GET  /docs",
        }
    }


# ── ENDPOINT 2: Customer Risk Table ──────────────────────────────────────────
# USED BY: Dashboard page (KPI cards) + Customer Risk Table page (the table)
#
# Query Parameters (all optional — for filtering/sorting):
#   risk_level → filter to HIGH / MEDIUM / LOW only
#   plan_type  → filter by Basic / Standard / Premium
#   limit      → max rows to return (default 500)
#   sort_by    → field to sort descending (default: churn_prob)
#
# Returns:
#   summary → KPI data for the 4 stat cards on dashboard
#   customers → list of customer objects for the table
#   count → how many records returned (for pagination UI)
@app.get("/customers", tags=["Customers"], response_model=CustomersResponse,
         responses={422: ERROR_RESPONSES[422]})
def get_customers(
    risk_level: Optional[str] = Query(None, description="Filter: HIGH, MEDIUM, LOW or NOT_SCORED (case-insensitive)"),
    plan_type:  Optional[str] = Query(None, description="Filter: Basic, Standard, or Premium (case-insensitive)"),
    limit:      int           = Query(500,  ge=1, le=MAX_CUSTOMERS_LIMIT,
                                      description=f"Max records to return (1-{MAX_CUSTOMERS_LIMIT})"),
    sort_by:    str           = Query("churn_prob",
                                      description="Field to sort by (descending): " + ", ".join(CUSTOMERS_SORT_FIELDS)),
):
    """
    Returns the full customer risk table with churn probabilities and risk levels.
    Also returns KPI summary data for the dashboard stat cards.

    Supports filtering by risk_level and plan_type.
    Default: all customers sorted by churn_prob descending (highest risk first).

    CHURN-20: unknown filter values and sort fields are rejected with 422
    (previously ignored silently, returning unfiltered data). Sorting is
    restricted to displayed fields — the generator's `churn_probability` and
    the ground-truth `churn` label can no longer be used to order customers.
    """
    df = FULL_DF.copy()

    # Apply filters
    if risk_level is not None:
        level = risk_level.strip().upper()
        if level not in ('HIGH', 'MEDIUM', 'LOW', NOT_SCORED):
            raise APIError(422, 'validation_error',
                           f"risk_level must be one of HIGH, MEDIUM, LOW, {NOT_SCORED}")
        df = df[df['risk_level'].isna()] if level == NOT_SCORED else df[df['risk_level'] == level]

    if plan_type is not None:
        plans = {p.lower(): p for p in churniq_core.PLAN_ORDER}
        plan = plans.get(plan_type.strip().lower())
        if plan is None:
            raise APIError(422, 'validation_error',
                           f"plan_type must be one of {', '.join(churniq_core.PLAN_ORDER)}")
        df = df[df['plan_type'] == plan]

    # Sort (descending) — highest churn risk first by default; unscored last
    if sort_by not in CUSTOMERS_SORT_FIELDS:
        raise APIError(422, 'validation_error',
                       f"sort_by must be one of {', '.join(CUSTOMERS_SORT_FIELDS)}")
    df = df.sort_values(sort_by, ascending=False, na_position='last', kind='stable')

    df = df.head(limit)

    # Build response — only return what frontend needs
    # CONCEPT: Don't send 33 columns when frontend uses 8
    # Smaller response = faster API = better UX
    customers = []
    for _, row in df.iterrows():
        churn_prob = model_prob(row)
        scored     = churn_prob is not None
        clv        = float(row['clv_score']) if scored else None
        customers.append({
            "customer_id":    str(row.get('customer_id', '')),
            "name":           str(row.get('name', '')),
            "plan_type":      str(row.get('plan_type', '')),
            "monthly_charge": int(row.get('monthly_charge', 0)),
            "tenure_months":  int(row.get('tenure_months', 0)),
            "scored":         scored,
            "churn_prob":     round(churn_prob, 4) if scored else None,
            "churn_percent":  f"{churn_prob * 100:.1f}%" if scored else NOT_SCORED_TEXT,
            "risk_level":     str(row['risk_level']) if scored else NOT_SCORED,
            "clv_score":      round(clv, 2) if scored else None,
            "clv_segment":    get_clv_segment(clv),
            "top_reason_1":   (explain_reason(str(row.get('customer_id', '')), row.get('top_reason_1', ''))
                               if scored else NOT_SCORED_REASON),
            "device_type":    str(row.get('device_type', '')),
            "watch_hours":    round(float(row.get('watch_hours_per_week', 0) or 0), 1),
        })

    # KPI Summary — always computed on FULL dataset (not filtered)
    all_df     = FULL_DF
    high_risk  = all_df[all_df['risk_level'] == 'HIGH']
    rev_risk   = (all_df['monthly_charge'] * all_df['churn_prob']).sum()

    avg_prob = _mean_or_none(all_df['churn_prob'])
    summary = {
        "total_customers":          int(len(all_df)),
        "high_risk_count":          int(len(high_risk)),
        "medium_risk_count":        int(len(all_df[all_df['risk_level'] == 'MEDIUM'])),
        "low_risk_count":           int(len(all_df[all_df['risk_level'] == 'LOW'])),
        # high + medium + low + unscored == total_customers
        "unscored_count":           UNSCORED_COUNT,
        "scored_customers":         SCORED_COUNT,
        "avg_churn_probability":    round(avg_prob, 4) if avg_prob is not None else None,  # scored only
        "avg_churn_percent":        f"{avg_prob * 100:.1f}%" if avg_prob is not None else NOT_SCORED_TEXT,
        "revenue_at_risk_monthly":  round(float(rev_risk), 2),                      # scored only
        "revenue_at_risk_formatted": f"₹{float(rev_risk):,.0f}",
    }

    return {
        "summary":   summary,
        "customers": customers,
        "count":     len(customers),
        "filters_applied": {
            "risk_level": risk_level,
            "plan_type":  plan_type,
        }
    }


# ── ENDPOINT 3: Customer Detail ───────────────────────────────────────────────
# USED BY: Customer Detail page (when user clicks a row in Risk Table)
#
# Returns EVERYTHING about one customer:
#   - Full profile (plan, tenure, behavior)
#   - Churn probability + risk level
#   - Top 3 SHAP reasons (plain English)
#   - CLV score + breakdown
#   - Default values for what-if simulator sliders
@app.get("/customer/{customer_id}", tags=["Customers"], response_model=CustomerDetailResponse,
         responses={404: ERROR_RESPONSES[404], 422: ERROR_RESPONSES[422]})
def get_customer_detail(customer_id: str = Path(..., max_length=64, description=CUSTOMER_ID_RULE)):
    """
    Returns complete detail for a single customer.
    Used on the Customer Detail page to populate:
      - Customer profile card
      - Churn probability gauge
      - SHAP reasons cards
      - CLV score
      - What-if simulator slider default values
    """
    # HTTP 404 = Resource Not Found — standard REST convention
    # Never return a 200 with empty data for not-found (anti-pattern)
    row        = get_customer_row(customer_id)
    cid        = str(row['customer_id'])
    # Bug A: unscored customers are reported as NOT_SCORED, never as 0 % / ₹0.
    # Bug B: the CUST99999 hard-coded override (churn 0.96, CLV ₹500) was
    # removed; demo customers are scored by the model at startup.
    churn_prob = model_prob(row)
    scored     = churn_prob is not None
    clv        = float(row['clv_score']) if scored else None

    def reason(k):
        return explain_reason(cid, row.get(f'top_reason_{k}', '')) if scored else NOT_SCORED_REASON

    return {
        "scored":            scored,
        "prediction_source": str(row['prediction_source']) if scored else None,
        # ── Identity ────────────────────────────────
        "customer_id":    str(row['customer_id']),
        "name":           str(row.get('name', '')),
        "age":            int(row.get('age', 0)),
        "gender":         str(row.get('gender', '')),
        "country":        str(row.get('country', '')),

        # ── Subscription ────────────────────────────
        "plan_type":       str(row.get('plan_type', '')),
        "monthly_charge":  int(row.get('monthly_charge', 0)),
        "tenure_months":   int(row.get('tenure_months', 0)),
        "tenure_display":  f"{int(row.get('tenure_months', 0))} months",

        # ── Behavior (also used as slider defaults in what-if) ───────
        "watch_hours_per_week":  round(float(row.get('watch_hours_per_week', 0) or 0), 1),
        "logins_last_30_days":   int(row.get('logins_last_30_days', 0)),
        "last_login_days_ago":   int(row.get('last_login_days_ago', 0)),
        "payment_failures_3m":   int(row.get('payment_failures_3m', 0)),
        "support_tickets":       int(row.get('support_tickets', 0)),
        "num_profiles":          int(row.get('num_profiles', 1)),
        "device_type":           str(row.get('device_type', '')),
        "payment_method":        str(row.get('payment_method', '')),
        "preferred_genre":       str(row.get('preferred_genre', '')),

        # ── ML Predictions ──────────────────────────
        "churn_prob":     round(churn_prob, 4) if scored else None,
        "churn_percent":  f"{churn_prob * 100:.1f}%" if scored else NOT_SCORED_TEXT,
        "risk_level":     get_risk_level(churn_prob) if scored else NOT_SCORED,

        # ── SHAP Reasons (plain English) ─────────────
        # These are pre-computed by the ML pipeline
        # On the frontend: display as colored reason cards
        # In the Gemini prompt: sent as context for email generation
        "top_reason_1":   reason(1),
        "top_reason_2":   reason(2),
        "top_reason_3":   reason(3),

        # ── CLV ──────────────────────────────────────
        # Shows business team HOW MUCH this customer is worth
        # Helps prioritize: High CLV + High Risk = act immediately
        "clv_score":    round(clv, 2) if scored else None,
        "clv_segment":  get_clv_segment(clv),
        "clv_formatted": f"₹{clv:,.0f}" if scored else 'N/A',
        "clv_breakdown": {
            "monthly_charge":   int(row.get('monthly_charge', 0)),
            "tenure_months":    int(row.get('tenure_months', 0)),
            "retention_factor": round(1 - churn_prob, 4) if scored else None,
            "formula":          "monthly_charge × max(tenure, 6) × (1 − churn_probability)",
        },
    }


# ── ENDPOINT 4: What-If Simulator ─────────────────────────────────────────────
# USED BY: What-If Simulator sliders on Customer Detail page
#
# HOW IT WORKS:
#   1. User moves a slider (e.g., payment_failures: 3 → 0)
#   2. React sends POST request with customer_id + new feature values
#   3. FastAPI loads customer's original data
#   4. Overrides only the changed values
#   5. Rebuilds the full feature vector (encoding + engineering)
#   6. Calls MODEL.predict_proba() → gets new churn probability
#   7. Returns before/after comparison
#
# WHY THIS IS POWERFUL:
#   This is LIVE model inference — the actual ML model running in real-time!
#   Business team can ask: "If we fix this customer's payment issues,
#   how much does their churn risk drop?"
#   And get a precise, model-backed answer instantly.
#
# VIVA TIP:
#   "The what-if simulator demonstrates counterfactual analysis —
#    changing one input to see its causal impact on the prediction.
#    This is implemented as a live inference call to the loaded
#    XGBoost model with modified feature values."
@app.post("/whatif", response_model=WhatIfResponse, tags=["Simulation"],
          responses={**ERROR_RESPONSES, 409: {"model": ErrorResponse,
                     "description": "Customer not scored, or its fold model is unavailable"}})
def what_if_simulation(request: WhatIfRequest):
    """
    Recalculates churn probability with modified feature values.
    Powers the interactive sliders on the Customer Detail page.

    Send only the fields you want to change — the rest stay at the customer's actual values.

    Example: Set payment_failures_3m=0 to see how fixing billing issues affects churn risk.
    """
    # Get original customer data (404 unknown / 422 malformed)
    row = get_customer_row(request.customer_id)

    original_prob = model_prob(row)
    if original_prob is None:
        # Bug A: previously NaN → HTTP 500. There is no out-of-sample baseline
        # prediction to compare against, so the what-if comparison is unavailable.
        raise not_scored_error(request.customer_id, "a what-if comparison is unavailable")
    scoring_model = model_for(row)
    if scoring_model is None:
        raise APIError(
            409, 'fold_model_unavailable',
            f"Customer '{request.customer_id}' was scored out-of-fold, but the fold "
            f"models (oof_fold_models.pkl) are not available, so a consistent "
            f"what-if comparison cannot be made."
        )
    customer_data = row.to_dict()

    # Apply overrides — only change what was explicitly sent
    # CONCEPT: If frontend sends None for a field, we keep original value
    # This lets the user change just ONE slider without resetting others
    override_map = {
        'watch_hours_per_week': request.watch_hours_per_week,
        'tenure_months':        request.tenure_months,
        'payment_failures_3m':  request.payment_failures_3m,
        'support_tickets':      request.support_tickets,
        'logins_last_30_days':  request.logins_last_30_days,
        'monthly_charge':       request.monthly_charge,
    }
    for field, value in override_map.items():
        if value is not None:
            customer_data[field] = value

    # Rebuild feature vector and run prediction
    try:
        feature_df = build_feature_row(customer_data)
        # predict_proba returns shape (1, 2) → [[prob_class_0, prob_class_1]]
        # prob_class_1 = probability of churning
        # CHURN-37: use the model that produced the displayed probability
        # (fold model for out-of-fold customers, production MODEL otherwise)
        new_prob = float(scoring_model.predict_proba(feature_df)[0][1])
        if not np.isfinite(new_prob):
            raise ValueError(f"model returned a non-finite probability ({new_prob})")
    except Exception as e:
        # CHURN-21: details go to the server log, not to the client.
        log_exception(e, "What-if prediction failed for %s: %s", request.customer_id, redact(e))
        raise APIError(500, 'prediction_failed',
                       "The what-if prediction could not be computed. The error has been logged.")

    change = round(new_prob - original_prob, 4) + 0.0   # + 0.0 turns -0.0 into 0.0

    return WhatIfResponse(
        customer_id=         request.customer_id,
        original_churn_prob= round(original_prob, 4),
        new_churn_prob=      round(new_prob, 4),
        change=              change,
        change_percent=      f"{change * 100:+.1f}%",
        original_risk=       get_risk_level(original_prob),
        new_risk=            get_risk_level(new_prob),
        improved=            change < 0,
    )


# ── ENDPOINT 4B: Customer Similarity Finder (KNN) ─────────────────────────────
_SIMILARITY_RESPONSES = {**ERROR_RESPONSES, 503: {"model": ErrorResponse,
                         "description": "Similarity engine unavailable"}}


@app.post("/api/customer-similarity", response_model=CustomerSimilarityResponse, tags=["Customer Similarity"],
          responses=_SIMILARITY_RESPONSES)
@app.post("/customer-similarity", response_model=CustomerSimilarityResponse, tags=["Customer Similarity"],
          responses=_SIMILARITY_RESPONSES)
def get_customer_similarity(request: CustomerSimilarityRequest):
    """
    Finds the N most similar historical customers using K-Nearest Neighbors (KNN).

    - Computes geometric similarity across behavioral, engagement, and subscription features.
    - Excludes the selected customer's own record from the returned neighbor list.
    - Preserves ground-truth historical churn outcomes from the dataset.
    - Returns distance-derived similarity percentages and factual lookalike insights.
    - n_neighbors must be 1-50 (default 5); neighbours are ordered closest first.
    """
    cid = request.customer_id                    # already stripped + format-checked
    n_k = request.n_neighbors if request.n_neighbors is not None else 5

    if cid not in FULL_DF["customer_id"].values:
        raise APIError(
            404, 'customer_not_found',
            f"Customer '{cid}' not found. Please provide a valid customer ID (e.g., CUST00001)."
        )
    if SIMILARITY_ENGINE is None:
        raise APIError(503, 'similarity_unavailable',
                       "The customer similarity engine is not available on this server. "
                       "Check the server log and the similarity_*.joblib artifacts.")

    try:
        results = SIMILARITY_ENGINE.find_similar_customers(
            customer_id=cid,
            n_neighbors=n_k,
            full_df=FULL_DF,
            xgboost_model=MODEL,
            feature_names=FEATURE_NAMES,
            build_feature_row_fn=build_feature_row,
        )
        return results
    except KeyError:
        # The ID is in FULL_DF but not in the fitted engine (stale artifacts).
        logger.warning("Similarity engine has no record for %s (stale artifacts?)", cid)
        raise APIError(404, 'customer_not_found',
                       f"Customer '{cid}' is not indexed by the similarity engine.")
    except ValueError as ve:
        logger.error("Similarity engine rejected request for %s: %s", cid, ve)
        raise APIError(503, 'similarity_unavailable',
                       "The customer similarity engine is not ready. The error has been logged.")
    except Exception as e:
        log_exception(e, "Similarity calculation failed for %s: %s", cid, redact(e))
        raise APIError(500, 'similarity_failed',
                       "Similarity calculation failed. The error has been logged.")


# ── ENDPOINT 5: Gemini Retention Email ────────────────────────────────────────
# USED BY: Retention Email Card on Customer Detail page (Generate button)
#
# THIS IS THE AI LAYER OF CHURNIQ PRO:
#   Traditional system: if risk > 70%: send_generic_email()
#   ChurnIQ Pro:        SHAP reasons → Gemini prompt → personalized email
#                       that specifically addresses THIS customer's issues
#
# THE GEMINI PROMPT IS CAREFULLY ENGINEERED:
#   1. Role: "You are a retention specialist..."
#   2. Context: Customer profile + SHAP churn reasons
#   3. Task: Write email + 2 actions
#   4. Format: "Respond in JSON only" → easy to parse
#
# ALWAYS HAS A FALLBACK:
#   If Gemini is unavailable or returns malformed JSON,
#   a rule-based fallback generates context-aware responses.
#   "Graceful degradation" = fail softly, never show error to user.
#
# VIVA TIP:
#   "We use prompt engineering to translate SHAP's technical output into
#    a business action. The prompt includes the top 3 SHAP-identified
#    churn drivers with their impact scores, enabling Gemini to write
#    emails that address specific pain points rather than generic offers."
GEMINI_FALLBACK_REASONS = {
    'gemini_not_configured':   'GEMINI_API_KEY is not set, so no AI generation was attempted.',
    'gemini_timeout':          'The Gemini call exceeded the time limit.',
    'gemini_api_error':        'The Gemini API returned an error.',
    'gemini_invalid_response': 'Gemini returned a response that was not the expected JSON.',
}


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__
    return isinstance(exc, TimeoutError) or 'Timeout' in name or 'DeadlineExceeded' in name


def _parse_gemini_json(text: str) -> dict:
    """Strip optional markdown fences and validate Gemini's JSON (ValueError if unusable)."""
    # Even when told "no markdown fences", LLMs sometimes add them
    text = re.sub(r'^```json\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'^```\s*',     '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$',     '', text).strip()
    data = json.loads(text)                     # JSONDecodeError is a ValueError
    if not isinstance(data, dict):
        raise ValueError('Gemini JSON is not an object')
    for key in ('subject', 'email'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Gemini JSON has no usable '{key}'")
    actions = data.get('actions')
    if (not isinstance(actions, list) or not actions
            or not all(isinstance(a, str) and a.strip() for a in actions)):
        raise ValueError("Gemini JSON has no usable 'actions' list")
    return data


def call_gemini(prompt: str, customer_id: str):
    """
    One Gemini call with a timeout. Returns (data, None) on success or
    (None, fallback_reason) on any failure — it never raises, never logs the
    API key (messages pass through redact()) and never logs the prompt.
    """
    if not GEMINI_ENABLED or GEMINI_MODEL is None:
        return None, 'gemini_not_configured'
    try:
        response = GEMINI_MODEL.generate_content(
            prompt, request_options={"timeout": GEMINI_TIMEOUT_SECONDS})
        return _parse_gemini_json(response.text), None
    except ValueError as e:
        # Malformed / incomplete JSON, or response.text unavailable (e.g. blocked)
        logger.warning("Gemini invalid response for %s: %s", customer_id, redact(e))
        return None, 'gemini_invalid_response'
    except Exception as e:
        if _is_timeout(e):
            logger.warning("Gemini timeout (%.0fs) for %s", GEMINI_TIMEOUT_SECONDS, customer_id)
            return None, 'gemini_timeout'
        # Gemini API error (quota exceeded, network issue, invalid key, etc.)
        logger.warning("Gemini API error for %s: %s: %s", customer_id, type(e).__name__, redact(e))
        return None, 'gemini_api_error'


@app.get("/retention/{customer_id}", tags=["AI Retention"], response_model=RetentionResponse,
         responses={**ERROR_RESPONSES, 409: {"model": ErrorResponse,
                    "description": "Customer not scored by the model"}})
def get_retention_strategy(customer_id: str = Path(..., max_length=64, description=CUSTOMER_ID_RULE)):
    """
    Generates a personalized retention email and recommended actions
    using Google Gemini AI, based on the customer's SHAP churn reasons.

    Returns: subject line, email body, 2 business actions, priority level,
             and the top churn reasons that informed the email.

    Falls back to rule-based generation if Gemini is unavailable, times out,
    errors or returns unusable output. Fallback content is always labelled:
    generated_by="rule-based-fallback", ai_generated=false and a
    fallback_reason code (CHURN-22).
    """
    row = get_customer_row(customer_id)
    customer_id = str(row['customer_id'])
    prob = model_prob(row)
    if prob is None:
        # Bug A: previously NaN → HTTP 500. Without a model prediction there are
        # no SHAP churn reasons to base a retention strategy on.
        raise not_scored_error(customer_id, "no SHAP-based retention strategy can be generated")

    # Extract customer context for prompt
    raw_name    = row.get('name')
    raw_name    = str(raw_name).strip() if isinstance(raw_name, str) and raw_name.strip() else 'Valued Customer'
    name        = raw_name.split()[0]   # First name only
    plan        = str(row.get('plan_type', 'Basic'))
    charge      = int(row.get('monthly_charge', 199))
    tenure      = int(row.get('tenure_months', 1))
    watch_hrs   = round(float(row.get('watch_hours_per_week', 0) or 0), 1)
    pay_fail    = int(row.get('payment_failures_3m', 0))
    support     = int(row.get('support_tickets', 0))
    churn_pct   = round(prob * 100, 1)
    risk        = get_risk_level(prob)
    clv         = round(float(row.get('clv_score', 0) or 0), 0)
    common      = {
        "customer_id":   customer_id,
        "name":          name,
        # CHURN-19: 0-1 like every other endpoint (was a 0-100 percentage)
        "churn_prob":    round(prob, 4),
        "churn_percent": f"{prob * 100:.1f}%",
        "risk_level":    risk,
        "clv_score":     clv,
    }
    reason1     = explain_reason(customer_id, row.get('top_reason_1', ''))
    reason2     = explain_reason(customer_id, row.get('top_reason_2', ''))
    reason3     = explain_reason(customer_id, row.get('top_reason_3', ''))
    

    # ── Build Gemini Prompt ─────────────────────────────────────────────────
    # PROMPT ENGINEERING PRINCIPLES USED HERE:
    #   1. Role assignment: "You are a retention specialist" → sets context/tone
    #   2. Structured input: clear sections with labels → easier for model to parse
    #   3. Constrained output: "max 100 words", "exactly 2 actions" → prevents rambling
    #   4. JSON format requirement: "no extra text" → parseable by our code
    #   5. CLV context: model can calibrate offer value based on customer worth
    prompt = f"""You are a customer retention specialist for a Netflix-style OTT streaming platform.

CUSTOMER PROFILE:
- First Name: {name}
- Plan: {plan} (₹{charge}/month)
- Subscription Tenure: {tenure} months
- Weekly Watch Hours: {watch_hrs} hrs
- Payment Failures (last 3 months): {pay_fail}
- Support Tickets Raised: {support}
- Churn Risk Score: {churn_pct}%
- Customer Lifetime Value: ₹{clv:,.0f}

TOP CHURN REASONS (identified by our ML model using SHAP analysis):
1. {reason1}
2. {reason2}
3. {reason3}

YOUR TASKS:
1. Write a SHORT, warm, personalized retention email (80-100 words max).
   - Address the customer by first name: {name}
   - Naturally reference their specific issues from the churn reasons
   - Offer a concrete incentive appropriate for their plan (₹{charge}/month)
   - Keep it conversational, NOT corporate/robotic
   - Subject line must be compelling and personal

2. List exactly 2 specific, actionable recommendations for the business team.
   - Be concrete: who does what, when, and how
   - Consider CLV: ₹{clv:,.0f} CLV {'is HIGH — worth significant retention investment' if clv > 5000 else 'is moderate — standard retention offer appropriate'}
   - Each action in 1-2 sentences

RESPOND IN THIS EXACT JSON FORMAT (no extra text before or after, no markdown fences):
{{
  "subject": "email subject line here",
  "email": "full email body here with greeting and sign-off",
  "actions": [
    "First specific business action with who/what/when",
    "Second specific business action with who/what/when"
  ],
  "priority": "HIGH or MEDIUM or LOW",
  "suggested_offer": "one-line description of the best retention offer for this specific customer"
}}"""

    # ── Call Gemini API ─────────────────────────────────────────────────────
    # Never raises; on any failure returns a fallback_reason and we fall
    # through to the rule-based fallback below.
    gemini_data, fallback_reason = call_gemini(prompt, customer_id)
    if gemini_data is not None:
        priority = str(gemini_data.get("priority", "")).strip().upper()
        return {
            **common,
            "generated_by":    GEMINI_MODEL_NAME,   # the configured model that produced it
            "ai_generated":    True,
            "fallback_reason": None,
            "subject":         gemini_data["subject"].strip(),
            "email":           gemini_data["email"].strip(),
            "actions":         [a.strip() for a in gemini_data["actions"]],
            "priority":        priority if priority in ('HIGH', 'MEDIUM', 'LOW') else risk,
            "suggested_offer": str(gemini_data.get("suggested_offer") or ""),
            "top_reasons":     [reason1, reason2, reason3],
        }

    # ── Rule-Based Fallback ─────────────────────────────────────────────────
    # CONCEPT: Graceful degradation — system still works without Gemini.
    # We analyze the primary churn reason and generate a targeted response.
    # Not as good as Gemini but far better than an error message.

    raw_r1 = str(row.get('top_reason_1', ''))

    # Determine response based on primary churn driver
    if 'friction' in raw_r1 or 'payment' in raw_r1:
        offer    = "1-month free subscription + payment assistance"
        action1  = (f"Contact {name} within 24 hours to resolve payment issue — "
                    f"offer to update billing method and waive the late charge.")
        action2  = ("Enable auto-retry with 3-day SMS reminder — "
                    "set up payment failure early-warning alert for this account.")
        body     = (f"Hi {name},\n\nWe noticed you've had some billing hiccups recently "
                    f"and we want to make it right. As a valued {plan} subscriber, "
                    f"we'd like to offer you 1 month free while we help sort out your "
                    f"payment setup. Our team is here to help — just reply to this email.\n\n"
                    f"Best regards,\nThe ChurnIQ Team")
        subject  = f"Let's fix this for you, {name} — 1 month on us"

    elif 'watch' in raw_r1 or 'engagement' in raw_r1:
        offer    = "free Premium upgrade for 30 days + curated content recommendations"
        action1  = (f"Send {name} a personalized content digest this week based on "
                    f"their '{row.get('preferred_genre', 'favourite')}' genre preference.")
        action2  = ("Trigger in-app push notification: 'New releases in your favourite "
                    "genre this week' — set for Tuesday 8PM when engagement is highest.")
        body     = (f"Hi {name},\n\nWe've curated a list of shows we think you'll love — "
                    f"specially picked based on what you enjoy. To make it even better, "
                    f"we're upgrading you to Premium free for 30 days. "
                    f"Dive in and let us know what you think!\n\n"
                    f"Best regards,\nThe ChurnIQ Team")
        subject  = f"We picked these just for you, {name} 🎬"

    elif 'tenure' in raw_r1 or 'new' in raw_r1.lower():
        offer    = "20% loyalty discount for next 3 months"
        action1  = (f"Assign {name} to the onboarding success team — "
                    f"schedule a 10-minute welcome call this week.")
        action2  = ("Send 'Getting Started' email series: Day 1 — top features, "
                    "Day 3 — content highlights, Day 7 — profile setup tips.")
        body     = (f"Hi {name},\n\nWelcome to the family! We want to make sure "
                    f"your first months with us are amazing. We're giving you 20% off "
                    f"your next 3 months as our way of saying thank you for joining. "
                    f"We'd love to hear what you think — reach out anytime.\n\n"
                    f"Best regards,\nThe ChurnIQ Team")
        subject  = f"A special welcome gift for you, {name}"

    else:
        offer    = "exclusive loyalty reward for valued subscribers"
        action1  = (f"Send {name} a personalized thank-you message acknowledging "
                    f"their {tenure}-month loyalty — include exclusive early access.")
        action2  = ("Offer a 2-month plan upgrade as a loyalty reward — "
                    "high-CLV customers respond well to recognition over discounts.")
        body     = (f"Hi {name},\n\nAs one of our valued subscribers, we just wanted "
                    f"to reach out and say thank you. You've been with us for "
                    f"{tenure} months and we truly appreciate it. "
                    f"As a token of thanks, we have a special offer waiting for you.\n\n"
                    f"Best regards,\nThe ChurnIQ Team")
        subject  = f"Thank you for being with us, {name}"

    return {
        **common,
        "generated_by":    "rule-based-fallback",
        "ai_generated":    False,
        "fallback_reason": fallback_reason,
        "subject":         subject,
        "email":           body,
        "actions":         [action1, action2],
        # Matches the risk tier (LOW-risk customers were labelled MEDIUM before)
        "priority":        risk,
        "suggested_offer": offer,
        "top_reasons":     [reason1, reason2, reason3],
    }
# ─────────────────────────────────────────────────────────────
# PART 2 — Yeh endpoint main.py mein add karo
#           (/retention endpoint ke BAAD)
# ─────────────────────────────────────────────────────────────
 
class SendEmailRequest(_CustomerIdModel):
    """Request body for POST /send-email.

    CHURN-20: subject 1-200 chars on a single line (CR/LF would allow e-mail
    header injection); body 1-5000 chars. Unknown fields are rejected.
    """
    model_config = ConfigDict(extra='forbid')

    customer_id: str                                                   # Customer jiske liye email generate hui
    subject:     Annotated[str, Field(min_length=1, max_length=200)]   # Gemini generated subject line
    body:        Annotated[str, Field(min_length=1, max_length=5000)]  # Gemini generated email body

    @field_validator('subject')
    @classmethod
    def _single_line_subject(cls, v):
        # CHURN-44: every line break (CR, LF, VT, FF, NEL, U+2028/9 …) and
        # control character is rejected, not only CR/LF.
        if esec.has_line_break_or_control(v):
            raise ValueError('subject must be a single line (no CR/LF or control characters)')
        if not v.strip():
            raise ValueError('subject must not be blank')
        return v.strip()

    @field_validator('body')
    @classmethod
    def _non_blank_body(cls, v):
        if esec.has_line_break_or_control(v, allow='\n\r\t\u2028\u2029'):
            raise ValueError('body must not contain control characters')
        if not v.strip():
            raise ValueError('body must not be blank')
        return v


_email_bearer = HTTPBearer(auto_error=False, scheme_name='EmailApiToken',
                          description='EMAIL_API_TOKEN (CHURN-44)')


def require_email_token(http_request: Request,
                        _creds: Optional[HTTPAuthorizationCredentials] = Security(_email_bearer)):
    """Defence in depth behind email_endpoint_gate; also shows the lock in /docs."""
    if esec.check_bearer_token(http_request.headers.get('authorization'), EMAIL_API_TOKEN) != 'ok':
        raise APIError(401, 'unauthorized', EMAIL_UNAUTHORIZED_MESSAGE)


@app.post("/send-email", tags=["AI Retention"], response_model=SendEmailResponse,
          responses={**ERROR_RESPONSES,
                     401: {"model": ErrorResponse, "description": "Missing, malformed or invalid API token"},
                     429: {"model": ErrorResponse, "description": "Email rate limit exceeded"},
                     502: {"model": ErrorResponse, "description": "SMTP delivery failed"},
                     503: {"model": ErrorResponse, "description": "Email sending not configured"}})
def send_retention_email(request: SendEmailRequest,
                         _auth: None = Depends(require_email_token)):
    """
    Sends Gemini-generated retention email via Gmail SMTP.
 
    DEMO MODE:
      Always sends to DEMO_RECEIVER (your own Gmail).
      This proves the email pipeline works end-to-end.
 
    PRODUCTION:
      Replace DEMO_RECEIVER with customer's actual email
      from the dataset.
 
    HOW GMAIL SMTP WORKS:
      1. Connect to Gmail's SMTP server (smtp.gmail.com port 465)
      2. Authenticate with App Password (not your Gmail password)
      3. Send the email as a MIME message
      4. Server delivers it to inbox
 
    VIVA TIP:
      "We use Gmail SMTP with App Password authentication.
       In production, this would be replaced with a transactional
       email service like SendGrid for bulk sending and analytics."
    """
    # Check email is configured
    if not EMAIL_ENABLED:
        raise APIError(
            503, 'email_not_configured',
            "Email sending not configured. "
            "Run add_emails.py first to set up Gmail credentials."
        )

    # CHURN-44: the recipient is never taken from the request (no open relay);
    # the configured addresses are checked before they go into a header.
    if not (esec.is_valid_address(GMAIL_SENDER) and esec.is_valid_address(DEMO_RECEIVER)):
        logger.error("Email misconfigured: GMAIL_SENDER or DEMO_RECEIVER is not a valid address")
        raise APIError(
            503, 'email_misconfigured',
            "Email sending is misconfigured on the server (invalid sender or demo "
            "recipient address). The error has been logged."
        )

    # Get customer details for email header (404 unknown / 422 malformed)
    r          = get_customer_row(request.customer_id)
    cust_name  = str(r.get('name', 'Unknown'))
    plan       = str(r.get('plan_type', ''))
    _p         = model_prob(r)
    # Unscored customers: 'N/A', never a fabricated 0 % / ₹0 (Bug A)
    churn_txt  = f"{round(_p * 100, 1)}%" if _p is not None else 'N/A (not scored)'
    clv_txt    = f"Rs.{round(float(r['clv_score']), 0):,.0f}" if _p is not None else 'N/A'
    # CHURN-20: user-supplied text is HTML-escaped before it goes into the HTML part
    h_body            = html.escape(request.body)
    h_name, h_plan    = html.escape(cust_name), html.escape(plan)
    h_cid             = html.escape(request.customer_id)
 
    try:
        # ── Build Email ───────────────────────────────────────
        msg            = MIMEMultipart('alternative')
        msg['From']    = f"ChurnIQ Pro <{GMAIL_SENDER}>"
        msg['To']      = DEMO_RECEIVER
        msg['Subject'] = f"[ChurnIQ Demo] {request.subject}"
 
        # Plain text version
        plain_body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ChurnIQ Pro — Retention Email Demo
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Customer   : {cust_name} ({request.customer_id})
Plan       : {plan}
Churn Risk : {churn_txt}
CLV Score  : {clv_txt}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI Generated Retention Email:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 
{request.body}
 
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sent by ChurnIQ Pro — AI Churn Prevention System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """.strip()
 
        # HTML version (nicer in inbox)
        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
 
  <div style="background: #1A1A2E; padding: 20px; border-radius: 8px 8px 0 0;">
    <h2 style="color: #4A90E2; margin: 0;">⚡ ChurnIQ Pro</h2>
    <p style="color: #888; margin: 5px 0 0 0; font-size: 13px;">
      AI-Powered Retention Email — Demo Mode
    </p>
  </div>
 
  <div style="background: #f8f9ff; padding: 15px; border-left: 4px solid #FF4444;">
    <table style="width: 100%; font-size: 14px;">
      <tr>
        <td style="color: #666; padding: 3px 0;">Customer</td>
        <td style="font-weight: bold;">{h_name} ({h_cid})</td>
      </tr>
      <tr>
        <td style="color: #666; padding: 3px 0;">Plan</td>
        <td>{h_plan}</td>
      </tr>
      <tr>
        <td style="color: #666; padding: 3px 0;">Churn Risk</td>
        <td style="color: #FF4444; font-weight: bold;">{html.escape(churn_txt)}</td>
      </tr>
      <tr>
        <td style="color: #666; padding: 3px 0;">CLV Score</td>
        <td>{html.escape(clv_txt)}</td>
      </tr>
    </table>
  </div>
 
  <div style="background: white; padding: 25px; border: 1px solid #e0e0e0;">
    <p style="color: #888; font-size: 12px; margin: 0 0 15px 0;">
      ✨ AI-Generated Retention Email (by Gemini)
    </p>
    <div style="background: #f0f4ff; padding: 20px; border-radius: 6px;
                font-size: 15px; line-height: 1.7; white-space: pre-wrap;">
{h_body}
    </div>
  </div>
 
  <div style="background: #1A1A2E; padding: 15px; border-radius: 0 0 8px 8px;
              text-align: center;">
    <p style="color: #555; font-size: 12px; margin: 0;">
      Sent by ChurnIQ Pro — AI Churn Prevention System
    </p>
  </div>
 
</body>
</html>
        """.strip()
 
        # Attach both versions
        # CONCEPT: MIMEMultipart('alternative') = email client chooses
        # which version to display (HTML if supported, plain text fallback)
        msg.attach(MIMEText(plain_body, 'plain'))
        msg.attach(MIMEText(html_body,  'html'))
 
        # ── Send via Gmail SMTP ───────────────────────────────
        # SMTP_SSL = encrypted connection from the start (port 465)
        # Alternative: SMTP + STARTTLS on port 587 (also works)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASS)
            server.send_message(msg)
 
        logger.info("Retention email sent for %s", request.customer_id)
        masked = _mask_email(DEMO_RECEIVER)

        return {
            "success":     True,
            "message":     f"Email sent to {masked}",
            "customer_id": request.customer_id,
            "customer":    cust_name,
            "subject":     request.subject,
            # CHURN-21: masked — this API is unauthenticated
            "sent_to":     masked,
        }

    # CHURN-21: SMTP failures are the SERVER's upstream problem, so they are
    # 502 (not 401/500), and the SMTP server's text is logged, not returned.
    except smtplib.SMTPAuthenticationError as e:
        logger.error("Gmail authentication failed (SMTP %s)", getattr(e, 'smtp_code', '?'))
        raise APIError(
            502, 'smtp_auth_failed',
            "Gmail authentication failed. "
            "Check App Password in email_config.json. "
            "Make sure 2-Step Verification is ON in Google Account."
        )
    except (smtplib.SMTPException, OSError) as e:
        logger.error("SMTP delivery failed for %s: %s: %s", request.customer_id,
                     type(e).__name__, redact(e))
        raise APIError(502, 'smtp_error',
                       "The email could not be delivered by the mail server. The error has been logged.")


@app.get("/email-status", tags=["AI Retention"], response_model=EmailStatusResponse)
def email_status():
    """Check if Gmail email sending is configured and ready.
    Addresses are masked (CHURN-21): this endpoint is public."""
    return {
        "email_enabled": EMAIL_ENABLED,
        "sender":        _mask_email(GMAIL_SENDER) if EMAIL_ENABLED else "not configured",
        "demo_receiver": _mask_email(DEMO_RECEIVER) if EMAIL_ENABLED else "not configured",
        "auth_configured": bool(EMAIL_API_TOKEN),
        "rate_limit":    (f"{EMAIL_RATE_LIMIT_MAX} requests per "
                          f"{EMAIL_RATE_LIMIT_WINDOW_SECONDS} seconds per client"),
        "message":       (
            "Email sending is ready! Use POST /send-email"
            if EMAIL_ENABLED else
            "Run add_emails.py first to configure Gmail"
        )
    }

# ── ENDPOINT 6: Segment Analysis ─────────────────────────────────────────────
# USED BY: Segment Analysis page — all 5 charts
#
# CONCEPT: groupby().agg() = SQL GROUP BY with aggregation
# Returns pre-aggregated data so frontend just renders charts —
# no frontend-side data processing needed
@app.get("/segments", tags=["Analytics"], response_model=SegmentsResponse)
def get_segment_analysis():
    """
    Returns churn statistics aggregated by various segments.
    Powers all 5 charts on the Segment Analysis page.

    Returns: by_plan, by_device, by_tenure, by_genre, by_clv, monthly_trend
    """
    df = FULL_DF.copy()

    # ── By Plan Type ──────────────────────────────────────────────────
    plan_grp = df.groupby('plan_type').agg(
        count=             ('customer_id',    'count'),
        avg_churn=         ('churn_prob',     'mean'),
        high_risk_count=   ('risk_level',     lambda x: (x == 'HIGH').sum()),
        avg_monthly_charge=('monthly_charge', 'mean'),
        avg_clv=           ('clv_score',      'mean'),
    ).reset_index()
    plan_grp['churn_rate_pct'] = (plan_grp['avg_churn'] * 100).round(1)
    plan_grp['avg_clv']        = plan_grp['avg_clv'].round(0)

    # ── By Device Type ────────────────────────────────────────────────
    device_grp = df.groupby('device_type').agg(
        count=           ('customer_id', 'count'),
        avg_churn=       ('churn_prob',  'mean'),
        high_risk_count= ('risk_level',  lambda x: (x == 'HIGH').sum()),
    ).reset_index().sort_values('avg_churn', ascending=False)
    device_grp['churn_rate_pct'] = (device_grp['avg_churn'] * 100).round(1)

    # ── By Tenure Bucket ──────────────────────────────────────────────
    df['tenure_bucket'] = pd.cut(
        df['tenure_months'],
        bins=[0, 3, 6, 12, 24, 72],
        labels=['0-3m', '3-6m', '6-12m', '1-2yr', '2yr+']
    )
    tenure_grp = df.groupby('tenure_bucket', observed=True).agg(
        count=     ('customer_id', 'count'),
        avg_churn= ('churn_prob',  'mean'),
    ).reset_index()
    tenure_grp['churn_rate_pct'] = (tenure_grp['avg_churn'] * 100).round(1)
    tenure_grp['tenure_bucket']  = tenure_grp['tenure_bucket'].astype(str)

    # ── By Genre ──────────────────────────────────────────────────────
    genre_grp = df.groupby('preferred_genre').agg(
        count=     ('customer_id', 'count'),
        avg_churn= ('churn_prob',  'mean'),
    ).reset_index().sort_values('avg_churn', ascending=False)
    genre_grp['churn_rate_pct'] = (genre_grp['avg_churn'] * 100).round(1)

    # ── By CLV Segment ────────────────────────────────────────────────
    clv_grp = df.groupby('clv_segment').agg(
        count=     ('customer_id',    'count'),
        avg_churn= ('churn_prob',     'mean'),
        total_rev= ('monthly_charge', 'sum'),
    ).reset_index()
    clv_grp['churn_rate_pct'] = (clv_grp['avg_churn'] * 100).round(1)

    # ── Monthly Trend (simulated from data distribution) ─────────────
    # We don't have real time-series, so we simulate a realistic trend
    # In production: replace with actual monthly snapshot queries
    # A local RandomState(42) gives exactly the numbers np.random.seed(42)
    # did, without re-seeding NumPy's global RNG on every request (CHURN-21).
    rng        = np.random.RandomState(42)
    months     = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    _avg       = _mean_or_none(df['churn_prob'])
    base_rate  = _avg * 100 if _avg is not None else 0.0
    noise      = rng.normal(0, 2.0, 12).cumsum() * 0.3
    trend      = [
        {"month": m, "churn_rate": round(max(5.0, min(60.0, base_rate + n)), 1)}
        for m, n in zip(months, noise)
    ]

    return {
        "by_plan":         _json_safe(plan_grp.to_dict(orient='records')),
        "by_device":       _json_safe(device_grp.to_dict(orient='records')),
        "by_tenure":       _json_safe(tenure_grp.to_dict(orient='records')),
        "by_genre":        _json_safe(genre_grp.to_dict(orient='records')),
        "by_clv":          _json_safe(clv_grp.to_dict(orient='records')),
        "monthly_trend":   trend,
        "overall": {
            "total_customers":       int(len(df)),
            "scored_customers":      SCORED_COUNT,     # rates/averages use scored customers only
            "unscored_count":        UNSCORED_COUNT,   # shown as clv_segment 'Unknown' in by_clv
            "avg_churn_rate_pct":    round(base_rate, 1) if _avg is not None else None,
            "total_revenue_at_risk": round(float(
                (df['monthly_charge'] * df['churn_prob']).sum()
            ), 2),
        }
    }


# ── ENDPOINT 7: Dashboard Summary (All KPIs in One Call) ─────────────────────
# USED BY: Dashboard home page — populate ALL 4 KPI cards + priority list
# in a single network request instead of multiple calls
@app.get("/dashboard/summary", tags=["Analytics"], response_model=DashboardResponse)
def get_dashboard_summary():
    """
    Returns all KPI data for the dashboard home page in a single API call.
    More efficient than calling /customers and /segments separately.

    Returns: kpis (4 stat cards), churn_reasons_breakdown (donut chart),
             priority_customers (top 5 high-CLV at-risk customers)
    """
    df         = FULL_DF.copy()
    high_risk  = df[df['risk_level'] == 'HIGH']
    med_risk   = df[df['risk_level'] == 'MEDIUM']
    low_risk   = df[df['risk_level'] == 'LOW']
    rev_risk   = float((df['monthly_charge'] * df['churn_prob']).sum())

    avg_prob   = _mean_or_none(df['churn_prob'])

    # Top 5 highest-CLV high-risk customers = most impactful to act on first
    priority = df[df['risk_level'] == 'HIGH'].nlargest(5, 'clv_score')

    return {
        "kpis": {
            "total_customers":            int(len(df)),
            "high_risk_count":            int(len(high_risk)),
            "medium_risk_count":          int(len(med_risk)),
            "low_risk_count":             int(len(low_risk)),
            # high + medium + low + unscored == total_customers
            "unscored_count":             UNSCORED_COUNT,
            "scored_customers":           SCORED_COUNT,
            # share of SCORED customers (previously divided by all 5,001,
            # 80 % of whom have no prediction)
            "high_risk_pct":              (round(len(high_risk) / SCORED_COUNT * 100, 1)
                                           if SCORED_COUNT else 0.0),
            "avg_churn_probability":      round(avg_prob, 4) if avg_prob is not None else None,
            "avg_churn_percent":          (f"{avg_prob * 100:.1f}%" if avg_prob is not None
                                           else NOT_SCORED_TEXT),
            "revenue_at_risk_monthly":    round(rev_risk, 2),
            "revenue_at_risk_formatted":  f"₹{rev_risk:,.0f}",
            "high_value_at_risk":         int(len(df[
                (df['risk_level'] == 'HIGH') & (df['clv_segment'] == 'High')
            ])),
        },
        "churn_reasons_breakdown": {
            "low_engagement":  int(len(df[df['watch_hours_per_week'] < 3])),
            "payment_issues":  int(len(df[df['payment_failures_3m'] > 0])),
            "new_customers":   int(len(df[df['tenure_months'] < 6])),
            "support_issues":  int(len(df[df['support_tickets'] > 1])),
        },
        "priority_customers": [
            {
                "customer_id": str(r['customer_id']),
                "name":        str(r.get('name', '')),
                "churn_prob":  round(float(r['churn_prob']), 4),
                "churn_pct":   f"{float(r['churn_prob']) * 100:.1f}%",
                "clv_score":   round(float(r['clv_score']), 2),
                "plan_type":   str(r.get('plan_type', '')),
                "risk_level":  str(r.get('risk_level', '')),
            }
            for _, r in priority.iterrows()
        ],
    }


# =============================================================================
#   RUN SERVER
# =============================================================================
# This block only runs when you execute: python main.py
# When deployed on Render/Railway, they run: uvicorn main:app
# The if __name__ guard prevents this block from running on import

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  Starting ChurnIQ Pro API server...")
    print("  Local URL:  http://localhost:8000")
    print("  Swagger UI: http://localhost:8000/docs")
    print("  ReDoc:      http://localhost:8000/redoc")
    print("=" * 60 + "\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",   # Accept connections from any IP (needed for deployment)
        port=8000,
        reload=True,       # Auto-restart on file save (DEVELOPMENT ONLY)
        # reload=False     # Use this in production
    )
