from app.data_sources.clients.base import DataSourceClient

import pandas as pd
import struct
from contextlib import contextmanager
from typing import Generator, List, Optional
from app.ai.prompt_formatters import Table, TableColumn
from app.ai.prompt_formatters import TableFormatter

import time

import pyodbc
from azure.identity import ClientSecretCredential


# Fabric's redirect-policy endpoint intermittently throws 08001/(26)
# "error during handshakes before login" (server-busy / redirect race) even
# with the correct port + creds. The handshake itself is transient → retry a
# few times with backoff before surfacing the error.
def _connect_with_retry(conn_str: str, attrs_before: dict = None, attempts: int = 6):
    last_exc = None
    for i in range(attempts):
        try:
            if attrs_before is not None:
                return pyodbc.connect(conn_str, attrs_before=attrs_before)
            return pyodbc.connect(conn_str)
        except pyodbc.Error as e:
            sqlstate = e.args[0] if e.args else ""
            msg = str(e).lower()
            # Fabric redirect-policy bursts surface as several transient codes:
            #   08001/(26) handshake-before-login · HYT00 login-timeout · 08S01
            #   communication-link-failure · "server too busy".
            transient = (
                sqlstate in ("08001", "08S01", "HYT00", "HYTC0")
                or "before login" in msg
                or "(26)" in msg
                or "timeout expired" in msg
                or "communication link failure" in msg
                or "server too busy" in msg
            )
            if not transient or i == attempts - 1:
                raise
            last_exc = e
            time.sleep(min(0.6 * (i + 1), 2.5))
    if last_exc:
        raise last_exc


class MsFabricClient(DataSourceClient):
    """Client for Microsoft Fabric Warehouse/Lakehouse SQL endpoints."""

    def __init__(
        self,
        server_hostname: str,
        database: str = None,
        tenant_id: str = None,
        client_id: str = None,
        client_secret: str = None,
        schema: Optional[str] = None,
        access_token: str = None,
        refresh_token: str = None,
    ):
        self.server_hostname = server_hostname
        # Blank database = per-user connector template: discover the warehouses the
        # signed-in user can access (see _accessible_databases / get_tables) instead
        # of a fixed admin-set database.
        self.database = database or None
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.schema = schema
        self._delegated_access_token = access_token
        # Per-user device-code path: a stored refresh_token (FOCI public client) is
        # redeemed for a fresh SQL-endpoint access token at connect time. No app
        # registration, no client secret — works for MFA/guest/home accounts.
        self._refresh_token = refresh_token

        # Parse comma-separated schemas if provided
        self._schemas: List[str] = []
        if isinstance(self.schema, str) and self.schema.strip():
            parts = [s.strip() for s in self.schema.split(",") if s.strip()]
            # Dedupe while preserving order
            seen = set()
            for p in parts:
                if p not in seen:
                    seen.add(p)
                    self._schemas.append(p)

    def _get_access_token(self) -> str:
        """Get Azure AD access token for SQL endpoint."""
        if self._delegated_access_token:
            return self._delegated_access_token

        # Device-code per-user path: mint a fresh SQL token from the stored
        # refresh_token (redeemable across the FOCI family → database.windows.net).
        if self._refresh_token:
            from app.services.powerbi_device_code import (
                refresh_to_access_token,
                FABRIC_TOKEN_SCOPE,
            )
            res = refresh_to_access_token(
                tenant_id=self.tenant_id or "organizations",
                refresh_token=self._refresh_token,
                scope=FABRIC_TOKEN_SCOPE,
            )
            if res.get("ok") and res.get("access_token"):
                return res["access_token"]
            raise RuntimeError(
                f"Could not refresh Fabric access token: {res.get('error', 'unknown error')}"
            )

        credential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        token = credential.get_token("https://database.windows.net/.default")
        return token.token

    def _get_token_struct(self) -> bytes:
        """Convert token to struct format required by pyodbc."""
        token = self._get_access_token()
        token_bytes = token.encode("utf-16-le")
        token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
        return token_struct

    @contextmanager
    def connect(self) -> Generator:
        """Yield a connection to Microsoft Fabric SQL endpoint."""
        conn = None
        try:
            # Build connection string for Fabric. Explicit ,1433 + login timeout
            # avoid 08001/(26) "handshakes before login" on the redirect-policy
            # endpoint when the host is given without a port.
            host = self.server_hostname
            if "," not in host:
                host = f"{host},1433"
            # Omit DATABASE= when unset (per-user template) → connect to the
            # endpoint's default catalog; sys.databases then reveals the
            # warehouses this user can access for discovery.
            db_clause = f"DATABASE={self.database};" if self.database else ""
            conn_str = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={host};"
                f"{db_clause}"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
                f"Connection Timeout=30;"
            )

            # Get token and pass via attrs_before
            token_struct = self._get_token_struct()
            # SQL_COPT_SS_ACCESS_TOKEN = 1256
            conn = _connect_with_retry(conn_str, attrs_before={1256: token_struct})
            yield conn
        except Exception as e:
            raise RuntimeError(f"Error connecting to Microsoft Fabric: {e}")
        finally:
            if conn is not None:
                conn.close()

    def execute_query(self, sql: str) -> pd.DataFrame:
        """Execute SQL statement and return the result as a DataFrame."""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                # Fetch column names from cursor description
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                cursor.close()
                df = pd.DataFrame.from_records(rows, columns=columns)
            return df
        except Exception as e:
            print(f"Error executing SQL: {e}")
            raise

    def get_tables(self) -> List[Table]:
        """Get tables with graceful fallback if enriched query fails.

        When no database is set (per-user connector template), discover every
        warehouse/lakehouse the signed-in user can access and union their tables
        — so each user's private clone syncs only what THEIR account can see, with
        no admin-typed database. Table names are qualified `db.schema.table`.
        """
        if self.database:
            try:
                return self._get_tables_enriched()
            except Exception:
                return self._get_tables_basic()

        out: List[Table] = []
        for db in self._accessible_databases():
            try:
                out.extend(self._get_tables_for_db(db))
            except Exception:
                # A single inaccessible/locked warehouse must not abort the rest.
                continue
        return out

    def _accessible_databases(self) -> List[str]:
        """List warehouses/lakehouses the connecting principal can access on this
        endpoint (excludes system DBs). NEEDS-LIVE-TEST against a real Fabric ws."""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sys.databases "
                "WHERE database_id > 4 AND HAS_DBACCESS(name) = 1 ORDER BY name"
            )
            rows = cursor.fetchall()
            cursor.close()
        return [r[0] for r in rows if r and r[0]]

    def _get_tables_for_db(self, database: str) -> List[Table]:
        """Basic table+column pull for ONE database via 3-part naming (cross-db
        within the workspace). Names qualified `db.schema.table`."""
        tables = {}
        with self.connect() as conn:
            cursor = conn.cursor()
            where = [
                "TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA', 'queryinsights')",
                "HAS_PERMS_BY_NAME(QUOTENAME(TABLE_SCHEMA) + '.' + QUOTENAME(TABLE_NAME), 'OBJECT', 'SELECT') = 1",
            ]
            sql = f"""
                SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
                FROM [{database}].INFORMATION_SCHEMA.COLUMNS
                WHERE {' AND '.join(where)}
                ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            cursor.close()
            for row in results:
                table_schema, table_name, column_name, data_type = row
                key = (table_schema, table_name)
                fqn = f"{database}.{table_schema}.{table_name}"
                if key not in tables:
                    tables[key] = Table(
                        name=fqn,
                        columns=[],
                        pks=[],
                        fks=[],
                        metadata_json={"schema": table_schema, "database": database},
                    )
                tables[key].columns.append(TableColumn(name=column_name, dtype=data_type))
        return list(tables.values())

    def _get_tables_enriched(self) -> List[Table]:
        """Get tables with column/table descriptions. May fail on some configurations."""
        tables = {}
        with self.connect() as conn:
            cursor = conn.cursor()

            where_clauses = [f"c.TABLE_CATALOG = '{self.database}'"]
            where_clauses.append("c.TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA', 'queryinsights')")
            # Filter to objects the connecting principal actually has SELECT on.
            # INFORMATION_SCHEMA shows objects whose existence is visible (e.g. via REFERENCES,
            # CONTROL, or schema membership), which is broader than SELECT — so a user with
            # DENY SELECT still sees the table listed without this filter.
            where_clauses.append(
                "HAS_PERMS_BY_NAME(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME), 'OBJECT', 'SELECT') = 1"
            )
            if self._schemas:
                schema_list = ", ".join([f"'{s}'" for s in self._schemas])
                where_clauses.append(f"c.TABLE_SCHEMA IN ({schema_list})")

            where_sql = " WHERE " + " AND ".join(where_clauses)

            # Fabric supports extended properties for descriptions
            sql = f"""
                SELECT
                    c.TABLE_SCHEMA,
                    c.TABLE_NAME,
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    CAST(ep_col.value AS NVARCHAR(MAX)) AS column_comment,
                    CAST(ep_tbl.value AS NVARCHAR(MAX)) AS table_comment
                FROM INFORMATION_SCHEMA.COLUMNS c
                LEFT JOIN sys.columns sc
                    ON sc.name = c.COLUMN_NAME
                    AND sc.object_id = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
                LEFT JOIN sys.extended_properties ep_col
                    ON ep_col.major_id = sc.object_id
                    AND ep_col.minor_id = sc.column_id
                    AND ep_col.name = 'MS_Description'
                LEFT JOIN sys.extended_properties ep_tbl
                    ON ep_tbl.major_id = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
                    AND ep_tbl.minor_id = 0
                    AND ep_tbl.name = 'MS_Description'
                {where_sql}
                ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
            """

            cursor.execute(sql)
            results = cursor.fetchall()
            cursor.close()

            for row in results:
                table_schema, table_name, column_name, data_type, col_comment, tbl_comment = row
                key = (table_schema, table_name)
                fqn = f"{table_schema}.{table_name}"
                if key not in tables:
                    tables[key] = Table(
                        name=fqn,
                        description=tbl_comment if tbl_comment else None,
                        columns=[],
                        pks=[],
                        fks=[],
                        metadata_json={"schema": table_schema, "database": self.database}
                    )
                tables[key].columns.append(TableColumn(
                    name=column_name,
                    dtype=data_type,
                    description=col_comment if col_comment else None
                ))

        return list(tables.values())

    def _get_tables_basic(self) -> List[Table]:
        """Get tables without comments (always works)."""
        tables = {}
        with self.connect() as conn:
            cursor = conn.cursor()

            where_clauses = [f"TABLE_CATALOG = '{self.database}'"]
            where_clauses.append("TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA', 'queryinsights')")
            # Filter to objects the connecting principal actually has SELECT on
            # (see _get_tables_enriched for rationale).
            where_clauses.append(
                "HAS_PERMS_BY_NAME(QUOTENAME(TABLE_SCHEMA) + '.' + QUOTENAME(TABLE_NAME), 'OBJECT', 'SELECT') = 1"
            )
            if self._schemas:
                schema_list = ", ".join([f"'{s}'" for s in self._schemas])
                where_clauses.append(f"TABLE_SCHEMA IN ({schema_list})")

            where_sql = " WHERE " + " AND ".join(where_clauses)

            sql = f"""
                SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                {where_sql}
                ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
            """

            cursor.execute(sql)
            results = cursor.fetchall()
            cursor.close()

            for row in results:
                table_schema, table_name, column_name, data_type = row
                key = (table_schema, table_name)
                fqn = f"{table_schema}.{table_name}"
                if key not in tables:
                    tables[key] = Table(
                        name=fqn,
                        columns=[],
                        pks=[],
                        fks=[],
                        metadata_json={"schema": table_schema, "database": self.database}
                    )
                tables[key].columns.append(TableColumn(name=column_name, dtype=data_type))

        return list(tables.values())

    def get_schema(self, table_name: str) -> Table:
        """Get schema for a specific table. Deprecated - use get_tables() instead."""
        raise NotImplementedError("get_schema() is deprecated. Use get_tables() instead.")

    def get_schemas(self) -> List[Table]:
        """Get all table schemas. Wrapper for get_tables()."""
        return self.get_tables()

    def prompt_schema(self) -> str:
        """Return formatted schema string for LLM prompts."""
        schemas = self.get_schemas()
        return TableFormatter(schemas).table_str

    def test_connection(self) -> dict:
        """Test connection to Microsoft Fabric and return status information."""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return {
                    "success": True,
                    "message": "Successfully connected to Microsoft Fabric"
                }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    @property
    def description(self) -> str:
        """System prompt describing this data source for LLM context."""
        schema_info = ", ".join(self._schemas) if self._schemas else "all schemas"
        return f"""Microsoft Fabric SQL Endpoint
Server: {self.server_hostname}
Database: {self.database}
Schemas: {schema_info}

Microsoft Fabric uses T-SQL syntax (SQL Server compatible).
Tables are organized in a two-level namespace: schema.table

T-SQL syntax rules:
- Use TOP N instead of LIMIT (e.g., SELECT TOP 10 * FROM table)
- String concatenation uses + not ||
- Use GETDATE() instead of NOW()
- Use ISNULL() or COALESCE() for null handling
- Use DATEPART(), DATEADD(), DATEDIFF() for date operations
- When using UNION/INTERSECT/EXCEPT with ORDER BY, the ORDER BY column must appear in the SELECT list
- Use square brackets [column] for reserved words or special characters
- Use CAST(x AS VARCHAR) or CONVERT() for type conversions
"""
