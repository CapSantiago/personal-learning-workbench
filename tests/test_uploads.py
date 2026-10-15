"""Browser uploads use only synthetic bytes and isolated test datasets."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from plw import db, materials
from plw.materials import (
    MaterialConflictError, MaterialNotFoundError, MaterialService,
    MaterialStorageError, MaterialValidationError,
)
from plw.services import LearningService


@pytest.fixture
def env():
    root = Path(__file__).resolve().parents[1] / ".sandbox" / "test-runs" / f"uploads-{uuid4().hex}"
    path = root / "dataset" / "plw.sqlite3"
    db.initialize(path)
    learning = LearningService(path)
    semester = learning.create_semester("合成上传学期", request_id=uuid4())
    course = learning.create_course(semester["id"], "机器人原理", request_id=uuid4())
    return MaterialService(path), course, learning


def operations(service):
    with db.transaction(service.db_path) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM file_operations ORDER BY created_at,id")]


def upload(env, content=b"%PDF-1.7\nsynthetic only", filename="第四讲 机器人运动学.pdf", **kwargs):
    service, course, _ = env
    return service.import_upload(course["id"], filename, content, request_id=kwargs.pop("request_id", uuid4()), **kwargs)


@pytest.mark.parametrize("filename", ["第四讲 机器人运动学.pdf", "Lecture.PDF", "中文 slides.pptx", "legacy.ppt"])
def test_upload_is_managed_with_baseline_and_honest_source_metadata(env, filename):
    service, _, _ = env
    content = b"synthetic immutable bytes" * 70000
    row = upload(env, content, filename)
    target = service.root / row["managed_relpath"]
    assert row["storage_mode"] == "managed_copy" and row["reference_path"] is None
    assert row["original_path"] == str(target)
    assert row["name"] == filename and row["material_type"] == "slides"
    assert target.read_bytes() == content
    assert target.suffix == Path(filename).suffix.lower()
    assert row["size_bytes"] == len(content)
    assert row["baseline_sha256"] == row["observed_sha256"] == hashlib.sha256(content).hexdigest()
    assert row["import_state"] == "ready" and row["file_status"] == "normal"
    op, = operations(service)
    assert op["state"] == "committed"
    payload = json.loads(op["payload_json"])
    assert payload["source_kind"] == "browser_upload" and payload["filename"] == filename
    assert not (service.root / op["staging_relpath"]).exists()
    assert service.check_material(row["id"])["file_status"] == "normal"


def test_same_request_is_idempotent_and_other_content_conflicts(env):
    service, _, _ = env
    token = uuid4()
    first = upload(env, request_id=token)
    assert upload(env, request_id=token)["id"] == first["id"]
    with pytest.raises(MaterialConflictError, match="另一组"):
        upload(env, b"different bytes", request_id=token)
    with pytest.raises(MaterialConflictError, match="另一组"):
        upload(env, filename="other.pdf", request_id=token)
    with pytest.raises(MaterialConflictError, match="另一组"):
        upload(env, material_type="textbook", request_id=token)
    assert len(service.list_materials()) == len(operations(service)) == 1


def test_request_cannot_be_reused_for_a_different_course(env):
    service, course, learning = env
    token = uuid4()
    upload(env, request_id=token)
    second = learning.create_course(course["semester_id"], "另一合成课程", request_id=uuid4())
    with pytest.raises(MaterialConflictError, match="另一组"):
        service.import_upload(second["id"], "第四讲 机器人运动学.pdf", b"%PDF-1.7\nsynthetic only", request_id=token)


def test_same_name_different_bytes_and_duplicate_content_remain_separate(env):
    first = upload(env)
    second = upload(env, b"other synthetic bytes")
    third = upload(env, filename="同一份课件另一个名字.pdf")
    assert len({first["id"], second["id"], third["id"]}) == 3
    assert second["duplicate_candidates"] == []
    assert [x["id"] for x in third["duplicate_candidates"]] == [first["id"]]


@pytest.mark.parametrize("filename", [
    "", "..", "../escape.pdf", r"..\escape.pdf", r"C:\fakepath\x.pdf", "/tmp/x.pdf",
    "x:ads.pdf", " bad.pdf", "bad.pdf ", "bad.pdf.", "x\n.pdf", "x\x7f.pdf", "x\u202e.pdf",
    "CON.pdf", "prn.pptx", "AUX.pdf", "COM1.pdf", "LPT9.ppt", "COM¹.pdf", "CONIN$.pdf",
    "bad?.pdf", "bad*.pdf", 'bad".pdf', "bad|.pdf", "x.exe", "x.docx", "x.pdf.exe", ".pdf",
    "a" * 256 + ".pdf", "🦾" * 126 + ".pdf", None,
])
def test_unsafe_or_unsupported_filename_rejected_before_any_write(env, filename):
    service, _, _ = env
    with pytest.raises(MaterialValidationError):
        upload(env, filename=filename)
    assert service.list_materials() == [] and operations(service) == []
    assert not (service.root / ".staging").exists()
    assert not (service.root / "managed").exists()


@pytest.mark.parametrize("content", [b"", "text", bytearray(b"x"), memoryview(b"x"), None])
def test_invalid_or_empty_bytes_rejected(env, content):
    with pytest.raises(MaterialValidationError):
        upload(env, content)
    assert operations(env[0]) == []


def test_size_limit_before_write_and_exact_limit_allowed(env, monkeypatch):
    monkeypatch.setattr(materials, "UPLOAD_MAX_BYTES", 8)
    with pytest.raises(MaterialValidationError, match="200 MiB"):
        upload(env, b"123456789")
    assert operations(env[0]) == []
    assert upload(env, b"12345678")["size_bytes"] == 8


def test_unknown_course_does_not_create_file_or_intent(env):
    service, _, _ = env
    with pytest.raises(MaterialNotFoundError):
        service.import_upload(uuid4(), "x.pdf", b"bytes", request_id=uuid4())
    assert operations(service) == []
    assert not (service.root / ".staging").exists()


def test_partial_write_is_preserved_for_reconciliation_without_overwrite(env, monkeypatch):
    service, _, _ = env
    token = uuid4()
    def partial_write(staged, content):
        staged.parent.mkdir(parents=True)
        staged.write_bytes(content[:3])
        raise OSError("synthetic disk full")
    monkeypatch.setattr(service, "_stage_upload", partial_write)
    with pytest.raises(MaterialStorageError, match="操作日志"):
        upload(env, request_id=token)
    op, = operations(service)
    assert op["state"] == "failed"
    assert service.get_material(op["entity_id"])["import_state"] == "failed"
    with pytest.raises(MaterialConflictError, match="先执行"):
        upload(env, request_id=token)
    assert service.reconcile_operations()[0]["state"] == "quarantined"
    assert (service.root / op["staging_relpath"]).read_bytes() == b"%PD"


@pytest.mark.parametrize("failure_point", ["_promote", "_commit_import"])
def test_complete_upload_recovers_after_promotion_or_commit_failure(env, monkeypatch, failure_point):
    service, _, _ = env
    original = getattr(service, failure_point)
    token = uuid4()
    def fail(*args):
        raise OSError("synthetic interruption")
    monkeypatch.setattr(service, failure_point, fail)
    with pytest.raises(MaterialStorageError):
        upload(env, request_id=token)
    op, = operations(service)
    assert op["state"] == "failed"
    monkeypatch.setattr(service, failure_point, original)
    assert service.reconcile_operations()[0]["state"] == "committed"
    assert upload(env, request_id=token)["id"] == op["entity_id"]
    assert len(service.list_materials()) == 1


def test_corrupt_staging_never_promotes(env, monkeypatch):
    service, _, _ = env
    def corrupt(staged, _content):
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"corrupt bytes")
    monkeypatch.setattr(service, "_stage_upload", corrupt)
    with pytest.raises(MaterialConflictError, match="校验"):
        upload(env)
    op, = operations(service)
    assert not (service.root / op["target_relpath"]).exists()
    assert service.reconcile_operations()[0]["state"] == "quarantined"


def test_concurrent_double_click_commits_one_material(env):
    service, _, _ = env
    token, barrier = uuid4(), Barrier(2)
    def call(_):
        barrier.wait()
        return upload(env, request_id=token)["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(call, range(2)))
    assert result[0] == result[1]
    assert len(operations(service)) == len(service.list_materials()) == 1
