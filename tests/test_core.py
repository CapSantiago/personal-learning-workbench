"""Synthetic-only M0 tests. No real learning-data paths or databases are opened."""

from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import uuid

import pytest

from plw_probe import core


@pytest.fixture
def probe_root(monkeypatch):
    # Keep artifacts on E: for inspection; never use a C: pytest temporary directory.
    root = Path("E:/Projects/PLW/.sandbox/test-runs") / str(uuid.uuid4())
    monkeypatch.setattr(core, "_ALLOWED_ROOT", root)
    return root


@pytest.fixture
def demo(probe_root):
    sources = core.create_demo_sources(probe_root)
    core.initialize(probe_root)
    return probe_root, sources


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _operation(root, operation_id):
    with closing(core._connect(root, read_only=True)) as connection:
        return dict(connection.execute(
            "SELECT * FROM probe_operations WHERE operation_id=?", (operation_id,)
        ).fetchone())


def test_read_missing_does_not_create(probe_root):
    assert core.list_imports(probe_root) == []
    assert not probe_root.exists()


def test_wrong_root_rejected_without_writing(probe_root):
    with pytest.raises(ValueError, match="synthetic sandbox"):
        core.initialize(probe_root.parent / "unapproved")


def test_fixtures_repeat_without_overwriting(probe_root):
    first = core.create_demo_sources(probe_root)
    before = {key: (path.stat().st_mtime_ns, _sha(path)) for key, path in first.items()}
    assert core.create_demo_sources(probe_root) == first
    assert {key: (path.stat().st_mtime_ns, _sha(path)) for key, path in first.items()} == before
    first["chinese_text"].write_text("Changed synthetic fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="not overwriting"):
        core.create_demo_sources(probe_root)
    assert first["chinese_text"].read_text(encoding="utf-8") == "Changed synthetic fixture"


def test_pdf_has_valid_xref_and_page(probe_root):
    data = core.create_demo_sources(probe_root)["pdf"].read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.endswith(b"%%EOF\n")
    xref = int(data.split(b"startxref\n")[1].splitlines()[0])
    assert data[xref:].startswith(b"xref\n0 6\n")
    entries = data[xref:].splitlines()[3:8]
    for number, line in enumerate(entries, 1):
        offset = int(line.split()[0])
        assert data[offset:].startswith(f"{number} 0 obj\n".encode("ascii"))
    assert b"/Type /Page /Parent" in data


@pytest.mark.parametrize("mode", ["managed_copy", "external_reference"])
def test_modes_chinese_spaces_original_unchanged(demo, mode):
    root, sources = demo
    source = sources["chinese_text"]
    before = (_sha(source), source.stat().st_mtime_ns)
    record = core.probe_import(root, source, mode, str(uuid.uuid4()))
    assert record["storage_mode"] == mode
    assert record["status"] == "active"
    assert record["sha256"] == before[0]
    assert record["original_path"] == str(source)
    assert record["size_bytes"] == source.stat().st_size
    assert (_sha(source), source.stat().st_mtime_ns) == before
    if mode == "managed_copy":
        managed = root / record["managed_relative_path"]
        assert managed != source and _sha(managed) == before[0]
    else:
        assert record["managed_relative_path"] is None
        assert list((root / "managed").iterdir()) == []
        assert list((root / "staging").iterdir()) == []
    assert core.list_imports(root) == [record]


def test_idempotent_operation_and_initialization(demo):
    root, sources = demo
    operation_id = str(uuid.uuid4())
    first = core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    core.initialize(root)
    second = core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    assert first == second
    assert len(core.list_imports(root)) == 1
    assert len(list((root / "managed").iterdir())) == 1


def test_completed_operation_replay_does_not_require_source(demo):
    root, sources = demo
    operation_id = str(uuid.uuid4())
    first = core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    # Remove only this test's generated synthetic fixture, never any user's file.
    sources["pdf"].unlink()
    assert core.probe_import(root, sources["pdf"], "managed_copy", operation_id) == first


def test_hardlinked_source_rejected(demo):
    root, sources = demo
    hardlink = root / "sources" / "synthetic hardlink.txt"
    os.link(sources["chinese_text"], hardlink)
    with pytest.raises(ValueError, match="hard link"):
        core.probe_import(root, hardlink, "external_reference", str(uuid.uuid4()))
    assert core.list_imports(root) == []


def test_windows_junction_source_rejected(demo):
    if os.name != "nt":
        pytest.skip("Actual Windows junction test")
    import _winapi

    root, sources = demo
    # The junction and its target are both disposable synthetic test paths.
    junction = root / "sources" / "synthetic junction"
    target = root / "synthetic-junction-target"
    target.mkdir()
    (target / sources["pdf"].name).write_bytes(b"synthetic junction fixture")
    _winapi.CreateJunction(str(target), str(junction))
    with pytest.raises(ValueError, match="junctions"):
        core.probe_import(root, junction / sources["pdf"].name, "managed_copy", str(uuid.uuid4()))
    assert core.list_imports(root) == []


def test_existing_managed_candidate_never_overwritten(demo):
    root, sources = demo
    operation_id = str(uuid.uuid4())
    target = root / "managed" / f"{operation_id}.pdf"
    target.write_bytes(b"Existing synthetic bytes")
    with pytest.raises(FileExistsError, match="not overwriting"):
        core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    assert target.read_bytes() == b"Existing synthetic bytes"
    assert core.list_imports(root) == []
    assert _operation(root, operation_id)["status"] == "failed"


def test_non_probe_database_is_not_modified(probe_root):
    probe_root.mkdir(parents=True)
    database = probe_root / "probe.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated_synthetic_table (id INTEGER)")
    before = _sha(database)
    with pytest.raises(ValueError, match="Not this synthetic"):
        core.initialize(probe_root)
    assert _sha(database) == before


@pytest.mark.parametrize("different", ["mode", "path"])
def test_operation_id_different_payload_rejected(demo, different):
    root, sources = demo
    operation_id = str(uuid.uuid4())
    core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    source = sources["chinese_text"] if different == "path" else sources["pdf"]
    mode = "external_reference" if different == "mode" else "managed_copy"
    with pytest.raises(ValueError, match="different payload"):
        core.probe_import(root, source, mode, operation_id)
    assert len(core.list_imports(root)) == 1


def test_missing_outside_and_directory_sources_rejected(demo):
    root, _ = demo
    with pytest.raises(FileNotFoundError):
        core.probe_import(root, root / "sources" / "absent.txt", "managed_copy", str(uuid.uuid4()))
    with pytest.raises(ValueError, match="inside sandbox/sources"):
        core.probe_import(root, root.parent / "outside.txt", "managed_copy", str(uuid.uuid4()))
    subdir = root / "sources" / "folder"
    subdir.mkdir()
    with pytest.raises(ValueError, match="ordinary file"):
        core.probe_import(root, subdir, "external_reference", str(uuid.uuid4()))
    assert core.list_imports(root) == []


def test_invalid_mode_and_operation_id_rejected(demo):
    root, sources = demo
    with pytest.raises(ValueError, match="storage mode"):
        core.probe_import(root, sources["pdf"], "move", str(uuid.uuid4()))
    with pytest.raises(ValueError, match="UUID"):
        core.probe_import(root, sources["pdf"], "managed_copy", "../../unsafe")
    assert core.list_imports(root) == []


def test_copy_failure_is_detectable_without_active_record(demo, monkeypatch):
    root, sources = demo
    operation_id = str(uuid.uuid4())
    source_hash = _sha(sources["chinese_text"])

    def fail_copy(source, destination):
        destination.write_bytes(b"partial synthetic bytes")
        raise OSError("simulated disk full")

    monkeypatch.setattr(core, "_copy_verified", fail_copy)
    with pytest.raises(OSError, match="disk full"):
        core.probe_import(root, sources["chinese_text"], "managed_copy", operation_id)
    assert core.list_imports(root) == []
    assert _operation(root, operation_id)["status"] == "failed"
    assert (root / "staging" / f"{operation_id}.part").exists()
    assert _sha(sources["chinese_text"]) == source_hash
    with pytest.raises(RuntimeError, match="failed"):
        core.probe_import(root, sources["chinese_text"], "managed_copy", operation_id)


def test_commit_failure_rolls_back_activation(demo, monkeypatch):
    root, sources = demo
    operation_id = str(uuid.uuid4())

    def fail_commit(connection):
        assert connection.in_transaction
        raise sqlite3.OperationalError("simulated COMMIT failure")

    monkeypatch.setattr(core, "_commit", fail_commit)
    with pytest.raises(sqlite3.OperationalError, match="COMMIT failure"):
        core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    assert core.list_imports(root) == []
    operation = _operation(root, operation_id)
    assert operation["status"] == "failed"
    assert (root / operation["candidate_relative_path"]).exists()


def test_foreign_keys_and_transaction_rollback(demo):
    root, _ = demo
    for read_only in (False, True):
        with closing(core._connect(root, read_only=read_only)) as connection:
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
            assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    with closing(core._connect(root)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT INTO probe_parents VALUES ('must-rollback')")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                """INSERT INTO probe_imports VALUES
                    (?, ?, 'missing-parent', 'external_reference', 'synthetic', NULL,
                     1, ?, 'active', 'synthetic')""",
                (str(uuid.uuid4()), str(uuid.uuid4()), "0" * 64),
            )
        connection.execute("ROLLBACK")
        assert connection.execute("SELECT 1 FROM probe_parents WHERE id='must-rollback'").fetchone() is None
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert core.list_imports(root) == []


def test_database_write_then_constraint_failure_rolls_back(demo, monkeypatch):
    root, sources = demo
    operation_id = str(uuid.uuid4())
    actual_activate = core._activate_import

    def fail_after_insert(connection, record):
        actual_activate(connection, record)
        connection.execute("UPDATE probe_imports SET size_bytes=-1 WHERE id=?", (record["id"],))

    monkeypatch.setattr(core, "_activate_import", fail_after_insert)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        core.probe_import(root, sources["pdf"], "external_reference", operation_id)
    assert core.list_imports(root) == []
    assert _operation(root, operation_id)["status"] == "failed"


def test_changed_source_detection_rejects_activation(demo, monkeypatch):
    root, sources = demo
    actual_fingerprint = core._fingerprint
    count = 0

    def changed_fingerprint(path):
        nonlocal count
        count += 1
        result = actual_fingerprint(path)
        return result if count == 1 else (*result[:3], result[3] + 1, result[4])

    monkeypatch.setattr(core, "_fingerprint", changed_fingerprint)
    operation_id = str(uuid.uuid4())
    with pytest.raises(RuntimeError, match="source changed"):
        core.probe_import(root, sources["pdf"], "managed_copy", operation_id)
    assert core.list_imports(root) == []
    assert _operation(root, operation_id)["status"] == "failed"
