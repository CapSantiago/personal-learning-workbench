"""Independent M2 safety checks; all writes use newly created synthetic fixtures."""

from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from plw import backups, db, locking, storage, workspace
from plw.services import ConflictError, LearningService


@pytest.fixture
def root():
    path = storage.PROJECT_ROOT / ".sandbox" / "test-runs" / f"workspace-{uuid4().hex}"
    path.mkdir(parents=True)
    return path


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def source_file(root, name="中文 合成来源.txt"):
    path = root / "sources" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("合成资料，只用于安全测试。\n".encode("utf-8"))
    return path


def initialized(root):
    workspace.initialize_workspace(root)
    return workspace.active_db(root)


def test_read_before_explicit_initialize_does_not_create(root):
    with pytest.raises(FileNotFoundError):
        workspace.describe(root)
    assert list(root.iterdir()) == []


def test_initialize_is_explicit_idempotent_and_preserves_records(root):
    path = initialized(root)
    service = LearningService(path)
    row = service.create_semester("合成学期", request_id=uuid4())
    before = fingerprint(path)
    pointer = (root / "control" / "active.json").read_bytes()
    assert workspace.initialize_workspace(root)["db_path"] == str(path)
    assert fingerprint(path) == before
    assert (root / "control" / "active.json").read_bytes() == pointer
    assert service.get_semester(row["id"])["name"] == "合成学期"
    assert len(list((root / "datasets").iterdir())) == 1


def test_unpublished_dataset_blocks_implicit_reinitialization(root):
    path = workspace.create_dataset(root)
    before = fingerprint(path)
    with pytest.raises(workspace.WorkspaceError, match="已有无活动指针"):
        workspace.initialize_workspace(root)
    assert fingerprint(path) == before
    assert not (root / "control" / "active.json").exists()
    assert len(list((root / "datasets").iterdir())) == 1


def test_switch_preserves_old_data_and_invalidates_old_service(root):
    old = initialized(root)
    service = LearningService(old)
    row = service.create_semester("旧数据集的合成学期", request_id=uuid4())
    before = fingerprint(old)
    new = workspace.create_dataset(root)
    workspace.set_active(root, new.parent.name, expected_dataset_id=old.parent.name)
    assert workspace.active_db(root) == new
    with pytest.raises(ConflictError, match="数据集已切换"):
        service.update_semester(row["id"], row["revision"], name="不应写入")
    assert fingerprint(old) == before
    assert service.get_semester(row["id"])["name"] == "旧数据集的合成学期"
    assert LearningService(new).list_semesters() == []
    LearningService(new).create_semester("新活动数据集", request_id=uuid4())


def test_switch_compare_and_swap_refuses_stale_preview(root):
    old = initialized(root)
    first, second = workspace.create_dataset(root), workspace.create_dataset(root)
    workspace.set_active(root, first.parent.name, expected_dataset_id=old.parent.name)
    pointer = (root / "control" / "active.json").read_bytes()
    with pytest.raises(workspace.WorkspaceError, match="已经变化"):
        workspace.set_active(root, second.parent.name, expected_dataset_id=old.parent.name)
    assert (root / "control" / "active.json").read_bytes() == pointer
    assert workspace.active_db(root) == first


@pytest.mark.parametrize("invalid", [None, "not JSON", "[]", '{"format_version":2}', '{"format_version":1,"dataset_id":"../other"}'])
def test_bad_or_missing_pointer_refuses_write_without_database_change(root, invalid):
    path = initialized(root)
    before = fingerprint(path)
    pointer = root / "control" / "active.json"
    if invalid is None:
        pointer.unlink()
    else:
        pointer.write_text(invalid, encoding="utf-8")
    pointer_before = pointer.read_bytes() if pointer.exists() else None
    with pytest.raises(ConflictError, match="指针无效"):
        LearningService(path).create_semester("不应写入", request_id=uuid4())
    assert fingerprint(path) == before
    assert (pointer.read_bytes() if pointer.exists() else None) == pointer_before


def test_identity_mismatch_blocks_active_write(root):
    path = initialized(root)
    before = fingerprint(path)
    storage.atomic_json(path.parent / "config.json", {"format_version": 1, "dataset_id": str(uuid4())})
    with pytest.raises(ConflictError, match="指针无效"):
        LearningService(path).create_semester("不应写入", request_id=uuid4())
    assert fingerprint(path) == before


def test_switch_target_identity_mismatch_keeps_pointer(root):
    old = initialized(root)
    new = workspace.create_dataset(root)
    storage.atomic_json(new.parent / "config.json", {"format_version": 1, "dataset_id": old.parent.name})
    pointer_before = (root / "control" / "active.json").read_bytes()
    with pytest.raises(workspace.WorkspaceError, match="身份无效"):
        workspace.set_active(root, new.parent.name, expected_dataset_id=old.parent.name)
    assert (root / "control" / "active.json").read_bytes() == pointer_before


def test_reentrant_lock_allows_same_thread_nested_transaction(root):
    path = initialized(root)
    with locking.workspace_lock(root), locking.write_barrier(path):
        row = LearningService(path).create_semester("嵌套写屏障", request_id=uuid4())
    assert LearningService(path).get_semester(row["id"])["name"] == "嵌套写屏障"


def test_other_thread_cannot_write_while_workspace_is_frozen(root, monkeypatch):
    path = initialized(root)
    before = fingerprint(path)
    monkeypatch.setattr(locking, "LOCK_TIMEOUT", 0.05)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with locking.workspace_lock(root):
            future = pool.submit(LearningService(path).create_semester, "应等待", request_id=uuid4())
            with pytest.raises(ConflictError, match="正在备份"):
                future.result(timeout=5)
    assert fingerprint(path) == before
    assert LearningService(path).list_semesters() == []
    LearningService(path).create_semester("锁释放后成功", request_id=uuid4())


def test_second_real_python_process_is_denied_by_windows_lock(root):
    path = initialized(root)
    before = fingerprint(path)
    code = """
import sys
from pathlib import Path
from plw import locking
try:
    with locking.workspace_lock(Path(sys.argv[1])):
        print('unexpected-acquisition')
        raise SystemExit(9)
except locking.LockError:
    print('cross-process-lock-blocked')
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(storage.PROJECT_ROOT / "src")
    with locking.workspace_lock(root):
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(root)],
                                cwd=storage.PROJECT_ROOT, env=env, capture_output=True, text=True,
                                encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip() == "cross-process-lock-blocked"
    assert fingerprint(path) == before
    with locking.workspace_lock(root):
        pass


@pytest.mark.parametrize("suffix", ["../outside.txt", "bad:stream.txt", "CON.txt", "trailing. ", "bad?.txt"])
def test_ambiguous_paths_are_rejected_before_creation(root, suffix):
    with pytest.raises(storage.StorageError):
        storage.safe_path(root / suffix)
    assert list(root.iterdir()) == []


def test_source_restriction_excludes_internal_and_real_paths(root):
    source = source_file(root)
    assert storage.check_source(source) == source
    internal = root / "managed" / "payload.txt"
    internal.parent.mkdir()
    internal.write_bytes(b"synthetic internal")
    with pytest.raises(storage.StorageError, match="sources"):
        storage.check_source(internal)
    with pytest.raises(storage.StorageError, match="合成目录"):
        storage.check_source(Path("E:/PLW-Data/anything.txt"))
    assert storage.hash_file(source)[0] == len(source.read_bytes())


def test_actual_windows_hard_link_is_rejected(root):
    source = source_file(root)
    alias = source.with_name("hardlink-alias.txt")
    os.link(source, alias)
    with pytest.raises(storage.StorageError, match="硬链接"):
        storage.check_source(source)
    with pytest.raises(storage.StorageError, match="硬链接"):
        storage.hash_file(alias)


def test_actual_windows_junction_ancestor_is_rejected(root):
    target = root / "junction-target"
    target.mkdir()
    link = root / "junction-alias"
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    command = ("$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction -Path "
               + quote(link) + " -Target " + quote(target) + " | Out-Null")
    result = subprocess.run([r"C:\Program Files\PowerShell\7\pwsh.exe", "-NoProfile", "-Command", command],
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr
    assert link.is_junction()
    with pytest.raises(storage.StorageError, match="重解析点"):
        storage.safe_path(link / "not-yet-created.txt")
    assert list(target.iterdir()) == []


def test_copy_chinese_path_and_no_overwrite(root):
    source = source_file(root)
    before = fingerprint(source)
    target = root / "managed" / "中文 空格.txt"
    size, digest = storage.copy_verified(source, target)
    assert (size, digest) == storage.hash_file(source) == storage.hash_file(target)
    assert fingerprint(source) == before
    with pytest.raises(storage.StorageError, match="尚不存在"):
        storage.copy_verified(source, target)
    assert fingerprint(source) == before


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EACCES])
def test_injected_copy_fsync_failure_preserves_source_and_does_not_claim_success(root, monkeypatch, failure):
    source = source_file(root)
    before = fingerprint(source)
    target = root / "staging" / "payload.part"
    def fail_fsync(_fd):
        raise OSError(failure, "synthetic injected failure")
    monkeypatch.setattr(storage.os, "fsync", fail_fsync)
    with pytest.raises(OSError) as error:
        storage.copy_verified(source, target)
    assert error.value.errno == failure
    assert fingerprint(source) == before
    assert target.exists()  # Retained unfinished copy, never silently published.


def test_atomic_pointer_replace_failure_keeps_previous_bytes(root, monkeypatch):
    path = initialized(root)
    new = workspace.create_dataset(root)
    pointer = root / "control" / "active.json"
    before = pointer.read_bytes()
    def fail_replace(source, target):
        raise PermissionError("synthetic pointer file in use")
    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        workspace.set_active(root, new.parent.name, expected_dataset_id=path.parent.name)
    assert pointer.read_bytes() == before
    assert workspace.active_db(root) == path


def test_json_duplicate_fields_are_rejected(root):
    path = root / "duplicate.json"
    path.write_text('{"dataset_id":"first","dataset_id":"second"}', encoding="utf-8")
    before = fingerprint(path)
    with pytest.raises(storage.StorageError, match="重复字段"):
        storage.read_json(path)
    assert fingerprint(path) == before


def write_restore_journal(root, phase, old_id, new_id):
    path = root / "control" / "restore-journal.json"
    storage.atomic_json(path, {
        "journal_version": 1, "phase": phase,
        "old_dataset_id": old_id, "new_dataset_id": new_id,
    })
    return path


@pytest.mark.parametrize("phase", ["preparing", "old_preserved", "copying", "ready_to_switch", "rolling_back"])
def test_unfinished_restore_journal_blocks_ordinary_writes(root, phase):
    path = initialized(root)
    before = fingerprint(path)
    journal = write_restore_journal(root, phase, path.parent.name, str(uuid4()))
    journal_before = journal.read_bytes()
    with pytest.raises(ConflictError, match="尚未核对的恢复"):
        LearningService(path).create_semester("中断恢复期间不得写入", request_id=uuid4())
    assert fingerprint(path) == before
    assert journal.read_bytes() == journal_before
    assert LearningService(path).list_semesters() == []


def test_failed_restore_with_new_dataset_active_blocks_ordinary_writes(root):
    old = initialized(root)
    new = workspace.create_dataset(root)
    workspace.set_active(root, new.parent.name, expected_dataset_id=old.parent.name)
    journal = write_restore_journal(root, "failed", old.parent.name, new.parent.name)
    before = fingerprint(new)
    journal_before = journal.read_bytes()
    with pytest.raises(ConflictError, match="尚未核对的恢复"):
        LearningService(new).create_semester("切换已发生但恢复未核对", request_id=uuid4())
    assert fingerprint(new) == before
    assert journal.read_bytes() == journal_before


@pytest.mark.parametrize("damaged", ["invalid JSON", "[]", "{}", '{"journal_version":99,"phase":"complete"}'])
def test_corrupt_restore_journal_fails_closed(root, damaged):
    path = initialized(root)
    journal = root / "control" / "restore-journal.json"
    journal.write_text(damaged, encoding="utf-8")
    before = fingerprint(path)
    with pytest.raises(ConflictError, match="尚未核对的恢复"):
        LearningService(path).create_semester("损坏日志不得绕过保护", request_id=uuid4())
    assert fingerprint(path) == before
    assert journal.read_text(encoding="utf-8") == damaged


@pytest.mark.parametrize("phase", ["complete", "rolled_back", "failed"])
def test_terminal_restore_journal_rejects_mismatched_active_identity(root, phase):
    path = initialized(root)
    before = fingerprint(path)
    write_restore_journal(root, phase, str(uuid4()), str(uuid4()))
    with pytest.raises(ConflictError, match="尚未核对的恢复"):
        LearningService(path).create_semester("日志对应另一数据集", request_id=uuid4())
    assert fingerprint(path) == before


@pytest.mark.parametrize("phase", ["complete", "rolled_back", "failed"])
def test_resolved_restore_journal_allows_matching_active_identity(root, phase):
    path = initialized(root)
    current, other = path.parent.name, str(uuid4())
    write_restore_journal(root, phase, other if phase == "complete" else current,
                          current if phase == "complete" else other)
    row = LearningService(path).create_semester("已核对后可正常写入", request_id=uuid4())
    assert LearningService(path).get_semester(row["id"])["name"] == "已核对后可正常写入"


def test_maintenance_allows_active_write_and_backup_but_not_inactive_write(root):
    active = initialized(root)
    inactive = workspace.create_dataset(root)
    inactive_before = fingerprint(inactive)
    journal = write_restore_journal(root, "copying", active.parent.name, inactive.parent.name)
    journal_before = journal.read_bytes()
    with locking.maintenance_barrier(root):
        # Nested maintenance must not clear the outer thread-local capability.
        with locking.maintenance_barrier(root):
            row = LearningService(active).create_semester("维护范围内的合成变更", request_id=uuid4())
        report = backups.create_backup(active)
        assert report["complete"]
        assert backups.verify_backup(report["path"])["complete"]
        with pytest.raises(ConflictError, match="数据集已切换"):
            LearningService(inactive).create_semester("维护也不可改失活集", request_id=uuid4())
    assert fingerprint(inactive) == inactive_before
    assert journal.read_bytes() == journal_before
    assert LearningService(active).get_semester(row["id"])["name"] == "维护范围内的合成变更"
    # The capability must end with the context; ordinary callers remain blocked.
    with pytest.raises(ConflictError, match="尚未核对的恢复"):
        LearningService(active).create_semester("维护结束后仍需核对", request_id=uuid4())
