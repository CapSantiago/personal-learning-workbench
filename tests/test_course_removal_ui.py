"""Recoverable course removal never deletes learning content or filesystem data."""
import shutil
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import db, storage, ui_workbench, workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench


FIXTURES = storage.PROJECT_ROOT / '.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources'


def uid():
    return str(uuid4())


@pytest.fixture
def environment(monkeypatch):
    root = storage.ROOTS[1] / ('course-removal-ui-' + uid())
    monkeypatch.setenv('PLW_WORKSPACE', str(root))
    monkeypatch.setattr(ui_workbench, 'read_edition',
                        lambda path, edition: ui_workbench.st.caption('test edition: ' + edition['id']))
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    semester = service.create_semester('移除课程合成学期', request_id=uid())
    course = service.create_course(semester['id'], '保留所有学习内容', status='active', request_id=uid())
    return root, path, service, semester, course


def app(course_id):
    page = AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()
    page.button(key='nav_课程书架').click().run()
    page.button(key='shelf_course_' + course_id).click().run()
    assert not page.exception and not page.error
    return page


def seed_content(root, path, course):
    source = root / 'sources/保留原件 中文课件.pdf'
    source.parent.mkdir()
    shutil.copyfile(FIXTURES / '原生 PDF 中文课件.pdf', source)
    material = MaterialService(path).import_file(course['id'], source, 'managed_copy', request_id=uid())
    w = Workbench(path)
    edition = w.create_edition(material['id'], uid(), local_copy_confirmed=True)
    w.reader_action(dict(id=uid(), run=path.parent.name, doc=edition, page=2, base_revision=0, kind='position'))
    w.save_annotation(edition, 2, 'bookmark', '课程恢复后仍然保留的标记', uid())
    values = dict(title='保留任务', task_type='assignment', due_kind='date', due_date='2026-10-20',
                  due_at_utc=None, due_timezone=None, planned_date='2026-10-19', priority='high',
                  status='todo', estimated_minutes=30, actual_minutes=5, remarks='不可清除')
    w.save_task(course['id'], values, [material['id']], uid())
    chapter = w.save_chapter(course['id'], '保留章节', [material['id']], uid())
    w.save_note(course['id'], '保留笔记', '正文 $x^2$ 与历史版本', chapter, [material['id']], uid())
    w.save_knowledge(course['id'], chapter, '保留知识点', 'learning', '', uid())
    files = [source, path.parent / material['managed_relpath']]
    files.extend(path.parent / item['pdf_relpath'] for item in w.rows('reading_editions'))
    files.extend((path.parent / 'notes').rglob('*.md'))
    return material, edition, {file: storage.hash_file(file) for file in files}


def content_rows(path):
    tables = ('materials', 'tasks', 'chapters', 'knowledge_points', 'notes', 'note_revisions',
              'reading_editions', 'edition_pages', 'reading_progress', 'annotations',
              'task_materials', 'note_materials', 'chapter_materials')
    with db.transaction(path, write=False) as connection:
        return {table: sorted(tuple(row) for row in connection.execute('SELECT * FROM ' + table))
                for table in tables}


def test_remove_last_course_then_undo_preserves_content_files_and_reading(environment):
    root, path, service, _, course = environment
    material, edition, hashes = seed_content(root, path, course)
    before = content_rows(path)
    page = app(course['id'])
    assert service.get_course(course['id'])['archived_at'] is None
    page.button(key='remove_shelf_course_' + course['id']).click().run()
    assert not page.exception and not page.error
    removed = service.get_course(course['id'])
    assert removed['archived_at'] and removed['status'] == 'active'
    assert service.list_courses() == []
    assert not any(item.key == 'shelf_course_' + course['id'] for item in page.button)
    assert any(item.value == '课程书架' for item in page.header)
    assert page.button(key='undo_course_removal_' + course['id'])
    assert content_rows(path) == before
    assert {file: storage.hash_file(file) for file in hashes} == hashes
    page.button(key='undo_course_removal_' + course['id']).click().run()
    assert not page.exception and not page.error
    restored = service.get_course(course['id'])
    assert restored['archived_at'] is None and restored['status'] == 'active'
    assert page.session_state['_selected_course'] == course['id']
    assert any(item.value == course['name'] for item in page.header)
    assert page.selectbox(key='shelf_material').value == material['id']
    assert Workbench(path).edition_state(edition)['page'] == 2
    assert content_rows(path) == before
    assert {file: storage.hash_file(file) for file in hashes} == hashes
    assert not any(item.key == 'undo_course_removal_' + course['id'] for item in page.button)


def test_stale_removal_confirmation_does_not_archive_a_newer_course(environment):
    _, _, service, _, course = environment
    page = app(course['id'])
    changed = service.update_course(course['id'], course['revision'], teacher='另一窗口保存的教师')
    page.button(key='remove_shelf_course_' + course['id']).click().run()
    assert not page.exception
    assert any('已被其他操作更新' in item.value for item in page.error)
    assert service.get_course(course['id']) == changed
    assert not any(item.key == 'undo_course_removal_' + course['id'] for item in page.button)


def test_undo_does_not_restore_a_newer_rearchived_course(environment):
    _, _, service, _, course = environment
    page = app(course['id'])
    page.button(key='remove_shelf_course_' + course['id']).click().run()
    archived = service.get_course(course['id'])
    restored = service.set_course_archived(course['id'], False, archived['revision'])
    changed = service.update_course(course['id'], restored['revision'], remarks='恢复期间已修改')
    rearchived = service.set_course_archived(course['id'], True, changed['revision'])
    page.button(key='undo_course_removal_' + course['id']).click().run()
    assert not page.exception
    assert any('已被其他操作更新' in item.value for item in page.error)
    assert service.get_course(course['id']) == rearchived


def test_undo_never_automatically_unarchives_the_parent_semester(environment):
    _, _, service, semester, course = environment
    page = app(course['id'])
    page.button(key='remove_shelf_course_' + course['id']).click().run()
    archived = service.get_course(course['id'])
    parent = service.set_semester_archived(semester['id'], True, semester['revision'])
    # Submit the previously rendered undo control, before its disabled state
    # can refresh: the service must still reject a newly archived parent.
    page.button(key='undo_course_removal_' + course['id']).click().run()
    assert not page.exception
    assert any('所属学期已归档' in item.value for item in page.error)
    assert service.get_semester(semester['id']) == parent
    current = service.get_course(course['id'])
    assert current['archived_at'] == archived['archived_at'] and current['revision'] == archived['revision']
    assert page.button(key='undo_course_removal_' + course['id']).disabled
