# ChurnIQ Pro

> **AI-powered OTT customer churn prediction and retention intelligence system**

ChurnIQ Pro goes beyond basic churn prediction — it tells you **WHO** will churn, **WHY** they will churn, and **WHAT TO DO** about it, all in real time through a professional analytics dashboard.

---

## 🚀 Live Demo

| **Deployed** | `https://churn-iq-frontend-five.vercel.app/` |
---


##  What Makes This Different

| Traditional Churn Tools | ChurnIQ Pro |
|---|---|
| Outputs a probability number | Explains WHY with SHAP values |
| Generic retention offers | Personalized AI emails via Gemini |
| No prioritization | CLV scoring to prioritize who to save |
| Static reports | Live what-if simulator |
| Technical ML output | Plain English explanations |

---

##  Features

###  Churn Prediction Engine
- **XGBoost** gradient boosting model trained on 5,000 OTT customers: the regularised recipe (depth 2, learning rate 0.03, 400 trees, no SMOTE) with **monotone constraints** on the What-If features (CHURN-45 / CHURN-57, [`docs/ml/07-monotonic-constraints.md`](../docs/ml/07-monotonic-constraints.md))
- Predicts churn probability from 0–100% per customer
- Achieves **ROC-AUC: 0.76** on the held-out test set. Verified: 0.7597; accuracy 0.703, precision 0.679, recall 0.589, F1 0.631, Brier 0.196. See `docs/ml/results/evaluation_results.json`. The previous SMOTE + XGBoost model scored 0.7167
- Recorded training config and seed: `model_metadata.json`. Retrain from the committed dataset with `python churniq_ml_pipeline.py --from-dataset ott_churn_dataset.csv --output-dir .`, then `python generate_predictions.py`
- Preprocessing shared between training and the API in `churniq_core.py` (no training/serving skew)
- ML validation reports for pipeline, evaluation, SHAP, CLV and model research: [`docs/ml/`](../docs/ml/README.md)

###  Explainable AI (SHAP)
- **SHAP TreeExplainer** computes per-customer feature contributions
- Global beeswarm plot — which features matter most overall
- Individual waterfall plots — exactly why THIS customer will churn
- Top 3 churn reasons in plain English for every customer

###  Customer Lifetime Value (CLV)
- Formula: `monthly_charge × tenure × (1 − churn_probability)`
- Segments customers into High / Medium / Low value
- Helps prioritize: High CLV + High Risk = act immediately

### 👥 Customer Similarity Finder (KNN)
- **K-Nearest Neighbors (KNN)** lookalike search engine across 5,000 OTT customers
- Discovers the **5 most similar historical customers** based on actual behavioral and subscription patterns
- Displays **actual ground-truth churn outcomes** ("Retained" vs "Churned") alongside current XGBoost churn probabilities
- **Distance-derived similarity percentage**: Normalized geometric similarity score in standardized feature space
- **Target leakage prevention**: Churn labels, CLV, and predictions are strictly excluded from distance calculations
- **Self-exclusion**: Automatically filters out the query customer's own record from neighbor results
- **Side-by-side customer comparison**: Direct head-to-head diff of viewing hours, logins, payment failures, support tickets, tenure, and charges
- **Factual lookalike insights**: Generates data-driven takeaways based on lookalike churn rates and engagement gaps

###  Gemini AI Retention Emails
- SHAP reasons → structured Gemini prompt → personalized email
- Returns subject line, email body, 2 business actions, suggested offer
- Rule-based fallback if Gemini is unavailable
- Sent live via **Gmail SMTP** directly from the dashboard

###  Interactive Dashboard
- KPI cards: Total customers, High risk count, Revenue at risk, Avg churn %
- Churn trend line chart, Reasons donut chart, Plan type bar chart
- Sortable, filterable customer risk table with color-coded risk badges
- **What-if simulator**: move sliders → live churn % recalculation
- Segment analysis: by plan, device, tenure, genre
- Light / Dark mode toggle

---

##  Tech Stack

### Machine Learning
| Tool | Purpose |
|---|---|
| Python | Core language |
| XGBoost | Gradient boosting classifier |
| SHAP | Explainable AI (Shapley values) |
| Scikit-learn | Preprocessing, metrics, train-test split |
| imbalanced-learn | SMOTE for class balancing |
| Pandas + NumPy | Data manipulation |
| Faker | Synthetic dataset generation |
| Matplotlib + Seaborn | EDA visualization |

### Backend
| Tool | Purpose |
|---|---|
| FastAPI | REST API framework |
| Uvicorn | ASGI server |
| Pydantic | Request/response validation |
| Google Gemini API | AI retention email generation |
| Gmail SMTP | Live email delivery |

### Frontend
| Tool | Purpose |
|---|---|
| React 18 | UI framework |
| Vite | Build tool |
| Tailwind CSS | Utility-first styling |
| Recharts | Data visualization charts |
| React Router v6 | Client-side routing |
| Lucide React | Icons |

### Deployment
| Service | Purpose |
|---|---|
| Render | Backend hosting (free tier) |
| Vercel | Frontend hosting (free tier) |
| GitHub | Version control + CI/CD |

---

## 📁 Project Structure

```
ChurnIQ/
├── churniq_ml_pipeline.py    # Complete ML pipeline (Parts A–H)
├── main.py                   # FastAPI backend + Gemini + Email
├── requirements.txt          # Python dependencies
├── runtime.txt               # Python version for Render
├── add_emails.py             # Setup script for demo customer
├── fix_cust99999.py          # Adds demo customer to predictions
├── ott_churn_dataset.csv     # Synthetic OTT dataset (5000 rows)
├── customer_predictions.csv  # Precomputed predictions + SHAP reasons
├── churniq_model.pkl         # Trained XGBoost model
├── feature_names.pkl         # Feature column names for inference
└── frontend/
    ├── src/
    │   ├── App.jsx           # Main layout + routing + dark mode
    │   ├── api/churniq.js    # All API calls
    │   └── pages/
    │       ├── Dashboard.jsx
    │       ├── RiskTable.jsx
    │       ├── CustomerDetail.jsx
    │       ├── SegmentAnalysis.jsx
    │       └── ChurnPredict.jsx
    ├── package.json
    └── vite.config.js
```

---

## ⚙️ ML Pipeline (churniq_ml_pipeline.py)

```
Part A → Synthetic Dataset Generation  (5000 OTT customers, 21 features)
Part B → Exploratory Data Analysis      (6-chart EDA dashboard)
Part C → Preprocessing                  (encoding, feature engineering)
Part D → SMOTE                          (class imbalance fix, train only)
Part E → XGBoost Training               (200 trees, depth 5, lr 0.1)
Part F → Model Evaluation               (ROC-AUC, confusion matrix)
Part G → SHAP                           (global + per-customer explanations)
Part H → Predictions Table              (churn_prob + top 3 SHAP reasons)
```

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/customers` | Full risk table + KPI summary |
| GET | `/customer/{id}` | Single customer detail + SHAP |
| POST | `/whatif` | Live what-if simulation |
| POST | `/api/customer-similarity` | Customer Similarity Finder (KNN lookalike search) |
| GET | `/retention/{id}` | Gemini AI email + actions |
| GET | `/segments` | Churn stats by segment |
| GET | `/dashboard/summary` | All KPIs in one call |
| POST | `/send-email` | Send retention email via Gmail (bearer token `EMAIL_API_TOKEN`, rate limited — see docs/api §12) |
| GET | `/email-status` | Check email configuration |

Validation rules, error format and test results: [`docs/api/README.md`](../docs/api/README.md).

---

##  Local Setup

### 1. Clone the repo
```bash
git clone https://github.com/Kd1880/ChurnIQ.git
cd ChurnIQ
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Run ML pipeline (generates dataset + trains model)
```bash
python churniq_ml_pipeline.py
```

### 4. Configure environment
```bash
# Set your Gemini API key
set GEMINI_API_KEY=your_key_here   # Windows
export GEMINI_API_KEY=your_key_here # Mac/Linux

# Set up demo customer + Gmail (optional)
python add_emails.py

# Required to enable POST /send-email (CHURN-44): a random secret, >= 16 chars
export EMAIL_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
# Optional rate limit (defaults: 5 requests per 600 s per client)
export EMAIL_RATE_LIMIT_MAX=5
export EMAIL_RATE_LIMIT_WINDOW_SECONDS=600
```
The frontend asks for this token the first time you click **Send Email**.
API clients send it as `Authorization: Bearer <token>`.

### 5. Start backend
```bash
uvicorn main:app --reload --port 8000
```

### 6. Start frontend
```bash
cd frontend
npm install
npm run dev
```

##  Key Engineered Features

| Feature | Formula | Why |
|---|---|---|
| `engagement_score` | `watch_hours × logins / 30` | Single number capturing overall activity |
| `friction_score` | `payment_failures + support_tickets` | Combined negative experience signal |
| `inactivity_flag` | `1 if last_login > 14 days` | Binary signal for customers going dark |
| `is_new_customer` | `1 if tenure < 6 months` | 0–3 month customers have 72% churn rate |



## 🔍 Customer Similarity Finder (KNN Architecture)

### 1. What Customer Similarity Finder Does
Customer Similarity Finder identifies the **5 most similar historical customers** for any given customer. By analyzing historical users who displayed almost identical behavioral and subscription patterns in the past, customer success and retention teams can see whether those lookalikes ultimately stayed or churned. This offers empirical, case-based validation alongside model-based churn probability.

### 2. Why K-Nearest Neighbors (KNN) is Used
- **Instance-Based Learning**: Unlike parametric models that summarize patterns into weights, KNN stores historical instances directly and retrieves true nearest neighbors in feature space.
- **Explainability & Trust**: Retention managers can look at real peer examples ("Customer CUST00980 had nearly identical usage and churned after 2 payment failures") rather than treating the ML model as a black box.
- **Unsupervised / Non-Parametric Geometry**: It finds proximity without assuming linear relationships, making it ideal for multi-attribute behavioral matching.

### 3. Features Used for Similarity
Only genuine behavioral and subscription features from the dataset are used:
- **Tenure & Pricing**: `tenure_months`, `monthly_charge`, `plan_type`
- **Engagement**: `watch_hours_per_week`, `logins_last_30_days`, `last_login_days_ago`
- **Friction**: `payment_failures_3m`, `support_tickets`
- **Account & Device**: `age`, `num_profiles`, `device_type`, `preferred_genre`, `payment_method`
- **Excluded Features (Leakage/Identifier)**: `customer_id`, `name`, `email` (identifiers), and `churn`, `churn_probability`, `clv_score`, `clv_segment` (target leakage).

### 4. Preprocessing Pipeline
- **Imputation**: Median imputation for numerical features; most frequent strategy for categorical features.
- **Encoding**: Ordinal encoding for `plan_type` (`Basic: 0`, `Standard: 1`, `Premium: 2`) preserving hierarchy; One-Hot Encoding (`handle_unknown='ignore'`) for nominal categories.
- **Scaling**: `StandardScaler` standardizes all continuous and ordinal features to zero mean and unit variance ($z = \frac{x - \mu}{\sigma}$). This prevents high-magnitude features (like `monthly_charge` ₹199–₹799) from overwhelming small-magnitude features (like `payment_failures_3m` 0–4).
- **Persistence**: Fitted pipeline and model are serialized with `joblib` (`similarity_pipeline.joblib`, `customer_similarity_model.joblib`).

### 5. Similarity Score Calculation
- **Metric**: Euclidean distance ($d$) in standardized multidimensional space:
  $$d(u, v) = \sqrt{\sum_{i=1}^n (u_i - v_i)^2}$$
- **Normalized Similarity Percentage**:
  $$\text{similarity} = \frac{1}{1 + d} \times 100\%$$
- **Properties**:
  - $d = 0 \implies 100\%$ (identical profile).
  - As $d$ increases, similarity smoothly decreases toward $0\%$.
  - Strictly bounded in $(0, 100\%]$.
  - **Important**: This is a geometric distance-derived similarity score, *not* a probability.

### 6. API Endpoint: `POST /api/customer-similarity`
**Request Body:**
```json
{
  "customer_id": "CUST00001",
  "n_neighbors": 5
}
```
**Response:**
```json
{
  "selected_customer": {
    "customer_id": "CUST00001",
    "name": "Warjas Bhalla",
    "plan_type": "Standard",
    "monthly_charge": 499,
    "tenure_months": 28,
    "watch_hours_per_week": 1.0,
    "logins_last_30_days": 13,
    "payment_failures_3m": 0,
    "support_tickets": 0,
    "churn_prob": 0.3223,
    "risk_level": "LOW",
    "historical_outcome": "Churned"
  },
  "similar_customers": [
    {
      "customer_id": "CUST00980",
      "similarity_score": 45.7,
      "distance": 1.1883,
      "churn_prob": 0.4485,
      "risk_level": "MEDIUM",
      "historical_churn": 1,
      "historical_outcome": "Churned",
      "plan_type": "Standard",
      "tenure_months": 24,
      "monthly_charge": 499,
      "watch_hours_per_week": 3.1,
      "logins_last_30_days": 13
    }
  ],
  "insights": [
    "2 of the 5 most similar historical customers (40%) previously churned.",
    "This customer watches 1.9 fewer hours/week than similar historical customers.",
    "5 of the 5 nearest lookalikes share the exact same Standard subscription plan."
  ]
}
```

### 7. How to Run & Test
```bash
# 0. ML validation suite (pipeline, evaluation, SHAP, CLV, model research)
pip install -r requirements-dev.txt
python -m pytest

# Regenerate predictions for all customers (held-out + out-of-fold, CHURN-37)
python generate_predictions.py

# 1. Run unit tests for similarity engine & KNN training
#    (note: rewrites the committed *.joblib similarity artifacts)
python test_similarity_engine.py

# 2. Run API integration tests (health check, similarity, regression)
python test_api_endpoints.py

# 3. Start backend API server
uvicorn main:app --reload --port 8000

# 4. In ChurnIQ-Frontend, build or launch dev server
npm run build
npm run dev
```

##  Acknowledgements

- [SHAP](https://github.com/slundberg/shap) — Explainable AI library
- [XGBoost](https://xgboost.readthedocs.io/) — Gradient boosting framework
- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python API framework
- [Google Gemini](https://aistudio.google.com/) — AI language model
- [Recharts](https://recharts.org/) — React charting library
---
