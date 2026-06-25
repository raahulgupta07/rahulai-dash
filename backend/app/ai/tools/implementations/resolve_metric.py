"""resolve_metric Tool — look up an approved business metric definition.

Knowledge Layer Phase 4. Given a metric name (case-insensitive, scoped to the
organization, optionally to a data source), returns the approved
MetricDefinition's definition, table_ref, sql_calc and owner so the agent reuses
the canonical metric rather than re-deriving it.

Self-gates on flags.METRICS_CATALOG: when the catalog is off the tool simply
returns ``found=False`` (it never raises), so a fresh deploy behaves like
upstream. Native ToolRegistry pattern (auto-registered via implementations/).

VERIFIED_METRICS extension (flags.VERIFIED_METRICS):
When this flag is ON and the resolved metric has is_locked=True, the tool
executes the metric's sql_calc read-only (using the same _is_read_only_sql
guard and DataSource.get_client().aexecute_query() path used by
POST /metrics/{id}/test), returns the live scalar as live_value, persists
last_value/last_value_at back to the row, and includes a drift_note
showing the abs % change vs the prior last_value. When the flag is OFF the
behaviour is identical to pre-P7 (no execution, no DB write).
"""
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Any, Optional, Type
import logging

from pydantic import BaseModel
from sqlalchemy import select, func

from app.ai.tools.base import Tool
from app.ai.tools.metadata import ToolMetadata
from app.ai.tools.schemas.events import (
    ToolEvent,
    ToolStartEvent,
    ToolEndEvent,
    ToolErrorEvent,
)
from app.ai.tools.schemas.resolve_metric import (
    ResolveMetricInput,
    ResolveMetricOutput,
    ResolveMetricMatch,
)
from app.settings.hybrid_flags import flags
from app.models.metric_definition import MetricDefinition
from app.ai.brain import bitemporal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VERIFIED_METRICS helpers (P7)
# ---------------------------------------------------------------------------

def _drift_note(prior: Optional[float], current: float) -> Optional[str]:
    """Return a human-readable drift note or None when unavailable."""
    if prior is None:
        return None
    try:
        if prior == 0:
            return f"prior value was 0; current value is {current:.4g} (infinite change)"
        pct = abs((current - float(prior)) / float(prior)) * 100
        direction = "up" if current > float(prior) else "down"
        return (
            f"drifted {direction} {pct:.2f}% vs prior value "
            f"({float(prior):.4g} → {current:.4g})"
        )
    except Exception:
        return None


async def _execute_locked_metric(row: MetricDefinition, db, organization) -> Optional[float]:
    """Execute sql_calc read-only and return the scalar (first cell of first row).

    Returns None on any failure (guard rejection, execution error, non-scalar
    result). Never raises — failures are surfaced via None + logged.
    """
    try:
        from app.routes.knowledge import _is_read_only_sql  # local to avoid circular
    except ImportError:
        try:
            # Fallback: minimal inline guard (covers the common case)
            import re as _re

            def _is_read_only_sql(sql: str) -> bool:  # type: ignore[override]
                if not sql or not sql.strip():
                    return False
                cleaned = _re.sub(r"/\*.*?\*/", " ", sql, flags=_re.DOTALL)
                cleaned = _re.sub(r"--[^\n]*", " ", cleaned).strip()
                body = cleaned.rstrip().rstrip(";")
                if ";" in body:
                    return False
                first = body.lower().split(None, 1)[0] if body.split(None, 1) else ""
                return first in ("select", "with")
        except Exception:
            return None

    sql = (row.sql_calc or "").strip()
    if not sql:
        logger.debug("resolve_metric locked exec: empty sql_calc for metric %s", row.id)
        return None
    if not _is_read_only_sql(sql):
        logger.warning(
            "resolve_metric locked exec: sql_calc rejected by read-only guard for metric %s",
            row.id,
        )
        return None

    try:
        from sqlalchemy import select as sa_select
        from app.models.data_source import DataSource

        ds_res = await db.execute(
            sa_select(DataSource).where(
                DataSource.id == row.data_source_id,
                DataSource.organization_id == str(organization.id),
            )
        )
        data_source = ds_res.scalar_one_or_none()
        if data_source is None:
            logger.warning(
                "resolve_metric locked exec: data source %s not found for metric %s",
                row.data_source_id, row.id,
            )
            return None

        client = data_source.get_client()
        df = await client.aexecute_query(sql)

        if df is None or len(df) == 0:
            return None
        # Scalar: single-cell result (e.g. SELECT COUNT(*) FROM …)
        val = df.iat[0, 0]
        if val is None:
            return None
        # Coerce numpy/pandas scalar → python float
        item_fn = getattr(val, "item", None)
        if callable(item_fn):
            val = item_fn()
        return float(val)
    except Exception as exc:
        logger.warning("resolve_metric locked exec failed for metric %s: %s", row.id, exc)
        return None


async def _persist_last_value(row: MetricDefinition, value: float, db) -> None:
    """Write last_value + last_value_at back to the metric row. Best-effort."""
    try:
        row.last_value = value
        row.last_value_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)  # naive UTC
        await db.commit()
        await db.refresh(row)
    except Exception as exc:
        logger.warning("resolve_metric: failed to persist last_value for metric %s: %s", row.id, exc)
        try:
            await db.rollback()
        except Exception:
            pass


class ResolveMetricTool(Tool):
    """Resolve an approved named business metric to its definition + SQL."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="resolve_metric",
            description=(
                "Look up an APPROVED business metric by name (case-insensitive). "
                "Use this before computing a named metric so you reuse the "
                "organization's canonical definition and SQL instead of "
                "inventing one. Returns definition, table_ref, sql_calc and "
                "owner. Optionally scope by data_source_id."
            ),
            category="both",
            version="1.0.0",
            input_schema=ResolveMetricInput.model_json_schema(),
            output_schema=ResolveMetricOutput.model_json_schema(),
            max_retries=1,
            timeout_seconds=15,
            idempotent=True,
            tags=["metrics", "knowledge", "lookup"],
            examples=[
                {
                    "input": {"metric_name": "Active Customers"},
                    "description": "Resolve a metric by name across the org",
                },
                {
                    "input": {"metric_name": "MRR", "data_source_id": "<ds-uuid>"},
                    "description": "Resolve a metric scoped to one data source",
                },
            ],
        )

    @property
    def input_model(self) -> Type[BaseModel]:
        return ResolveMetricInput

    @property
    def output_model(self) -> Type[BaseModel]:
        return ResolveMetricOutput

    async def run_stream(
        self, tool_input: Dict[str, Any], runtime_ctx: Dict[str, Any]
    ) -> AsyncIterator[ToolEvent]:
        try:
            data = ResolveMetricInput(**tool_input)
        except Exception as e:
            yield ToolErrorEvent(
                type="tool.error",
                payload={"error": f"Invalid input: {e}", "code": "INVALID_INPUT"},
            )
            return

        yield ToolStartEvent(
            type="tool.start",
            payload={"metric_name": data.metric_name, "data_source_id": data.data_source_id},
        )

        db = runtime_ctx.get("db")
        organization = runtime_ctx.get("organization")
        if not db or not organization:
            yield ToolErrorEvent(
                type="tool.error",
                payload={
                    "error": "Missing required runtime context (db, organization)",
                    "code": "MISSING_CONTEXT",
                },
            )
            return

        # When the catalog is off, behave as "no approved metric" — no leak.
        if not flags.METRICS_CATALOG:
            output = ResolveMetricOutput(
                success=True,
                found=False,
                message="Metrics catalog is not enabled.",
            )
            yield ToolEndEvent(
                type="tool.end",
                payload={
                    "output": output.model_dump(),
                    "observation": {"summary": "Metrics catalog disabled; no metric resolved."},
                },
            )
            return

        try:
            name = (data.metric_name or "").strip()
            stmt = (
                select(MetricDefinition)
                .where(MetricDefinition.organization_id == str(organization.id))
                .where(MetricDefinition.status == "approved")
                .where(func.lower(MetricDefinition.name) == name.lower())
            )
            if data.data_source_id:
                stmt = stmt.where(MetricDefinition.data_source_id == str(data.data_source_id))

            # Bi-temporal (HYBRID_BITEMPORAL): time-travel if as_of is given,
            # else only the currently-valid version reaches the agent. Both are
            # no-ops when the flag is OFF (conditions empty / None).
            as_of = None
            if getattr(data, "as_of", None):
                try:
                    from datetime import datetime
                    raw = str(data.as_of).strip()
                    # tolerate a trailing Z (UTC) which fromisoformat rejects pre-3.11
                    if raw.endswith("Z"):
                        raw = raw[:-1] + "+00:00"
                    as_of = datetime.fromisoformat(raw)
                except Exception:
                    as_of = None  # parse fail -> ignore, fall back to current
            if as_of is not None:
                for cond in bitemporal.asof_conditions(MetricDefinition, as_of):
                    stmt = stmt.where(cond)
            else:
                cond = bitemporal.current_condition(MetricDefinition)
                if cond is not None:
                    stmt = stmt.where(cond)

            stmt = stmt.order_by(MetricDefinition.name.asc())
            row = (await db.execute(stmt)).scalars().first()

            if row is None:
                # Surface approved metric names as candidates for a near-miss.
                cand_stmt = (
                    select(MetricDefinition.name)
                    .where(MetricDefinition.organization_id == str(organization.id))
                    .where(MetricDefinition.status == "approved")
                )
                if data.data_source_id:
                    cand_stmt = cand_stmt.where(
                        MetricDefinition.data_source_id == str(data.data_source_id)
                    )
                cand_stmt = cand_stmt.order_by(MetricDefinition.name.asc()).limit(25)
                candidates = [c for c in (await db.execute(cand_stmt)).scalars().all() if c]
                output = ResolveMetricOutput(
                    success=True,
                    found=False,
                    candidates=candidates,
                    message=f"No approved metric named '{name}'.",
                )
                yield ToolEndEvent(
                    type="tool.end",
                    payload={
                        "output": output.model_dump(),
                        "observation": {
                            "summary": f"No approved metric '{name}' (candidates: {len(candidates)})",
                        },
                    },
                )
                return

            # --- VERIFIED_METRICS: execute locked sql_calc (P7) ----------------
            live_value: Optional[float] = None
            drift: Optional[str] = None
            is_locked = bool(getattr(row, "is_locked", False))

            if flags.VERIFIED_METRICS and is_locked:
                prior_value: Optional[float] = None
                try:
                    raw_prior = getattr(row, "last_value", None)
                    if raw_prior is not None:
                        prior_value = float(raw_prior)
                except Exception:
                    prior_value = None

                live_value = await _execute_locked_metric(row, db, organization)
                if live_value is not None:
                    drift = _drift_note(prior_value, live_value)
                    await _persist_last_value(row, live_value, db)

            match = ResolveMetricMatch(
                name=row.name,
                definition=row.definition or "",
                table_ref=row.table_ref or "",
                sql_calc=row.sql_calc or "",
                owner=row.owner,
                data_source_id=str(row.data_source_id),
                is_locked=is_locked,
                live_value=live_value,
                drift_note=drift,
            )

            summary = f"Resolved metric '{row.name}' -> {row.table_ref or 'n/a'}"
            if flags.VERIFIED_METRICS and is_locked:
                if live_value is not None:
                    summary += f" [LOCKED, live_value={live_value:.4g}"
                    if drift:
                        summary += f", {drift}"
                    summary += "]"
                else:
                    summary += " [LOCKED, exec failed — using definition only]"

            output = ResolveMetricOutput(
                success=True,
                found=True,
                metric=match,
                message=f"Resolved metric '{row.name}'.",
            )
            yield ToolEndEvent(
                type="tool.end",
                payload={
                    "output": output.model_dump(),
                    "observation": {
                        "summary": summary,
                        "artifacts": [
                            {
                                "type": "metric_definition",
                                "name": row.name,
                                "definition": match.definition,
                                "table_ref": match.table_ref,
                                "sql_calc": match.sql_calc,
                                "owner": match.owner,
                                "is_locked": is_locked,
                                "live_value": live_value,
                                "drift_note": drift,
                            }
                        ],
                    },
                },
            )
        except Exception as e:
            logger.exception(f"resolve_metric failed: {e}")
            yield ToolErrorEvent(
                type="tool.error",
                payload={"error": f"Resolve failed: {e}", "code": "RESOLVE_FAILED"},
            )
