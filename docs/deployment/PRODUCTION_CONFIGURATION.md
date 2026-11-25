# Production configuration (CHURN-54)

**Jira:** CHURN-54. Prepared by Avanish Rajauria with AI-assisted development tools, on 25 November 2026.

## 1. Deployment

| Part | Host | URL |
|---|---|---|
| Frontend (React + Vite) | Vercel | `https://churn-iq-frontend-five.vercel.app` |
| Backend (FastAPI) | Render | `https://churniq-32r3.onrender.com` |

## 2. CORS policy (backend)

**Before CHURN-54,** `backend/main.py` used `allow_origins=["*"]` together with `allow_credentials=True`, so any website could call the API from a browser.

**The policy is now defined in `backend/cors_config.py`:**

* **Allowed origins:**
  * `https://churn-iq-frontend-five.vercel.app` (production);
  * `http://localhost:5173` and `http://127.0.0.1:5173` (`npm run dev`);
  * `http://localhost:4173` and `http://127.0.0.1:4173` (`npm run preview`).
* **Any other origin** gets no `Access-Control-Allow-Origin` header, so the browser blocks the response. A preflight from it is answered with `400`.
* **No wildcard.** A `*` in the configuration is ignored.
* **No credentials** (`allow_credentials=False`). The frontend sends no cookies. `/send-email` authenticates with `Authorization: Bearer …`, which does not need credentialed CORS.
* **Methods and headers:** methods `GET` and `POST`; headers `Content-Type` and `Authorization`, which are all the frontend sends.

**Override per deployment, without a code change.** Set `CORS_ALLOWED_ORIGINS` to a comma-separated list of exact origins:

```bash
CORS_ALLOWED_ORIGINS=https://churn-iq-frontend-five.vercel.app,http://localhost:5173
```

How the list is handled:

* Entries are normalised: lower-case, with no trailing slash.
* Invalid entries (a wildcard, a path, a non-http scheme) are ignored, and a warning is printed at startup.
* If the variable is unset, blank or entirely invalid, the defaults above are used. It never falls back to "allow everything".
* Vercel **preview** deployments have per-commit URLs, so they are not allowed by default. Add a specific preview URL to the list if one needs to call the production API.

**Tests:** `backend/tests/test_cors_config.py`. They cover:

* allowed and rejected origins on the real app;
* preflight from allowed and rejected origins, and an unlisted method;
* no wildcard and no credentials header;
* parsing and normalisation of `CORS_ALLOWED_ORIGINS`.

Restoring the old wildcard configuration makes 11 of these tests fail.

## 3. Environment variables

### Backend (Render → Service → Environment)

| Variable | Required | Purpose | Default if unset |
|---|---|---|---|
| `CORS_ALLOWED_ORIGINS` | No | Browser origins allowed to call the API | Production frontend and localhost dev/preview origins |
| `EMAIL_API_TOKEN` | For `/send-email` | Bearer token (16 characters or more) for `/send-email` | `/send-email` returns 503 |
| `GMAIL_SENDER`, `GMAIL_APP_PASS`, `DEMO_RECEIVER` | For `/send-email` | Gmail SMTP sender, app password and demo inbox | Email disabled |
| `EMAIL_RATE_LIMIT_MAX`, `EMAIL_RATE_LIMIT_WINDOW_SECONDS` | No | Email rate limit | 5 per 600 s |
| `GEMINI_API_KEY` | No | Gemini for `/retention` | Rule-based fallback, labelled as such in the UI |
| `GEMINI_MODEL_NAME`, `GEMINI_TIMEOUT_SECONDS` | No | Gemini model and timeout | `gemini-3.5-flash`, 20 s |
| `WEB_CONCURRENCY` | No | Worker count (a warning is printed above 1, because the email rate limiter is per process) | 1 |

**Secrets:** `EMAIL_API_TOKEN`, `GMAIL_APP_PASS` and `GEMINI_API_KEY` are secrets. Set them in the hosting dashboard; never commit them.

**Startup:** the CORS configuration itself needs no secret. The app starts and serves the dashboard with none of the optional variables set.

### Frontend (Vercel → Project → Settings → Environment Variables)

| Variable | Purpose | Value |
|---|---|---|
| `VITE_API_URL` | API base URL, compiled into the bundle at build time | `https://churniq-32r3.onrender.com` |

**Where the value comes from.** If the Vercel variable is not set, `vite build` uses `frontend/.env.production`, which contains the same URL. Anything in a `VITE_*` variable is public, so never put a secret there.

## 4. Verification on 25 November 2026

| Check | How | Result |
|---|---|---|
| API URL used by the **deployed** frontend | Downloaded `https://churn-iq-frontend-five.vercel.app/` and its bundle `/assets/index-DK36Gx0B.js`; searched it for API URLs | The bundle contains exactly one API base URL, **`https://churniq-32r3.onrender.com`**, and no localhost URL. The effective `VITE_API_URL` is therefore correct. |
| The Vercel `VITE_API_URL` **setting** itself | Needs the Vercel project dashboard | **Not checked.** Only the project owner can see it. The bundle check shows the built result, not whether it came from the dashboard variable or from `.env.production` (both give the same URL). |
| CORS on the **deployed** backend | `GET` on the Render API with `Origin: https://evil.example` | Still `access-control-allow-origin: *` with `access-control-allow-credentials: true`. **The deployed backend predates this change.** |
| Age of both deployments | `GET /` on the Render API; text search of the Vercel bundle | **Both predate the team's merged PRs.** `GET /` reports `high_risk_count: 250`, the count from before the out-of-fold scoring in PR #1 and the model change in PR #14. The bundle contains none of the UI text added in PR #8 (for example "Cannot reach the ChurnIQ API" or "Illustrative only"). The live site therefore does not yet show any of the merged work. |
| CORS in this branch | `backend/tests/test_cors_config.py` against the real app | Allowed origins echoed; rejected origins get no CORS headers; no wildcard or credentials |

## 5. Deployment steps (hosting account owners)

These need the Render and Vercel account owners and team agreement (CHURN-54's last criterion). They have **not** been carried out as part of this change.

1. **Merge** this PR after review.
2. **Redeploy the Render service from `main`.** No new variable is required, because the defaults include the production frontend. Optionally, set `CORS_ALLOWED_ORIGINS` explicitly.
3. **Check the deployed API:**
   * `curl -sD - -o /dev/null -H 'Origin: https://evil.example' https://churniq-32r3.onrender.com/` must show **no** `access-control-allow-origin` header;
   * the same request with `Origin: https://churn-iq-frontend-five.vercel.app` must echo that origin.
4. **Vercel:** confirm `VITE_API_URL` in the project settings, or confirm it is unset so that `.env.production` applies. Redeploy from `main`, open the site, and check that the Dashboard loads with "API connected".
5. **Record** the results on CHURN-54.
