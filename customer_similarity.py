"""
Customer Similarity Finder - K-Nearest Neighbors (KNN) Engine
============================================================
This module implements the customer similarity finder using K-Nearest Neighbors (KNN).
It allows business and customer success teams to find historical lookalike customers
for any selected customer based on behavioral, subscription, and engagement features.

Methodology & Rationale:
------------------------
1. Feature Selection:
   - Behavioral: watch_hours_per_week, logins_last_30_days, last_login_days_ago,
                 payment_failures_3m, support_tickets
   - Subscription: tenure_months, monthly_charge, plan_type
   - Demographic & Preferences: age, num_profiles, device_type, preferred_genre, payment_method
   - EXCLUDED (Leakage/Identifier): customer_id, name, email (identifiers);
                                    churn, churn_probability, clv_score, clv_segment (target leakage)

2. Preprocessing:
   - Missing values are imputed with median for numerical and most frequent for categorical.
   - plan_type is ordinally encoded (Basic=0, Standard=1, Premium=2) to preserve pricing hierarchy.
   - Categorical features are one-hot encoded with handle_unknown='ignore'.
   - All numerical features are scaled using StandardScaler (zero mean, unit variance).
     Standardization is essential for KNN so that features with large numerical ranges
     (e.g., monthly_charge: 199-799, tenure: 1-72) do not mathematically dominate features
     with small numerical ranges (e.g., payment_failures_3m: 0-4, support_tickets: 0-5).

3. Metric & Distance:
   - Euclidean distance in the standardized feature space:
       d(u, v) = sqrt(sum((u_i - v_i)^2))
   - Normalized Similarity Percentage:
       similarity_percentage = round((1.0 / (1.0 + distance)) * 100, 1)
     This score is strictly bounded in (0, 100%], where 100% represents an exact match (d=0).
     NOTE: This is a geometric distance-derived similarity metric, NOT a churn probability.

4. Neighbor Querying & Customer Exclusion:
   - Queries n_neighbors + 1 (default 6) neighbors.
   - If the selected customer is already in the historical dataset, their own record
     (distance ~ 0) is excluded so we only return the 5 nearest OTHER historical customers.
"""

import os
import joblib
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

# Model & artifact filenames
MODEL_FILE = "customer_similarity_model.joblib"
PIPELINE_FILE = "similarity_pipeline.joblib"
METADATA_FILE = "similarity_metadata.joblib"

PLAN_ORDER = {"Basic": 0, "Standard": 1, "Premium": 2}

NUMERICAL_FEATURES = [
    "tenure_months",
    "watch_hours_per_week",
    "logins_last_30_days",
    "last_login_days_ago",
    "payment_failures_3m",
    "support_tickets",
    "monthly_charge",
    "age",
    "num_profiles",
    "plan_type_encoded",
]

CATEGORICAL_FEATURES = [
    "device_type",
    "preferred_genre",
    "payment_method",
]


class CustomerSimilarityEngine:
    """
    K-Nearest Neighbors Customer Similarity Engine.
    Handles data preprocessing, model fitting, persistence, and similarity queries.
    """

    def __init__(self, data_df: Optional[pd.DataFrame] = None, artifacts_dir: Optional[str] = None):
        self.artifacts_dir = artifacts_dir or os.path.dirname(os.path.abspath(__file__))
        self.data_df: Optional[pd.DataFrame] = data_df
        self.pipeline: Optional[ColumnTransformer] = None
        self.knn_model: Optional[NearestNeighbors] = None
        self.customer_ids: List[str] = []
        self.customer_id_to_idx: Dict[str, int] = {}
        self.is_fitted: bool = False

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add encoded plan type and handle types."""
        df_copy = df.copy()
        if "plan_type" in df_copy.columns:
            df_copy["plan_type_encoded"] = df_copy["plan_type"].map(PLAN_ORDER).fillna(0)
        else:
            df_copy["plan_type_encoded"] = 0
        return df_copy

    def fit(self, df: pd.DataFrame) -> "CustomerSimilarityEngine":
        """
        Train the KNN model and preprocessing pipeline on the historical customer dataset.
        """
        print("[Similarity Engine] Fitting preprocessing pipeline & KNN model...")
        self.data_df = df.copy().reset_index(drop=True)
        self.customer_ids = self.data_df["customer_id"].astype(str).tolist()
        self.customer_id_to_idx = {cid: idx for idx, cid in enumerate(self.customer_ids)}

        prepared_df = self._prepare_dataframe(self.data_df)

        # Build consistent Scikit-Learn preprocessing pipeline
        num_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ])

        cat_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])

        self.pipeline = ColumnTransformer(
            transformers=[
                ("num", num_pipeline, NUMERICAL_FEATURES),
                ("cat", cat_pipeline, CATEGORICAL_FEATURES),
            ],
            remainder="drop",
        )

        X_processed = self.pipeline.fit_transform(prepared_df)

        # Fit NearestNeighbors with euclidean distance metric
        # n_neighbors=6 so we can exclude self and return top 5
        self.knn_model = NearestNeighbors(
            n_neighbors=min(6, len(df)),
            metric="euclidean",
            algorithm="auto",
        )
        self.knn_model.fit(X_processed)
        self.is_fitted = True
        print(f"[Similarity Engine] Fitted on {len(self.data_df)} customers with {X_processed.shape[1]} processed features.")
        return self

    def save(self, directory: Optional[str] = None):
        """Persist fitted pipeline, model, and metadata to disk."""
        target_dir = directory or self.artifacts_dir
        os.makedirs(target_dir, exist_ok=True)
        joblib.dump(self.pipeline, os.path.join(target_dir, PIPELINE_FILE))
        joblib.dump(self.knn_model, os.path.join(target_dir, MODEL_FILE))
        metadata = {
            "customer_ids": self.customer_ids,
            "customer_id_to_idx": self.customer_id_to_idx,
            "numerical_features": NUMERICAL_FEATURES,
            "categorical_features": CATEGORICAL_FEATURES,
            "plan_order": PLAN_ORDER,
        }
        joblib.dump(metadata, os.path.join(target_dir, METADATA_FILE))
        print(f"[Similarity Engine] Artifacts saved to {target_dir}")

    def load(self, directory: Optional[str] = None, data_df: Optional[pd.DataFrame] = None) -> bool:
        """Load fitted pipeline and model from disk."""
        target_dir = directory or self.artifacts_dir
        pipeline_path = os.path.join(target_dir, PIPELINE_FILE)
        model_path = os.path.join(target_dir, MODEL_FILE)
        metadata_path = os.path.join(target_dir, METADATA_FILE)

        if not (os.path.exists(pipeline_path) and os.path.exists(model_path) and os.path.exists(metadata_path)):
            return False

        try:
            self.pipeline = joblib.load(pipeline_path)
            self.knn_model = joblib.load(model_path)
            metadata = joblib.load(metadata_path)
            self.customer_ids = metadata["customer_ids"]
            self.customer_id_to_idx = metadata["customer_id_to_idx"]
            if data_df is not None:
                self.data_df = data_df.copy().reset_index(drop=True)
            self.is_fitted = True
            print(f"[Similarity Engine] Loaded fitted model & pipeline ({len(self.customer_ids)} customers).")
            return True
        except Exception as e:
            print(f"[Similarity Engine] Failed to load artifacts: {e}")
            return False

    @staticmethod
    def calculate_similarity_score(distance: float) -> float:
        """
        Convert Euclidean distance into a normalized similarity percentage.
        Formula: similarity = 1.0 / (1.0 + distance) * 100
        - d = 0.0 -> 100.0%
        - d = 1.0 -> 50.0%
        - d -> inf -> 0.0%
        """
        if distance < 0:
            distance = 0.0
        score = (1.0 / (1.0 + float(distance))) * 100.0
        return round(score, 1)

    def find_similar_customers(
        self,
        customer_id: str,
        n_neighbors: int = 5,
        full_df: Optional[pd.DataFrame] = None,
        xgboost_model: Optional[Any] = None,
        feature_names: Optional[List[str]] = None,
        build_feature_row_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Find the n_neighbors most similar historical customers for a given customer_id.

        Returns:
            Dict containing selected_customer, similar_customers list, and factual insights.
        """
        if not self.is_fitted or self.knn_model is None or self.pipeline is None:
            raise ValueError("CustomerSimilarityEngine is not fitted or loaded.")

        df_to_use = full_df if full_df is not None else self.data_df
        if df_to_use is None or df_to_use.empty:
            raise ValueError("Customer dataset is empty or not provided.")

        # Locate selected customer
        selected_rows = df_to_use[df_to_use["customer_id"] == customer_id]
        if selected_rows.empty:
            raise KeyError(f"Customer '{customer_id}' not found in dataset.")

        selected_row = selected_rows.iloc[0]
        selected_dict = selected_row.to_dict()

        # Build feature vector for selected customer
        selected_df = self._prepare_dataframe(pd.DataFrame([selected_dict]))
        selected_vec = self.pipeline.transform(selected_df)

        # Query KNN for n_neighbors + 2 to ensure enough neighbors after excluding self
        k_query = min(n_neighbors + 3, len(self.customer_ids))
        distances, indices = self.knn_model.kneighbors(selected_vec, n_neighbors=k_query)

        # Parse neighbors and strictly exclude the selected customer
        similar_customers = []
        for dist, idx in zip(distances[0], indices[0]):
            candidate_id = self.customer_ids[idx]
            if candidate_id == customer_id:
                # Exclude self-match
                continue

            # Lookup full data for this neighbor
            cand_rows = df_to_use[df_to_use["customer_id"] == candidate_id]
            if cand_rows.empty:
                continue
            cand_row = cand_rows.iloc[0]

            # Actual historical outcome from dataset
            # Only use actual ground-truth 'churn' column: 0 = Retained, 1 = Churned
            actual_churn_val = cand_row.get("churn")
            if pd.notna(actual_churn_val):
                hist_churn_int = int(actual_churn_val)
                hist_outcome_str = "Churned" if hist_churn_int == 1 else "Retained"
            else:
                hist_churn_int = None
                hist_outcome_str = "Unknown"

            # Churn probability calculation / lookup
            churn_prob = cand_row.get("churn_prob")
            if pd.isna(churn_prob) or churn_prob is None:
                # Try raw dataset churn_probability
                churn_prob = cand_row.get("churn_probability")

            if (pd.isna(churn_prob) or churn_prob is None) and xgboost_model and build_feature_row_fn:
                try:
                    feat_row = build_feature_row_fn(cand_row.to_dict())
                    churn_prob = float(xgboost_model.predict_proba(feat_row)[0][1])
                except Exception:
                    churn_prob = 0.5

            churn_prob = float(churn_prob) if (churn_prob is not None and not pd.isna(churn_prob)) else 0.0

            risk_level = "HIGH" if churn_prob >= 0.70 else "MEDIUM" if churn_prob >= 0.40 else "LOW"

            similarity_pct = self.calculate_similarity_score(dist)

            neighbor_info = {
                "customer_id": candidate_id,
                "name": str(cand_row.get("name", "")),
                "similarity_score": similarity_pct,
                "distance": round(float(dist), 4),
                "similarity_explanation": f"Distance-derived similarity: {similarity_pct}% based on Euclidean metric in normalized behavioral feature space.",
                "historical_churn": hist_churn_int,
                "historical_outcome": hist_outcome_str,
                "churn_prob": round(churn_prob, 4),
                "churn_percent": f"{churn_prob * 100:.1f}%",
                "risk_level": risk_level,
                "plan_type": str(cand_row.get("plan_type", "Basic")),
                "monthly_charge": int(cand_row.get("monthly_charge", 0)),
                "tenure_months": int(cand_row.get("tenure_months", 0)),
                "watch_hours_per_week": round(float(cand_row.get("watch_hours_per_week", 0) or 0), 1),
                "logins_last_30_days": int(cand_row.get("logins_last_30_days", 0)),
                "last_login_days_ago": int(cand_row.get("last_login_days_ago", 0)),
                "payment_failures_3m": int(cand_row.get("payment_failures_3m", 0)),
                "support_tickets": int(cand_row.get("support_tickets", 0)),
                "device_type": str(cand_row.get("device_type", "")),
                "preferred_genre": str(cand_row.get("preferred_genre", "")),
                "payment_method": str(cand_row.get("payment_method", "")),
                "num_profiles": int(cand_row.get("num_profiles", 1)),
                "age": int(cand_row.get("age", 0)),
            }
            similar_customers.append(neighbor_info)

            if len(similar_customers) == n_neighbors:
                break

        # Selected customer profile details
        sel_churn_prob = selected_row.get("churn_prob")
        if pd.isna(sel_churn_prob) or sel_churn_prob is None:
            sel_churn_prob = selected_row.get("churn_probability")
        if (pd.isna(sel_churn_prob) or sel_churn_prob is None) and xgboost_model and build_feature_row_fn:
            try:
                feat_row = build_feature_row_fn(selected_dict)
                sel_churn_prob = float(xgboost_model.predict_proba(feat_row)[0][1])
            except Exception:
                sel_churn_prob = 0.5
        sel_churn_prob = float(sel_churn_prob) if (sel_churn_prob is not None and not pd.isna(sel_churn_prob)) else 0.0

        sel_hist_churn = selected_row.get("churn")
        sel_hist_outcome = (
            "Churned" if int(sel_hist_churn) == 1 else "Retained"
        ) if pd.notna(sel_hist_churn) else "Active"

        selected_customer_payload = {
            "customer_id": customer_id,
            "name": str(selected_row.get("name", "")),
            "plan_type": str(selected_row.get("plan_type", "Basic")),
            "monthly_charge": int(selected_row.get("monthly_charge", 0)),
            "tenure_months": int(selected_row.get("tenure_months", 0)),
            "watch_hours_per_week": round(float(selected_row.get("watch_hours_per_week", 0) or 0), 1),
            "logins_last_30_days": int(selected_row.get("logins_last_30_days", 0)),
            "last_login_days_ago": int(selected_row.get("last_login_days_ago", 0)),
            "payment_failures_3m": int(selected_row.get("payment_failures_3m", 0)),
            "support_tickets": int(selected_row.get("support_tickets", 0)),
            "device_type": str(selected_row.get("device_type", "")),
            "preferred_genre": str(selected_row.get("preferred_genre", "")),
            "payment_method": str(selected_row.get("payment_method", "")),
            "num_profiles": int(selected_row.get("num_profiles", 1)),
            "age": int(selected_row.get("age", 0)),
            "churn_prob": round(sel_churn_prob, 4),
            "churn_percent": f"{sel_churn_prob * 100:.1f}%",
            "risk_level": "HIGH" if sel_churn_prob >= 0.70 else "MEDIUM" if sel_churn_prob >= 0.40 else "LOW",
            "historical_churn": int(sel_hist_churn) if pd.notna(sel_hist_churn) else None,
            "historical_outcome": sel_hist_outcome,
        }

        # Generate factual, evidence-backed insights based on actual returned neighbors
        insights = self._generate_factual_insights(selected_customer_payload, similar_customers)

        return {
            "selected_customer": selected_customer_payload,
            "similar_customers": similar_customers,
            "count": len(similar_customers),
            "insights": insights,
        }

    def _generate_factual_insights(
        self,
        selected: Dict[str, Any],
        neighbors: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate strict, factual insights derived directly from data without hallucinating.
        """
        if not neighbors:
            return ["No similar customer records found for comparison."]

        insights = []
        n_count = len(neighbors)

        # 1. Historical Churn Distribution among lookalikes
        churned_neighbors = [n for n in neighbors if n.get("historical_churn") == 1]
        retained_neighbors = [n for n in neighbors if n.get("historical_churn") == 0]
        churn_pct = round((len(churned_neighbors) / n_count) * 100)

        if len(churned_neighbors) > 0:
            insights.append(
                f"{len(churned_neighbors)} of the {n_count} most similar historical customers ({churn_pct}%) previously churned."
            )
        else:
            insights.append(
                f"All {n_count} similar historical customers successfully remained retained."
            )

        # 2. Watch Hours & Engagement comparison
        avg_watch = round(sum(n["watch_hours_per_week"] for n in neighbors) / n_count, 1)
        sel_watch = selected["watch_hours_per_week"]
        diff_watch = round(sel_watch - avg_watch, 1)

        if abs(diff_watch) <= 1.5:
            insights.append(
                f"This customer's weekly viewing time ({sel_watch} hrs/wk) is very closely aligned with lookalike average ({avg_watch} hrs/wk)."
            )
        elif diff_watch > 0:
            insights.append(
                f"This customer watches {abs(diff_watch)} more hours/week than similar historical customers (average {avg_watch} hrs/wk)."
            )
        else:
            insights.append(
                f"This customer watches {abs(diff_watch)} fewer hours/week than similar historical customers (average {avg_watch} hrs/wk)."
            )

        # 3. Billing & Support Friction
        avg_failures = round(sum(n["payment_failures_3m"] for n in neighbors) / n_count, 1)
        sel_failures = selected["payment_failures_3m"]
        avg_tickets = round(sum(n["support_tickets"] for n in neighbors) / n_count, 1)
        sel_tickets = selected["support_tickets"]

        if sel_failures > 0 or avg_failures > 0:
            churned_with_failures = len([n for n in churned_neighbors if n["payment_failures_3m"] > 0])
            if churned_with_failures > 0:
                insights.append(
                    f"{churned_with_failures} of the churned lookalikes had recurring payment failures in their final 3 months."
                )

        # 4. Plan & Tenure distribution
        same_plan = len([n for n in neighbors if n["plan_type"] == selected["plan_type"]])
        if same_plan >= 3:
            insights.append(
                f"{same_plan} of the {n_count} nearest lookalikes share the exact same {selected['plan_type']} subscription plan."
            )

        # 5. Login frequency comparison
        avg_logins = round(sum(n["logins_last_30_days"] for n in neighbors) / n_count, 1)
        sel_logins = selected["logins_last_30_days"]
        if sel_logins < avg_logins - 3:
            insights.append(
                f"Selected customer has lower monthly login activity ({sel_logins} logins) compared to similar peers ({avg_logins} logins)."
            )

        return insights
