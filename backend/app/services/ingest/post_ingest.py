"""Post-ingest enrichment for the from-file route (T4 / T6 / T7).

Three additive, fail-soft, flag-gated (except T7) enrichments that run AFTER a
spreadsheet upload has created its DataSource + DataSourceTable rows:

  * T4 CROSS-SOURCE UNIFY (flags.CROSS_SOURCE_UNIFY) — detect groups of sibling
    tables that share the same column signature and differ only by a month/date
    token in the name, record a union group on each member, optionally build a
    `<stem>_unified` SQL VIEW (UNION ALL + a `_period` column) and register it as
    a new queryable DataSourceTable, then emit one guidance instruction.
  * T6 DATA QUALITY SCAN (flags.DATA_QUALITY) — scan each table's columns for
    high null %, type-coercion risk, near-constant, and numeric outliers; write
    findings to metadata_json['quality_findings'] and emit one instruction.
  * T7 BETTER MULTI-FILE NAMING (unflagged, safe) — when a default-named source
    holds >=2 sibling monthly tables, rename it after the common stem (period
    token stripped), optionally with a "(Jan–Jun '25)" range.

EVERYTHING here is defensive: every public entry point is wrapped so it can
never raise into the ingest request. No DB migration. SQL built for the VIEW is
server-derived from real table/column names only (quoted identifiers; the
`_period` literal is server-derived from the table name and is still escaped).

KEY ARCHITECTURE NOTE (why the VIEW is usually skipped on this route):
The from-file route stores spreadsheet data in an IN-MEMORY DuckDB engine
(SpreadsheetClient), NOT in the per-org Postgres `staging_<orgid>` schema. The
VIEW path only fires when a table's linked ConnectionTable carries a real
`metadata_json['schema']` (the autotrain/register.py staging path). For a plain
spreadsheet upload there is no such schema, so we keep the union-group metadata +
instruction and skip the physical view — exactly the documented fail-soft branch.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Period / stem derivation (shared by T4 grouping + T7 naming)
# ---------------------------------------------------------------------------

_MON3 = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MON_DISPLAY = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

# Month token (optionally followed by a 2/4-digit year) inside a slugged name.
_PERIOD_RE = re.compile(
    r"(?:^|_)("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")(?:_?((?:19|20)?\d{2}))?(?=_|$)"
)
# Numeric YYYY_MM form.
_PERIOD_NUM_RE = re.compile(r"(?:^|_)((?:19|20)\d{2})_(0[1-9]|1[0-2])(?=_|$)")


class PeriodInfo:
    """Lightweight period descriptor derived from a table name."""

    __slots__ = ("label", "month", "year", "sort")

    def __init__(self, label: str, month: Optional[int], year: Optional[int]):
        self.label = label
        self.month = month
        self.year = year
        self.sort = (year or 0, month or 0)


def _collapse(name: str, start: int, end: int) -> str:
    """Remove [start:end] from name and collapse the resulting underscores."""
    joined = name[:start] + "_" + name[end:]
    return re.sub(r"_+", "_", joined).strip("_")


def derive_period_and_stem(table_name: str) -> Tuple[str, Optional[PeriodInfo]]:
    """Return (stem, PeriodInfo|None) from a slugged table name.

    stem = the name with the month/date token removed. PeriodInfo is None when
    no period token is found (such tables are never grouped — conservative).
    """
    name = (table_name or "").strip().lower()
    if not name:
        return name, None
    try:
        m = _PERIOD_RE.search(name)
        if m:
            word = m.group(1)
            num = _MON3.get(word[:3])
            year = None
            yy = m.group(2)
            if yy:
                yi = int(yy)
                year = yi if yi >= 100 else 2000 + yi
            disp_yy = f"{year % 100:02d}" if year is not None else ""
            label = f"{word[:3]}_{disp_yy}" if disp_yy else word[:3]
            stem = _collapse(name, m.start(), m.end())
            return stem, PeriodInfo(label, num, year)

        mn = _PERIOD_NUM_RE.search(name)
        if mn:
            year = int(mn.group(1))
            num = int(mn.group(2))
            label = f"{year}_{mn.group(2)}"
            stem = _collapse(name, mn.start(), mn.end())
            return stem, PeriodInfo(label, num, year)
    except Exception:  # noqa: BLE001
        logger.warning("post_ingest.derive_period_and_stem failed for %s", table_name, exc_info=True)
    return name, None


# ---------------------------------------------------------------------------
# Column signature + grouping (shared by T4 + T7)
# ---------------------------------------------------------------------------

def _columns_of(dst) -> List[dict]:
    """Best column list for a DataSourceTable: ConnectionTable schema, else legacy."""
    ct = getattr(dst, "connection_table", None)
    if ct is not None and getattr(ct, "columns", None):
        return ct.columns or []
    return dst.columns or []


def _signature(cols: List[dict]) -> frozenset:
    """Order-independent (name, dtype) set, excluding system/lineage cols (``_``)."""
    out = set()
    for c in cols or []:
        try:
            n = str(c.get("name", "")).strip().lower()
        except Exception:  # noqa: BLE001 - tolerate odd column shapes
            continue
        if not n or n.startswith("_"):
            continue
        d = str(c.get("dtype", "") or "").strip().lower()
        out.add((n, d))
    return frozenset(out)


def _is_unified(dst) -> bool:
    md = getattr(dst, "metadata_json", None) or {}
    return bool(md.get("unified"))


async def _active_tables(db, data_source_id: str) -> list:
    from app.models.datasource_table import DataSourceTable

    rows = (
        await db.execute(
            select(DataSourceTable)
            .options(selectinload(DataSourceTable.connection_table))
            .where(
                DataSourceTable.datasource_id == data_source_id,
                DataSourceTable.is_active.is_(True),
            )
        )
    ).scalars().all()
    return [r for r in rows if not _is_unified(r)]


def _detect_groups(tables: list) -> List[dict]:
    """Group sibling tables sharing (stem, signature). Returns groups with >=2
    members. Each group: {stem, signature, members:[{dst, period}]}.

    Only tables that BOTH have a period token AND a non-empty signature are
    grouped — conservative, never merges unrelated tables.
    """
    buckets: Dict[Tuple[str, frozenset], List[dict]] = {}
    for dst in tables:
        sig = _signature(_columns_of(dst))
        if not sig:
            continue
        stem, period = derive_period_and_stem(dst.name)
        if period is None:
            continue
        buckets.setdefault((stem, sig), []).append({"dst": dst, "period": period})
    groups = []
    for (stem, sig), members in buckets.items():
        if len(members) >= 2:
            groups.append({"stem": stem, "signature": sig, "members": members})
    return groups


# ---------------------------------------------------------------------------
# Instruction emission (mirrors build_data_asset._record_instruction)
# ---------------------------------------------------------------------------

async def _emit_instruction(
    db, *, organization, data_source_id: str, body: str, category: str, ai_source: str,
    structured_data: Optional[dict] = None,
) -> None:
    """Record an agent-readable Instruction linked to this data source.

    status='published' + load_mode='always' so the agent always sees it. Linked
    to the data source via a direct association insert (the ORM relationship is
    lazy='raise', so we can't append it)."""
    from app.models.instruction import Instruction

    inst = Instruction(
        id=str(uuid.uuid4()),
        text=body,
        source_type="ai",
        status="published",
        load_mode="always",
        category=category,
        ai_source=ai_source,
        organization_id=str(organization.id),
        structured_data=structured_data or {},
    )
    db.add(inst)
    await db.flush()
    try:
        await db.execute(
            text(
                "INSERT INTO instruction_data_source_association "
                "(instruction_id, data_source_id) VALUES (:i, :d) ON CONFLICT DO NOTHING"
            ),
            {"i": inst.id, "d": str(data_source_id)},
        )
    except Exception:  # noqa: BLE001 - global instruction still useful unlinked
        logger.warning("post_ingest: could not link instruction to data source", exc_info=True)


# ---------------------------------------------------------------------------
# T4 — CROSS-SOURCE UNIFY
# ---------------------------------------------------------------------------

def _physical_ref(dst) -> Optional[Tuple[str, str]]:
    """(schema, physical_table) for a member, or None when the table isn't backed
    by a real Postgres schema (e.g. the in-memory DuckDB spreadsheet path)."""
    ct = getattr(dst, "connection_table", None)
    if ct is None:
        return None
    md = getattr(ct, "metadata_json", None) or {}
    schema = md.get("schema")
    if not schema:
        return None
    phys = ct.name.split(".", 1)[1] if "." in (ct.name or "") else ct.name
    if not phys:
        return None
    return str(schema), str(phys)


def _create_unified_view(schema: str, view_name: str, members: List[Tuple[str, str]]) -> bool:
    """CREATE OR REPLACE VIEW "<schema>"."<view_name>" via loader_write_engine.

    members = [(physical_table, period_label)]. Verifies every member table
    exists first. Returns True on success, False (skip) on any failure.
    """
    try:
        from app.services.ingest.tenant_schema import loader_write_engine

        eng = loader_write_engine()
        with eng.begin() as conn:
            for phys, _period in members:
                ok = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema=:s AND table_name=:t"
                    ),
                    {"s": schema, "t": phys},
                ).first()
                if not ok:
                    logger.info("post_ingest[T4]: member %s.%s missing; skipping view", schema, phys)
                    return False
            parts = []
            for phys, period in members:
                plit = str(period).replace("'", "''")  # server-derived label, still escaped
                parts.append(f'SELECT *, \'{plit}\' AS _period FROM "{schema}"."{phys}"')
            ddl = (
                f'CREATE OR REPLACE VIEW "{schema}"."{view_name}" AS\n'
                + "\nUNION ALL\n".join(parts)
            )
            conn.execute(text(ddl))
        logger.info("post_ingest[T4]: created view %s.%s over %d members", schema, view_name, len(members))
        return True
    except Exception:  # noqa: BLE001 - perms/engine/DDL — keep metadata + instruction
        logger.warning("post_ingest[T4]: view DDL failed; keeping metadata only", exc_info=True)
        return False


async def _register_unified_table(
    db, *, data_source_id: str, schema: str, view_name: str,
    member_conn_id: str, columns: List[dict], member_names: List[str],
) -> None:
    """Register the unified VIEW as a queryable DataSourceTable (+ ConnectionTable)."""
    from app.models.connection_table import ConnectionTable
    from app.models.datasource_table import DataSourceTable

    cols = list(columns or []) + [{"name": "_period", "dtype": "text"}]
    ct = ConnectionTable(
        id=str(uuid.uuid4()),
        connection_id=member_conn_id,
        name=f"{schema}.{view_name}",
        columns=cols,
        pks=[],
        fks=[],
        no_rows=0,
        metadata_json={"schema": schema, "unified": True, "members": member_names,
                       "source": "cross_source_unify"},
    )
    db.add(ct)
    await db.flush()
    dst = DataSourceTable(
        id=str(uuid.uuid4()),
        datasource_id=data_source_id,
        connection_table_id=ct.id,
        name=view_name,
        is_active=True,
        columns=cols,
        metadata_json={"unified": True, "members": member_names},
    )
    db.add(dst)


async def run_cross_source_unify(db, *, organization, data_source) -> List[dict]:
    """Detect same-shape monthly sibling groups, record union groups, build a
    unified view when physically possible, and emit one instruction per group.

    Returns a list of {stem, members, view, view_created} for the response.
    Never raises."""
    out: List[dict] = []
    try:
        tables = await _active_tables(db, str(data_source.id))
        groups = _detect_groups(tables)
        if not groups:
            return out

        from app.services.ingest.loader import safe_table_name

        for g in groups:
            members = g["members"]
            stem = g["stem"]
            member_names = [m["dst"].name for m in members]
            gid = uuid.uuid5(uuid.NAMESPACE_OID, f"{data_source.id}:{stem}").hex[:16]
            view_name = safe_table_name(f"{stem}_unified")

            # 1) record the union group on every member's metadata_json.
            for m in members:
                dst = m["dst"]
                md = dict(getattr(dst, "metadata_json", None) or {})
                md["union_group"] = {
                    "group_id": gid,
                    "members": member_names,
                    "period_from_name": m["period"].label,
                    "unified_view": view_name,
                }
                dst.metadata_json = md
                flag_modified(dst, "metadata_json")

            # 2) attempt the physical VIEW (only when staging-backed).
            view_created = False
            refs = [(_physical_ref(m["dst"]), m["period"].label) for m in members]
            if all(r[0] is not None for r in refs):
                schemas = {r[0][0] for r in refs}
                if len(schemas) == 1:
                    schema = next(iter(schemas))
                    phys_members = [(r[0][1], r[1]) for r in refs]
                    if _create_unified_view(schema, view_name, phys_members):
                        view_created = True
                        try:
                            member_conn_id = members[0]["dst"].connection_table.connection_id
                            await _register_unified_table(
                                db, data_source_id=str(data_source.id), schema=schema,
                                view_name=view_name,
                                member_conn_id=member_conn_id,
                                columns=_columns_of(members[0]["dst"]),
                                member_names=member_names,
                            )
                        except Exception:  # noqa: BLE001
                            logger.warning("post_ingest[T4]: view created but registration failed",
                                           exc_info=True)

            # 3) emit one instruction.
            joined = ", ".join(member_names)
            body = (
                f"Tables {joined} are the same monthly dataset (identical columns, one per period). "
                f"Prefer the unified view '{view_name}' (it adds a `_period` column) for cross-month "
                f"questions instead of querying a single month or UNION-ing by hand."
            )
            if not view_created:
                body += (
                    " (The unified view is logical only here — UNION ALL these tables and add a "
                    "period label per source when answering across months.)"
                )
            await _emit_instruction(
                db, organization=organization, data_source_id=str(data_source.id),
                body=body, category="data_asset", ai_source="cross_source_unify",
                structured_data={"group_id": gid, "members": member_names,
                                 "unified_view": view_name, "view_created": view_created},
            )
            out.append({"stem": stem, "members": member_names, "view": view_name,
                        "view_created": view_created})

        await db.commit()
    except Exception:  # noqa: BLE001 - never block ingest
        logger.warning("post_ingest.run_cross_source_unify failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------------------------------------------------------------------------
# T6 — DATA QUALITY SCAN
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
_MAX_FINDINGS = 8
_MAX_COLS = 80


def _is_number(v) -> bool:
    try:
        float(str(v).replace(",", "").strip())
        return True
    except (ValueError, TypeError):
        return False


def scan_dataframe_quality(df, *, max_cols: int = _MAX_COLS) -> List[dict]:
    """Pure-pandas column scan. Returns [{column, issue, detail, severity}]."""
    findings: List[dict] = []
    try:
        import pandas as pd  # local import keeps module import cheap

        if df is None or len(df) == 0:
            return findings
        n = len(df)
        for col in list(df.columns)[:max_cols]:
            if str(col).startswith("_"):  # skip lineage/system columns
                continue
            s = df[col]
            non_null = s.dropna()
            # high null %
            null_frac = 1.0 - (len(non_null) / n if n else 0.0)
            if null_frac > 0.40:
                findings.append({
                    "column": str(col), "issue": "high_null",
                    "detail": f"{round(null_frac * 100)}% null",
                    "severity": "high" if null_frac > 0.70 else "medium",
                })
            if len(non_null) == 0:
                continue
            # near-constant
            try:
                nuniq = non_null.nunique(dropna=True)
            except Exception:  # noqa: BLE001
                nuniq = None
            if nuniq is not None and nuniq <= 1:
                findings.append({
                    "column": str(col), "issue": "near_constant",
                    "detail": "single distinct value", "severity": "low",
                })
            # type-coercion / mixed-type risk (object columns only)
            is_object = (s.dtype == object)
            if is_object:
                sample = non_null.head(500).tolist()
                if sample:
                    num_frac = sum(1 for v in sample if _is_number(v)) / len(sample)
                    if num_frac >= 0.80 and num_frac < 1.0:
                        findings.append({
                            "column": str(col), "issue": "mixed_type",
                            "detail": f"{round(num_frac * 100)}% numeric values stored as text",
                            "severity": "medium",
                        })
                    elif num_frac >= 1.0:
                        findings.append({
                            "column": str(col), "issue": "type_coercion",
                            "detail": "numeric values stored as text",
                            "severity": "medium",
                        })
            # numeric outliers (mean ± 4σ)
            if pd.api.types.is_numeric_dtype(s):
                try:
                    vals = pd.to_numeric(non_null, errors="coerce").dropna()
                    if len(vals) >= 10:
                        mu, sd = float(vals.mean()), float(vals.std())
                        if sd and sd > 0:
                            out_ct = int(((vals - mu).abs() > 4 * sd).sum())
                            if out_ct > 0:
                                findings.append({
                                    "column": str(col), "issue": "outliers",
                                    "detail": f"{out_ct} value(s) beyond 4σ",
                                    "severity": "low",
                                })
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        logger.warning("post_ingest.scan_dataframe_quality failed", exc_info=True)
    # rank + cap
    findings.sort(key=lambda f: _SEVERITY_RANK.get(f.get("severity"), 0), reverse=True)
    return findings[:_MAX_FINDINGS]


async def run_data_quality_scan(db, *, organization, data_source, file) -> List[dict]:
    """Scan each active table, store findings on metadata_json['quality_findings'],
    and emit ONE concise data_quality instruction. Never raises."""
    summary: List[dict] = []
    try:
        from app.data_sources.clients.spreadsheet_client import SpreadsheetClient

        try:
            frames = SpreadsheetClient(path=file.path, file_id=str(file.id))._load_frames()
        except Exception:  # noqa: BLE001
            frames = {}

        tables = await _active_tables(db, str(data_source.id))
        top_issues: List[dict] = []
        for dst in tables:
            df = frames.get(dst.name)
            if df is None:
                continue
            findings = scan_dataframe_quality(df)
            if not findings:
                continue
            md = dict(getattr(dst, "metadata_json", None) or {})
            md["quality_findings"] = findings
            dst.metadata_json = md
            flag_modified(dst, "metadata_json")
            summary.append({"table": dst.name, "findings": findings})
            for f in findings:
                top_issues.append({"table": dst.name, **f})

        if summary:
            top_issues.sort(key=lambda f: _SEVERITY_RANK.get(f.get("severity"), 0), reverse=True)
            bullets = "; ".join(
                f"'{f['column']}' in {f['table']} — {f['detail']}" for f in top_issues[:_MAX_FINDINGS]
            )
            body = (
                "Data-quality notes for this source: " + bullets + ". "
                "Qualify aggregates over high-null columns, coerce numeric-looking text before math, "
                "and treat flagged outliers/near-constant columns with care."
            )
            await _emit_instruction(
                db, organization=organization, data_source_id=str(data_source.id),
                body=body, category="data_quality", ai_source="data_quality_scan",
                structured_data={"tables": [s["table"] for s in summary]},
            )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("post_ingest.run_data_quality_scan failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return summary


# ---------------------------------------------------------------------------
# T7 — BETTER MULTI-FILE NAMING (unflagged, safe)
# ---------------------------------------------------------------------------

# Period token in a human filename (spaces/parens/apostrophes tolerated).
_FNAME_PERIOD_RE = re.compile(
    r"[\s_\-(]*\(?(?<![a-z])("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")(?![a-z])[\s'`’_]*((?:19|20)?\d{2})?\)?",
    re.IGNORECASE,
)


def _range_suffix(members: List[dict]) -> str:
    """Build "(Jan–Jun '25)" from a group's periods, or '' if not derivable."""
    try:
        periods = [m["period"] for m in members if m.get("period") and m["period"].month]
        if len(periods) < 2:
            return ""
        years = {p.year for p in periods if p.year is not None}
        periods.sort(key=lambda p: p.sort)
        lo, hi = periods[0], periods[-1]
        lo_d, hi_d = _MON_DISPLAY.get(lo.month, ""), _MON_DISPLAY.get(hi.month, "")
        if not lo_d or not hi_d:
            return ""
        if len(years) == 1 and lo.year is not None:
            return f"({lo_d}–{hi_d} '{lo.year % 100:02d})"
        return f"({lo_d}–{hi_d})"
    except Exception:  # noqa: BLE001
        return ""


def humanize_common_name(filename: str, members: List[dict]) -> Optional[str]:
    """Derive a cleaner data-source name from the filename: strip the month/date
    token, append a period range when known. Returns None if nothing improved."""
    try:
        import os

        stem = os.path.splitext(os.path.basename(filename or ""))[0].strip()
        if not stem:
            return None
        stripped = _FNAME_PERIOD_RE.sub(" ", stem)
        # tidy leftover empty parens + separators + whitespace
        stripped = re.sub(r"\(\s*\)", " ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip(" -_·")
        if not stripped or stripped.lower() == stem.lower():
            return None
        suffix = _range_suffix(members)
        name = f"{stripped} {suffix}".strip() if suffix else stripped
        return name or None
    except Exception:  # noqa: BLE001
        return None


async def run_better_naming(db, *, organization, data_source, file, dedupe_fn) -> Optional[str]:
    """Rename a default-named multi-file source after its common stem. Returns the
    new name when renamed, else None. Never raises. (Caller gates on
    'payload.data_source_name not provided'.)"""
    try:
        tables = await _active_tables(db, str(data_source.id))
        groups = _detect_groups(tables)
        if not groups:
            return None
        # pick the largest sibling group as the naming basis
        groups.sort(key=lambda g: len(g["members"]), reverse=True)
        new_name = humanize_common_name(file.filename or file.path or "", groups[0]["members"])
        if not new_name:
            return None
        if new_name.strip().lower() == str(data_source.name or "").strip().lower():
            return None
        final = await dedupe_fn(db, str(organization.id), new_name)
        data_source.name = final
        await db.commit()
        logger.info("post_ingest[T7]: renamed data source -> %s", final)
        return final
    except Exception:  # noqa: BLE001
        logger.warning("post_ingest.run_better_naming failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return None
