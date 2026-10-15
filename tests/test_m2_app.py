"""Explicit UI writes and restore confirmation against fresh synthetic workspaces."""
from pathlib import Path
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import config, workspace
from plw.materials import MaterialService
from plw.services import LearningService

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root(monkeypatch):
    root = PROJECT / '.sandbox' / 'test-runs' / f'm2-ui-{uuid4()}'
    monkeypatch.setattr(config, 'DEFAULT_WORKSPACE', root)
    return root


def app():
    return AppTest.from_file(str(PROJECT / 'app_m2.py'), default_timeout=30).run()


def button(page, label):
    return next(x for x in page.button if x.label == label)


def text(page, label):
    return next(x for x in page.text_input if x.label == label)


def seeded(root):
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    semester = service.create_semester('M2 UI 合成学期', request_id=str(uuid4()))
    course = service.create_course(semester['id'], '合成机器人学', request_id=str(uuid4()))
    return service, course


def test_read_and_rerun_do_not_create_workspace(root):
    page = app()
    assert not page.exception
    assert not root.exists()
    page.run()
    assert not root.exists()
    button(page, '创建 M2 合成工作区').click().run()
    assert not page.exception
    assert workspace.active_db(root).exists()
    assert LearningService(workspace.active_db(root)).list_semesters() == []


def test_managed_import_replay_and_hide_keep_source_and_body(root):
    seeded(root)
    page = app()
    page.radio(key='navigation').set_value('资料管理').run()
    button(page, '生成合成来源样例').click().run()
    source = root / 'sources' / '合成 控制原理.txt'
    original, mtime = source.read_bytes(), source.stat().st_mtime_ns
    button(page, '添加资料').click().run()
    assert not page.exception and not page.error
    button(page, '添加资料').click().run()
    service = MaterialService(workspace.active_db(root))
    rows = service.list_materials()
    assert len(rows) == 1
    target = workspace.active_db(root).parent / rows[0]['managed_relpath']
    button(page, '隐藏资料记录（保留文件）').click().run()
    assert not page.exception
    assert not service.list_materials()
    assert target.read_bytes() == original
    assert source.read_bytes() == original and source.stat().st_mtime_ns == mtime


def test_course_pages_show_success_in_m2_host(root):
    workspace.initialize_workspace(root)
    page = app()
    page.radio(key='navigation').set_value('学期管理').run()
    text(page, '学期名称').set_value('M2 表单成功提示')
    button(page, '创建学期').click().run()
    assert not page.exception
    assert any('学期已保存' in x.value for x in page.success)
    page.radio(key='navigation').set_value('课程工作台').run()
    text(page, '课程名称').set_value('M2 表单课程')
    button(page, '创建课程').click().run()
    assert not page.exception
    assert any('课程已保存' in x.value for x in page.success)


def test_import_error_keeps_path_input(root):
    seeded(root)
    page = app()
    page.radio(key='navigation').set_value('资料管理').run()
    missing = str(root / 'sources' / '缺失样例.txt')
    text(page, '来源文件路径').set_value(missing)
    button(page, '添加资料').click().run()
    assert not page.exception and page.error
    assert text(page, '来源文件路径').value == missing
    assert not MaterialService(workspace.active_db(root)).list_materials()


def test_backup_restore_confirmation_and_rollback_ui(root):
    service, course = seeded(root)
    old_path = workspace.active_db(root)
    page = app()
    page.radio(key='navigation').set_value('数据与备份').run()
    button(page, '创建完整备份').click().run()
    assert not page.exception and not page.error
    report = page.session_state['m2_backup_report']
    assert Path(report['path']).is_dir()
    updated = service.update_course(course['id'], course['revision'], name='备份后修改课程')
    button(page, '验证并预览备份').click().run()
    text(page, '输入当前数据集 ID 确认恢复').set_value('错误确认')
    button(page, '恢复并切换数据集').click().run()
    assert page.error and not page.exception
    assert workspace.active_db(root) == old_path
    text(page, '输入当前数据集 ID 确认恢复').set_value(old_path.parent.name)
    button(page, '恢复并切换数据集').click().run()
    assert not page.exception and not page.error
    new_path = workspace.active_db(root)
    assert new_path != old_path and old_path.exists()
    assert LearningService(new_path).get_course(course['id'])['name'] == course['name']
    page.radio(key='navigation').set_value('数据与备份').run()
    text(page, '输入当前数据集 ID 确认维护操作').set_value(new_path.parent.name)
    button(page, '保存当前副本并回滚').click().run()
    assert not page.exception and not page.error
    assert workspace.active_db(root) == old_path
    assert service.get_course(course['id'])['name'] == updated['name']


def test_corrupt_pointer_displays_error_without_reset(root):
    seeded(root)
    pointer = root / 'control' / 'active.json'
    pointer.write_text('[]', encoding='utf-8')
    before = pointer.read_bytes()
    page = app()
    assert page.error and not page.exception
    assert pointer.read_bytes() == before
    assert not any(x.label == '创建 M2 合成工作区' for x in page.button)
