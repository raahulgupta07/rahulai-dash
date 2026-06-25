"""Schemas for the ``forecast_df`` tool (Wave1 P3 — Prophet forecasting).

Takes a date column + value column (from the last query result or supplied
inline) and returns a Prophet forecast for N future periods (yhat, yhat_lower,
yhat_upper, ds).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ForecastInput(BaseModel):
    """Input for ``forecast_df``."""

    date_column: str = Field(
        ...,
        description=(
            "Name of the date/timestamp column in the last create_data result "
            "(must be parseable as a date). The agent should verify this column "
            "exists in the result df before calling."
        ),
        max_length=200,
    )
    value_column: str = Field(
        ...,
        description=(
            "Name of the numeric value column to forecast (e.g. 'revenue', "
            "'order_count'). Must be numeric."
        ),
        max_length=200,
    )
    periods: int = Field(
        30,
        description="Number of future periods to forecast (1–365). Defaults to 30.",
        ge=1,
        le=365,
    )
    freq: str = Field(
        "D",
        description=(
            "Pandas/Prophet frequency string: 'D' (daily), 'W' (weekly), "
            "'M' (monthly), 'H' (hourly). Defaults to 'D'."
        ),
        max_length=10,
    )
    data_source_id: Optional[str] = Field(
        None,
        description="Optional data source id for context (not used in computation).",
    )


class ForecastRow(BaseModel):
    ds: str = Field(..., description="Forecast date (ISO-8601 string).")
    yhat: float = Field(..., description="Point forecast.")
    yhat_lower: float = Field(..., description="Lower bound of prediction interval.")
    yhat_upper: float = Field(..., description="Upper bound of prediction interval.")


class ForecastOutput(BaseModel):
    success: bool
    rows: List[ForecastRow] = Field(default_factory=list)
    periods: int = 0
    date_column: str = ""
    value_column: str = ""
    message: Optional[str] = None
