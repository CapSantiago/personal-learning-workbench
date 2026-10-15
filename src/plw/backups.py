"""Verified directory backups and reversible dataset switches (synthetic M2 only).

External-reference paths are metadata: this module never opens them. Failed
backups and restored datasets remain available for diagnosis; nothing is deleted.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import uuid

from . import db, locking, storage, workspace

FORMAT_VERSION = 1
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 100_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class BackupError(RuntimeError):
    """A failed operation leaves its source dataset intact."""


class VerificationError(BackupError):
    """A backup or dataset does not meet the complete-backup contract."""


class RestoreError(BackupError):
    """A restore was rejected or interrupted; consult recovery_status()."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uuid(value):
    if not isinstance(value, str):
        raise VerificationError("Expected canonical UUID")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except ValueError as error:
        raise VerificationError("Expected canonical UUID") from error
    return value


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("Duplicate JSON key")
        result[key] = value
    return result


def _read_json(path, limit=MAX_MANIFEST_BYTES):
    storage.safe_path(path, must_exist=True, directory=False)
    if path.stat().st_size > limit:
        raise VerificationError("JSON exceeds size limit")
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(VerificationError("Invalid JSON number")))
    except (UnicodeError, ValueError) as error:
        raise VerificationError("Invalid UTF-8 JSON") from error


def _write_new(path, value):
    storage.safe_path(path, directory=False)
    with path.open("xb") as stream:
        stream.write(_json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path, value):
    storage.safe_path(path, directory=False)
    temporary = path.with_name(path.name + "." + str(uuid.uuid4()) + ".tmp")
    _write_new(temporary, value)
    storage.safe_path(path, directory=False)
    os.replace(temporary, path)
    storage.sync_directory(path.parent)


def _keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise VerificationError(f"Unexpected {label} fields")


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/"))
            or PurePosixPath(value).as_posix() != value):
        raise VerificationError("Invalid relative path")
    # storage also rejects device names, alternate streams and ambiguous Win32 names.
    return value


def _schema(connection):
    return [tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name")]


def _validate_database(path):
    with closing(db.connect_snapshot(path)) as connection:
        if [row[0] for row in connection.execute("PRAGMA integrity_check")] != ["ok"]:
            raise VerificationError("SQLite integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise VerificationError("SQLite foreign_key_check failed")
        with closing(sqlite3.connect(":memory:")) as expected:
            expected.execute(db._HISTORY_SQL)
            for migration in db._load_migrations()[:connection.execute("PRAGMA user_version").fetchone()[0]]:
                expected.executescript(migration.sql)
            if _schema(connection) != _schema(expected):
                raise VerificationError("Database has unknown or altered schema objects")
        return connection.execute("PRAGMA user_version").fetchone()[0]


def _table_digests(path, reference=None):
    with closing(db.connect_snapshot(path)) as connection:
        names = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT GLOB 'sqlite_*' ORDER BY name")]
        if reference is not None:
            with closing(db.connect_snapshot(reference)) as ref:
                columns = {row[0]: [c[1] for c in ref.execute('PRAGMA table_info("' + row[0] + '")')] for row in ref.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT GLOB 'sqlite_*'")}
            names = [n for n in columns if n != 'schema_migrations']
        else:
            columns = {n: ['*'] for n in names}
        return {name: hashlib.sha256(_json_bytes(sorted(
            [list(row) for row in connection.execute('SELECT ' + ','.join(columns[name]) + ' FROM "' + name.replace('"', '""') + '"')],
            key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True)))).hexdigest() for name in names}


def _catalog(path):
    """Use snapshot metadata, never live external file state."""
    files, external, deleted = [], [], []
    with closing(db.connect_snapshot(path)) as connection:
        if connection.execute("SELECT 1 FROM file_operations WHERE state<>'committed' LIMIT 1").fetchone():
            raise VerificationError("Unresolved file operations prevent a complete backup")
        if connection.execute("SELECT 1 FROM materials WHERE import_state<>'ready' LIMIT 1").fetchone():
            raise VerificationError("Unfinished material imports prevent a complete backup")
        for raw in connection.execute("SELECT * FROM materials ORDER BY id"):
            row = dict(raw)
            if row["storage_mode"] == "external_reference":
                external.append({"material_id": row["id"], "course_id": row["course_id"],
                    "original_path": row["original_path"], "reference_path": row["reference_path"],
                    "size_bytes": row["size_bytes"], "baseline_sha256": row["baseline_sha256"],
                    "last_checked_at": row["last_checked_at"], "recorded_status": row["file_status"],
                    "included": False, "reason": "index_only_not_inspected"})
            elif row["file_deleted_at"] is not None:
                rel = _relative(row["managed_relpath"])
                if len(rel.split("/")) != 3 or rel.split("/")[:2] != ["managed", row["id"]]:
                    raise VerificationError("Deleted managed path does not match identity")
                evidence = connection.execute("""SELECT payload_json,expected_sha256 FROM file_operations
                    WHERE kind='delete_managed_file' AND state='committed' AND entity_id=? AND target_relpath=?""",
                    (row["id"], rel)).fetchall()
                if not row["baseline_sha256"] or not any(
                    item["expected_sha256"] == row["baseline_sha256"]
                    and json.loads(item["payload_json"], object_pairs_hook=_pairs) == {"confirmation": row["id"]}
                    for item in evidence):
                    raise VerificationError("Deleted body has no committed, confirmed deletion evidence")
                deleted.append({"material_id": row["id"], "relative_path": row["managed_relpath"],
                                "deleted_at": row["deleted_at"], "file_deleted_at": row["file_deleted_at"]})
            else:
                rel = _relative(row["managed_relpath"])
                if len(rel.split("/")) != 3 or rel.split("/")[:2] != ["managed", row["id"]]:
                    raise VerificationError("Managed path does not match its material identity")
                files.append({"type": "managed", "relative_path": rel, "entity_id": row["id"],
                              "size_bytes": row["size_bytes"], "sha256": row["baseline_sha256"]})
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
            if connection.execute("SELECT 1 FROM content_operations WHERE state<>'committed' LIMIT 1").fetchone():
                raise VerificationError("Unresolved reading/note operations prevent complete backup")
            for row in connection.execute("SELECT * FROM reading_editions ORDER BY id"):
                rel = _relative(row['pdf_relpath'])
                if rel != f"reading/{row['id']}.pdf":
                    raise VerificationError("Reading PDF path differs from edition identity")
                count = connection.execute("SELECT count(*) FROM edition_pages WHERE edition_id=? AND page BETWEEN 1 AND ?", (row['id'], row['page_count'])).fetchone()[0]
                if count != row['page_count']:
                    raise VerificationError("Edition page catalog is incomplete")
                files.append({'type':'reading_pdf', 'relative_path':rel, 'entity_id':row['id'], 'size_bytes':row['size_bytes'], 'sha256':row['pdf_sha256']})
        for row in connection.execute("SELECT * FROM note_revisions ORDER BY id"):
            rel = _relative(row["body_relpath"])
            if rel != f"notes/{row['note_id']}/{row['id']}.md":
                raise VerificationError("Note revision path does not match its identity")
            files.append({"type": "note_revision", "relative_path": rel, "entity_id": row["id"],
                          "size_bytes": row["size_bytes"], "sha256": row["sha256"]})
        if connection.execute("SELECT 1 FROM notes WHERE current_revision_id IS NULL LIMIT 1").fetchone():
            raise VerificationError("A note has no committed current revision")
    for entry in files:
        if type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0 or not isinstance(entry["sha256"], str) or not _SHA.fullmatch(entry["sha256"]):
            raise VerificationError("Internal file has no trusted size/hash baseline")
    return files, external, deleted


def _empty_directories(path):
    """Known empty operation directories are not unknown leftover file bodies."""
    result = {"managed", "notes", ".staging", "staging", "reading"}
    with closing(db.connect_snapshot(path)) as connection:
        result.update("managed/" + row[0] for row in connection.execute(
            "SELECT id FROM materials WHERE storage_mode='managed_copy'"))
        for row in connection.execute("SELECT id FROM file_operations WHERE state='committed'"):
            result.add(".staging/" + row[0])
    return result


def _tree(root):
    root = storage.safe_path(root, must_exist=True, directory=True)
    files, directories = set(), set()
    def visit(folder):
        for item in folder.iterdir():
            item = storage.safe_path(item, root=root, must_exist=True)
            rel = item.relative_to(root).as_posix()
            if item.is_dir():
                directories.add(rel)
                visit(item)
            else:
                storage.safe_path(item, root=root, must_exist=True, directory=False)
                files.add(rel)
    visit(root)
    return files, directories


def _ancestors(files):
    return {parent.as_posix() for value in files for parent in PurePosixPath(value).parents
            if parent.as_posix() != "."}


def _exact_tree(root, expected_files, allowed_empty=()):
    files, directories = _tree(root)
    if files != set(expected_files) or directories - _ancestors(expected_files) - set(allowed_empty):
        raise VerificationError("Unexpected or missing internal files/directories")
    folded = [p.casefold() for p in files | directories]
    if len(folded) != len(set(folded)):
        raise VerificationError("Case-colliding internal paths")


def _config(dataset):
    config = _read_json(dataset / "config.json", 4096)
    _keys(config, {"format_version", "dataset_id"}, "dataset config")
    if type(config["format_version"]) is not int or config["format_version"] != 1:
        raise VerificationError("Unsupported dataset config version")
    _uuid(config["dataset_id"])
    return config


def _entry(root, relative, kind, entity_id=None):
    size, digest = storage.hash_file(storage.relative_file(root, relative, must_exist=True))
    return {"type": kind, "relative_path": relative, "payload_path": "payload/" + relative,
            "size_bytes": size, "sha256": digest, "entity_id": entity_id}


def _space(parent, needed):
    if shutil.disk_usage(parent).free < needed + 8 * 1024 * 1024:
        raise BackupError("Insufficient free space; no existing backup was removed")


def _report(path, manifest):
    return {"path": str(path), "id": manifest["backup_id"], "dataset_id": manifest["dataset_id"],
            "count": len(manifest["files"]), "size_bytes": sum(e["size_bytes"] for e in manifest["files"]),
            "external": manifest["external"], "deleted": manifest["deleted"],
            "reading_pdfs": [e for e in manifest['files'] if e['type']=='reading_pdf'],
            "schema_version": manifest["schema_version"], "complete": True,
            "verified_at": _now(), "manifest_sha256": storage.hash_file(path / "manifest.json")[1]}


def create_backup(db_path, destination_parent=None):
    """Freeze PLW writes, snapshot SQLite, verify every internal file, then publish."""
    path = storage.safe_path(Path(db_path), must_exist=True, directory=False)
    dataset = path.parent
    if path.name != "plw.sqlite3" or dataset.parent.name != "datasets":
        raise BackupError("Backup source must be a workspace datasets/<UUID>/plw.sqlite3")
    _uuid(dataset.name)
    if destination_parent is None:
        if dataset.parent.name != "datasets":
            raise BackupError("Explicit backup parent is required for non-workspace datasets")
        destination_parent = storage.BACKUP_ROOT if path.is_relative_to(storage.PRODUCTION_ROOT) else dataset.parent.parent / "backups"
    parent = storage.safe_path(Path(destination_parent), directory=True)
    if parent == dataset or parent.is_relative_to(dataset) or dataset.is_relative_to(parent):
        raise BackupError("Backup source and destination must not be nested")
    if "datasets" in parent.parts:
        raise BackupError("Backup destination cannot be inside any dataset")
    with locking.write_barrier(path):
        try:
            config = _config(dataset)
            if config["dataset_id"] != dataset.name:
                raise VerificationError("Backup source identity differs from its dataset directory")
            _validate_database(path)
            catalog, external, deleted = _catalog(path)
            expected = {"plw.sqlite3", "config.json", *(e["relative_path"] for e in catalog)}
            _exact_tree(dataset, expected, _empty_directories(path))
            parent.mkdir(parents=True, exist_ok=True)
            storage.safe_path(parent, must_exist=True, directory=True)
            _space(parent, path.stat().st_size + sum(e["size_bytes"] for e in catalog) + 65536)
            backup_id = str(uuid.uuid4())
            target = parent / backup_id
            target.mkdir()
            payload = target / "payload"
            payload.mkdir()
            _write_new(target / "incomplete.json", {"backup_id": backup_id, "started_at": _now()})
            snapshot = payload / "plw.sqlite3"
            with closing(db.connect_snapshot(path)) as source, closing(sqlite3.connect(snapshot, autocommit=True)) as destination:
                source.backup(destination)
            _validate_database(snapshot)
            snapshot_catalog, snapshot_external, snapshot_deleted = _catalog(snapshot)
            if (catalog, external, deleted) != (snapshot_catalog, snapshot_external, snapshot_deleted):
                raise VerificationError("Dataset changed outside the PLW write barrier")
            storage.copy_verified(dataset / "config.json", payload / "config.json")
            files = [_entry(payload, "plw.sqlite3", "database"), _entry(payload, "config.json", "config")]
            for expected_entry in snapshot_catalog:
                rel = expected_entry["relative_path"]
                source = storage.relative_file(dataset, rel, must_exist=True)
                destination = storage.relative_file(payload, rel)
                destination.parent.mkdir(parents=True, exist_ok=True)
                size, digest = storage.copy_verified(source, destination, expected_sha256=expected_entry["sha256"])
                if (size, digest) != (expected_entry["size_bytes"], expected_entry["sha256"]):
                    raise VerificationError("Internal file differs from its trusted baseline")
                files.append(_entry(payload, rel, expected_entry["type"], expected_entry["entity_id"]))
            manifest = {"backup_format_version": FORMAT_VERSION, "backup_id": backup_id,
                "dataset_id": config["dataset_id"], "created_at_utc": _now(), "app_version": db.APP_VERSION,
                "schema_version": _validate_database(snapshot), "complete": True,
                "files": files, "external": snapshot_external, "deleted": snapshot_deleted}
            _write_new(target / "manifest.json", manifest)
            with (target / "manifest.sha256").open("xb") as stream:
                stream.write((hashlib.sha256((target / "manifest.json").read_bytes()).hexdigest() + "\n").encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
            _verify(target, published=False)
            # The marker, not manifest.complete alone, is the publication boundary.
            _write_new(target / "complete.json", {"backup_id": backup_id})
            return verify_backup(target)
        except BackupError:
            raise
        except (OSError, ValueError, sqlite3.Error, db.DatabaseError, storage.StorageError) as error:
            raise BackupError(f"Backup failed; original dataset retained: {error}") from error


def _verify_impl(path, *, published):
    path = storage.safe_path(Path(path), must_exist=True, directory=True)
    manifest_path = storage.relative_file(path, "manifest.json", must_exist=True)
    sha_path = storage.relative_file(path, "manifest.sha256", must_exist=True)
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES or sha_path.stat().st_size != 65:
        raise VerificationError("Invalid manifest size")
    claimed = sha_path.read_text(encoding="ascii").strip()
    if not _SHA.fullmatch(claimed) or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != claimed:
        raise VerificationError("Manifest checksum mismatch")
    manifest = _read_json(manifest_path)
    _keys(manifest, {"backup_format_version", "backup_id", "dataset_id", "created_at_utc", "app_version", "schema_version", "complete", "files", "external", "deleted"}, "manifest")
    if type(manifest["backup_format_version"]) is not int or manifest["backup_format_version"] != FORMAT_VERSION or manifest["complete"] is not True:
        raise VerificationError("Unsupported or incomplete backup")
    _uuid(manifest["backup_id"])
    _uuid(manifest["dataset_id"])
    if type(manifest["schema_version"]) is not int or not 1 <= manifest["schema_version"] <= db._load_migrations()[-1].version:
        raise VerificationError("Unsupported backup database schema")
    if not isinstance(manifest["app_version"], str) or not isinstance(manifest["created_at_utc"], str):
        raise VerificationError("Invalid backup metadata")
    try:
        if datetime.fromisoformat(manifest["created_at_utc"]).utcoffset().total_seconds() != 0:
            raise ValueError
    except (ValueError, AttributeError):
        raise VerificationError("Backup timestamp must be UTC") from None
    if not isinstance(manifest["files"], list) or not 2 <= len(manifest["files"]) <= MAX_FILES:
        raise VerificationError("Invalid file list")
    seen, entries = set(), {}
    for entry in manifest["files"]:
        _keys(entry, {"type", "relative_path", "payload_path", "size_bytes", "sha256", "entity_id"}, "file entry")
        rel = _relative(entry["relative_path"])
        if entry["payload_path"] != "payload/" + rel or rel.casefold() in seen:
            raise VerificationError("Duplicate or invalid payload path")
        seen.add(rel.casefold())
        if type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0 or not isinstance(entry["sha256"], str) or not _SHA.fullmatch(entry["sha256"]):
            raise VerificationError("Invalid file size/hash")
        if entry["type"] == "database":
            valid = rel == "plw.sqlite3" and entry["entity_id"] is None
        elif entry["type"] == "config":
            valid = rel == "config.json" and entry["entity_id"] is None
        elif entry["type"] in ("managed", "note_revision", "reading_pdf"):
            _uuid(entry["entity_id"])
            valid = rel.startswith({"managed":"managed/", "note_revision":"notes/", "reading_pdf":"reading/"}[entry["type"]])
        else:
            valid = False
        if not valid:
            raise VerificationError("Unknown or misplaced file type")
        file = storage.relative_file(path, entry["payload_path"], must_exist=True)
        if storage.hash_file(file) != (entry["size_bytes"], entry["sha256"]):
            raise VerificationError("Payload size/hash mismatch")
        entries[rel] = entry
    expected_files = {"manifest.json", "manifest.sha256", "incomplete.json", *(e["payload_path"] for e in manifest["files"])}
    if published:
        expected_files.add("complete.json")
        complete = _read_json(path / "complete.json", 4096)
        if complete != {"backup_id": manifest["backup_id"]}:
            raise VerificationError("Invalid publication marker")
    started = _read_json(path / "incomplete.json", 4096)
    _keys(started, {"backup_id", "started_at"}, "creation marker")
    if started["backup_id"] != manifest["backup_id"]:
        raise VerificationError("Creation marker identity mismatch")
    _exact_tree(path, expected_files)
    if set(entries).intersection({"plw.sqlite3", "config.json"}) != {"plw.sqlite3", "config.json"}:
        raise VerificationError("Required database/config is missing")
    snapshot = path / "payload" / "plw.sqlite3"
    if _validate_database(snapshot) != manifest["schema_version"]:
        raise VerificationError("Database schema does not match manifest")
    config = _config(path / "payload")
    if config["dataset_id"] != manifest["dataset_id"]:
        raise VerificationError("Dataset identity mismatch")
    expected, external, deleted = _catalog(snapshot)
    if external != manifest["external"] or deleted != manifest["deleted"]:
        raise VerificationError("External/deleted reports do not match snapshot")
    logical = {e["relative_path"]: e for e in expected}
    if set(entries) != set(logical) | {"plw.sqlite3", "config.json"}:
        raise VerificationError("Payload does not match database file references")
    for rel, entry in logical.items():
        if any(entries[rel][key] != entry[key] for key in entry):
            raise VerificationError("Payload metadata differs from trusted database baseline")
    return manifest


def _verify(path, *, published):
    try:
        return _verify_impl(path, published=published)
    except BackupError:
        raise
    except (OSError, ValueError, sqlite3.Error, db.DatabaseError, storage.StorageError) as error:
        raise VerificationError(f"Backup verification failed: {error}") from error


def verify_backup(path):
    """Independently validate directory, manifest, every file, schema and relations."""
    try:
        manifest = _verify(Path(path), published=True)
        return _report(Path(path), manifest)
    except BackupError:
        raise
    except (OSError, ValueError, sqlite3.Error, db.DatabaseError, storage.StorageError) as error:
        raise VerificationError(f"Backup verification failed: {error}") from error


def _active(root):
    pointer = root / "control" / "active.json"
    if not pointer.exists():
        return None, None
    path = workspace.active_db(root)
    return _uuid(path.parent.name), path


def _journal(root, data):
    _atomic_json(root / "control" / "restore-journal.json", data)


def recovery_status(workspace_root):
    """Read-only restart diagnosis; never guesses from timestamps or auto-switches."""
    root = storage.safe_path(Path(workspace_root), directory=True)
    active_id, _ = _active(root)
    path = root / "control" / "restore-journal.json"
    if not path.exists():
        return {"phase": "none", "active_dataset_id": active_id, "can_rollback": False, "switch_state": "none"}
    value = _read_json(path, 32768)
    if not isinstance(value, dict) or value.get("journal_version") != 1:
        raise RestoreError("Unknown restore journal; manual inspection required")
    if value.get("phase") not in ("preparing", "old_preserved", "copying", "ready_to_switch", "complete", "failed", "rolling_back", "rolled_back"):
        raise RestoreError("Unknown restore phase; manual inspection required")
    old_id, new_id = value.get("old_dataset_id"), value.get("new_dataset_id")
    for item in (old_id, new_id):
        if item is not None:
            _uuid(item)
    switch = "new_active" if new_id and active_id == new_id else "old_active" if active_id == old_id else "unrelated_active"
    return {**value, "active_dataset_id": active_id, "switch_state": switch,
            "can_rollback": bool(old_id and new_id and active_id == new_id and value.get("rollback_backup"))}


def _check_confirmation(root, confirmation, *, allow_unpublished=False):
    current_id, current_db = _active(root)
    if confirmation != (current_id or "EMPTY"):
        raise RestoreError("Confirmation must exactly match the current dataset ID (or EMPTY)")
    datasets = root / "datasets"
    if current_id is None and datasets.exists() and any(datasets.iterdir()) and not allow_unpublished:
        raise RestoreError("Existing datasets have no active pointer; this is not an EMPTY workspace")
    return current_id, current_db


def _validate_restored(dataset, manifest, source_snapshot):
    _validate_database(dataset / "plw.sqlite3")
    if _table_digests(dataset / "plw.sqlite3", source_snapshot) != _table_digests(source_snapshot, source_snapshot):
        raise VerificationError("Restored database rows differ from backup")
    expected, _, _ = _catalog(dataset / "plw.sqlite3")
    _exact_tree(dataset, {"plw.sqlite3", "config.json", *(e["relative_path"] for e in expected)}, _empty_directories(dataset / "plw.sqlite3"))
    for entry in expected:
        if storage.hash_file(storage.relative_file(dataset, entry["relative_path"], must_exist=True)) != (entry["size_bytes"], entry["sha256"]):
            raise VerificationError("Restored internal file differs from backup")
    if _config(dataset)["dataset_id"] != dataset.name:
        raise VerificationError("Restored dataset identity mismatch")


def restore_backup(workspace_root, backup_path, *, confirmation, expected_manifest_sha256=None):
    """Restore to a fresh dataset, preserve old data, then compare-and-swap pointer."""
    root = storage.safe_path(Path(workspace_root), must_exist=True, directory=True)
    source = storage.safe_path(Path(backup_path), must_exist=True, directory=True)
    if root == source or root.is_relative_to(source):
        raise RestoreError("Workspace cannot be the backup or be inside it")
    if source.is_relative_to(root) and source.relative_to(root).parts[0] not in ("backups", "rollback"):
        raise RestoreError("Workspace backup input must be inside backups or rollback")
    with locking.maintenance_barrier(root):
        old_id, old_db = _check_confirmation(root, confirmation)
        status = recovery_status(root)
        if status["phase"] not in ("none", "complete", "rolled_back", "failed"):
            raise RestoreError("An interrupted restore needs diagnosis before another restore")
        if status.get("switch_state") == "new_active" and status["phase"] == "failed":
            raise RestoreError("Previous switch occurred; resolve or roll it back first")
        if status.get("switch_state") == "unrelated_active":
            raise RestoreError("Active dataset differs from recovery journal; inspect before restore")
        manifest = _verify(source, published=True)
        manifest_hash = storage.hash_file(source / "manifest.json")[1]
        if expected_manifest_sha256 is not None and manifest_hash != expected_manifest_sha256:
            raise RestoreError("Backup changed since the confirmation preview")
        needed = sum(e["size_bytes"] for e in manifest["files"])
        _space(root, needed * 2)
        journal = {"journal_version": 1, "operation_id": str(uuid.uuid4()), "phase": "preparing",
            "old_dataset_id": old_id, "new_dataset_id": None, "backup_id": manifest["backup_id"],
            "backup_path": str(source), "manifest_sha256": manifest_hash,
            "rollback_backup": None, "created_at": _now()}
        _journal(root, journal)
        try:
            if old_db is not None:
                rollback = create_backup(old_db, root / "rollback")
                journal["rollback_backup"] = rollback["path"]
            journal["phase"] = "old_preserved"
            _journal(root, journal)
            new_db = workspace.create_dataset(root)
            new_id = new_db.parent.name
            journal.update(new_dataset_id=new_id, phase="copying")
            _journal(root, journal)
            snapshot = source / "payload" / "plw.sqlite3"
            with closing(db.connect_snapshot(snapshot)) as origin, closing(sqlite3.connect(new_db, autocommit=True)) as destination:
                origin.backup(destination)
            for entry in manifest["files"]:
                if entry["type"] in ("database", "config"):
                    continue
                target = storage.relative_file(new_db.parent, entry["relative_path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                storage.copy_verified(storage.relative_file(source, entry["payload_path"], must_exist=True), target, expected_sha256=entry["sha256"])
            _validate_restored(new_db.parent, manifest, snapshot)
            # Migrate only the newly restored, unpublished copy under maintenance lock.
            db._initialize(new_db)
            _validate_restored(new_db.parent, manifest, snapshot)
            # Reverify the immutable input at the last possible point before switch.
            _verify(source, published=True)
            if storage.hash_file(source / "manifest.json")[1] != manifest_hash:
                raise VerificationError("Backup manifest changed during restore")
            journal["phase"] = "ready_to_switch"
            _journal(root, journal)
            workspace.set_active(root, new_id, expected_dataset_id=old_id)
            journal["phase"] = "complete"
            journal["completed_at"] = _now()
            _journal(root, journal)
            return {**journal, "active_dataset_id": new_id, "path": str(new_db), "external": manifest["external"]}
        except Exception as error:
            journal.update(phase="failed", error=str(error), failed_at=_now())
            try:
                _journal(root, journal)
            except OSError:
                pass
            raise RestoreError(f"Restore interrupted; inspect recovery status. Old data retained: {error}") from error


def rollback_restore(workspace_root, *, confirmation):
    """Preserve post-restore edits, verify the old dataset, and switch back safely."""
    root = storage.safe_path(Path(workspace_root), must_exist=True, directory=True)
    with locking.maintenance_barrier(root):
        current_id, current_db = _check_confirmation(root, confirmation)
        status = recovery_status(root)
        if not status.get("can_rollback"):
            raise RestoreError("No verified previous dataset is available for this active dataset")
        old_id = _uuid(status["old_dataset_id"])
        old_db = root / "datasets" / old_id / "plw.sqlite3"
        saved = storage.safe_path(Path(status["rollback_backup"]), root=root / "rollback", must_exist=True, directory=True)
        manifest = _verify(saved, published=True)
        if manifest["dataset_id"] != old_id:
            raise RestoreError("Rollback snapshot does not belong to the old dataset")
        _validate_restored(old_db.parent, manifest, saved / "payload" / "plw.sqlite3")
        if _config(old_db.parent)["dataset_id"] != old_id:
            raise RestoreError("Old dataset identity changed")
        try:
            current_backup = create_backup(current_db, root / "rollback")
            journal = {k: v for k, v in status.items() if k not in ("can_rollback", "active_dataset_id", "switch_state")}
            journal.update(phase="rolling_back", post_restore_backup=current_backup["path"])
            _journal(root, journal)
            workspace.set_active(root, old_id, expected_dataset_id=current_id)
            journal.update(phase="rolled_back", rolled_back_at=_now())
            _journal(root, journal)
            return {**journal, "active_dataset_id": old_id, "path": str(old_db)}
        except Exception as error:
            raise RestoreError(f"Rollback interrupted; retained datasets and snapshots: {error}") from error


def _validate_live_dataset(path):
    _validate_database(path)
    entries, _, _ = _catalog(path)
    _exact_tree(path.parent, {"plw.sqlite3", "config.json", *(e["relative_path"] for e in entries)}, _empty_directories(path))
    if _config(path.parent)["dataset_id"] != path.parent.name:
        raise VerificationError("Dataset identity mismatch")
    for entry in entries:
        if storage.hash_file(storage.relative_file(path.parent, entry["relative_path"], must_exist=True)) != (entry["size_bytes"], entry["sha256"]):
            raise VerificationError("Dataset file differs from trusted baseline")


def reconcile_restore(workspace_root, *, confirmation):
    """Explicitly validate and finish an interrupted journal without switching."""
    root = storage.safe_path(Path(workspace_root), must_exist=True, directory=True)
    with locking.maintenance_barrier(root):
        current_id, current_db = _check_confirmation(root, confirmation, allow_unpublished=True)
        status = recovery_status(root)
        if status["phase"] == "none":
            if current_id is None and (root / "datasets").exists() and any((root / "datasets").iterdir()):
                raise RestoreError("Unpublished datasets have no recovery journal; manual inspection required")
            return status
        journal = {k: v for k, v in status.items() if k not in ("can_rollback", "active_dataset_id", "switch_state")}
        if status["switch_state"] == "old_active":
            if current_db is not None:
                _validate_live_dataset(current_db)
            elif (root / "datasets").exists():
                recorded = {status["new_dataset_id"]} if status["new_dataset_id"] else set()
                if {p.name for p in (root / "datasets").iterdir()} - recorded:
                    raise RestoreError("Unpublished dataset identities are not explained by this journal")
            journal.update(phase="rolled_back" if status["phase"] in ("rolling_back", "rolled_back") else "failed",
                           reconciled_at=_now(), error="Explicitly verified old dataset remains active; retained staging datasets")
        elif status["switch_state"] == "new_active":
            source = storage.safe_path(Path(status["backup_path"]), must_exist=True, directory=True)
            manifest = _verify(source, published=True)
            if storage.hash_file(source / "manifest.json")[1] != status["manifest_sha256"]:
                raise RestoreError("Recovery source changed since the original restore")
            _validate_restored(current_db.parent, manifest, source / "payload" / "plw.sqlite3")
            journal.update(phase="complete", reconciled_at=_now())
        else:
            raise RestoreError("Actual active pointer is unrelated to the journal; no automatic repair")
        _journal(root, journal)
        return recovery_status(root)
