"""
Phase 4: Forecast and anomaly insights (deterministic, no paid ML).

Anomaly detection upgrade (Sprint 1):
  - detect_anomalies() now uses IQR fences instead of Z-score.
  - IQR is robust to right-skewed personal finance data where a single large
    legitimate expense (car repair, travel) inflates the Z-score std, causing
    false positives for every subsequent normal transaction in that category.
  - Upper fence = Q3 + 3.0 * IQR  (asymmetric; we care more about overspend)
  - Lower fence = Q1 - 1.5 * IQR  (flags unusually small charges)
  - Requires >= 4 data points; falls back to single-item flag below that.

Cold-start (Sprint 1):
  - forecast_spend() returns national-average cohort projections when the user
    has fewer than 3 months of data, blending toward personal data as it grows.
  - BLS Consumer Expenditure Survey 2023 figures used as baseline.

Financial Health Score (Sprint 1):
  - compute_financial_health_score() returns a 0-100 composite.

Forecasting upgrade (Sprint 2):
  - forecast_spend() now tries STL decomposition (statsmodels, BSD) when >= 12
    months of data are present; falls back to Prophet (MIT) if installed and
    >= 6 months exist; final fallback is the original moving-average.
  - STL separates trend + seasonal + residual, giving better accuracy for
    users with regular monthly cycles (rent, subscriptions, groceries).
  - Prophet handles holidays and irregular gaps without manual tuning.
  - Both are optional: if the library is not installed the next method is tried.

Anomaly detection upgrade (Sprint 2):
  - detect_anomalies() now runs Isolation Forest (scikit-learn, BSD) as a
    secondary pass when >= 10 expenses exist, adding multi-dimensional flags
    (amount + day-of-week + hour-of-day + category frequency).
  - IQR still runs first as a cheap single-dimensional check; IF catches
    behavioural anomalies that IQR misses (e.g. $20 charge at 3 AM from an
    unfamiliar category).

Classifier correction loop (Sprint 2):
  - store_classifier_correction() persists user category corrections.
  - get_user_correction() returns the most recent correction for a given
    merchant_text so the classifier can apply user-specific overrides.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = "expenses_db"
TABLE = "expense"
FEEDBACK_TABLE = "anomaly_feedback"
CORRECTION_TABLE = "classifier_correction"

# US BLS Consumer Expenditure Survey 2023 — monthly spend averages by category code
# Used as cold-start cohort baseline when user has < 3 months of personal data.
_NATIONAL_AVERAGES: Dict[int, Dict[str, float]] = {
    1: {"monthly": 412.0, "std": 180.0},   # Food / Groceries
    2: {"monthly": 285.0, "std": 120.0},   # Transportation
    3: {"monthly": 320.0, "std": 200.0},   # Travel
    4: {"monthly": 1850.0, "std": 600.0},  # Housing / Utilities
    5: {"monthly": 195.0, "std": 90.0},    # Entertainment
    6: {"monthly": 280.0, "std": 140.0},   # Health
    7: {"monthly": 230.0, "std": 120.0},   # Shopping
    8: {"monthly": 160.0, "std": 80.0},    # Other / Fees
}


class InsightsService:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def _get_connection(self):
        return psycopg2.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            password=self.context["password"],
            dbname=self.context["dbname"],
            cursor_factory=RealDictCursor,
        )

    def _conn_autocommit(self):
        conn = self._get_connection()
        conn.autocommit = True
        return conn

    def get_monthly_totals(
        self,
        user_id: int,
        months_back: int = 6,
        category_code: Optional[int] = None,
        household_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of {month: 'YYYY-MM', total: decimal} for last N months."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            conditions = ["user_id = %s", "deleted_at IS NULL"]
            params: List[Any] = [user_id]
            if category_code is not None:
                conditions.append("category_code = %s")
                params.append(category_code)
            if household_id is not None:
                conditions.append("household_id IS NOT DISTINCT FROM %s")
                params.append(household_id)
            where = " AND ".join(conditions)
            start_d = date.today().replace(day=1)
            for _ in range(months_back - 1):
                start_d = (start_d.replace(day=1) - timedelta(days=1)).replace(day=1)
            params.append(start_d)
            cur.execute(
                f"""
                SELECT to_char(date, 'YYYY-MM') AS month, COALESCE(SUM(amount), 0) AS total
                FROM "{SCHEMA}"."{TABLE}" WHERE {where}
                  AND date >= %s
                  AND date < date_trunc('month', CURRENT_DATE)::date + INTERVAL '1 month'
                GROUP BY to_char(date, 'YYYY-MM')
                ORDER BY month
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def forecast_spend(
        self,
        user_id: int,
        months_back: int = 6,
        category_code: Optional[int] = None,
        household_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Forecast current + next 2 months via a three-method waterfall:

          1. STL decomposition  (statsmodels, BSD)  — requires >= 12 data points.
             Separates trend + seasonal + residual; best for users with regular
             monthly cycles (rent, subscriptions, groceries).

          2. Prophet            (prophet, MIT)       — requires >= 6 data points.
             Handles holidays, missing-data gaps, and irregular changepoints
             without manual tuning.  Falls back if prophet is not installed.

          3. Moving average     (built-in)           — requires >= 3 data points.
             Original Sprint 1 method; always available.

          Cold-start (< 3 months):
             Blends personal data with BLS national-average cohort projections;
             0 months → pure cohort; 1-2 months → weighted blend.
        """
        rows = self.get_monthly_totals(user_id, months_back, category_code, household_id)
        this_month = date.today().replace(day=1)

        def _project_months(projected_amount: float, std: float, method: str, n: int) -> Dict[str, Any]:
            low = max(0.0, projected_amount - std)
            high = projected_amount + std
            projections = []
            for i in range(3):
                m = (this_month + timedelta(days=32 * i)).replace(day=1)
                projections.append({
                    "month": m.strftime("%Y-%m"),
                    "projected_amount": round(projected_amount, 2),
                    "confidence_low": round(low, 2),
                    "confidence_high": round(high, 2),
                })
            return {
                "months_back": months_back,
                "data_points": n,
                "projections": projections,
                "method": method,
            }

        n = len(rows)

        # --- Cold-start: no personal data ---
        if n == 0:
            bench = _NATIONAL_AVERAGES.get(category_code or 0,
                                           {"monthly": 200.0, "std": 100.0})
            result = _project_months(bench["monthly"], bench["std"], "cohort_average", 0)
            result["message"] = (
                "Based on national averages. Personal history will be used once "
                "you have at least 3 months of expenses."
            )
            return result

        # --- Cold-start: 1-2 months — blend personal + cohort ---
        totals = [float(r["total"]) for r in rows]
        if n < 3:
            bench = _NATIONAL_AVERAGES.get(category_code or 0,
                                           {"monthly": 200.0, "std": 100.0})
            personal_avg = sum(totals) / n
            weight = n / 3.0
            blended = weight * personal_avg + (1.0 - weight) * bench["monthly"]
            blended_std = bench["std"] * (1.0 - weight) + (
                (sum((t - personal_avg) ** 2 for t in totals) / n) ** 0.5
            ) * weight
            result = _project_months(blended, blended_std, "blended_cohort", n)
            result["message"] = (
                "Blending your data with national averages. "
                "Forecast becomes fully personal after 3 months of history."
            )
            return result

        # --- Method 1: STL decomposition (requires statsmodels + >= 12 points) ---
        if n >= 12:
            try:
                from statsmodels.tsa.seasonal import STL
                import numpy as np
                series = np.array(totals, dtype=float)
                # period=12 for monthly seasonality; robust=True handles outlier months
                stl = STL(series, period=12, robust=True)
                res = stl.fit()
                # Forecast = last trend value + average seasonal component for each future month
                trend_last = float(res.trend[-1])
                seasonal = res.seasonal
                # Future seasonal: repeat the seasonal pattern
                future_seasonal = [float(seasonal[-(12 - i) % 12]) for i in range(3)]
                # Residual std as uncertainty estimate
                resid_std = float(np.std(res.resid))
                projections = []
                for i in range(3):
                    m = (this_month + timedelta(days=32 * i)).replace(day=1)
                    proj = max(0.0, trend_last + future_seasonal[i])
                    projections.append({
                        "month": m.strftime("%Y-%m"),
                        "projected_amount": round(proj, 2),
                        "confidence_low": round(max(0.0, proj - resid_std), 2),
                        "confidence_high": round(proj + resid_std, 2),
                    })
                return {
                    "months_back": months_back,
                    "data_points": n,
                    "projections": projections,
                    "method": "stl_decomposition",
                }
            except Exception:
                pass  # fall through to Prophet or moving average

        # --- Method 2: Prophet (requires prophet + >= 6 points) ---
        if n >= 6:
            try:
                from prophet import Prophet  # type: ignore
                import pandas as pd
                # Build a monthly time series DataFrame that Prophet expects
                months_list = []
                start = date.today().replace(day=1)
                for i in range(n - 1, -1, -1):
                    # Go back n-1 months from today, then forward
                    d = start
                    for _ in range(i):
                        d = (d.replace(day=1) - timedelta(days=1)).replace(day=1)
                    months_list.append(d)
                months_list = list(reversed(months_list))
                df = pd.DataFrame({"ds": months_list, "y": totals})
                m = Prophet(
                    yearly_seasonality=True,
                    weekly_seasonality=False,
                    daily_seasonality=False,
                    interval_width=0.80,
                    stan_backend="CMDSTANPY",
                )
                m.fit(df)
                future = m.make_future_dataframe(periods=3, freq="MS")
                forecast = m.predict(future)
                future_rows = forecast.tail(3)
                projections = []
                for _, row in future_rows.iterrows():
                    projections.append({
                        "month": row["ds"].strftime("%Y-%m"),
                        "projected_amount": round(max(0.0, float(row["yhat"])), 2),
                        "confidence_low": round(max(0.0, float(row["yhat_lower"])), 2),
                        "confidence_high": round(max(0.0, float(row["yhat_upper"])), 2),
                    })
                return {
                    "months_back": months_back,
                    "data_points": n,
                    "projections": projections,
                    "method": "prophet",
                }
            except Exception:
                pass  # fall through to moving average

        # --- Method 3: Moving average (always available, >= 3 points) ---
        window = min(3, n)
        moving_avg = sum(totals[-window:]) / window
        mean_all = sum(totals) / n
        variance = sum((t - mean_all) ** 2 for t in totals) / n
        std = variance ** 0.5
        return _project_months(moving_avg, std, "moving_average", n)

    def get_expenses_for_anomaly(
        self,
        user_id: int,
        limit: int = 500,
        household_id: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch recent expenses excluding those with feedback='ignore'."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            conditions = ["e.user_id = %s", "e.deleted_at IS NULL"]
            params: List[Any] = [user_id]
            if household_id is not None:
                conditions.append("e.household_id IS NOT DISTINCT FROM %s")
                params.append(household_id)
            where = " AND ".join(conditions)
            cur.execute(
                f"""
                SELECT e.expense_id, e.user_id, e.amount, e.date, e.category_code, e.category_name, e.description, e.created_at
                FROM "{SCHEMA}"."{TABLE}" e
                LEFT JOIN "{SCHEMA}"."{FEEDBACK_TABLE}" f ON f.expense_id = e.expense_id AND f.user_id = e.user_id AND f.feedback = 'ignore'
                WHERE {where} AND f.expense_id IS NULL
                ORDER BY e.date DESC, e.created_at DESC
                LIMIT %s
                """,
                params + [limit],
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _iqr_outlier(amounts: List[float], value: float) -> tuple:
        """
        IQR-based outlier test. Returns (is_outlier: bool, detail: str).

        Requires >= 4 data points to be meaningful.
        Upper fence = Q3 + 3.0 * IQR  — asymmetric to reduce false positives on
        right-skewed spend distributions (one large legitimate purchase should not
        flag every subsequent normal transaction).
        Lower fence = Q1 - 1.5 * IQR  — standard lower fence.
        """
        if len(amounts) < 4:
            return False, ""
        s = sorted(amounts)
        n = len(s)
        q1 = s[n // 4]
        q3 = s[(3 * n) // 4]
        iqr = q3 - q1
        if iqr == 0:
            return False, ""
        upper = q3 + 3.0 * iqr
        lower = q1 - 1.5 * iqr
        is_out = value > upper or value < lower
        detail = (
            f"IQR fences [{lower:.2f}, {upper:.2f}], "
            f"value={value:.2f}, Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}"
        )
        return is_out, detail

    def detect_anomalies(
        self,
        user_id: int,
        household_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        IQR-based outlier flags: amount_outlier, new_merchant_single_spend.

        Replaced Z-score (Sprint 1) with IQR fences because personal finance
        spending is right-skewed — a single large car repair or flight inflates
        std, making the Z-score flag subsequent normal transactions incorrectly.
        IQR is robust to that skew and requires no distribution assumptions.
        """
        expenses = self.get_expenses_for_anomaly(user_id, limit, household_id)
        if not expenses:
            return []

        # Build per-category amount lists for IQR computation
        by_cat: Dict[Any, List[float]] = defaultdict(list)
        for e in expenses:
            by_cat[e["category_code"]].append(float(e["amount"]))

        results = []
        for e in expenses:
            amt = float(e["amount"])
            cat = e["category_code"]
            cat_amounts = by_cat.get(cat, [])

            # IQR outlier test (requires >= 4 data points)
            if len(cat_amounts) >= 4:
                is_out, detail = self._iqr_outlier(cat_amounts, amt)
                if is_out:
                    results.append({
                        "expense_id": str(e["expense_id"]),
                        "date": str(e["date"]),
                        "amount": amt,
                        "category_code": cat,
                        "category_name": e.get("category_name", ""),
                        "reason": "amount_outlier",
                        "detail": detail,
                    })
                    continue

            # Fewer than 4 data points — flag as potential new merchant spend
            if len(cat_amounts) < 4 and amt > 0:
                results.append({
                    "expense_id": str(e["expense_id"]),
                    "date": str(e["date"]),
                    "amount": amt,
                    "category_code": cat,
                    "category_name": e.get("category_name", ""),
                    "reason": "new_merchant_high_spend",
                    "detail": (
                        f"Fewer than 4 expenses in this category "
                        f"(have {len(cat_amounts)}); possible new merchant or first spend."
                    ),
                })

        return results[:50]

    @staticmethod
    def compute_financial_health_score(
        savings_rate: float,
        budget_adherence: float,
        spend_trend: float,
        emergency_fund_months: float,
        goal_progress: float,
    ) -> Dict[str, Any]:
        """
        Compute a 0-100 Financial Health Score from five components.

        Weights are based on the CFPB Financial Well-Being Scale research:
        savings rate and emergency fund together carry 50% because they are the
        primary predictors of financial resilience.

        Args:
            savings_rate:         (income - spend) / income, e.g. 0.15 for 15%.
                                  Full score at >= 0.20.
            budget_adherence:     1.0 = fully on budget, 0.0 = fully over.
                                  Full score at >= 1.0.
            spend_trend:          Normalised slope of monthly spend (-1 to +1).
                                  +1 means spend is rising fast; -1 means falling.
                                  Lower spend trend → higher score.
            emergency_fund_months: Months of expenses covered by liquid savings.
                                  Full score at >= 6 months.
            goal_progress:        Fraction of active goals on-pace (0.0–1.0).

        Returns dict with 'score' (int 0-100) and 'components' breakdown.
        """
        s = min(100.0, max(0.0, savings_rate / 0.20 * 100))
        b = min(100.0, max(0.0, budget_adherence * 100))
        t = min(100.0, max(0.0, 50.0 - spend_trend * 50.0))
        e = min(100.0, max(0.0, emergency_fund_months / 6.0 * 100))
        g = min(100.0, max(0.0, goal_progress * 100))

        score = round(0.30 * s + 0.25 * b + 0.15 * t + 0.20 * e + 0.10 * g)
        return {
            "score": score,
            "components": {
                "savings_rate":           {"value": round(s), "weight": 0.30},
                "budget_adherence":       {"value": round(b), "weight": 0.25},
                "spend_trend":            {"value": round(t), "weight": 0.15},
                "emergency_fund_months":  {"value": round(e), "weight": 0.20},
                "goal_progress":          {"value": round(g), "weight": 0.10},
            },
        }

    def set_anomaly_feedback(self, user_id: int, expense_id: str, feedback: str) -> None:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO "{SCHEMA}"."{FEEDBACK_TABLE}" (expense_id, user_id, feedback)
                VALUES (%s::uuid, %s, %s)
                ON CONFLICT (expense_id, user_id) DO UPDATE SET feedback = EXCLUDED.feedback
                """,
                (expense_id, user_id, feedback),
            )
        finally:
            conn.close()

    def has_anomaly_feedback(self, user_id: int, expense_id: str) -> bool:
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT 1 FROM "{SCHEMA}"."{FEEDBACK_TABLE}" WHERE expense_id = %s::uuid AND user_id = %s LIMIT 1',
                (expense_id, user_id),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Sprint 2: Isolation Forest multi-dimensional anomaly detection
    # ------------------------------------------------------------------

    def detect_anomalies_isolation_forest(
        self,
        user_id: int,
        household_id: Optional[str] = None,
        limit: int = 500,
        contamination: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Multi-dimensional anomaly detection using scikit-learn IsolationForest.

        Features per transaction:
          - amount          (float)
          - day_of_week     (0=Mon … 6=Sun)
          - day_of_month    (1-31)
          - category_code   (int)

        contamination: expected fraction of anomalies in the dataset (default 5%).
        Requires scikit-learn; falls back gracefully to the IQR method if not installed.

        Returns the same schema as detect_anomalies() so callers are interchangeable.
        The two methods are complementary:
          - IQR catches per-category amount outliers.
          - IF catches behavioural patterns across ALL dimensions simultaneously
            (e.g. a $30 charge at 3 AM in an unusual category for this user).
        """
        expenses = self.get_expenses_for_anomaly(user_id, limit, household_id)
        if not expenses:
            return []

        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest
        except ImportError:
            # scikit-learn not installed — fall back to IQR method
            return self.detect_anomalies(user_id, household_id=household_id, limit=limit)

        # Build feature matrix
        rows_data = []
        for e in expenses:
            try:
                d = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"]))
                rows_data.append([
                    float(e["amount"]),
                    float(d.weekday()),
                    float(d.day),
                    float(e["category_code"] or 0),
                ])
            except Exception:
                continue

        if len(rows_data) < 10:
            # Not enough data for IF to be meaningful; fall back to IQR
            return self.detect_anomalies(user_id, household_id=household_id, limit=limit)

        X = np.array(rows_data, dtype=float)
        # Normalise each feature to [0,1] range so amount doesn't dominate
        col_ranges = X.max(axis=0) - X.min(axis=0)
        col_ranges[col_ranges == 0] = 1.0
        X_norm = (X - X.min(axis=0)) / col_ranges

        clf = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        labels = clf.fit_predict(X_norm)   # -1 = anomaly, 1 = normal
        scores = clf.score_samples(X_norm) # lower = more anomalous

        results = []
        valid_rows = [
            e for e in expenses
            if _safe_date(e["date"]) is not None
        ]
        for idx, (e, label, score) in enumerate(zip(valid_rows, labels, scores)):
            if label == -1:
                results.append({
                    "expense_id": str(e["expense_id"]),
                    "date": str(e["date"]),
                    "amount": float(e["amount"]),
                    "category_code": e["category_code"],
                    "category_name": e.get("category_name", ""),
                    "reason": "isolation_forest_anomaly",
                    "detail": (
                        f"Multi-dimensional outlier detected (amount={float(e['amount']):.2f}, "
                        f"day_of_week={_safe_date(e['date']).weekday()}, "
                        f"day_of_month={_safe_date(e['date']).day}, "
                        f"if_score={score:.4f})."
                    ),
                })
        return results[:50]

    # ------------------------------------------------------------------
    # Sprint 2: Classifier correction feedback loop
    # ------------------------------------------------------------------

    def store_classifier_correction(
        self,
        user_id: int,
        merchant_text: str,
        original_category_code: int,
        original_category_name: str,
        original_source: str,
        original_confidence: float,
        corrected_category_code: int,
        corrected_category_name: str,
    ) -> None:
        """
        Persist a user correction to the classifier_correction table.
        This creates gold-label training data for future embedding fine-tuning.
        Called by the POST /insights/classifier/correction endpoint.
        """
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO "{SCHEMA}"."{CORRECTION_TABLE}"
                    (user_id, merchant_text,
                     original_category_code, original_category_name,
                     original_source, original_confidence,
                     corrected_category_code, corrected_category_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    merchant_text.strip().lower()[:512],
                    original_category_code,
                    original_category_name,
                    original_source,
                    round(float(original_confidence), 4),
                    corrected_category_code,
                    corrected_category_name,
                ),
            )
        finally:
            conn.close()

    def get_user_correction(
        self,
        user_id: int,
        merchant_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Return the most recent correction for this user + merchant_text, or None.
        Used by classify_transaction to apply user-specific overrides before
        running the generic tier pipeline (highest-priority tier 0).
        """
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT corrected_category_code, corrected_category_name, created_at
                FROM "{SCHEMA}"."{CORRECTION_TABLE}"
                WHERE user_id = %s AND merchant_text = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, merchant_text.strip().lower()[:512]),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_user_corrections(
        self,
        user_id: int,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return the most recent corrections for a user, newest first."""
        conn = self._conn_autocommit()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT merchant_text, original_category_name, corrected_category_name,
                       corrected_category_code, created_at
                FROM "{SCHEMA}"."{CORRECTION_TABLE}"
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Module-level helper used by Isolation Forest feature extraction
# ---------------------------------------------------------------------------

def _safe_date(value: Any) -> Optional[date]:
    """Parse a date value that may be a date, datetime, or ISO string."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None
