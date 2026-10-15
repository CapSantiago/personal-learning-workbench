"""Synthetic M0 storage probes, NOT production storage or a recovery system.

Only E:/Projects/PLW/.sandbox/m0 is accepted at runtime. Never place real learning
data or damaged databases here. Tests replace the private allowed-root constant
with a unique directory inside this project's .sandbox/test-runs tree.

An operation journal makes failed/interrupted imports detectable. This is not a
complete M2 recovery protocol: failed staging/published files are retained for
inspection, and there is no automatic retry, deletion, backup, or repair.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import uuid


_PROJECT_ROOT = Path("E:/Projects/PLW")
_ALLOWED_ROOT = _PROJECT_ROOT / ".sandbox" / "m0"
_DB_NAME = "probe.sqlite3"
_APPLICATION_ID = 0x504C5730
_SCHEMA_VERSION = 1
_LOCK = threading.RLock()
_MODES = {"managed_copy", "external_reference"}
_SCHEMA = (
    "CREATE TABLE probe_parents (id TEXT PRIMARY KEY)",
    """CREATE TABLE probe_operations (
        operation_id TEXT PRIMARY KEY,
        source_path TEXT NOT NULL,
        storage_mode TEXT NOT NULL CHECK(storage_mode IN
            ('managed_copy', 'external_reference')),
        status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'failed')),
        candidate_relative_path TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE probe_imports (
        id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE REFERENCES probe_operations(operation_id),
        parent_id TEXT NOT NULL REFERENCES probe_parents(id),
        storage_mode TEXT NOT NULL CHECK(storage_mode IN
            ('managed_copy', 'external_reference')),
        original_path TEXT NOT NULL,
        managed_relative_path TEXT UNIQUE,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
        status TEXT NOT NULL CHECK(status = 'active'),
        created_at TEXT NOT NULL,
        CHECK ((storage_mode = 'managed_copy' AND managed_relative_path IS NOT NULL)
            OR (storage_mode = 'external_reference' AND managed_relative_path IS NULL))
    )""",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _key(path: Path) -> str:
    return os.path.normcase(str(path))


def _reject_reparse_chain(path: Path) -> None:
    for item in (path, *path.parents):
        try:
            details = item.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(details, "st_file_attributes", 0)
        if stat.S_ISLNK(details.st_mode) or attributes & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise ValueError(f"Links/junctions/reparse paths are not accepted: {item}")


def _checked_root(root: Path | str) -> Path:
    candidate = _canonical(root)
    allowed = _canonical(_ALLOWED_ROOT)
    sandbox = _canonical(_PROJECT_ROOT / ".sandbox")
    # The second check limits even the private test override to project sandboxes.
    if not allowed.is_relative_to(sandbox) or _key(candidate) != _key(allowed):
        raise ValueError("The probe accepts only its configured synthetic sandbox root")
    _reject_reparse_chain(candidate)
    return candidate


def _checked_source(root: Path, source: Path | str, *, must_exist: bool) -> Path:
    path = _canonical(source)
    sources = root / "sources"
    if not path.is_relative_to(sources) or path == sources:
        raise ValueError("Source must be an ordinary synthetic file inside sandbox/sources")
    if any(":" in part for part in path.parts[1:]):
        raise ValueError("Alternate data streams are not supported")
    _reject_reparse_chain(path)
    if must_exist:
        details = path.stat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise ValueError("Source must be an ordinary file, not a directory or hard link")
    return path


def _checked_internal(root: Path, relative: str) -> Path:
    path = _canonical(root / relative)
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Internal path escapes the synthetic sandbox")
    _reject_reparse_chain(path)
    return path


def _connect(root: Path | str, *, read_only: bool = False, create: bool = False) -> sqlite3.Connection:
    """Internal connection factory. Read paths never create a database."""
    root = _checked_root(root)
    db = _checked_internal(root, _DB_NAME)
    for suffix in ("-journal", "-wal", "-shm"):
        _checked_internal(root, _DB_NAME + suffix)
    mode = "ro" if read_only else ("rwc" if create else "rw")
    connection = sqlite3.connect(
        db.as_uri() + "?mode=" + mode, uri=True, timeout=3, isolation_level=None
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 3000")
        if not read_only and create:
            connection.execute("PRAGMA journal_mode = DELETE")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("Foreign-key enforcement unavailable")
        if connection.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete":
            raise RuntimeError("Probe requires rollback journal mode DELETE")
        if connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise RuntimeError("Probe requires synchronous FULL")
    except BaseException:
        connection.close()
        raise
    return connection


def _check_schema(connection: sqlite3.Connection) -> None:
    app_id = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if app_id != _APPLICATION_ID or version != _SCHEMA_VERSION:
        raise ValueError("Not this synthetic probe's database; refusing to modify or repair it")


def initialize(root: Path | str) -> None:
    """Create only the minimal synthetic probe database; never a business schema."""
    with _LOCK:
        root = _checked_root(root)
        db = _checked_internal(root, _DB_NAME)
        if db.exists():
            with closing(_connect(root, read_only=True)) as connection:
                _check_schema(connection)
            return
        root.mkdir(parents=True, exist_ok=True)
        for folder in ("sources", "managed", "staging"):
            _checked_internal(root, folder).mkdir(exist_ok=True)
        with closing(_connect(root, create=True)) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO probe_parents(id) VALUES ('m0-demo')")
                connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise


def _synthetic_pdf() -> bytes:
    stream = b"BT /F1 20 Tf 72 760 Td (PLW M0 - Synthetic PDF) Tj 0 -32 Td (No real learning data.) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(data)


def create_demo_sources(root: Path | str) -> dict[str, Path]:
    """Create tiny synthetic fixtures, without overwriting any existing file."""
    with _LOCK:
        root = _checked_root(root)
        sources = _checked_internal(root, "sources")
        sources.mkdir(parents=True, exist_ok=True)
        payloads = {
            "chinese_text": ("合成资料 中文 空格.txt", "PLW M0 合成资料，仅用于技术验证。\nNo real learning data.\n".encode("utf-8")),
            "pdf": ("合成 PDF 样本.pdf", _synthetic_pdf()),
        }
        result = {}
        for key, (filename, content) in payloads.items():
            path = _checked_source(root, sources / filename, must_exist=False)
            if path.exists():
                _checked_source(root, path, must_exist=True)
                if path.read_bytes() != content:
                    raise ValueError(f"Existing synthetic fixture differs; not overwriting: {path.name}")
            else:
                with path.open("xb") as output:
                    output.write(content)
            result[key] = path
        return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    details = path.stat()
    return (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns, details.st_ctime_ns)


def _measure_source(source: Path) -> tuple[int, str]:
    before = _fingerprint(source)
    digest = _hash_file(source)
    if before != _fingerprint(source):
        raise RuntimeError("Synthetic source changed during verification")
    return before[2], digest


def _copy_verified(source: Path, destination: Path) -> tuple[int, str]:
    """Stream a synthetic source into a new staging file; do not alter the source."""
    before = _fingerprint(source)
    digest = hashlib.sha256()
    copied = 0
    with source.open("rb") as original, destination.open("xb") as output:
        while chunk := original.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            copied += len(chunk)
        output.flush()
        os.fsync(output.fileno())
    expected = digest.hexdigest()
    if before != _fingerprint(source) or copied != before[2]:
        raise RuntimeError("Synthetic source changed during copy")
    if _hash_file(destination) != expected or _hash_file(source) != expected:
        raise RuntimeError("Copy checksum mismatch or synthetic source changed")
    if before != _fingerprint(source):
        raise RuntimeError("Synthetic source changed during checksum verification")
    return copied, expected


def _activate_import(connection: sqlite3.Connection, record: dict) -> None:
    """Fault-injection seam; caller owns the transaction."""
    connection.execute(
        """INSERT INTO probe_imports
           (id, operation_id, parent_id, storage_mode, original_path,
            managed_relative_path, size_bytes, sha256, status, created_at)
           VALUES (:id, :operation_id, :parent_id, :storage_mode, :original_path,
                   :managed_relative_path, :size_bytes, :sha256, :status, :created_at)""",
        record,
    )
    connection.execute(
        "UPDATE probe_operations SET status='completed', updated_at=? WHERE operation_id=?",
        (record["created_at"], record["operation_id"]),
    )


def _commit(connection: sqlite3.Connection) -> None:
    """Fault-injection seam for a failed COMMIT before activation becomes durable."""
    connection.execute("COMMIT")


def probe_import(root: Path | str, source: Path | str, mode: str, operation_id: str) -> dict:
    """Import a synthetic source, or return the completed result for the same UUID.

    Same ID + different path/mode is rejected. A failed/pending ID cannot be
    retried automatically. Exceptions never return a success record. This is
    only an M0 probe, not a production ingest or crash-recovery implementation.
    """
    with _LOCK:
        root = _checked_root(root)
        if mode not in _MODES:
            raise ValueError("Unknown storage mode")
        try:
            operation_id = str(uuid.UUID(operation_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("operation_id must be a UUID string") from error
        source = _checked_source(root, source, must_exist=False)
        with closing(_connect(root)) as connection:
            _check_schema(connection)
            existing = connection.execute(
                "SELECT * FROM probe_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if existing is not None:
                if _key(Path(existing["source_path"])) != _key(source) or existing["storage_mode"] != mode:
                    raise ValueError("Operation ID already used with different payload")
                if existing["status"] != "completed":
                    raise RuntimeError(f"Operation is {existing['status']}; inspect it and use a new ID")
                result = connection.execute(
                    "SELECT * FROM probe_imports WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if result is None:
                    raise RuntimeError("Completed operation has no import; refusing false success")
                return dict(result)

            source = _checked_source(root, source, must_exist=True)
            suffix = source.suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", source.suffix) else ".bin"
            relative = f"managed/{operation_id}{suffix}" if mode == "managed_copy" else None
            now = _utc_now()
            connection.execute(
                """INSERT INTO probe_operations
                   (operation_id, source_path, storage_mode, status,
                    candidate_relative_path, created_at, updated_at)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
                (operation_id, str(source), mode, relative, now, now),
            )
            try:
                if mode == "managed_copy":
                    stage = _checked_internal(root, f"staging/{operation_id}.part")
                    target = _checked_internal(root, relative)
                    stage.parent.mkdir(exist_ok=True)
                    target.parent.mkdir(exist_ok=True)
                    if target.exists():
                        raise FileExistsError("Candidate managed file already exists; not overwriting")
                    size, digest = _copy_verified(source, stage)
                    # Windows rename fails if a target already exists; source is never moved.
                    os.rename(stage, target)
                else:
                    size, digest = _measure_source(source)
                record = {
                    "id": operation_id, "operation_id": operation_id,
                    "parent_id": "m0-demo", "storage_mode": mode,
                    "original_path": str(source), "managed_relative_path": relative,
                    "size_bytes": size, "sha256": digest,
                    "status": "active", "created_at": _utc_now(),
                }
                connection.execute("BEGIN IMMEDIATE")
                _activate_import(connection, record)
                _commit(connection)
            except Exception as error:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                try:
                    connection.execute(
                        """UPDATE probe_operations SET status='failed', error=?, updated_at=?
                           WHERE operation_id=? AND status='pending'""",
                        (f"{type(error).__name__}: {error}"[:500], _utc_now(), operation_id),
                    )
                except sqlite3.Error:
                    # A persistent pending row still makes a database-write failure detectable.
                    pass
                raise
            return record


def list_imports(root: Path | str) -> list[dict]:
    """Read active synthetic imports. Missing DB returns []; never create anything."""
    root = _checked_root(root)
    if not _checked_internal(root, _DB_NAME).exists():
        return []
    with closing(_connect(root, read_only=True)) as connection:
        _check_schema(connection)
        return [dict(row) for row in connection.execute(
            "SELECT * FROM probe_imports ORDER BY created_at, id"
        )]
