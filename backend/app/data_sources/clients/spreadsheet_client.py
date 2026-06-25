from __future__ import annotations

"""Spreadsheet data-source client.

Loads a single uploaded local file (.xlsx / .xls / .csv) into an in-memory
DuckDB connection so the agent can query it with SQL exactly like any other
warehouse connector. Each Excel sheet (or the single CSV) becomes a DuckDB
table whose name is a sanitized version of the sheet name / file stem.

The client is credential-less: everything it needs lives in the connection
`config` (`path`, optional `sheet_names`). It reuses the DuckDB base machinery
for `get_tables` / `get_schema` / `prompt_schema` by loading the spreadsheet
into real tables inside a fresh in-memory connection on each `connect()`.
"""

import os
import re
from contextlib import contextmanager
from typing import Generator, List, Optional

import duckdb
import pandas as pd

from app.ai.prompt_formatters import Table, TableColumn, TableFormatter
from app.data_sources.clients.base import DataSourceClient


_CSV_EXTS = {".csv", ".tsv", ".txt"}
_XLSX_EXTS = {".xlsx", ".xlsm"}
_XLS_EXTS = {".xls"}


class SpreadsheetClient(DataSourceClient):
    """Query an uploaded Excel/CSV file via an in-memory DuckDB engine."""

    def __init__(
        self,
        path: str | None = None,
        sheet_names: Optional[List[str]] = None,
        file_id: str | None = None,
        # Task 5 (HYBRID_MERGE_SAME_SCHEMA): extra same-schema files merged into
        # this one source. Each entry: {"path": str, "label": str}. The primary
        # `path` is loaded first; merged paths are UNION-appended with a
        # `_source_label` provenance column. Forwarded from connection config.
        merged_paths: Optional[List[dict]] = None,
        # Tolerate any extra config/cred keys the registry/constructor merge
        # may forward (this client is credential-less).
        **_kwargs,
    ):
        self.path = path
        # Normalize sheet_names to a clean list[str] | None.
        if isinstance(sheet_names, str):
            sheet_names = [s.strip() for s in sheet_names.split(",") if s.strip()]
        self.sheet_names: Optional[List[str]] = (
            [str(s) for s in sheet_names] if sheet_names else None
        )
        self.file_id = file_id
        self.merged_paths: List[dict] = list(merged_paths or [])

    # ── helpers ──────────────────────────────────────────────────────────

    def _resolve_path(self, raw_path: str | None = None) -> str:
        """Resolve the on-disk path of an uploaded file.

        Uploaded files are stored flat under <cwd>/uploads/files/<basename>.
        We rebuild the path from that trusted root + the sanitized basename so
        a tampered DB value can never escape the uploads directory (matches the
        guard in routes/file.py:get_file_content).
        """
        raw_path = raw_path if raw_path is not None else self.path
        if not raw_path:
            raise RuntimeError("Spreadsheet client has no file path configured")
        # If the stored path already points at an existing absolute file, trust it.
        if os.path.isabs(raw_path) and os.path.exists(raw_path):
            return raw_path
        base = os.path.basename(raw_path)
        candidate = os.path.join(os.getcwd(), "uploads", "files", base)
        if os.path.exists(candidate):
            return candidate
        # Fall back to cwd-relative (path is e.g. "uploads/files/<name>").
        rel = os.path.join(os.getcwd(), raw_path)
        if os.path.exists(rel):
            return rel
        raise RuntimeError(f"Spreadsheet file not found: {raw_path}")

    @staticmethod
    def _safe_table_name(base: str, used: set[str]) -> str:
        name = re.sub(r"[^a-zA-Z0-9_]+", "_", str(base)).strip("_").lower() or "sheet"
        # DuckDB identifiers must not start with a digit when unquoted.
        if name[0].isdigit():
            name = f"t_{name}"
        original = name
        i = 1
        while name in used:
            i += 1
            name = f"{original}_{i}"
        used.add(name)
        return name

    @staticmethod
    def _maybe_fix_header(df: "pd.DataFrame", path: str, sheet, engine: str | None) -> "pd.DataFrame":
        """Task 6 (HYBRID_SMART_HEADER): if the default read produced too many
        ``Unnamed: N`` columns, re-read raw + detect the real header row.

        Fail-soft: returns ``df`` unchanged on any error or when the flag is off.
        """
        try:
            from app.settings.hybrid_flags import flags

            if not flags.SMART_HEADER:
                return df
            from app.services.ingest import smart_upload

            if smart_upload.unnamed_fraction(df.columns) <= 0.40:
                return df
            if sheet is None:  # CSV
                raw = pd.read_csv(path, header=None, sep=None, engine="python")
            else:
                raw = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
            return smart_upload.reread_with_detected_header(
                df, raw, sheet_label=str(sheet if sheet is not None else os.path.basename(path))
            )
        except Exception:  # noqa: BLE001 - never break ingest on header heuristics
            return df

    def _read_one_file(self, raw_path: str) -> "dict[str, pd.DataFrame]":
        """Read ONE file into {sheet/stem -> DataFrame}, applying smart-header.

        Keyed by the ORIGINAL sheet/stem name (not yet table-slugged) so the
        merge step can align same-named sheets across files. Raises on an
        unreadable / unsupported file so the caller can surface a 400.
        """
        path = self._resolve_path(raw_path)
        ext = os.path.splitext(path)[1].lower()
        out: dict[str, pd.DataFrame] = {}

        if ext in _CSV_EXTS:
            sep = "\t" if ext == ".tsv" else None  # None → pandas sniffs ',' default
            df = pd.read_csv(path, sep=sep, engine="python")
            df = self._maybe_fix_header(df, path, None, None)
            stem = os.path.splitext(os.path.basename(path))[0]
            out[stem] = df
            return out

        if ext in _XLSX_EXTS or ext in _XLS_EXTS:
            engine = "openpyxl" if (ext in _XLSX_EXTS) else "xlrd"
            # sheet_name=None → all sheets as an ordered dict.
            all_sheets = pd.read_excel(path, sheet_name=None, engine=engine)
            wanted = self.sheet_names
            for sheet, df in all_sheets.items():
                if wanted is not None and str(sheet) not in wanted:
                    continue
                out[str(sheet)] = self._maybe_fix_header(df, path, sheet, engine)
            if not out and wanted is not None:
                raise RuntimeError(
                    f"None of the requested sheets {wanted} were found in the file. "
                    f"Available: {list(all_sheets.keys())}"
                )
            return out

        raise RuntimeError(f"Unsupported spreadsheet file type: {ext or '(none)'}")

    def _load_frames(self) -> "dict[str, pd.DataFrame]":
        """Read the file(s) into a mapping of {table_name: DataFrame}.

        With Task-5 merged_paths set, same-named sheets across all files are
        concatenated into one frame and stamped with a `_source_label`
        provenance column. Raises on an unreadable/unsupported primary file.
        """
        used: set[str] = set()
        primary = self._read_one_file(self.path)

        # Fast path: no merge -> preserve exact prior behavior (slug + return).
        if not self.merged_paths:
            return {self._safe_table_name(name, used): df for name, df in primary.items()}

        from app.services.ingest.smart_upload import SOURCE_LABEL_COL, label_from_filename

        # Stamp the primary file's rows with its own provenance label.
        primary_label = label_from_filename(self.path or "primary")
        merged: dict[str, list[pd.DataFrame]] = {}
        for name, df in primary.items():
            d = df.copy()
            d[SOURCE_LABEL_COL] = primary_label
            merged.setdefault(name, []).append(d)

        # Append each merged file, aligning by sheet/stem name (fail-soft per file).
        for spec in self.merged_paths:
            try:
                mpath = spec.get("path") if isinstance(spec, dict) else spec
                mlabel = (spec.get("label") if isinstance(spec, dict) else None) or label_from_filename(mpath)
                for name, df in self._read_one_file(mpath).items():
                    d = df.copy()
                    d[SOURCE_LABEL_COL] = mlabel
                    merged.setdefault(name, []).append(d)
            except Exception:
                # A bad merged file never blocks the primary upload's queries.
                continue

        frames: dict[str, pd.DataFrame] = {}
        for name, parts in merged.items():
            try:
                combined = pd.concat(parts, ignore_index=True, sort=False) if len(parts) > 1 else parts[0]
            except Exception:
                combined = parts[0]
            frames[self._safe_table_name(name, used)] = combined
        return frames

    @contextmanager
    def connect(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        con: duckdb.DuckDBPyConnection | None = None
        try:
            frames = self._load_frames()
            con = duckdb.connect(database=":memory:")
            for table_name, df in frames.items():
                # Register the DataFrame then materialize a real table so the
                # view survives after the local `df` ref leaves scope.
                con.register(f"_src_{table_name}", df)
                con.execute(
                    f'CREATE TABLE "{table_name}" AS SELECT * FROM _src_{table_name}'
                )
                con.unregister(f"_src_{table_name}")
            yield con
        except Exception as e:
            raise RuntimeError(f"Error while loading spreadsheet: {e}")
        finally:
            try:
                if con is not None:
                    con.close()
            except Exception:
                pass

    # ── base interface ───────────────────────────────────────────────────

    def execute_query(self, sql: str) -> pd.DataFrame:
        with self.connect() as con:
            return con.execute(sql).df()

    def get_tables(self) -> List[Table]:
        tables: List[Table] = []
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchall()
            for (name,) in rows:
                cols: List[TableColumn] = []
                try:
                    desc = con.execute(f'DESCRIBE "{name}"').fetchall()
                    for d in desc:
                        cols.append(TableColumn(name=d[0], dtype=str(d[1])))
                except Exception:
                    try:
                        df = con.execute(f'SELECT * FROM "{name}" LIMIT 0').df()
                        for c in df.columns:
                            cols.append(TableColumn(name=str(c), dtype="unknown"))
                    except Exception:
                        pass
                tables.append(
                    Table(
                        name=name,
                        columns=cols,
                        pks=[],
                        fks=[],
                        metadata_json={"source": "spreadsheet", "file_id": self.file_id},
                    )
                )
        return tables

    def get_schema(self, table_name: str) -> Table:
        cols: List[TableColumn] = []
        with self.connect() as con:
            try:
                desc = con.execute(f'DESCRIBE "{table_name}"').fetchall()
                for d in desc:
                    cols.append(TableColumn(name=d[0], dtype=str(d[1])))
            except Exception:
                pass
        return Table(name=table_name, columns=cols, pks=[], fks=[])

    def get_schemas(self) -> List[Table]:
        return self.get_tables()

    def prompt_schema(self) -> str:
        return TableFormatter(self.get_schemas()).table_str

    def test_connection(self):
        try:
            with self.connect() as con:
                rows = con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
                ).fetchall()
                table_count = len(rows)
            return {
                "success": True,
                "message": f"Spreadsheet loaded: {table_count} table(s) ready",
                "details": {"table_count": table_count, "file_id": self.file_id},
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    @property
    def description(self):
        system_prompt = """
        You can call the execute_query method to run SQL queries (DuckDB syntax)
        over the spreadsheet's sheets. Each sheet/CSV is a table.

        ```python
        df = client.execute_query("SELECT * FROM sheet1 LIMIT 10")
        ```
        """
        try:
            names = ", ".join(t.name for t in self.get_schemas())
        except Exception:
            names = ""
        head = f"Spreadsheet data source. Tables: {names}\n\n" if names else "Spreadsheet data source.\n\n"
        return head + system_prompt


# Compatibility alias for dynamic resolver expecting 'SpreadsheetClient'.
SpreadsheetClient = SpreadsheetClient
