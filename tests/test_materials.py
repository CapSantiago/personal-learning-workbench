"""M2 file operations exercise only files created for synthetic test datasets."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
from threading import Barrier
from uuid import uuid4

import pytest

from plw import db, storage
from plw.materials import (
    MaterialConflictError, MaterialError, MaterialService, MaterialStorageError,
    MaterialValidationError,
)
from plw.services import LearningService


@pytest.fixture
def env():
    root = Path(__file__).resolve().parents[1] / ".sandbox" / "test-runs" / f"materials-{uuid4().hex}"
    dataset = root / "dataset"
    sources = root / "sources"
    sources.mkdir(parents=True)
    path = dataset / "plw.sqlite3"
    db.initialize(path)
    learning = LearningService(path)
    semester = learning.create_semester("合成学期", request_id=uuid4())
    course = learning.create_course(semester["id"], "机器人原理", request_id=uuid4())
    return MaterialService(path), course, sources


def source_file(env, name="中文 文件 %_ 资料.txt", content=b"synthetic course bytes\n"):
    path = env[2] / name
    path.write_bytes(content)
    return path


def imported(env, mode="managed_copy", **kwargs):
    service, course, _ = env
    return service.import_file(course["id"], source_file(env), mode, request_id=uuid4(), **kwargs)


def operations(service):
    with db.transaction(service.db_path, write=False) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM file_operations ORDER BY created_at,id")]


def test_managed_copy_chinese_spaces_source_untouched_and_baseline(env):
    service, course, _ = env
    source = source_file(env)
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    result = service.import_file(course["id"], source, "managed_copy", request_id=uuid4())
    target = service.root / result["managed_relpath"]
    assert target.read_bytes() == before[0]
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert result["name"] == source.name
    assert result["original_path"] == str(source)
    assert result["reference_path"] is None
    assert result["baseline_sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert result["observed_sha256"] == result["baseline_sha256"]
    assert result["file_status"] == "normal" and result["import_state"] == "ready"
    assert operations(service)[0]["state"] == "committed"
    assert not (service.root / operations(service)[0]["staging_relpath"]).exists()


def test_reference_import_copies_no_source(env):
    service, _, _ = env
    row = imported(env, "external_reference")
    assert row["managed_relpath"] is None
    assert row["reference_path"] == row["original_path"]
    assert not (service.root / "managed").exists()
    assert not (service.root / ".staging").exists()
    assert service.check_material(row["id"])["file_status"] == "normal"


@pytest.mark.parametrize("mode", ["managed_copy", "external_reference"])
def test_request_is_idempotent_but_content_duplicates_are_separate(env, mode):
    service, course, _ = env
    source = source_file(env)
    token = uuid4()
    first = service.import_file(course["id"], source, mode, request_id=token)
    again = service.import_file(course["id"], source, mode, request_id=token)
    second = service.import_file(course["id"], source, mode, request_id=uuid4())
    assert first["id"] == again["id"] != second["id"]
    assert len(service.list_materials()) == 2
    assert [item["id"] for item in second["duplicate_candidates"]] == [first["id"]]
    with pytest.raises(MaterialConflictError, match="另一组"):
        service.import_file(course["id"], source, mode, name="changed", request_id=token)
    assert len(operations(service)) == 2


def test_ready_retry_does_not_require_source_still_present(env):
    service, course, _ = env
    source = source_file(env)
    token = uuid4()
    first = service.import_file(course["id"], source, "managed_copy", request_id=token)
    source.rename(source.with_name("合成移动后.txt"))
    assert service.import_file(course["id"], source, "managed_copy", request_id=token)["id"] == first["id"]


def test_reference_missing_relink_same_hash_preserves_original(env):
    service, _, _ = env
    row = imported(env, "external_reference")
    original = Path(row["original_path"])
    moved = original.with_name("合成移动后 有空格.txt")
    original.rename(moved)
    assert service.check_material(row["id"])["file_status"] == "missing"
    fixed = service.relink_reference(row["id"], moved)
    assert fixed["reference_path"] == str(moved)
    assert fixed["original_path"] == str(original)
    assert fixed["file_status"] == "normal"
    assert service.check_material(row["id"])["file_status"] == "normal"


def test_hash_change_cannot_replace_baseline_even_after_confirmed_relink(env):
    service, _, _ = env
    row = imported(env, "external_reference")
    source = Path(row["reference_path"])
    source.write_bytes(b"changed content")
    changed = service.check_material(row["id"])
    assert changed["file_status"] == "possibly_changed"
    assert changed["baseline_sha256"] == row["baseline_sha256"]
    assert changed["observed_sha256"] != row["baseline_sha256"]
    with pytest.raises(MaterialConflictError, match="明确确认"):
        service.relink_reference(row["id"], source)
    result = service.relink_reference(row["id"], source, confirm_changed=True)
    assert result["baseline_sha256"] == row["baseline_sha256"]
    assert result["file_status"] == "possibly_changed"
    assert service.check_material(row["id"], full_hash=False)["file_status"] == "possibly_changed"


def test_metadata_probe_is_conservative_and_full_hash_can_clear_it(env):
    service, _, _ = env
    row = imported(env, "external_reference")
    source = Path(row["reference_path"])
    os.utime(source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 1_000_000_000))
    fast = service.check_material(row["id"], full_hash=False)
    assert fast["file_status"] == "possibly_changed"
    assert fast["hash_checked_at"] == row["hash_checked_at"]
    verified = service.check_material(row["id"])
    assert verified["file_status"] == "normal"
    assert verified["baseline_sha256"] == row["baseline_sha256"]


def test_managed_records_cannot_be_relinked_as_external(env):
    service, _, _ = env
    row = imported(env)
    with pytest.raises(MaterialConflictError, match="外部引用"):
        service.relink_reference(row["id"], row["original_path"])


def test_permission_failure_is_inaccessible_not_missing(env, monkeypatch):
    service, _, _ = env
    row = imported(env, "external_reference")
    def denied(_path):
        raise PermissionError("synthetic locked file")
    monkeypatch.setattr(storage, "hash_file", denied)
    checked = service.check_material(row["id"])
    assert checked["file_status"] == "inaccessible"
    assert checked["last_error_code"] == "PermissionError"
    assert checked["baseline_sha256"] == row["baseline_sha256"]


def test_source_copy_failure_keeps_failed_intent_and_refuses_retry(env, monkeypatch):
    service, course, _ = env
    source = source_file(env)
    token = uuid4()
    def failed_copy(_source, target, **_kwargs):
        target.parent.mkdir(parents=True)
        target.write_bytes(b"partial")
        raise OSError("synthetic disk full")
    monkeypatch.setattr(storage, "copy_verified", failed_copy)
    with pytest.raises(MaterialStorageError):
        service.import_file(course["id"], source, "managed_copy", request_id=token)
    row = service.list_materials()[0]
    assert row["import_state"] == "failed"
    assert operations(service)[0]["state"] == "failed"
    with pytest.raises(MaterialConflictError, match="先执行"):
        service.import_file(course["id"], source, "managed_copy", request_id=token)
    result = service.reconcile_operations()
    assert result[0]["state"] == "quarantined"
    assert (service.root / result[0]["staging_relpath"]).read_bytes() == b"partial"
    assert source.read_bytes() == b"synthetic course bytes\n"
    assert not (service.root / row["managed_relpath"]).exists()


def test_promoted_file_after_commit_failure_recovers_without_recopy(env, monkeypatch):
    service, course, _ = env
    source = source_file(env)
    token = uuid4()
    commit = service._commit_import
    def fail_commit(*_args):
        raise MaterialStorageError("synthetic commit failure")
    monkeypatch.setattr(service, "_commit_import", fail_commit)
    with pytest.raises(MaterialStorageError):
        service.import_file(course["id"], source, "managed_copy", request_id=token)
    row = service.list_materials()[0]
    target = service.root / row["managed_relpath"]
    assert target.exists() and row["import_state"] == "failed"
    before = target.stat().st_mtime_ns
    monkeypatch.setattr(service, "_commit_import", commit)
    source.rename(source.with_name("moved-after-copy.txt"))
    assert service.reconcile_operations()[0]["state"] == "committed"
    assert target.stat().st_mtime_ns == before
    assert service.get_material(row["id"])["import_state"] == "ready"
    assert service.import_file(course["id"], source, "managed_copy", request_id=token)["id"] == row["id"]


def test_complete_staging_recovers_after_promotion_failure(env, monkeypatch):
    service, course, _ = env
    original_promote = service._promote
    def fail_promote(*_args):
        raise PermissionError("synthetic rename blocked")
    monkeypatch.setattr(service, "_promote", fail_promote)
    with pytest.raises(MaterialStorageError):
        service.import_file(course["id"], source_file(env), "managed_copy", request_id=uuid4())
    op = operations(service)[0]
    assert (service.root / op["staging_relpath"]).exists()
    monkeypatch.setattr(service, "_promote", original_promote)
    assert service.reconcile_operations()[0]["state"] == "committed"
    assert service.get_material(op["entity_id"])["import_state"] == "ready"


def test_unexpected_target_is_never_overwritten(env, monkeypatch):
    service, course, _ = env
    real_promote = service._promote
    def competing_target(staged, target):
        target.parent.mkdir(parents=True)
        target.write_bytes(b"other owner's synthetic data")
        real_promote(staged, target)
    monkeypatch.setattr(service, "_promote", competing_target)
    with pytest.raises(MaterialConflictError, match="绝不覆盖"):
        service.import_file(course["id"], source_file(env), "managed_copy", request_id=uuid4())
    op = operations(service)[0]
    assert (service.root / op["target_relpath"]).read_bytes() == b"other owner's synthetic data"
    assert service.reconcile_operations()[0]["state"] == "quarantined"
    assert (service.root / op["staging_relpath"]).exists()


def test_logical_delete_keeps_files_and_associations_and_can_restore(env):
    service, course, _ = env
    row = imported(env)
    chapter_id = str(uuid4())
    with db.transaction(service.db_path) as connection:
        connection.execute("INSERT INTO chapters(id,course_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                           (chapter_id, course["id"], "合成章节", row["created_at"], row["created_at"]))
        connection.execute("INSERT INTO chapter_materials(chapter_id,material_id) VALUES(?,?)", (chapter_id, row["id"]))
    service.set_deleted(row["id"], True)
    assert not service.list_materials()
    assert len(service.list_materials(include_deleted=True)) == 1
    assert (service.root / row["managed_relpath"]).exists()
    with db.transaction(service.db_path, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM chapter_materials").fetchone()[0] == 1
    assert service.association_counts(row["id"]) == {"tasks": 0, "notes": 0, "chapters": 1, "editions": 0}
    with pytest.raises(MaterialConflictError, match="仍被"):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    assert (service.root / row["managed_relpath"]).exists()
    assert service.set_deleted(row["id"], False)["deleted_at"] is None
    assert len(service.list_materials()) == 1


def test_managed_physical_delete_needs_index_removal_and_exact_confirmation(env):
    service, _, _ = env
    row = imported(env)
    with pytest.raises(MaterialValidationError):
        service.delete_managed_file(row["id"], confirmation="yes")
    with pytest.raises(MaterialConflictError, match="从列表移除"):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    service.set_deleted(row["id"], True)
    deleted = service.delete_managed_file(row["id"], confirmation=row["id"])
    assert deleted["file_deleted_at"] and deleted["file_status"] == "missing"
    assert not (service.root / row["managed_relpath"]).exists()
    assert Path(row["original_path"]).exists()
    assert operations(service)[-1]["kind"] == "delete_managed_file"
    assert operations(service)[-1]["state"] == "committed"
    with pytest.raises(MaterialConflictError):
        service.set_deleted(row["id"], False)
    assert service.delete_managed_file(row["id"], confirmation=row["id"])["file_deleted_at"] == deleted["file_deleted_at"]


def test_reference_physical_delete_is_always_rejected(env):
    service, _, _ = env
    row = imported(env, "external_reference")
    service.set_deleted(row["id"], True)
    before = Path(row["original_path"]).read_bytes()
    with pytest.raises(MaterialConflictError, match="绝不能"):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    assert Path(row["original_path"]).read_bytes() == before
    assert len(operations(service)) == 1


def test_changed_managed_file_delete_refused(env):
    service, _, _ = env
    row = imported(env)
    target = service.root / row["managed_relpath"]
    target.write_bytes(b"unexpected synthetic change")
    service.set_deleted(row["id"], True)
    with pytest.raises(MaterialConflictError, match="内容已变化"):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    assert target.exists()


def test_record_cannot_expand_delete_authority_to_another_managed_id(env):
    service, _, _ = env
    row = imported(env)
    first_path = service.root / row["managed_relpath"]
    foreign_relpath = f"managed/{uuid4()}/payload.txt"
    foreign = service.root / foreign_relpath
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(first_path.read_bytes())
    service.set_deleted(row["id"], True)
    with db.transaction(service.db_path) as connection:
        connection.execute("UPDATE materials SET managed_relpath=? WHERE id=?", (foreign_relpath, row["id"]))
    with pytest.raises(MaterialValidationError, match="资料 ID"):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    assert foreign.exists() and first_path.exists()


def test_source_link_swap_cannot_allow_delete_or_check_as_normal(env):
    service, _, sources = env
    row = imported(env)
    target = service.root / row["managed_relpath"]
    second = sources / "extra-link.txt"
    os.link(target, second)
    service.set_deleted(row["id"], True)
    with pytest.raises(MaterialStorageError):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    assert service.check_material(row["id"])["file_status"] == "inaccessible"
    assert target.exists() and second.exists()


def test_delete_commit_interruption_is_reconciled_without_second_delete(env, monkeypatch):
    service, _, _ = env
    row = imported(env)
    service.set_deleted(row["id"], True)
    commit = service._commit_delete
    def fail(*_args):
        raise MaterialStorageError("synthetic commit failure")
    monkeypatch.setattr(service, "_commit_delete", fail)
    with pytest.raises(MaterialStorageError):
        service.delete_managed_file(row["id"], confirmation=row["id"])
    assert not (service.root / row["managed_relpath"]).exists()
    assert service.get_material(row["id"])["file_deleted_at"] is None
    monkeypatch.setattr(service, "_commit_delete", commit)
    assert service.reconcile_operations()[0]["state"] == "committed"
    assert service.get_material(row["id"])["file_deleted_at"]


def test_missing_staging_does_not_recopysource_on_reconcile(env, monkeypatch):
    service, course, _ = env
    def fail(*_args, **_kwargs):
        raise PermissionError("copy never started")
    monkeypatch.setattr(storage, "copy_verified", fail)
    with pytest.raises(MaterialStorageError):
        service.import_file(course["id"], source_file(env), "managed_copy", request_id=uuid4())
    assert service.reconcile_operations()[0]["state"] == "failed"
    assert not (service.root / service.list_materials()[0]["managed_relpath"]).exists()


def test_concurrent_same_request_yields_single_material(env):
    service, course, _ = env
    source = source_file(env)
    request_id = uuid4()
    barrier = Barrier(2)
    def run():
        barrier.wait()
        return MaterialService(service.db_path).import_file(course["id"], source, "managed_copy", request_id=request_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results[0]["id"] == results[1]["id"]
    assert len(service.list_materials()) == len(operations(service)) == 1


def test_search_literals_and_course_filter(env):
    service, course, _ = env
    row = imported(env, name="资料 100%_ 中文")
    imported(env, name="资料 100xy 中文")
    assert [item["id"] for item in service.list_materials(course["id"], "%_")] == [row["id"]]
    assert not service.list_materials(uuid4())


def test_archived_course_and_out_of_scope_source_rejected_without_intent(env):
    service, course, _ = env
    source = source_file(env)
    learning = LearningService(service.db_path)
    learning.set_course_archived(course["id"], True, course["revision"])
    with pytest.raises(MaterialConflictError, match="归档"):
        service.import_file(course["id"], source, "managed_copy", request_id=uuid4())
    with pytest.raises(MaterialError):
        service.import_file(course["id"], Path("E:/some-real-user-file.pdf"), "managed_copy", request_id=uuid4())
    assert not service.list_materials(include_deleted=True)
    assert not operations(service)


@pytest.mark.parametrize("field,value", [("storage_mode", "auto"), ("material_type", "exe"), ("name", " ")])
def test_invalid_inputs_create_no_rows(env, field, value):
    service, course, _ = env
    args = {"storage_mode": "managed_copy", "material_type": "other", "name": "有效名称"}
    args[field] = value
    with pytest.raises(MaterialValidationError):
        service.import_file(course["id"], source_file(env), request_id=uuid4(), **args)
    assert not service.list_materials()
