# ChurnIQ Pro — AI-Powered Customer Churn Intelligence & Similarity Finder

> **Enterprise-grade OTT Customer Churn Prediction, Explainable AI (SHAP), Customer Lifetime Value (CLV) Analytics, and K-Nearest Neighbors (KNN) Lookalike Customer Similarity Engine.**

ChurnIQ Pro provides actionable retention intelligence for subscription streaming platforms. It goes beyond predicting *who* might churn by explaining *why* they are at risk using SHAP values, identifying *who else behaved similarly* using K-Nearest Neighbors (KNN), and generating targeted retention actions using Google Gemini AI.

---

## 🏛️ System Architecture

```
CHURN-IQ/
├── backend/                              # FastAPI Backend & Machine Learning Engine
│   ├── churniq_ml_pipeline.py            # Complete ML Pipeline (EDA, SMOTE, XGBoost, SHAP)
│   ├── churniq_core.py                   # Shared features/encoding, risk, SHAP reasons, CLV (pipeline + API)
│   ├── evaluate_model.py                 # Reproducible evaluation of the committed model (CHURN-14)
│   ├── validate_shap.py                  # SHAP validation (CHURN-15)
│   ├── model_experiments.py              # Controlled model-improvement experiments (CHURN-17)
│   ├── generate_predictions.py           # Full-coverage predictions: held-out + out-of-fold (CHURN-37)
│   ├── oof_fold_models.pkl               # 5 out-of-fold models used for training-customer predictions
│   ├── tests/                            # pytest ML validation suite (run: python -m pytest)
│   ├── requirements-dev.txt              # Training / test dependencies
│   ├── customer_similarity.py            # KNN Customer Similarity Engine (Preprocessing & Inference)
│   ├── main.py                           # REST API Server (Endpoints, Models, Gemini, Gmail SMTP)
│   ├── ott_churn_dataset.csv             # Synthetic OTT Customer Dataset (5,001 rows, 22 columns)
│   ├── customer_predictions.csv          # Predictions & SHAP reasons for all customers (prediction_source column)
│   ├── churniq_model.pkl                 # Serialized XGBoost Churn Classification Model
│   ├── feature_names.pkl                 # Serialized feature list for inference alignment
│   ├── customer_similarity_model.joblib  # Serialized NearestNeighbors Model
│   ├── similarity_pipeline.joblib        # Serialized StandardScaler & OneHotEncoder Pipeline
│   ├── similarity_metadata.joblib        # Feature indices and metadata for similarity lookups
│   ├── test_api_endpoints.py             # FastAPI automated test suite (Health, Similarity, What-If)
│   ├── test_similarity_engine.py         # KNN engine unit test suite (Self-exclusion, Distances, Ordering)
│   ├── requirements.txt                  # Python dependencies
│   ├── runtime.txt                       # Python runtime specification
│   ├── email_config.example.json         # Gmail SMTP configuration template
│   └── README.md                         # Detailed backend documentation
│
├── frontend/                             # React 18 + Vite Modern Dashboard
│   ├── src/
│   │   ├── api/
│   │   │   └── churniq.js                # API client with multi-host fallback support
│   │   ├── pages/
│   │   │   ├── CustomerSimilarity.jsx    # Customer Similarity Finder page
│   │   │   ├── Dashboard.jsx             # Executive KPI cards & overview charts
│   │   │   ├── RiskTable.jsx             # Filterable Customer Risk Table
│   │   │   ├── CustomerDetail.jsx        # Individual profile, What-If sliders, Gemini retention email
│   │   │   ├── SegmentAnalysis.jsx       # Plan, device, tenure, and genre analytics
│   │   │   └── ChurnPredict.jsx          # Interactive churn simulator
│   │   ├── App.jsx                       # Navigation layout, sidebar, dark/light theme provider
│   │   ├── index.css                     # Minimal, professional styling with CSS variables
│   │   └── main.jsx                      # React application entry point
│   ├── index.html                        # HTML template
│   ├── package.json                      # Frontend dependencies & scripts
│   ├── vite.config.js                    # Vite bundler configuration
│   └── README.md                         # Detailed frontend documentation
│
├── docs/ml/                              # ML validation reports (pipeline, evaluation, SHAP, CLV, research)
├── docs/api/                             # API quality report (endpoint inventory, contracts, validation, errors, tests)
├── .gitignore                            # Root gitignore (ignores node_modules, dist, __pycache__, .env)
└── README.md                             # Root Project Documentation
```

---

## 🌟 Core Features

### 1. 👥 Customer Similarity Finder (KNN)
* **Instance-Based Lookalike Search**: Finds the 5 most similar historical customers based on behavior, engagement, and subscription characteristics.
* **Standardized Feature Space**: Applies `StandardScaler` to continuous and ordinal attributes and `OneHotEncoder` to nominal categories.
* **Target Leakage Prevention**: Churn labels, probabilities, and CLV metrics are strictly excluded from distance computation.
* **Self-Match Exclusion**: Automatically excludes the query customer from the neighbor list when querying historical customers.
* **Ground-Truth Historical Outcomes**: Displays whether lookalike customers actually stayed ("Retained") or left ("Churned").
* **Distance-Derived Similarity Percentage**:
  $$\text{similarity} = \frac{1}{1 + d} \times 100\%$$
* **Interactive Side-by-Side Comparison**: Direct head-to-head comparison of viewing hours, logins, payment failures, tickets, tenure, and charges.
* **Factual Lookalike Insights**: Data-backed insights summarizing historical churn rates and behavioral differences.

### 2. ⚡ XGBoost Churn Prediction
* Gradient boosted decision trees trained on 5,000 customers.
* SMOTE class balancing applied on the training split to handle class imbalance.
* Achieves strong ROC-AUC on held-out test data.

### 3. 🔍 Explainable AI (SHAP)
* TreeExplainer computes per-customer Shapley values.
* Converts technical feature importances into plain-English business reasons (e.g., billing friction, low engagement).

### 4. 💰 Customer Lifetime Value (CLV)
* Formula: $\text{monthly\_charge} \times \text{tenure} \times (1 - \text{churn\_probability})$.
* Categorizes customers into High, Medium, and Low value tiers to prioritize retention campaigns.

### 5. 🎛️ Counterfactual What-If Simulator
* Live inference endpoint where users adjust sliders (e.g., reducing payment failures or increasing watch time) and immediately see the recalculated churn risk.

### 6. 🤖 Gemini AI Retention Strategy
* Generates personalized retention emails and business recommendations tailored to each customer's specific SHAP churn drivers.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check and API system status |
| `POST` | `/api/customer-similarity` | Finds top N similar customers using KNN |
| `GET` | `/customers` | Filterable customer risk table + summary statistics |
| `GET` | `/customer/{id}` | Detailed customer profile with SHAP reasons and CLV |
| `POST` | `/whatif` | Counterfactual live what-if prediction |
| `GET` | `/retention/{id}` | Gemini AI personalized retention email and actions |
| `GET` | `/segments` | Aggregated churn distributions across segments |
| `GET` | `/dashboard/summary` | Executive dashboard KPI summary in a single call |
| `POST` | `/send-email` | Send the retention email to the demo inbox (needs Gmail config and `Authorization: Bearer <EMAIL_API_TOKEN>`; rate limited) |
| `GET` | `/email-status` | Whether email sending is configured (addresses masked) |

Full inventory, response contracts, input-validation rules and the JSON error format (`{detail, error, status_code, errors?, request_id?}`): [`docs/api/README.md`](docs/api/README.md).

### Customer Similarity Request & Response
**`POST /api/customer-similarity`**
```json
{
  "customer_id": "CUST00001",
  "n_neighbors": 5
}
```
**Response Sample:**
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
    "This customer watches 1.9 fewer hours/week than similar historical customers (average 2.9 hrs/wk).",
    "5 of the 5 nearest lookalikes share the exact same Standard subscription plan."
  ]
}
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
* Python 3.10+ (tested on Python 3.11, 3.12, 3.13)
* Node.js 18+ and npm

### 2. Backend Setup
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# (Optional) Run ML pipeline to regenerate models from scratch:
# python churniq_ml_pipeline.py

# Run unit and API tests
python test_similarity_engine.py
python test_api_endpoints.py

# Start FastAPI server
python -m uvicorn main:app --reload --port 8000
```
Interactive Swagger docs: `http://localhost:8000/docs`

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Build for production verification
npm run build

# Start development server
npm run dev
```
Open your browser at: `http://localhost:5173/similarity`

---

## 🧪 Testing & Verification

Run the whole backend suite (ML validation + API quality, CHURN-13..25) from `backend/`:

```bash
python -m pytest
```

Commands, coverage and results: [`docs/api/README.md` §9](docs/api/README.md#9-test-commands-and-results). The two original script-style suites can still be run directly:
* **Engine Tests**: `python backend/test_similarity_engine.py` validates KNN training, scaling consistency, distance sorting, self-neighbor exclusion, and error handling for invalid customer IDs.
* **Endpoint Tests**: `python backend/test_api_endpoints.py` tests all REST endpoints, response schemas, and ensures zero regressions on existing XGBoost and What-If routes.

---

## 📄 License
MIT License
