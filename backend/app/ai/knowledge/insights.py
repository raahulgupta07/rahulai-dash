"""Proactive Insights — pure-function anomaly + trend scanner.

Scans a pandas DataFrame produced by a create_data step and returns a
capped list of insight dicts with no LLM calls and no I/O. Always
fail-soft: any error returns [].

Public surface
--------------
    compute_insights(df) -> list[dict]

Each dict:
    {
        "kind":     "outlier" | "spike" | "trend",
        "column":   "<col name>",
        "message":  "<human-readable one-liner>",
        "severity": "high" | "medium" | "low",
    }

Cap: at most MAX_INSIGHTS (5) total, preference order:
    high-severity first, then by column discovery order.

Design rules
------------
- NO LLM, NO network, NO DB.
- Pure pandas + stdlib math only (scipy is NOT available in the image;
  z-scores are computed by hand).
- All public entry-points catch every exception and return [] — never
  raises into the caller.
- Flag gate is applied by the CALLER (create_data.py), not here, so
  unit tests can call these functions directly without a flag env.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

MAX_INSIGHTS = 5
# Z-score threshold for "high" outlier signal.
_Z_HIGH = 3.0
# Z-score threshold for "medium" outlier signal.
_Z_MED = 2.5
# Minimum non-null rows needed to attempt a scan.
_MIN_ROWS = 3
# IQR fence multiplier (Tukey outer fence).
_IQR_FENCE = 1.5
# Minimum % jump (last-point vs trailing mean) to flag as a spike.
_SPIKE_PCT_HIGH = 50.0
_SPIKE_PCT_MED = 25.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: List[float], mean: float) -> float:
    if len(vals) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return math.sqrt(variance)


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Simple linear-interpolation percentile on a sorted list."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    idx = p / 100.0 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _severity_label(high: bool, med: bool) -> str:
    if high:
        return "high"
    if med:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Outlier scan: z-score AND IQR on each numeric column
# ---------------------------------------------------------------------------

def _scan_outliers(df: Any) -> List[Dict[str, Any]]:
    """Return one insight per numeric column that has >=1 outlier value."""
    try:
        import pandas as pd  # type: ignore

        results: List[Dict[str, Any]] = []
        numeric_cols = df.select_dtypes(include="number").columns.tolist()

        for col in numeric_cols:
            try:
                series = df[col].dropna()
                vals: List[float] = [float(v) for v in series if _is_finite(v)]
                if len(vals) < _MIN_ROWS:
                    continue

                mean = _mean(vals)
                std = _std(vals, mean)

                # --- z-score ---
                z_outlier_count = 0
                z_max = 0.0
                if std > 0:
                    for v in vals:
                        z = abs(v - mean) / std
                        if z >= _Z_MED:
                            z_outlier_count += 1
                            z_max = max(z_max, z)

                # --- IQR ---
                sorted_vals = sorted(vals)
                q1 = _percentile(sorted_vals, 25)
                q3 = _percentile(sorted_vals, 75)
                iqr = q3 - q1
                iqr_outlier_count = 0
                if iqr > 0:
                    lo_fence = q1 - _IQR_FENCE * iqr
                    hi_fence = q3 + _IQR_FENCE * iqr
                    iqr_outlier_count = sum(
                        1 for v in vals if v < lo_fence or v > hi_fence
                    )

                # Only report when BOTH methods agree, or z-score is very strong.
                n_outliers = max(z_outlier_count, iqr_outlier_count)
                if n_outliers == 0:
                    continue

                is_high = z_max >= _Z_HIGH or (z_outlier_count > 0 and iqr_outlier_count > 0)
                is_med = n_outliers > 0

                msg = (
                    f"'{col}' has {n_outliers} unusual value"
                    f"{'s' if n_outliers != 1 else ''} "
                    f"(z-score up to {z_max:.1f}x std, "
                    f"IQR check: {iqr_outlier_count} outside fence)"
                )
                results.append({
                    "kind": "outlier",
                    "column": col,
                    "message": msg,
                    "severity": _severity_label(is_high, is_med),
                })
            except Exception:
                continue

        return results
    except Exception:
        return []


def _is_finite(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Trend/spike scan: temporal sort + last-point % jump
# ---------------------------------------------------------------------------

def _scan_trend(df: Any) -> List[Dict[str, Any]]:
    """Detect a spike in the last data point vs the trailing mean.

    Strategy:
      1. Find the first date/datetime column (temporal anchor).
      2. Sort by it.
      3. For each numeric column, compare the last value to the mean of the
         preceding points. Flag as spike if the jump exceeds the threshold.
    """
    try:
        import pandas as pd  # type: ignore

        results: List[Dict[str, Any]] = []

        # Find a temporal column.
        date_col: Optional[str] = None
        for col in df.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    date_col = col
                    break
            except Exception:
                continue
        if date_col is None:
            # Try to parse any object column that looks like a date.
            for col in df.select_dtypes(include=["object"]).columns:
                try:
                    sample = df[col].dropna().head(5)
                    parsed = pd.to_datetime(sample, errors="coerce")
                    if parsed.notna().sum() >= 3:
                        date_col = col
                        break
                except Exception:
                    continue

        if date_col is None or len(df) < _MIN_ROWS + 1:
            return []

        try:
            df_sorted = df.sort_values(date_col).reset_index(drop=True)
        except Exception:
            return []

        numeric_cols = df_sorted.select_dtypes(include="number").columns.tolist()

        for col in numeric_cols:
            try:
                series = df_sorted[col].dropna()
                if len(series) < _MIN_ROWS + 1:
                    continue
                vals = [float(v) for v in series if _is_finite(v)]
                if len(vals) < _MIN_ROWS + 1:
                    continue

                last = vals[-1]
                preceding = vals[:-1]
                trail_mean = _mean(preceding)

                if trail_mean == 0:
                    continue

                pct_change = ((last - trail_mean) / abs(trail_mean)) * 100.0
                abs_pct = abs(pct_change)

                if abs_pct < _SPIKE_PCT_MED:
                    continue

                direction = "spike up" if pct_change > 0 else "drop"
                is_high = abs_pct >= _SPIKE_PCT_HIGH
                msg = (
                    f"'{col}' shows a {direction} of {abs_pct:.1f}% in the latest "
                    f"period vs trailing average "
                    f"({last:,.2f} vs mean {trail_mean:,.2f})"
                )
                results.append({
                    "kind": "spike",
                    "column": col,
                    "message": msg,
                    "severity": _severity_label(is_high, True),
                })
            except Exception:
                continue

        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_insights(df: Any) -> List[Dict[str, Any]]:
    """Scan *df* for anomalies and trends; return up to MAX_INSIGHTS insights.

    Pure function — no LLM, no I/O, no exceptions propagated.

    Parameters
    ----------
    df : pandas.DataFrame (or anything with .select_dtypes + .columns)

    Returns
    -------
    list[dict]  — each with keys: kind, column, message, severity.
                  Empty list on any error or when df has no interesting signal.
    """
    try:
        if df is None:
            return []
        # Guard: need at least _MIN_ROWS rows.
        try:
            if len(df) < _MIN_ROWS:
                return []
        except Exception:
            return []

        raw: List[Dict[str, Any]] = []
        raw.extend(_scan_outliers(df))
        raw.extend(_scan_trend(df))

        if not raw:
            return []

        # Sort: high first, then medium, then low; stable within same severity.
        _order = {"high": 0, "medium": 1, "low": 2}
        raw.sort(key=lambda x: _order.get(x.get("severity", "low"), 2))

        return raw[:MAX_INSIGHTS]
    except Exception:
        return []
