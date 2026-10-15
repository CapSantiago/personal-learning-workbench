"""M1 UI integration against isolated real SQLite files, never learning data."""
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import config, db
from plw.services import LearningService

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dataset(monkeypatch):
    path = PROJECT / ".sandbox" / "test-runs" / f"ui-{uuid4()}" / "plw.sqlite3"
    monkeypatch.setattr(config, "DEFAULT_DB_PATH", path)
    return path


def app():
    return AppTest.from_file(str(PROJECT / "app_m1.py"), default_timeout=20).run()


def button(page, label):
    return next(item for item in page.button if item.label == label)


def field(page, prefix, suffix):
    return next(item for item in page.text_input if item.key.startswith(prefix) and item.key.endswith(suffix))


def seeded(path, *, credits=3):
    db.initialize(path)
    service = LearningService(path)
    semester = service.create_semester("2026 秋季（合成）", request_id=str(uuid4()))
    course = service.create_course(semester["id"], "机器人学（合成）", teacher="测试教师", credits=credits, status="active", request_id=str(uuid4()))
    return service, semester, course


def test_first_visit_and_rerun_do_not_initialize(dataset):
    page = app()
    assert not page.exception
    assert not dataset.exists()
    page.run()
    assert not dataset.exists()
    button(page, "创建 M1 验收数据集").click().run()
    assert not page.exception
    assert dataset.exists()
    assert LearningService(dataset).list_semesters() == []


def test_create_semester_then_course_and_repeated_submit(dataset):
    db.initialize(dataset)
    page = app()
    page.radio(key="navigation").set_value("学期管理").run()
    next(x for x in page.text_input if x.label == "学期名称").set_value("2026 秋季（UI合成）")
    button(page, "创建学期").click().run()
    assert not page.exception
    service = LearningService(dataset)
    assert len(service.list_semesters()) == 1
    button(page, "创建学期").click().run()
    assert len(service.list_semesters()) == 1
    page.radio(key="navigation").set_value("课程工作台").run()
    field(page, "course_new_", "_name").set_value("控制原理（UI合成）")
    field(page, "course_new_", "_teacher").set_value("示例教师")
    button(page, "创建课程").click().run()
    assert not page.exception
    assert len(service.list_courses()) == 1
    button(page, "创建课程").click().run()
    page.run()
    assert not page.exception
    assert len(service.list_courses()) == 1


def test_stale_editor_preserves_unsaved_input_and_newer_record(dataset):
    service, _, course = seeded(dataset)
    page = app()
    assert not page.exception
    service.update_course(course["id"], course["revision"], teacher="另一标签页教师")
    field(page, "course_edit_", "_name").set_value("保留的未提交标题")
    button(page, "保存课程修改").click().run()
    assert not page.exception
    assert page.error
    assert field(page, "course_edit_", "_name").value == "保留的未提交标题"
    latest = service.get_course(course["id"])
    assert latest["teacher"] == "另一标签页教师"
    assert latest["name"] == course["name"]
    button(page, "放弃编辑并重新载入课程").click().run()
    assert field(page, "course_edit_", "_name").value == course["name"]
    assert field(page, "course_edit_", "_teacher").value == "另一标签页教师"


def test_course_archive_and_unarchive_keep_status_and_content(dataset):
    service, _, course = seeded(dataset)
    page = app()
    page.checkbox(key="course_include_archived").check().run()
    button(page, "归档课程").click().run()
    assert not page.exception
    assert service.list_courses() == []
    archived = service.get_course(course["id"])
    assert archived["status"] == "active"
    assert archived["archived_at"]
    assert len(service.list_courses(include_archived=True)) == 1
    button(page, "取消课程归档").click().run()
    assert not page.exception
    restored = service.get_course(course["id"])
    assert restored["archived_at"] is None
    assert restored["teacher"] == course["teacher"]
    assert restored["status"] == course["status"]


def test_edit_other_fields_does_not_convert_unknown_credits_to_zero(dataset):
    service, _, course = seeded(dataset, credits=None)
    page = app()
    assert not page.exception
    next(x for x in page.text_area if x.key.startswith("course_edit_")).set_value("只修改备注")
    button(page, "保存课程修改").click().run()
    assert not page.exception
    latest = service.get_course(course["id"])
    assert latest["credits"] is None
    assert latest["remarks"] == "只修改备注"


def test_future_database_shows_error_without_rewriting(dataset):
    seeded(dataset)
    with sqlite3.connect(dataset) as connection:
        connection.execute("PRAGMA user_version=999")
    before = dataset.read_bytes()
    page = app()
    assert not page.exception
    assert page.error
    assert dataset.read_bytes() == before
    button(page, "检查并应用受支持迁移").click().run()
    assert page.error
    assert dataset.read_bytes() == before


def test_duplicate_semester_names_have_distinct_labels(dataset):
    service, semester, _ = seeded(dataset)
    service.create_semester(semester["name"], request_id=str(uuid4()))
    page = app()
    page.radio(key="navigation").set_value("学期管理").run()
    labels = page.selectbox(key="semester_selected").options
    assert len(labels) == 2
    assert labels[0] != labels[1]
