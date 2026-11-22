# ChurnIQ Pro — Frontend

Modern React 18 + Vite frontend for ChurnIQ Pro, an AI-powered OTT customer churn prediction and retention intelligence platform.

---

## 🚀 Features & Pages

1. **Dashboard (`/`)**: Executive KPI cards, monthly churn trends, churn reasons donut chart, plan type distribution, and high-CLV priority intervention list.
2. **Customer Risk Table (`/risk`)**: Searchable, filterable risk table with color-coded churn badges, plan filters, and direct links to individual customer profiles.
3. **Customer Detail (`/risk/:id`)**: Comprehensive customer profile, live What-If simulator sliders, SHAP impact breakdown, and Gemini AI retention email generation.
4. **Segments (`/segments`)**: Deep dive analytics across plans, devices, tenure cohorts, and content genres.
5. **Churn Predict (`/predict`)**: Interactive churn simulator for hypothetical customer profiles.
6. **Customer Similarity Finder (`/similarity`)**:
   - Discovers the **5 nearest historical lookalikes** using K-Nearest Neighbors (KNN).
   - Displays real ground-truth historical churn outcomes ("Retained" vs "Churned").
   - Shows normalized similarity percentages derived from Euclidean distance in standardized feature space.
   - Interactive side-by-side metric comparison across viewing hours, logins, payment failures, support tickets, tenure, and monthly charges.
   - Factual, data-driven lookalike insights.

---

## 🛠️ Tech Stack

- **React 18** + **Vite**
- **React Router v6**
- **Recharts**
- **Lucide React** (Icons)
- **Tailwind CSS v4**

---

## 🏃‍♂️ Getting Started

### 1. Install dependencies:
```bash
npm install
```

### 2. Set backend API URL (Optional, defaults to http://localhost:8000):
```bash
# In .env or shell:
VITE_API_URL=http://localhost:8000
```

### 3. Run development server:
```bash
npm run dev
```

### 4. Build for production:
```bash
npm run build
```
