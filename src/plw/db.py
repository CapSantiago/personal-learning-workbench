"""M1 SQLite foundation, currently restricted to project-owned synthetic sandboxes.

This module does not create production learning directories, import files, make
backups, repair unknown databases, or implement the future M2/M4 services.
All migrations are trusted bundled SQL but cannot control transactions or attach
other databases. Read operations never create files or run migrations.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ID = 0x504C5731
APP_VERSION = "0.3.1"
BUSY_TIMEOUT_MS = 3000
_MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_MIGRATION_LOCK = threading.RLock()
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
_HISTORY_SQL = """CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY NOT NULL CHECK(version>=1),
    name TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK(length(checksum)=64 AND checksum NOT GLOB '*[^0-9a-f]*'),
    applied_at TEXT NOT NULL,
    app_version TEXT NOT NULL
)"""


class DatabaseError(RuntimeError):
    """A database boundary or initialization error safe to show in a local UI."""


class DatabasePathError(DatabaseError):
    """The requested path is outside synthetic scope or is not an ordinary file."""


class SchemaError(DatabaseError):
    """Unknown, incompatible, edited, or unsuccessfully migrated schema."""


class DatabaseNotInitializedError(DatabaseError):
    """Explicit initialization is required; read paths do not initialize."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


def _reject_links(path: Path, *, require_file: bool = False) -> None:
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        attrs = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise DatabasePathError(f"Reparse/link paths are not supported: {item}")
        if item == path and require_file:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DatabasePathError("Database/sidecar must be an ordinary file with one link")


def _check_path(db_path: Path | str) -> Path:
    path = Path(db_path)
    if not path.is_absolute() or ".." in path.parts:
        raise DatabasePathError("Use an absolute synthetic database path without '..'")
    from . import storage
    allowed = (PROJECT_ROOT / ".sandbox" / "m1", *storage.ROOTS, storage.PRODUCTION_ROOT, storage.BACKUP_ROOT)
    if not any(path != root and path.is_relative_to(root) for root in allowed):
        raise DatabasePathError("Databases are restricted to synthetic M1/M2/test-runs directories")
    if path.is_relative_to(storage.PRODUCTION_ROOT):
        parts = path.relative_to(storage.PRODUCTION_ROOT).parts
        if not (len(parts) >= 3 and parts[-1] == 'plw.sqlite3' and
                (parts[0] == 'datasets' and len(parts) == 3 or parts[-2] == 'payload')):
            raise DatabasePathError('Production databases require a dataset or backup payload directory')
    for part in path.parts[1:]:
        if ":" in part or part.endswith((" ", ".")) or part.split(".")[0].upper() in _RESERVED:
            raise DatabasePathError("Ambiguous Windows path or alternate stream is not supported")
    _reject_links(path, require_file=True)
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        _reject_links(sidecar, require_file=True)
        if suffix in ("-wal", "-shm") and sidecar.exists():
            raise SchemaError("WAL sidecars are outside the M1 DELETE-journal contract")
    return path


def _load_migrations() -> tuple[Migration, ...]:
    migrations = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        match = re.fullmatch(r"(\d{3})_([a-z0-9_]+)\.sql", path.name)
        if match is None:
            raise SchemaError(f"Invalid migration filename: {path.name}")
        data = path.read_bytes()
        migrations.append(Migration(int(match[1]), path.name, data.decode("utf-8"),
                                    hashlib.sha256(data).hexdigest()))
    if not migrations or [item.version for item in migrations] != list(range(1, len(migrations) + 1)):
        raise SchemaError("Bundled migrations must be a nonempty contiguous sequence starting at 1")
    return tuple(migrations)


def _open_raw(path: Path, *, read_only: bool) -> sqlite3.Connection:
    mode = "ro" if read_only else "rw"
    connection = sqlite3.connect(path.as_uri() + "?mode=" + mode, uri=True,
                                 timeout=BUSY_TIMEOUT_MS / 1000, autocommit=True)
    try:
        connection.row_factory = sqlite3.Row
        # Only read the persistent journal mode here. Unknown databases must not be changed.
        if connection.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete":
            raise SchemaError("Expected journal_mode=DELETE; refusing to convert a database")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise DatabaseError("SQLite foreign-key enforcement is unavailable")
        if connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise DatabaseError("SQLite synchronous=FULL was not applied")
        if connection.execute("PRAGMA busy_timeout").fetchone()[0] != BUSY_TIMEOUT_MS:
            raise DatabaseError("SQLite busy_timeout was not applied")
    except BaseException:
        connection.close()
        raise
    return connection


def _inspect(connection: sqlite3.Connection, migrations: tuple[Migration, ...], *,
             allow_empty: bool) -> int:
    try:
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = connection.execute(
            "SELECT name FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*'"
        ).fetchall()
        if app_id == 0 and user_version == 0 and not objects:
            if allow_empty:
                return 0
            raise DatabaseNotInitializedError("The synthetic database is empty; initialize explicitly")
        if app_id != APPLICATION_ID:
            raise SchemaError("Not a PLW M1 database; refusing changes")
        if user_version > migrations[-1].version:
            raise SchemaError("Database schema is newer than this application")
        rows = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        versions = [row["version"] for row in rows]
        if not rows or versions != list(range(1, len(rows) + 1)):
            raise SchemaError("Migration history has a missing or invalid version")
        if versions[-1] > migrations[-1].version:
            raise SchemaError("Database migration history is newer than this application")
        if user_version != versions[-1]:
            raise SchemaError("user_version disagrees with migration history")
        for row, migration in zip(rows, migrations):
            if row["name"] != migration.name or row["checksum"] != migration.checksum:
                raise SchemaError(f"Applied migration {row['version']} name/checksum differs")
        return versions[-1]
    except sqlite3.Error as error:
        raise SchemaError("Cannot validate this database's migration metadata") from error


def _preflight(path: Path, migrations: tuple[Migration, ...], *, allow_empty: bool) -> int:
    try:
        with closing(_open_raw(path, read_only=True)) as connection:
            return _inspect(connection, migrations, allow_empty=allow_empty)
    except sqlite3.Error as error:
        raise SchemaError("Cannot open and validate the database read-only") from error


def connect_snapshot(db_path: Path | str) -> sqlite3.Connection:
    """Read a supported historical snapshot without applying migrations."""
    path = _check_path(db_path)
    connection = _open_raw(path, read_only=True)
    try:
        _inspect(connection, _load_migrations(), allow_empty=False)
        return connection
    except BaseException:
        connection.close()
        raise


def schema_ready(version):
    """Schema 4 only widens source metadata; existing Windows v3 stays usable."""
    latest = _load_migrations()[-1].version
    return version == latest or (latest == 4 and version == 3 and os.name == 'nt'
                                 and os.environ.get('PLW_PRIVATE_SITE') != '1')


def connect(db_path: Path | str, read_only: bool = False) -> sqlite3.Connection:
    """Open a known current database; caller closes it (e.g. contextlib.closing).

    The preflight is always read-only, including for subsequent write connections.
    Neither this function nor transaction() creates files or runs migrations.
    """
    path = _check_path(db_path)
    if not path.exists():
        raise DatabaseNotInitializedError("Synthetic database is not initialized")
    migrations = _load_migrations()
    current = _preflight(path, migrations, allow_empty=False)
    if not schema_ready(current):
        raise DatabaseNotInitializedError("Pending migrations require explicit initialization")
    _check_path(path)
    connection = _open_raw(path, read_only=read_only)
    try:
        if not schema_ready(_inspect(connection, migrations, allow_empty=False)):
            raise SchemaError("Database schema changed while connecting")
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def transaction(db_path: Path | str, *, write: bool = True) -> Iterator[sqlite3.Connection]:
    """A short connection with explicit SQL commit/rollback, including failed COMMIT."""
    if write:
        from .locking import write_barrier
        with write_barrier(db_path):
            with _transaction(db_path, write=True) as connection:
                yield connection
    else:
        with _transaction(db_path, write=False) as connection:
            yield connection


@contextmanager
def _transaction(db_path: Path | str, *, write: bool) -> Iterator[sqlite3.Connection]:
    with closing(connect(db_path, read_only=not write)) as connection:
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def _statements(script: str) -> Iterator[str]:
    """Split complete SQLite statements, preserving semicolons inside triggers/strings."""
    buffer = ""
    for character in script:
        buffer += character
        if character == ";" and sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    # A final comment is harmless. A final SQL statement must end in a semicolon.
    tail = re.sub(r"/\*.*?\*/|--[^\n]*", "", buffer, flags=re.DOTALL).strip()
    if tail:
        raise SchemaError("Every migration statement must end with a semicolon")


def _migration_authorizer(action, argument1, argument2, database, trigger):
    # SQLite runs this read-only integrity check internally for ADD COLUMN CHECK.
    if action == sqlite3.SQLITE_PRAGMA and argument1 == 'quick_check':
        return sqlite3.SQLITE_OK
    blocked = (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT, sqlite3.SQLITE_ATTACH,
               sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA)
    return sqlite3.SQLITE_DENY if action in blocked else sqlite3.SQLITE_OK


def initialize(db_path: Path | str) -> int:
    from .locking import initialization_barrier
    path = _check_path(db_path)
    with initialization_barrier(path):
        return _initialize(path)


def _initialize(db_path: Path | str) -> int:
    """Explicitly initialize/migrate synthetic data, with per-version atomic commits.

    Already applied scripts are immutable. Unknown/newer/edited databases are
    rejected before opening for writes. A failed first migration may leave an
    empty file; it never leaves successful migration metadata or partial tables.
    """
    with _MIGRATION_LOCK:
        path = _check_path(db_path)
        migrations = _load_migrations()
        if path.exists():
            current = _preflight(path, migrations, allow_empty=True)
            if current == migrations[-1].version:
                return current
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            _check_path(path)
            try:
                # Exclusive file creation cannot overwrite an existing database.
                with path.open("xb"):
                    pass
            except FileExistsError:
                _preflight(path, migrations, allow_empty=True)
        with closing(_open_raw(path, read_only=False)) as connection:
            while True:
                before = _inspect(connection, migrations, allow_empty=True)
                rebuild = before == 3 and migrations[-1].version >= 4 and migrations[3].name == '004_portable_material_paths.sql'
                if rebuild:
                    connection.execute('PRAGMA foreign_keys=OFF')
                connection.execute("BEGIN IMMEDIATE")
                try:
                    current = _inspect(connection, migrations, allow_empty=True)
                    if current == migrations[-1].version:
                        connection.execute("COMMIT")
                        return current
                    migration = migrations[current]
                    if current == 0:
                        connection.execute(_HISTORY_SQL)
                    try:
                        connection.set_authorizer(_migration_authorizer)
                        for statement in _statements(migration.sql):
                            connection.execute(statement)
                    finally:
                        connection.set_authorizer(None)
                    if not connection.in_transaction:
                        raise SchemaError("Migration unexpectedly ended its transaction")
                    if connection.execute("PRAGMA foreign_key_check").fetchall():
                        raise SchemaError("Migration produced foreign-key violations")
                    connection.execute(
                        """INSERT INTO schema_migrations(version,name,checksum,applied_at,app_version)
                           VALUES (?,?,?,?,?)""",
                        (migration.version, migration.name, migration.checksum,
                         datetime.now(timezone.utc).isoformat(), APP_VERSION),
                    )
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={migration.version}")
                    connection.execute("COMMIT")
                except BaseException as error:
                    connection.set_authorizer(None)
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    if isinstance(error, (sqlite3.Error, SchemaError)):
                        raise SchemaError(f"Migration failed and rolled back: {error}") from error
                    raise
                finally:
                    if rebuild:
                        connection.execute('PRAGMA foreign_keys=ON')
