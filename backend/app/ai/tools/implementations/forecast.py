"""forecast_df Tool — Prophet time-series forecast on the last query result.

Wave1 P3. Given a date column + value column from the agent's last
create_data result, fits a Prophet model and returns a forecast df
(yhat, yhat_lower, yhat_upper, ds) for N future periods.

Self-gates on ``flags.FORECAST``: when OFF the tool is hidden from the
planner catalog (registry.py ``get_catalog_for_plan_type`` excludes it by
name) and if somehow called returns a benign disabled message — so a fresh
deploy behaves exactly like upstream. Prophet is imported LAZILY inside
``run_stream`` so a missing installation never breaks boot.

Native ToolRegistry pattern (auto-registered by dropping this file in
implementations/). Mirrors ``resolve_metric.py`` structure.
"""
from typing import AsyncIterator, Dict, Any, Type
import logging

from pydantic import BaseModel

from app.ai.tools.base import Tool
from app.ai.tools.metadata import ToolMetadata
from app.ai.tools.schemas.events import (
    ToolEvent,
    ToolStartEvent,
    ToolEndEvent,
    ToolErrorEvent,
)
from app.ai.tools.schemas.forecast import (
    ForecastInput,
    ForecastOutput,
    ForecastRow,
)
from app.settings.hybrid_flags import flags

logger = logging.getLogger(__name__)


class ForecastDfTool(Tool):
    """Fit Prophet on a date+value series and return future forecast rows."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="forecast_df",
            description=(
                "Forecast future values from a date+value time series using Prophet. "
                "Pass the date column name and the numeric value column name from "
                "the last create_data result, plus how many periods ahead to forecast. "
                "Returns ds (date), yhat (forecast), yhat_lower, yhat_upper columns. "
                "Use this when the user asks for a forecast, prediction, or projection."
            ),
            category="both",
            version="1.0.0",
            input_schema=ForecastInput.model_json_schema(),
            output_schema=ForecastOutput.model_json_schema(),
            max_retries=1,
            timeout_seconds=120,
            idempotent=True,
            tags=["forecast", "timeseries", "analytics"],
            examples=[
                {
                    "input": {
                        "date_column": "order_date",
                        "value_column": "revenue",
                        "periods": 30,
                        "freq": "D",
                    },
                    "description": "30-day daily revenue forecast from last query result",
                },
                {
                    "input": {
                        "date_column": "month",
                        "value_column": "sales",
                        "periods": 6,
                        "freq": "M",
                    },
                    "description": "6-month sales forecast",
                },
            ],
        )

    @property
    def input_model(self) -> Type[BaseModel]:
        return ForecastInput

    @property
    def output_model(self) -> Type[BaseModel]:
        return ForecastOutput

    async def run_stream(
        self, tool_input: Dict[str, Any], runtime_ctx: Dict[str, Any]
    ) -> AsyncIterator[ToolEvent]:
        # --- Input validation ------------------------------------------------
        try:
            data = ForecastInput(**tool_input)
        except Exception as e:
            yield ToolErrorEvent(
                type="tool.error",
                payload={"error": f"Invalid input: {e}", "code": "INVALID_INPUT"},
            )
            return

        yield ToolStartEvent(
            type="tool.start",
            payload={
                "date_column": data.date_column,
                "value_column": data.value_column,
                "periods": data.periods,
                "freq": data.freq,
            },
        )

        # --- Flag gate -------------------------------------------------------
        if not flags.FORECAST:
            output = ForecastOutput(
                success=True,
                message="Forecasting tool is not enabled (HYBRID_FORECAST=0).",
            )
            yield ToolEndEvent(
                type="tool.end",
                payload={
                    "output": output.model_dump(),
                    "observation": {"summary": "Forecasting disabled; no forecast produced."},
                },
            )
            return

        # --- Lazy-import Prophet (never break boot if absent) ----------------
        try:
            import pandas as pd  # already in image
        except ImportError as e:
            yield ToolErrorEvent(
                type="tool.error",
                payload={
                    "error": f"pandas is not available: {e}",
                    "code": "MISSING_DEPENDENCY",
                },
            )
            return

        try:
            from prophet import Prophet  # lazy — installed only when flag ON
        except ImportError:
            yield ToolErrorEvent(
                type="tool.error",
                payload={
                    "error": (
                        "Prophet is not installed. "
                        "Add prophet==1.1.6 to requirements_versioned.txt and rebuild."
                    ),
                    "code": "MISSING_DEPENDENCY",
                },
            )
            return

        # --- Get the last result df from runtime context ---------------------
        # The agent's sandbox stores the last create_data result as a DataFrame
        # under the key 'last_result_df'. If absent, we cannot proceed.
        last_df = runtime_ctx.get("last_result_df")
        if last_df is None:
            yield ToolErrorEvent(
                type="tool.error",
                payload={
                    "error": (
                        "No result dataframe found in context. "
                        "Run create_data first to produce a date+value table, "
                        "then call forecast_df."
                    ),
                    "code": "NO_DATA",
                },
            )
            return

        # --- Validate columns ------------------------------------------------
        try:
            df = pd.DataFrame(last_df)
        except Exception as e:
            yield ToolErrorEvent(
                type="tool.error",
                payload={"error": f"Could not read result as DataFrame: {e}", "code": "DATA_ERROR"},
            )
            return

        if data.date_column not in df.columns:
            yield ToolErrorEvent(
                type="tool.error",
                payload={
                    "error": (
                        f"Column '{data.date_column}' not found in result. "
                        f"Available columns: {list(df.columns)}"
                    ),
                    "code": "COLUMN_NOT_FOUND",
                },
            )
            return

        if data.value_column not in df.columns:
            yield ToolErrorEvent(
                type="tool.error",
                payload={
                    "error": (
                        f"Column '{data.value_column}' not found in result. "
                        f"Available columns: {list(df.columns)}"
                    ),
                    "code": "COLUMN_NOT_FOUND",
                },
            )
            return

        # --- Fit Prophet and forecast ----------------------------------------
        try:
            prophet_df = df[[data.date_column, data.value_column]].copy()
            prophet_df.columns = ["ds", "y"]
            prophet_df["ds"] = pd.to_datetime(prophet_df["ds"], infer_datetime_format=True)
            prophet_df["y"] = pd.to_numeric(prophet_df["y"], errors="coerce")
            prophet_df = prophet_df.dropna(subset=["ds", "y"]).sort_values("ds")

            if len(prophet_df) < 2:
                yield ToolErrorEvent(
                    type="tool.error",
                    payload={
                        "error": (
                            f"Need at least 2 valid date+value rows to fit a forecast, "
                            f"got {len(prophet_df)}."
                        ),
                        "code": "INSUFFICIENT_DATA",
                    },
                )
                return

            # Suppress Prophet's verbose stdout/logging during fit.
            import logging as _logging
            _prophet_logger = _logging.getLogger("prophet")
            _prophet_logger.setLevel(_logging.WARNING)
            _cmdstan_logger = _logging.getLogger("cmdstanpy")
            _cmdstan_logger.setLevel(_logging.WARNING)

            model = Prophet(
                yearly_seasonality="auto",
                weekly_seasonality="auto",
                daily_seasonality="auto",
            )
            model.fit(prophet_df)

            future = model.make_future_dataframe(periods=data.periods, freq=data.freq)
            forecast = model.predict(future)

            # Return only the FUTURE periods (beyond last observed date).
            last_obs_date = prophet_df["ds"].max()
            fut_only = forecast[forecast["ds"] > last_obs_date][
                ["ds", "yhat", "yhat_lower", "yhat_upper"]
            ].copy()

            rows = [
                ForecastRow(
                    ds=row["ds"].isoformat(),
                    yhat=float(row["yhat"]),
                    yhat_lower=float(row["yhat_lower"]),
                    yhat_upper=float(row["yhat_upper"]),
                )
                for _, row in fut_only.iterrows()
            ]

            output = ForecastOutput(
                success=True,
                rows=rows,
                periods=len(rows),
                date_column=data.date_column,
                value_column=data.value_column,
                message=(
                    f"Forecast produced: {len(rows)} periods "
                    f"({data.freq}) for '{data.value_column}'."
                ),
            )
            yield ToolEndEvent(
                type="tool.end",
                payload={
                    "output": output.model_dump(),
                    "observation": {
                        "summary": output.message,
                        "artifacts": [
                            {
                                "type": "forecast",
                                "date_column": data.date_column,
                                "value_column": data.value_column,
                                "periods": len(rows),
                                "rows": [r.model_dump() for r in rows[:5]],  # preview
                            }
                        ],
                    },
                },
            )

        except Exception as e:
            logger.exception(f"forecast_df failed: {e}")
            yield ToolErrorEvent(
                type="tool.error",
                payload={"error": f"Forecast failed: {e}", "code": "FORECAST_FAILED"},
            )
