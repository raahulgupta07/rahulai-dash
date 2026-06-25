"""Schemas for the ``resolve_metric`` tool (Knowledge Layer Phase 4)."""
from typing import List, Optional
from pydantic import BaseModel, Field


class ResolveMetricInput(BaseModel):
    """Input for ``resolve_metric``.

    Looks up an APPROVED business metric by name (case-insensitive) so the agent
    can reuse the canonical definition + SQL instead of inventing one.
    """

    metric_name: str = Field(
        ...,
        description="Name of the business metric to resolve (case-insensitive).",
        max_length=200,
    )
    data_source_id: Optional[str] = Field(
        None,
        description=(
            "Optional data source id to scope the lookup. When omitted, the "
            "first matching approved metric in the organization is returned."
        ),
    )
    as_of: Optional[str] = Field(
        None,
        description=(
            "Optional ISO-8601 datetime for time-travel: return the version of "
            "the metric that was valid AT that time (bi-temporal). When omitted, "
            "the currently-valid version is returned. Ignored if unparseable or "
            "if bi-temporal versioning is disabled."
        ),
    )


class ResolveMetricMatch(BaseModel):
    name: str
    definition: str = ""
    table_ref: str = ""
    sql_calc: str = ""
    owner: Optional[str] = None
    data_source_id: str = ""
    # --- VERIFIED_METRICS fields (populated only when flag is ON + is_locked) ---
    is_locked: bool = False
    live_value: Optional[float] = Field(
        None,
        description=(
            "Live scalar value computed by executing sql_calc read-only. "
            "Set only when VERIFIED_METRICS is ON and the metric is locked."
        ),
    )
    drift_note: Optional[str] = Field(
        None,
        description=(
            "Human-readable note about the % change between the previous "
            "last_value and the newly computed live_value. None when there "
            "is no prior value or the flag is OFF."
        ),
    )


class ResolveMetricOutput(BaseModel):
    success: bool
    found: bool = False
    metric: Optional[ResolveMetricMatch] = None
    candidates: List[str] = Field(default_factory=list)
    message: Optional[str] = None
