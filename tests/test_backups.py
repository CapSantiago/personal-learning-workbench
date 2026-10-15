"""Complete backup/recovery acceptance uses only isolated synthetic datasets."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from plw import backups, db, storage, workspace
from plw.services import LearningService

NOW = "2026-10-11T00:00:00+00:00"


def uid():
    return str(uuid4())


def write_body(root, rel, content):
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return len(content), hashlib.sha256(content).hexdigest()


@pytest.fixture
def sample():
    root = storage.PROJECT_ROOT / ".sandbox" / "test-runs" / ("backups-" + uid())
    info = workspace.initialize_workspace(root)
    path = Path(info["db_path"])
    service = LearningService(path)
    semester = service.create_semester("合成 2026", request_id=uid())
    courses = [service.create_course(semester["id"], name, request_id=uid()) for name in ("控制原理", "机器人运动学")]
    material_ids = [uid() for _ in range(4)]
    external = root / "sources" / "引用 中文 空格.txt"
    external.parent.mkdir()
    external.write_bytes(b"external source stays untouched")
    managed = []
    for index in (0, 1):
        rel = f"managed/{material_ids[index]}/讲义 {index}.txt"
        size, digest = write_body(path.parent, rel, f"synthetic material {index}".encode())
        managed.append((rel, size, digest))
    note_id, revisions = uid(), [uid(), uid()]
    notes = []
    for index, revision in enumerate(revisions):
        rel = f"notes/{note_id}/{revision}.md"
        size, digest = write_body(path.parent, rel, f"# 合成笔记 {index}\n$x^2$\n".encode())
        notes.append((rel, size, digest))
    with db.transaction(path) as connection:
        for index in (0, 1):
            rel, size, digest = managed[index]
            connection.execute("""INSERT INTO materials(id,course_id,name,storage_mode,original_path,managed_relpath,
                size_bytes,baseline_sha256,import_state,file_status,deleted_at,created_at,updated_at)
                VALUES(?,?,?,'managed_copy',?,?,?,?, 'ready','normal',?,?,?)""",
                (material_ids[index], courses[0]["id"], "资料" + str(index), str(external), rel, size, digest,
                 NOW if index else None, NOW, NOW))
        connection.execute("""INSERT INTO materials(id,course_id,name,storage_mode,original_path,reference_path,
            size_bytes,baseline_sha256,import_state,file_status,created_at,updated_at)
            VALUES(?,?,?,'external_reference',?,?,?,?, 'ready','unchecked',?,?)""",
            (material_ids[2], courses[1]["id"], "外部引用", str(external), str(external), external.stat().st_size,
             hashlib.sha256(external.read_bytes()).hexdigest(), NOW, NOW))
        connection.execute("""INSERT INTO materials(id,course_id,name,storage_mode,original_path,managed_relpath,
            import_state,baseline_sha256,deleted_at,file_deleted_at,created_at,updated_at)
            VALUES(?,?,?,'managed_copy',?,?,'ready',?,?,?,?,?)""",
            (material_ids[3], courses[0]["id"], "显式已删正文", str(external),
             f"managed/{material_ids[3]}/removed.txt", "a" * 64, NOW, NOW, NOW, NOW))
        connection.execute("""INSERT INTO file_operations(id,request_id,kind,entity_id,state,target_relpath,
            expected_sha256,payload_json,created_at,updated_at)
            VALUES(?,?,'delete_managed_file',?,'committed',?,?,?,?,?)""",
            (uid(), uid(), material_ids[3], f"managed/{material_ids[3]}/removed.txt", "a" * 64,
             json.dumps({"confirmation": material_ids[3]}), NOW, NOW))
        tasks = [uid(), uid()]
        for index, task in enumerate(tasks):
            connection.execute("""INSERT INTO tasks(id,course_id,title,task_type,created_at,updated_at)
                VALUES(?,?,?,'lab',?,?)""", (task, courses[index]["id"], "实验" + str(index), NOW, NOW))
            for material in material_ids[:3]:
                connection.execute("INSERT INTO task_materials VALUES(?,?)", (task, material))
        chapter = uid()
        connection.execute("INSERT INTO chapters(id,course_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                           (chapter, courses[0]["id"], "章节", NOW, NOW))
        connection.execute("INSERT INTO chapter_materials VALUES(?,?)", (chapter, material_ids[2]))
        connection.execute("INSERT INTO notes(id,course_id,chapter_id,title,current_revision_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                           (note_id, courses[0]["id"], chapter, "多版本笔记", revisions[-1], NOW, NOW))
        for index, revision in enumerate(revisions):
            rel, size, digest = notes[index]
            connection.execute("""INSERT INTO note_revisions(id,note_id,revision_no,body_relpath,sha256,size_bytes,created_at)
                VALUES(?,?,?,?,?,?,?)""", (revision, note_id, index + 1, rel, digest, size, NOW))
        connection.execute("INSERT INTO note_materials VALUES(?,?)", (note_id, material_ids[2]))
    return SimpleNamespace(root=root, path=path, service=service, courses=courses,
                           managed=managed, notes=notes, external=external, materials=material_ids)


def rewrite_manifest(target, update):
    file = target / "manifest.json"
    value = json.loads(file.read_bytes())
    update(value)
    data = backups._json_bytes(value)
    file.write_bytes(data)
    (target / "manifest.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode("ascii"))


def assert_active(sample, path=None):
    assert workspace.active_db(sample.root) == (path or sample.path)
    assert sample.service.get_course(sample.courses[0]["id"])["name"] == "控制原理"


def test_complete_backup_restores_every_table_file_and_external_unchanged(sample):
    before = (sample.external.read_bytes(), sample.external.stat().st_mtime_ns)
    report = backups.create_backup(sample.path)
    target = Path(report["path"])
    assert report["count"] == 6  # SQLite/config + two managed + two note revisions.
    assert len(report["external"]) == 1
    assert report["external"][0]["included"] is False
    assert report["external"][0]["reason"] == "index_only_not_inspected"
    assert len(report["deleted"]) == 1
    restored = backups.restore_backup(sample.root, target, confirmation=sample.path.parent.name,
                                     expected_manifest_sha256=report["manifest_sha256"])
    new_db = Path(restored["path"])
    assert new_db != sample.path
    assert backups._table_digests(new_db) == backups._table_digests(sample.path)
    for rel, size, digest in sample.managed + sample.notes:
        assert storage.hash_file(new_db.parent / rel) == (size, digest)
    assert sample.path.exists()
    assert backups.verify_backup(restored["rollback_backup"])["complete"]
    assert (sample.external.read_bytes(), sample.external.stat().st_mtime_ns) == before
    status = backups.recovery_status(sample.root)
    assert status["phase"] == "complete" and status["switch_state"] == "new_active"
    assert status["can_rollback"]


def test_restore_empty_requires_exact_confirmation_and_creates_no_old_snapshot(sample):
    report = backups.create_backup(sample.path)
    empty = sample.root.parent / ("empty-" + uid())
    empty.mkdir()
    with pytest.raises(backups.RestoreError, match="Confirmation"):
        backups.restore_backup(empty, report["path"], confirmation="")
    result = backups.restore_backup(empty, report["path"], confirmation="EMPTY")
    assert result["old_dataset_id"] is None and result["rollback_backup"] is None
    assert backups._table_digests(workspace.active_db(empty)) == backups._table_digests(sample.path)


def test_rollback_preserves_post_restore_changes(sample):
    report = backups.create_backup(sample.path)
    restored = backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    new_db = Path(restored["path"])
    service = LearningService(new_db)
    service.update_course(sample.courses[0]["id"], expected_revision=1, name="恢复后修改")
    result = backups.rollback_restore(sample.root, confirmation=new_db.parent.name)
    assert_active(sample)
    assert backups.recovery_status(sample.root)["phase"] == "rolled_back"
    assert new_db.exists()
    snapshot = Path(result["post_restore_backup"]) / "payload" / "plw.sqlite3"
    assert LearningService(snapshot).get_course(sample.courses[0]["id"])["name"] == "恢复后修改"
    assert backups.verify_backup(result["post_restore_backup"])["complete"]


@pytest.mark.parametrize("change", ["missing", "corrupt", "extra", "empty_extra", "unknown_operation", "untrusted_baseline"])
def test_incomplete_source_never_publishes_complete_backup(sample, change):
    if change == "missing":
        (sample.path.parent / sample.managed[0][0]).unlink()
    elif change == "corrupt":
        (sample.path.parent / sample.managed[0][0]).write_bytes(b"different")
    elif change == "extra":
        (sample.path.parent / "unindexed.bin").write_bytes(b"unknown")
    elif change == "empty_extra":
        (sample.path.parent / "unknown").mkdir()
    elif change == "unknown_operation":
        with db.transaction(sample.path) as connection:
            connection.execute("""INSERT INTO file_operations(id,request_id,kind,entity_id,state,created_at,updated_at)
                VALUES(?,?,'import_material',?,'failed',?,?)""", (uid(), uid(), sample.materials[0], NOW, NOW))
    else:
        with db.transaction(sample.path) as connection:
            connection.execute("UPDATE materials SET baseline_sha256=NULL WHERE id=?", (sample.materials[0],))
    with pytest.raises(backups.BackupError):
        backups.create_backup(sample.path)
    assert not list((sample.root / "backups").glob("*/complete.json"))
    assert_active(sample)


def test_missing_external_is_not_opened_or_silently_reported_as_included(sample, monkeypatch):
    sample.external.unlink()
    original = storage.hash_file
    def checked(path):
        assert Path(path) != sample.external
        return original(path)
    monkeypatch.setattr(storage, "hash_file", checked)
    report = backups.create_backup(sample.path)
    assert report["external"][0]["included"] is False
    assert report["external"][0]["recorded_status"] == "unchecked"


@pytest.mark.parametrize("fault", ["manifest", "body", "database", "extra", "missing", "unknown_version", "unknown_schema", "traversal", "absolute", "case_duplicate", "unknown_type"])
def test_bad_backup_rejected_before_any_restore_switch(sample, fault):
    report = backups.create_backup(sample.path)
    target = Path(report["path"])
    if fault == "manifest":
        (target / "manifest.json").write_bytes(b"{}")
    elif fault in ("body", "database"):
        path = target / "payload" / (sample.managed[0][0] if fault == "body" else "plw.sqlite3")
        path.write_bytes(b"corrupt")
    elif fault == "extra":
        (target / "payload" / "extra").write_bytes(b"x")
    elif fault == "missing":
        (target / "payload" / sample.notes[0][0]).unlink()
    elif fault == "unknown_version":
        rewrite_manifest(target, lambda m: m.update(backup_format_version=99))
    elif fault == "unknown_schema":
        rewrite_manifest(target, lambda m: m.update(schema_version=99))
    elif fault in ("traversal", "absolute"):
        value = "../escape" if fault == "traversal" else "E:/escape"
        rewrite_manifest(target, lambda m: m["files"][0].update(relative_path=value, payload_path="payload/" + value))
    elif fault == "case_duplicate":
        def duplicate(m):
            entry = dict(m["files"][0])
            entry.update(relative_path="PLW.SQLITE3", payload_path="payload/PLW.SQLITE3")
            m["files"].append(entry)
        rewrite_manifest(target, duplicate)
    else:
        rewrite_manifest(target, lambda m: m["files"][0].update(type="executable"))
    with pytest.raises(backups.BackupError):
        backups.verify_backup(target)
    with pytest.raises((backups.BackupError, storage.StorageError)):
        backups.restore_backup(sample.root, target, confirmation=sample.path.parent.name)
    assert_active(sample)
    assert not (sample.root / "rollback").exists()


def test_manifest_preview_hash_binds_confirmation(sample):
    report = backups.create_backup(sample.path)
    target = Path(report["path"])
    rewrite_manifest(target, lambda m: m.update(app_version="different but valid label"))
    assert backups.verify_backup(target)["complete"]
    with pytest.raises(backups.RestoreError, match="changed since"):
        backups.restore_backup(sample.root, target, confirmation=sample.path.parent.name,
                               expected_manifest_sha256=report["manifest_sha256"])
    assert_active(sample)


@pytest.mark.parametrize("error", [PermissionError("injected denied"), OSError(28, "injected full disk")])
def test_copy_fault_keeps_original_and_retains_unpublished_output(sample, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(storage, "copy_verified", fail)
    with pytest.raises(backups.BackupError):
        backups.create_backup(sample.path)
    assert list((sample.root / "backups").glob("*/incomplete.json"))
    assert not list((sample.root / "backups").glob("*/complete.json"))
    assert_active(sample)


def test_disk_space_preflight(sample, monkeypatch):
    monkeypatch.setattr(backups.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(backups.BackupError, match="Insufficient"):
        backups.create_backup(sample.path)
    assert_active(sample)


def test_rollback_snapshot_failure_prevents_restore(sample, monkeypatch):
    report = backups.create_backup(sample.path)
    monkeypatch.setattr(backups, "create_backup", lambda *a, **k: (_ for _ in ()).throw(backups.BackupError("injected rollback failure")))
    with pytest.raises(backups.RestoreError):
        backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    assert_active(sample)
    status = backups.recovery_status(sample.root)
    assert status["phase"] == "failed" and status["switch_state"] == "old_active"
    assert not status["can_rollback"]


@pytest.mark.parametrize("after_switch", [False, True])
def test_pointer_failure_restart_diagnosis_and_old_data_preserved(sample, monkeypatch, after_switch):
    report = backups.create_backup(sample.path)
    original = workspace.set_active
    def failure(*args, **kwargs):
        if after_switch:
            original(*args, **kwargs)
        raise PermissionError("injected pointer failure")
    monkeypatch.setattr(workspace, "set_active", failure)
    with pytest.raises(backups.RestoreError):
        backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    status = backups.recovery_status(sample.root)
    assert status["phase"] == "failed"
    assert status["switch_state"] == ("new_active" if after_switch else "old_active")
    assert status["can_rollback"] is after_switch
    assert sample.path.exists()
    assert LearningService(sample.path).get_course(sample.courses[0]["id"])["name"] == "控制原理"


def test_restore_copy_failure_does_not_switch(sample, monkeypatch):
    report = backups.create_backup(sample.path)
    original = storage.copy_verified
    def copying(source, target, **kwargs):
        if "datasets" in Path(target).parts:
            raise OSError(28, "injected restore full disk")
        return original(source, target, **kwargs)
    monkeypatch.setattr(storage, "copy_verified", copying)
    with pytest.raises(backups.RestoreError):
        backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    assert_active(sample)
    assert len(list((sample.root / "datasets").iterdir())) == 2
    assert backups.recovery_status(sample.root)["phase"] == "failed"


def test_backup_write_barrier_blocks_course_write_until_snapshot_complete(sample, monkeypatch):
    entered, release, attempted, finished = (threading.Event() for _ in range(4))
    original = storage.copy_verified
    def copying(source, target, **kwargs):
        if Path(source).name == "config.json":
            entered.set()
            assert release.wait(2)
        return original(source, target, **kwargs)
    monkeypatch.setattr(storage, "copy_verified", copying)
    def writer():
        attempted.set()
        result = sample.service.update_course(sample.courses[0]["id"], expected_revision=1, teacher="备份之后")
        finished.set()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        backing = pool.submit(backups.create_backup, sample.path)
        assert entered.wait(2)
        editing = pool.submit(writer)
        assert attempted.wait(2)
        assert not finished.wait(0.1)
        release.set()
        report = backing.result(timeout=4)
        assert editing.result(timeout=4)["teacher"] == "备份之后"
    snapshot = Path(report["path"]) / "payload" / "plw.sqlite3"
    assert LearningService(snapshot).get_course(sample.courses[0]["id"])["teacher"] == ""


def test_unknown_database_objects_rejected_even_with_recomputed_file_hash(sample):
    report = backups.create_backup(sample.path)
    target = Path(report["path"])
    snapshot = target / "payload" / "plw.sqlite3"
    with closing(sqlite3.connect(snapshot, autocommit=True)) as connection:
        connection.execute("CREATE TABLE surprise(secret TEXT)")
    size, digest = storage.hash_file(snapshot)
    rewrite_manifest(target, lambda m: m["files"][0].update(size_bytes=size, sha256=digest))
    with pytest.raises(backups.VerificationError, match="unknown or altered schema"):
        backups.verify_backup(target)


def test_backup_rejects_hardlink_even_with_correct_bytes(sample):
    report = backups.create_backup(sample.path)
    target = Path(report["path"])
    file = target / "payload" / sample.managed[0][0]
    link = sample.root / "sources" / "synthetic hardlink"
    os.link(file, link)
    with pytest.raises(backups.VerificationError):
        backups.verify_backup(target)


def test_committed_empty_staging_and_deleted_material_dirs_allowed(sample):
    operation = uid()
    with db.transaction(sample.path) as connection:
        connection.execute("""INSERT INTO file_operations(id,request_id,kind,entity_id,state,created_at,updated_at)
            VALUES(?,?,'import_material',?,'committed',?,?)""", (operation, uid(), sample.materials[0], NOW, NOW))
    (sample.path.parent / ".staging" / operation).mkdir(parents=True)
    (sample.path.parent / "managed" / sample.materials[3]).mkdir()
    assert backups.create_backup(sample.path)["complete"]


def test_rollback_verifies_old_dataset_before_preserving_current_or_switching(sample):
    report = backups.create_backup(sample.path)
    restored = backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    (sample.path.parent / sample.managed[0][0]).write_bytes(b"corrupted old body")
    current = Path(restored["path"])
    with pytest.raises(backups.VerificationError):
        backups.rollback_restore(sample.root, confirmation=current.parent.name)
    assert workspace.active_db(sample.root) == current


def test_deleted_body_requires_matching_committed_confirmation(sample):
    with db.transaction(sample.path) as connection:
        connection.execute("UPDATE file_operations SET payload_json='{}' WHERE kind='delete_managed_file'")
    with pytest.raises(backups.VerificationError, match="deletion evidence"):
        backups.create_backup(sample.path)
    assert_active(sample)


@pytest.mark.parametrize("inside", [False, True])
def test_restore_never_writes_inside_backup_when_workspace_misconfigured(sample, inside):
    report = backups.create_backup(sample.path)
    backup = Path(report["path"])
    root = backup / "payload" if inside else backup
    before = {p: storage.hash_file(backup / p) for p in backups._tree(backup)[0]}
    with pytest.raises(backups.RestoreError, match="Workspace cannot"):
        backups.restore_backup(root, backup, confirmation="EMPTY")
    assert before == {p: storage.hash_file(backup / p) for p in backups._tree(backup)[0]}
    assert backups.verify_backup(backup)["complete"]


def test_lost_pointer_with_existing_dataset_is_never_treated_as_empty(sample):
    report = backups.create_backup(sample.path)
    before = storage.hash_file(sample.path)
    (sample.root / "control" / "active.json").unlink()
    with pytest.raises(backups.RestoreError, match="not an EMPTY"):
        backups.restore_backup(sample.root, report["path"], confirmation="EMPTY")
    assert storage.hash_file(sample.path) == before
    assert not (sample.root / "rollback").exists()
    assert backups.verify_backup(report["path"])["complete"]


@pytest.mark.parametrize("new_active", [False, True])
def test_explicit_reconcile_validates_interrupted_switch_and_unblocks_business(sample, monkeypatch, new_active):
    report = backups.create_backup(sample.path)
    if new_active:
        result = backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
        current = Path(result["path"])
        journal = json.loads((sample.root / "control" / "restore-journal.json").read_bytes())
        journal["phase"] = "ready_to_switch"
        backups._journal(sample.root, journal)
    else:
        original = workspace.set_active
        def stop(*args, **kwargs):
            raise KeyboardInterrupt("simulated termination before switch")
        monkeypatch.setattr(workspace, "set_active", stop)
        with pytest.raises(KeyboardInterrupt):
            backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
        monkeypatch.setattr(workspace, "set_active", original)
        current = sample.path
    status = backups.recovery_status(sample.root)
    assert status["phase"] == "ready_to_switch"
    assert status["switch_state"] == ("new_active" if new_active else "old_active")
    with pytest.raises(Exception, match="恢复|核对"):
        LearningService(current).update_course(sample.courses[0]["id"], expected_revision=1, teacher="must block")
    result = backups.reconcile_restore(sample.root, confirmation=current.parent.name)
    assert result["phase"] == ("complete" if new_active else "failed")
    assert LearningService(current).update_course(sample.courses[0]["id"], expected_revision=1, teacher="allowed")["teacher"] == "allowed"


def test_failed_rollback_pointer_keeps_both_datasets_and_can_retry(sample, monkeypatch):
    report = backups.create_backup(sample.path)
    result = backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    current = Path(result["path"])
    original = workspace.set_active
    monkeypatch.setattr(workspace, "set_active", lambda *a, **k: (_ for _ in ()).throw(PermissionError("rollback pointer denied")))
    with pytest.raises(backups.RestoreError, match="Rollback interrupted"):
        backups.rollback_restore(sample.root, confirmation=current.parent.name)
    assert workspace.active_db(sample.root) == current
    assert backups.recovery_status(sample.root)["phase"] == "rolling_back"
    monkeypatch.setattr(workspace, "set_active", original)
    assert backups.rollback_restore(sample.root, confirmation=current.parent.name)["active_dataset_id"] == sample.path.parent.name


def test_reconcile_refuses_corrupt_new_dataset(sample):
    report = backups.create_backup(sample.path)
    result = backups.restore_backup(sample.root, report["path"], confirmation=sample.path.parent.name)
    current = Path(result["path"])
    journal = json.loads((sample.root / "control" / "restore-journal.json").read_bytes())
    journal["phase"] = "ready_to_switch"
    backups._journal(sample.root, journal)
    (current.parent / sample.notes[0][0]).write_bytes(b"corrupt")
    with pytest.raises(backups.VerificationError):
        backups.reconcile_restore(sample.root, confirmation=current.parent.name)
    assert backups.recovery_status(sample.root)["phase"] == "ready_to_switch"
    assert sample.path.exists()


def test_snapshot_cannot_be_used_as_live_backup_source_or_other_dataset_as_destination(sample):
    report = backups.create_backup(sample.path)
    target = Path(report["path"])
    with pytest.raises(backups.BackupError, match="Backup source"):
        backups.create_backup(target / "payload" / "plw.sqlite3", sample.root / "backups")
    assert backups.verify_backup(target)["complete"]
    other = workspace.create_dataset(sample.root)
    with pytest.raises(backups.BackupError, match="destination"):
        backups.create_backup(sample.path, other.parent / "bad-backups")
    assert not (other.parent / "bad-backups").exists()
