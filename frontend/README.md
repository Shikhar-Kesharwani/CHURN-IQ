# ChurnIQ Pro — Frontend

React 18 + Vite frontend for ChurnIQ Pro, an OTT customer churn prediction and retention platform.

---

## Pages

1. **Dashboard (`/`)**
   * KPI cards from `GET /dashboard/summary`.
   * Churn-risk signals and the high-CLV priority list.
   * Plan churn, CLV and a monthly trend from `GET /segments`. The trend is clearly labelled as **simulated**, because the dataset has no monthly history.
2. **Customer Risk Table (`/risk`)**
   * All customers from `GET /customers?limit=10000`.
   * Search by name or ID, risk and plan filters, and sortable columns (risk sorts by severity).
   * Pagination (25, 50 or 100 rows), risk badges, and empty, loading and error states.
3. **Customer Detail (`/risk/:id`)**
   * Profile, CLV tier and SHAP reasons from `GET /customer/{id}`.
   * What-If sliders (`POST /whatif`).
   * Retention email draft from `GET /retention/{id}`, labelled as AI-generated or rule-based. Sending requires the operator's email API token (CHURN-44).
4. **Segments (`/segments`)**: churn by plan, device, tenure and genre (`GET /segments`).
5. **Churn Predict (`/predict`)**
   * What-If on a real customer: load a customer, then edit the six fields `POST /whatif` supports. The inputs are validated with the backend's own bounds.
   * Shows the model's before and after prediction.
   * The backend cannot score a hypothetical customer from scratch, so this page doesn't pretend to.
6. **Customer Similarity Finder (`/similarity`)**
   * Nearest historical lookalikes by KNN (`POST /api/customer-similarity`), with a choice of 3, 5, 10 or 20 neighbours.
   * Opens directly with `?customer=<ID>`, for example from Customer Detail.

**When the API is down:** every page shows a clear error with a **Retry** button, and no mock or estimated data. The navbar badge shows the real API status.

---

## Tech stack

React 18, Vite 6, React Router 6, Recharts, Lucide icons, Tailwind CSS 4. Tests use Vitest, Testing Library and jsdom.

---

## Getting started

```bash
npm ci
```

```bash
npm run dev
```

```bash
npm test
```

```bash
npm run build
```

### Contract checks and browser smoke tests (CHURN-55)

The tests in `src/` run against recorded API responses in `src/test/fixtures/`. Two further checks keep those fixtures and the real app honest.

**Fixture contract check.** `backend/tests/test_frontend_fixture_contracts.py` calls the real API for every fixture. It fails if a field is renamed, removed, added or changes JSON type; values are not compared. It runs with the backend suite (`cd backend && python -m pytest -q`).

When the API changes on purpose, re-capture the affected fixture from the running backend. Every new fixture file must be added to `CONTRACTS` in that test.

**Browser smoke tests** (`e2e/smoke.e2e.js`, Playwright with Chromium) cover four journeys:

* the Dashboard KPIs;
* Risk Table → Customer Detail;
* What-If;
* Similarity.

They run against a real `uvicorn` backend and a production build served by `vite preview`, both started automatically. Expected values are read from the same API during the test, so they do not depend on the model's numbers. No Gemini key or email configuration is used.

```bash
npx playwright install chromium        # once
E2E_PYTHON=python npm run test:e2e     # E2E_PYTHON: a Python with backend/requirements.txt installed
```

Both run in CI. The contract check runs in **Backend tests**; the smoke tests run in their own **Browser smoke tests** job, so the two existing required check names are unchanged.

### API base URL

The frontend calls exactly one API, `VITE_API_URL`. There is no silent fallback to another server.

| Situation | URL used |
|---|---|
| `npm run dev` | `VITE_API_URL` if set, otherwise `http://localhost:8000` |
| `npm run build` | `VITE_API_URL` from the environment if set, otherwise the value in `.env.production` |

To use another backend for one build:

```bash
VITE_API_URL=http://127.0.0.1:8000 npm run build
```

`.env.production` holds only the public production API URL. Anything in a `VITE_*` variable is compiled into the public JavaScript bundle, so never put a secret there. The email API token is typed in by the operator at send time and kept in `sessionStorage` only.
