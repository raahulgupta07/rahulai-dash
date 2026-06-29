"""Smart Upload — APPLY confirmed route records by calling EXISTING sinks.

The classifier (``classifier.py``) decides WHERE each uploaded file should go;
this module ACTS on a list of human-confirmed route records by dispatching each
to the matching knowledge-subsystem sink the rest of the platform already uses.
We never edit a sink — we reuse them exactly:

  * ``database``     -> ``routes.data_source_from_file.create_data_source_from_file``
                        (file -> spreadsheet Connection + DataSource, schema synced).
  * ``semantic``     -> ``ai.knowledge.doc_extractor.extract_proposal`` (binds a
                        glossary file to a target data source's live columns) +
                        merge the matched column descriptions into the schema
                        (mirrors ``routes.studio_autoconfigure.apply``).
  * ``instructions`` -> ``ai.packs.teach.classify`` (file text -> spans) +
    / ``examples``      ``ai.packs.teach.apply_spans`` (spans -> StudioInstruction /
                        StudioExample / KnowledgeDoc, **all born pending**).
  * ``knowledge``    -> ``ai.knowledge.docs_index.ingest_doc`` (chunks + indexes a
                        doc, **born pending**).
  * ``skip``         -> no-op.

Design contract (mirrors the classifier): every per-item dispatch runs in its
OWN ``try/except`` so one failure never blocks the others, and answer-changing
writes (semantic/instructions/examples/knowledge) land as **pending** — we never
force-approve. Returns a JSON-friendly summary ``{applied, results:[...]}``.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from app.services.smart_upload import contract
from app.services.smart_upload.contract import (
    DEST_DATABASE,
    DEST_EXAMPLES,
    DEST_INSTRUCTIONS,
    DEST_KNOWLEDGE,
    DEST_SEMANTIC,
    DEST_SKIP,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# File text extraction — reuse the classifier's own readers (no new deps)
# --------------------------------------------------------------------------- #
async def _load_file(db, organization, file_id: str):
    """Load a File row scoped to the org, or None. Never raises."""
    try:
        from sqlalchemy import select
        from app.models.file import File as FileModel

        res = await db.execute(
            select(FileModel).where(
                FileModel.id == str(file_id),
                FileModel.organization_id == organization.id,
            )
        )
        return res.scalar_one_or_none()
    except Exception:  # noqa: BLE001
        logger.warning("smart_upload.apply: file load failed for %s", file_id,
                       exc_info=True)
        return None


def _resolve_path(stored_path: str) -> Optional[str]:
    """Reuse the canonical upload-path resolver (traversal-safe)."""
    try:
        from app.routes.data_source_from_file import _resolve_upload_path
        return _resolve_upload_path(stored_path or "")
    except Exception:  # noqa: BLE001
        return None


def _file_text(path: str, filename: str) -> str:
    """Extract prose text from a file, reusing the classifier's readers.

    Tabular files degrade to a small CSV head; unsupported -> "". Never raises.
    """
    from app.services.smart_upload import classifier

    ext = os.path.splitext(filename or path or "")[1].lower()
    try:
        if ext in classifier._TABULAR_EXTS:
            df, _ = classifier._read_tabular(path, ext)
            if df is not None:
                return df.head(200).to_csv(index=False)
            return ""
        text, _ = classifier._extract_text(path, ext, filename)
        return text or ""
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# Per-destination sink dispatch — each reuses an existing subsystem, fail-soft
# --------------------------------------------------------------------------- #
async def _apply_database(db, *, organization, current_user, file_id, filename):
    """database sink: file -> DataSource via the existing from-file route."""
    from app.routes.data_source_from_file import (
        create_data_source_from_file,
        DataSourceFromFileRequest,
    )

    payload = DataSourceFromFileRequest(
        file_id=str(file_id),
        data_source_name=(filename or None),
    )
    body = await create_data_source_from_file(
        payload=payload,
        current_user=current_user,
        db=db,
        organization=organization,
    )
    body = body if isinstance(body, dict) else {}
    return {
        "data_source_id": body.get("id"),
        "name": body.get("name"),
        "tables": len(body.get("tables") or []),
        "reused": body.get("reused", False),
    }


async def _apply_semantic(db, *, organization, file_id, data_source_id):
    """semantic sink: bind a glossary file to a data source's live columns.

    Reuses ``doc_extractor.extract_proposal`` (fuzzy-matches the glossary to the
    schema) then merges the matched column descriptions into the
    ``DataSourceTable.columns`` JSON — the same write ``studio_autoconfigure``
    performs when a reviewed proposal is applied.
    """
    if not data_source_id:
        raise ValueError("semantic routing needs a target data_source_id")

    from app.ai.knowledge.doc_extractor import extract_proposal
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified
    from app.models.datasource_table import DataSourceTable

    proposal = await extract_proposal(
        db, organization=organization,
        file_ids=[str(file_id)], data_source_id=str(data_source_id),
    )
    if isinstance(proposal, dict) and proposal.get("error"):
        raise ValueError(proposal["error"])

    col_defs = (proposal or {}).get("column_descriptions") or []

    tbl_res = await db.execute(
        select(DataSourceTable).where(
            DataSourceTable.datasource_id == str(data_source_id),
            DataSourceTable.is_active == True,  # noqa: E712
        )
    )
    tables = list(tbl_res.scalars().all())
    by_id = {str(t.id): t for t in tables}

    def _norm(s: str) -> str:
        return "".join(ch for ch in (s or "").lower().strip() if ch.isalnum())

    written, unmatched = 0, []
    for cd in col_defs:
        col = str((cd or {}).get("column", "")).strip()
        desc = str((cd or {}).get("description", "")).strip()
        if not col or not desc:
            continue
        tid = (cd or {}).get("table_id")
        candidates = [by_id[str(tid)]] if (tid and str(tid) in by_id) else tables
        applied = False
        col_norm = _norm(col)
        for t in candidates:
            cols = t.columns
            if not isinstance(cols, list) or not cols:
                continue
            changed = False
            for entry in cols:
                if not isinstance(entry, dict):
                    continue
                ename = entry.get("name") or ""
                if (ename == col or ename.lower().strip() == col.lower().strip()
                        or _norm(ename) == col_norm):
                    entry["description"] = desc
                    changed = True
                    applied = True
                    break
            if changed:
                flag_modified(t, "columns")
                break
        if applied:
            written += 1
        else:
            unmatched.append(col)

    await db.commit()
    return {
        "descriptions_written": written,
        "columns_unmatched": unmatched,
        "data_source_id": str(data_source_id),
    }


async def _apply_teach(db, *, organization, studio_id, path, filename):
    """instructions/examples sink: file text -> spans -> pending studio rows.

    ``teach.classify`` turns the prose into typed spans (INSTRUCTION / DATA_RULE
    / KNOWLEDGE / SKILL / example); ``teach.apply_spans`` persists them — every
    span born ``status='pending'`` (the existing review gate).
    """
    from app.ai.packs import teach

    text = _file_text(path, filename)
    if not text or not text.strip():
        raise ValueError("no extractable text in file")

    spans = await teach.classify(db, organization, text)
    if not spans:
        return {"spans": 0, "note": "classifier produced no spans"}

    created = await teach.apply_spans(
        db, organization, str(studio_id), spans, default_status="pending"
    )
    summary = dict(created) if isinstance(created, dict) else {}
    summary["spans"] = len(spans)
    return summary


async def _apply_knowledge(db, *, organization, file_id, filename, path,
                           data_source_id):
    """knowledge sink: chunk + index the doc as a pending KnowledgeDoc."""
    from app.ai.knowledge.docs_index import ingest_doc

    text = _file_text(path, filename)
    if not text or not text.strip():
        raise ValueError("no extractable text in file")

    res = await ingest_doc(
        db, organization=organization,
        title=(filename or "Uploaded document"),
        body=text, source="upload",
        data_source_id=(str(data_source_id) if data_source_id else None),
    )
    res = res if isinstance(res, dict) else {}
    return {
        "doc_id": res.get("doc_id"),
        "chunks": res.get("chunks"),
        "deduped": res.get("deduped", False),
    }


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
async def apply_routes(
    db, *, organization, current_user, studio_id, data_source_id,
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply a list of confirmed route records by dispatching to existing sinks.

    ``items`` = [{file_id, filename?, dest, ...}, ...]. Each item is dispatched
    by ``dest`` in its OWN try/except (one failure never blocks the others). A
    per-item result ``{file_id, dest, ok, detail, created}`` is collected.

    Returns ``{applied: <n ok>, results: [...]}``.
    """
    results: List[Dict[str, Any]] = []

    for item in (items or []):
        item = item if isinstance(item, dict) else {}
        file_id = item.get("file_id")
        dest = str(item.get("dest") or "").strip().lower()
        # Defensive: coerce unknown destinations to knowledge (contract default).
        if dest not in contract.ALL_DESTS_SET:
            dest = contract.normalize_record({"dest": dest})["dest"]

        result: Dict[str, Any] = {
            "file_id": file_id, "dest": dest, "ok": False,
            "detail": "", "created": {},
        }

        if dest == DEST_SKIP:
            result.update(ok=True, detail="skipped (no-op)")
            results.append(result)
            continue

        try:
            # Resolve the File row + on-disk path for the text-based sinks.
            file = None
            filename = item.get("filename") or ""
            path = ""
            if file_id is not None:
                file = await _load_file(db, organization, file_id)
                if file is None:
                    raise ValueError("file not found in this organization")
                filename = filename or (file.filename or "")
                if dest in (DEST_INSTRUCTIONS, DEST_EXAMPLES, DEST_KNOWLEDGE):
                    path = _resolve_path(file.path or "")
                    if not path:
                        raise ValueError("file content missing on disk")

            if dest == DEST_DATABASE:
                created = await _apply_database(
                    db, organization=organization, current_user=current_user,
                    file_id=file_id, filename=filename,
                )
            elif dest == DEST_SEMANTIC:
                created = await _apply_semantic(
                    db, organization=organization, file_id=file_id,
                    data_source_id=data_source_id,
                )
            elif dest in (DEST_INSTRUCTIONS, DEST_EXAMPLES):
                created = await _apply_teach(
                    db, organization=organization, studio_id=studio_id,
                    path=path, filename=filename,
                )
            elif dest == DEST_KNOWLEDGE:
                created = await _apply_knowledge(
                    db, organization=organization, file_id=file_id,
                    filename=filename, path=path, data_source_id=data_source_id,
                )
            else:  # pragma: no cover - normalized above
                created = {}

            result.update(ok=True, detail="applied", created=created or {})
        except Exception as e:  # one bad item never sinks the batch
            logger.warning("smart_upload.apply: %s sink failed for file %s: %s",
                           dest, file_id, e, exc_info=True)
            # A failed write may have left the session dirty — roll back so the
            # next item starts clean.
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            result.update(ok=False, detail=f"{type(e).__name__}: {e}")

        results.append(result)

    applied = sum(1 for r in results if r.get("ok"))
    return {"applied": applied, "results": results}
