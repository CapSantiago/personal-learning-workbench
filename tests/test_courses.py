"""M1 business tests using real SQLite files and only synthetic learning data."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import hashlib
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from plw import db
from plw.services import (
    ArchivedError,
    ConflictError,
    LearningService,
    NotFoundError,
    StorageError,
    ValidationError,
)


@pytest.fixture(scope="module")
def service_test_root():
    root = Path(__file__).resolve().parents[1] / ".sandbox" / "test-runs"
    folder = root / f"services-{uuid4().hex}"
    folder.mkdir(parents=True)
    return folder


@pytest.fixture
def service(service_test_root):
    path = service_test_root / f"case-{uuid4().hex}.sqlite3"
    db.initialize(path)
    return LearningService(path)


def semester(service, name="合成学期"):
    return service.create_semester(name, request_id=uuid4())


def course(service, parent=None, name="合成机器人课程", **values):
    parent = parent or semester(service)
    return service.create_course(parent["id"], name, request_id=uuid4(), **values)


def test_semester_create_update_and_reopen(service):
    request_id = uuid4()
    created = service.create_semester(
        "  2026 秋季  ", date(2026, 9, 1), "2027-01-20", request_id=request_id
    )
    assert created["id"] == str(request_id)
    assert created["name"] == "2026 秋季"
    assert created["start_date"] == "2026-09-01"
    assert created["end_date"] == "2027-01-20"
    assert created["revision"] == 1
    assert created["created_at"] == created["updated_at"]
    assert created["created_at"].endswith("Z")
    changed = service.update_semester(
        created["id"], created["revision"], name="秋季学期", end_date=None
    )
    assert changed["revision"] == 2
    assert changed["end_date"] is None
    assert changed["created_at"] == created["created_at"]
    assert LearningService(service.db_path).get_semester(created["id"]) == changed


def test_course_all_fields_update_transfer_and_reopen(service):
    first = semester(service, "秋季")
    second = semester(service, "春季")
    created = course(
        service, first, name="  自动控制原理 ", teacher=" 张老师 ", credits=3.5,
        schedule_text="周一 08:00\n实验周四", assessment="闭卷 + 实验",
        status="active", remarks="合成备注",
    )
    assert created["name"] == "自动控制原理"
    assert created["teacher"] == "张老师"
    assert created["credits"] == 3.5
    assert created["semester_name"] == "秋季"
    updated = service.update_course(
        created["id"], 1, semester_id=second["id"], credits=None,
        status="completed", remarks="已完成",
    )
    assert updated["revision"] == 2
    assert updated["semester_id"] == second["id"]
    assert updated["semester_name"] == "春季"
    assert updated["credits"] is None
    assert updated["status"] == "completed"
    assert updated["created_at"] == created["created_at"]
    assert not service.list_courses(semester_id=first["id"])
    assert LearningService(service.db_path).get_course(created["id"]) == updated


def test_same_name_courses_can_exist_in_different_semesters(service):
    first = semester(service, "学期 A")
    second = semester(service, "学期 B")
    one = course(service, first, name="机器人学")
    two = course(service, second, name="机器人学")
    assert one["id"] != two["id"]
    assert len(service.list_courses(query="机器人学")) == 2
    assert [row["id"] for row in service.list_courses(first["id"])] == [one["id"]]
    assert [row["id"] for row in service.list_courses(second["id"])] == [two["id"]]


@pytest.mark.parametrize("needle", ["中文", "%", "_", "!", "\\", "' OR 1=1 --"])
def test_search_is_literal_and_supports_chinese(service, needle):
    parent = semester(service, f"合成{needle}学期")
    semester(service, "普通学期")
    target = course(service, parent, name=f"机器人{needle}课程")
    course(service, parent, name="普通课程")
    assert [row["id"] for row in service.list_semesters(needle)] == [parent["id"]]
    assert [row["id"] for row in service.list_courses(query=needle)] == [target["id"]]


def test_course_search_includes_teacher_and_remarks(service):
    target = course(service, teacher="测试教师", remarks="运动学专项复习")
    assert service.list_courses(query="测试教师")[0]["id"] == target["id"]
    assert service.list_courses(query="运动学")[0]["id"] == target["id"]


@pytest.mark.parametrize(
    "values",
    [
        {"name": " \t "},
        {"name": None},
        {"name": "学期\n新行"},
        {"start_date": "2026-02-30"},
        {"start_date": "20260901"},
        {"start_date": datetime(2026, 9, 1, 9)},
        {"start_date": "2026-09-01", "end_date": "2026-08-31"},
    ],
)
def test_invalid_semester_does_not_write(service, values):
    request_id = uuid4()
    payload = {"name": "合成学期", **values}
    with pytest.raises(ValidationError):
        service.create_semester(**payload, request_id=request_id)
    assert service.list_semesters(include_archived=True) == []
    with db.transaction(service.db_path, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM create_requests").fetchone()[0] == 0


@pytest.mark.parametrize(
    "values",
    [
        {"name": ""},
        {"name": "\x00"},
        {"credits": -0.1},
        {"credits": 101},
        {"credits": float("nan")},
        {"credits": float("inf")},
        {"credits": True},
        {"status": "unknown"},
    ],
)
def test_invalid_course_does_not_write(service, values):
    parent = semester(service)
    payload = {"name": "合成课程", **values}
    with pytest.raises(ValidationError):
        service.create_course(parent["id"], **payload, request_id=uuid4())
    assert service.list_courses(include_archived=True) == []
    with db.transaction(service.db_path, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM create_requests").fetchone()[0] == 1


def test_missing_parent_and_invalid_ids_do_not_write(service):
    parent = semester(service)
    existing = course(service, parent)
    with pytest.raises(NotFoundError):
        service.create_course(uuid4(), "不能创建", request_id=uuid4())
    with pytest.raises(NotFoundError):
        service.update_course(existing["id"], 1, semester_id=uuid4())
    with pytest.raises(ValidationError):
        service.get_course("not-a-uuid")
    with pytest.raises(NotFoundError):
        service.get_semester(uuid4())
    assert service.get_course(existing["id"]) == existing
    assert len(service.list_courses()) == 1


def test_duplicate_semester_request_reuses_normalized_original_payload(service):
    token = uuid4()
    original = service.create_semester(
        " 秋季 ", date(2026, 9, 1), request_id=token
    )
    repeated = service.create_semester(
        "秋季", "2026-09-01", request_id=str(token).upper()
    )
    assert repeated == original
    changed = service.update_semester(original["id"], 1, name="修改后的秋季")
    reopened = LearningService(service.db_path)
    assert reopened.create_semester(
        "秋季", "2026-09-01", request_id=token
    ) == changed
    with pytest.raises(ConflictError):
        reopened.create_semester("不同内容", request_id=token)
    assert len(reopened.list_semesters()) == 1


def test_duplicate_course_request_survives_edit_and_archive(service):
    parent = semester(service)
    token = uuid4()
    created = service.create_course(parent["id"], " 原课程 ", credits=3, request_id=token)
    assert service.create_course(
        UUID(parent["id"]), "原课程", credits=3.0, request_id=token
    ) == created
    changed = service.update_course(created["id"], 1, name="新课程名", credits=4)
    archived = service.set_course_archived(changed["id"], True, changed["revision"])
    service.set_semester_archived(parent["id"], True, parent["revision"])
    assert LearningService(service.db_path).create_course(
        parent["id"], "原课程", credits=3, request_id=token
    ) == {**archived, "semester_archived_at": service.get_semester(parent["id"])["archived_at"]}
    with pytest.raises(ConflictError):
        service.create_course(parent["id"], "新课程名", credits=4, request_id=token)
    assert len(service.list_courses(include_archived=True)) == 1


def test_request_id_cannot_be_reused_for_another_entity_type(service):
    token = uuid4()
    parent = service.create_semester("合成学期", request_id=token)
    with pytest.raises(ConflictError):
        service.create_course(parent["id"], "课程", request_id=token)
    assert service.list_courses() == []


def test_create_and_request_ledger_are_one_transaction(service):
    with db.transaction(service.db_path) as connection:
        connection.execute(
            """CREATE TRIGGER synthetic_reject_request
               BEFORE INSERT ON create_requests
               BEGIN SELECT RAISE(ABORT, 'synthetic request failure'); END"""
        )
    with pytest.raises(ValidationError):
        semester(service)
    with db.transaction(service.db_path, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM semesters").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM create_requests").fetchone()[0] == 0


def test_stale_revision_never_overwrites_new_data(service):
    parent = semester(service)
    updated_parent = service.update_semester(parent["id"], 1, name="新学期名称")
    with pytest.raises(ConflictError):
        service.update_semester(parent["id"], 1, name="旧表单内容")
    with pytest.raises(ConflictError):
        service.set_semester_archived(parent["id"], True, 1)
    assert service.get_semester(parent["id"]) == updated_parent
    item = course(service, parent)
    changed = service.update_course(item["id"], 1, teacher="新教师")
    with pytest.raises(ConflictError):
        service.update_course(item["id"], 1, teacher="旧教师")
    with pytest.raises(ConflictError):
        service.set_course_archived(item["id"], True, 1)
    assert service.get_course(item["id"]) == changed


@pytest.mark.parametrize("revision", [0, -1, True, 1.0, "1"])
def test_invalid_revision_is_rejected(service, revision):
    parent = semester(service)
    with pytest.raises(ValidationError):
        service.update_semester(parent["id"], revision, name="不能修改")
    assert service.get_semester(parent["id"]) == parent


def test_invalid_partial_update_does_not_lose_valid_fields(service):
    parent = service.create_semester(
        "学期", "2026-09-01", "2027-01-20", request_id=uuid4()
    )
    with pytest.raises(ValidationError):
        service.update_semester(parent["id"], 1, end_date="2026-08-01")
    assert service.get_semester(parent["id"]) == parent
    item = course(service, parent)
    with pytest.raises(ValidationError):
        service.update_course(item["id"], 1, status="wrong", teacher="不应保存")
    with pytest.raises(ValidationError):
        service.update_course(item["id"], 1, archived_at="2026-10-01")
    assert service.get_course(item["id"]) == item


def test_semester_archive_hides_courses_without_cascading(service):
    parent = semester(service)
    item = course(service, parent, status="active")
    chapter_id = str(uuid4())
    with db.transaction(service.db_path) as connection:
        connection.execute(
            """INSERT INTO chapters
               (id, course_id, parent_id, title, position, created_at, updated_at)
               VALUES (?, ?, NULL, '合成章节', 0, ?, ?)""",
            (chapter_id, item["id"], item["created_at"], item["updated_at"]),
        )
    archived_parent = service.set_semester_archived(parent["id"], True, 1)
    assert service.list_semesters() == []
    assert service.list_courses() == []
    historical = service.list_courses(include_archived=True)[0]
    assert historical["archived_at"] is None
    assert historical["status"] == "active"
    assert historical["revision"] == item["revision"]
    assert historical["semester_archived_at"] == archived_parent["archived_at"]
    with db.transaction(service.db_path, write=False) as connection:
        assert connection.execute(
            "SELECT course_id FROM chapters WHERE id = ?", (chapter_id,)
        ).fetchone()[0] == item["id"]
    with pytest.raises(ArchivedError):
        service.update_semester(parent["id"], 2, name="不能直接修改")
    with pytest.raises(ArchivedError):
        service.update_course(item["id"], 1, name="不能直接修改")
    with pytest.raises(ArchivedError):
        course(service, parent)
    with pytest.raises(ArchivedError):
        service.set_course_archived(item["id"], True, 1)
    service.set_semester_archived(parent["id"], False, archived_parent["revision"])
    assert service.list_courses()[0]["id"] == item["id"]
    assert service.get_course(item["id"])["status"] == "active"


def test_course_archive_and_unarchive_preserve_status(service):
    item = course(service, status="paused")
    archived = service.set_course_archived(item["id"], True, 1)
    assert archived["status"] == "paused"
    assert service.list_courses() == []
    assert service.get_course(item["id"]) == archived
    with pytest.raises(ArchivedError):
        service.update_course(item["id"], 2, status="active")
    restored = service.set_course_archived(item["id"], False, 2)
    assert restored["status"] == "paused"
    assert restored["archived_at"] is None
    assert restored["revision"] == 3
    assert service.list_courses()[0] == restored


def test_course_cannot_be_moved_into_archived_semester(service):
    item = course(service)
    archived_parent = semester(service, "归档目标学期")
    service.set_semester_archived(archived_parent["id"], True, 1)
    with pytest.raises(ArchivedError):
        service.update_course(item["id"], 1, semester_id=archived_parent["id"])
    assert service.get_course(item["id"]) == item


def test_noop_edit_or_archive_does_not_invent_new_revision(service):
    parent = semester(service)
    assert service.update_semester(parent["id"], 1, name=f" {parent['name']} ") == parent
    assert service.set_semester_archived(parent["id"], False, 1) == parent
    item = course(service, parent)
    assert service.update_course(item["id"], 1) == item
    assert service.set_course_archived(item["id"], False, 1) == item


def test_read_operations_do_not_change_database_bytes(service):
    parent = semester(service)
    item = course(service, parent)
    before = hashlib.sha256(service.db_path.read_bytes()).hexdigest()
    service.list_semesters(query="合成", include_archived=True)
    service.get_semester(parent["id"])
    service.list_courses(query="_", include_archived=True)
    service.get_course(item["id"])
    after = hashlib.sha256(service.db_path.read_bytes()).hexdigest()
    assert before == after


def test_service_does_not_initialize_missing_database(service_test_root):
    missing = service_test_root / f"not-initialized-{uuid4().hex}.sqlite3"
    service = LearningService(missing)
    assert not missing.exists()
    with pytest.raises(StorageError):
        service.list_semesters()
    assert not missing.exists()


def test_simultaneous_create_with_same_request_has_one_course(service):
    parent = semester(service)
    token = uuid4()
    barrier = Barrier(2)

    def submit():
        independent_service = LearningService(service.db_path)
        barrier.wait(timeout=10)
        return independent_service.create_course(
            parent["id"], "并发创建合成课程", credits=3, request_id=token
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]

    assert results[0] == results[1]
    assert results[0]["id"] == str(token)
    assert results[0]["revision"] == 1
    assert service.list_courses(include_archived=True) == [results[0]]
    with db.transaction(service.db_path, write=False) as connection:
        assert connection.execute("SELECT count(*) FROM courses").fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM create_requests WHERE entity_kind = 'course'"
        ).fetchone()[0] == 1


def test_simultaneous_edits_with_same_revision_have_one_winner(service):
    original = course(service, teacher="原教师", remarks="不能丢失的合成备注")
    barrier = Barrier(2)

    def submit(teacher):
        independent_service = LearningService(service.db_path)
        barrier.wait(timeout=10)
        try:
            return independent_service.update_course(
                original["id"], original["revision"], teacher=teacher
            )
        except ConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(submit, teacher) for teacher in ("线程 A 教师", "线程 B 教师")
        ]
        results = [future.result(timeout=15) for future in futures]

    successful = [result for result in results if isinstance(result, dict)]
    conflicts = [result for result in results if isinstance(result, ConflictError)]
    assert len(successful) == len(conflicts) == 1
    current = service.get_course(original["id"])
    assert current == successful[0]
    assert current["revision"] == original["revision"] + 1
    assert current["teacher"] in {"线程 A 教师", "线程 B 教师"}
    assert current["remarks"] == original["remarks"]
    assert current["name"] == original["name"]
    assert current["created_at"] == original["created_at"]
