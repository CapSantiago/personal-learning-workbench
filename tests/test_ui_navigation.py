"""Navigation checks use synthetic datasets and never load real learning files."""
import shutil
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import storage, ui_workbench, workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench


FIXTURES = storage.PROJECT_ROOT / '.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources'


def uid():
    return str(uuid4())


@pytest.fixture
def root(monkeypatch):
    path = storage.ROOTS[1] / ('navigation-ui-' + uid())
    monkeypatch.setenv('PLW_WORKSPACE', str(path))
    # The actual browser suite covers the PDF component. Here record which
    # immutable edition the UI hands it, without launching a reader server.
    monkeypatch.setattr(ui_workbench, 'read_edition',
                        lambda path, edition: ui_workbench.st.caption('test edition: ' + edition['id']))
    return path


def app():
    return AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()


def button(page, label):
    return next(x for x in page.button if x.label == label)


def navigate(page, label):
    if label == '课程书架':
        open_shelf(page)
        choices = [item for item in page.button if item.key and item.key.startswith('shelf_course_')]
        if choices:
            preferred = page.session_state.get('_selected_course')
            selected = next((item for item in choices if item.key == 'shelf_course_' + str(preferred)), choices[0])
            selected.click().run()
    else:
        page.button(key='nav_' + label).click().run()
    assert not page.exception and not page.error


def open_shelf(page):
    if not page.session_state.get('_shelf_nav_open', False):
        previous = page.session_state.get('navigation', '今日学习')
        page.button(key='nav_课程书架').click().run()
        assert page.session_state.get('navigation', '今日学习') == previous
    assert page.session_state['_shelf_nav_open']
    assert not page.exception and not page.error


def select_course(page, course):
    open_shelf(page)
    page.button(key='shelf_course_' + course['id']).click().run()
    assert page.session_state['navigation'] == '课程书架'
    assert page.session_state['_selected_course'] == course['id']
    assert any(item.value == course['name'] for item in page.header)
    assert not any(item.key == 'active_course' for item in page.selectbox)
    assert not page.exception and not page.error


def seed(root):
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    semester = service.create_semester('导航合成学期', request_id=uid())
    courses = [service.create_course(semester['id'], title, request_id=uid())
               for title in ('自动控制', '机器人学')]
    return path, courses


def editions(root, path, course_id):
    source = root / 'sources/导航 中文课件.pdf'
    source.parent.mkdir(exist_ok=True)
    shutil.copyfile(FIXTURES / '原生 PDF 中文课件.pdf', source)
    material = MaterialService(path).import_file(course_id, source, 'external_reference', request_id=uid())
    workbench = Workbench(path)
    first = workbench.create_edition(material['id'], uid(), local_copy_confirmed=True)
    source.write_bytes(source.read_bytes() + b'\n% synthetic newer edition\n')
    second = workbench.create_edition(material['id'], uid(), local_copy_confirmed=True)
    # An older edition is the most recently read one. Navigation must not
    # replace it with the newest edition and thus show the wrong annotations.
    workbench.reader_action(dict(id=uid(), run=path.parent.name, doc=first,
                                page=2, base_revision=0, kind='position'))
    return material, first, second


def test_empty_home_leads_to_missing_onboarding_step(root):
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    page = app()
    button(page, '创建第一个学期').click().run()
    assert page.session_state['navigation'] == '学期管理'
    assert not page.exception and not page.error
    LearningService(path).create_semester('已有学期', request_id=uid())
    navigate(page, '今日学习')
    button(page, '添加第一门课程').click().run()
    assert page.session_state['navigation'] == '课程管理'
    assert not page.exception and not page.error


def test_empty_bookshelf_has_a_working_course_creation_action(root):
    workspace.initialize_workspace(root)
    page = app()
    navigate(page, '课程书架')
    button(page, '先创建学期').click().run()
    assert page.session_state['navigation'] == '学期管理'
    assert not page.exception and not page.error


def test_course_context_survives_widget_cleanup_between_pages(root):
    path, courses = seed(root)
    target = courses[1]['id']
    chapter = Workbench(path).save_chapter(target, '仅机器人课程的章节', [], uid())
    page = app()
    navigate(page, '任务管理')
    page.selectbox(key='active_course').set_value(target).run()
    for destination in ('笔记', '章节与知识点', '今日学习', '使用说明', '课程书架', '任务管理'):
        navigate(page, destination)
        if destination == '课程书架':
            assert page.session_state['_selected_course'] == target
            assert any(item.value == courses[1]['name'] for item in page.header)
            assert not any(item.key == 'active_course' for item in page.selectbox)
        elif destination not in ('今日学习', '使用说明'):
            assert page.selectbox(key='active_course').value == target
    assert page.session_state['_selected_course'] == target
    # The bookshelf has its own course menu, while task/note pickers keep the
    # shared course context after the bookshelf's widgets have been removed.
    select_course(page, courses[1])
    page.text_input(key='shelf_query').set_value('旧课程筛选').run()
    page.selectbox(key='shelf_chapter').set_value(chapter).run()
    select_course(page, courses[0])
    assert page.text_input(key='shelf_query').value == ''
    assert page.selectbox(key='shelf_chapter').value is None
    page.button(key='nav_课程书架').click().run()
    assert not page.session_state['_shelf_nav_open']
    assert not any(item.key and item.key.startswith('shelf_course_') for item in page.button)
    assert page.session_state['_selected_course'] == courses[0]['id']
    assert any(item.value == courses[0]['name'] for item in page.header)
    open_shelf(page)
    assert page.button(key='shelf_course_' + courses[0]['id'])
    navigate(page, '任务管理')
    assert page.selectbox(key='active_course').value == courses[0]['id']


def test_home_course_action_opens_that_course(root):
    _, courses = seed(root)
    page = app()
    page.button(key='home_course_' + courses[1]['id']).click().run()
    assert page.session_state['navigation'] == '课程书架'
    assert page.session_state['_selected_course'] == courses[1]['id']
    assert any(item.value == courses[1]['name'] for item in page.header)
    assert not any(item.key == 'active_course' for item in page.selectbox)
    assert not page.exception and not page.error


def test_resume_keeps_old_edition_and_clears_stale_filters(root):
    path, courses = seed(root)
    material, first, second = editions(root, path, courses[1]['id'])
    chapter = Workbench(path).save_chapter(courses[1]['id'], '空章节', [], uid())
    page = app()
    # These values simulate a prior bookshelf filter left in the session.
    page.session_state['shelf_query'] = '不匹配的历史筛选'
    page.session_state['shelf_chapter'] = chapter
    page.session_state['shelf_edition'] = second
    page.button(key='resume_' + first).click().run()
    assert not page.exception and not page.error
    assert page.session_state['_selected_course'] == courses[1]['id']
    assert any(item.value == courses[1]['name'] for item in page.header)
    assert page.selectbox(key='shelf_material').value == material['id']
    assert page.selectbox(key='shelf_edition').value == first
    assert page.text_input(key='shelf_query').value == ''
    assert page.selectbox(key='shelf_chapter').value is None
    assert any(c.value == 'test edition: ' + first for c in page.caption)
    # Merely opening the target must not create a new edition or update progress.
    assert len(Workbench(path).rows('reading_editions')) == 2
    assert Workbench(path).edition_state(first)['page'] == 2


@pytest.mark.parametrize('unavailable', ['hidden', 'archived'])
def test_unavailable_courseware_is_not_offered_for_resume(root, unavailable):
    path, courses = seed(root)
    material, first, second = editions(root, path, courses[1]['id'])
    if unavailable == 'hidden':
        MaterialService(path).set_deleted(material['id'], True)
    else:
        LearningService(path).set_course_archived(courses[1]['id'], True, courses[1]['revision'])
    page = app()
    assert not page.exception and not page.error
    keys = {item.key for item in page.button}
    assert 'resume_' + first not in keys and 'resume_' + second not in keys


def test_stale_course_and_reading_target_fall_back_without_error(root):
    path, courses = seed(root)
    material, first, second = editions(root, path, courses[0]['id'])
    page = app()
    page.session_state['_selected_course'] = uid()
    page.session_state['active_course'] = uid()
    page.session_state['_shelf_target'] = {'material': uid(), 'edition': uid()}
    # Restore an outdated bookshelf route directly: choosing a sidebar course
    # would replace the stale ID before the application's fallback sees it.
    page.session_state['navigation'] = '课程书架'
    page.run()
    assert not page.exception and not page.error
    assert page.session_state['_selected_course'] in {row['id'] for row in courses}
    assert any(item.value in {row['name'] for row in courses} for item in page.header)
    # Select the course with valid courseware to exercise the stale edition too.
    select_course(page, courses[0])
    assert not page.exception and not page.error
    assert page.selectbox(key='shelf_material').value == material['id']
    assert page.selectbox(key='shelf_edition').value in (first, second)


def test_first_page_bookmark_offers_resume_without_a_page_turn(root):
    path, courses = seed(root)
    material, read_edition, marked_edition = editions(root, path, courses[0]['id'])
    workbench = Workbench(path)
    source = root / 'sources/导航 中文课件.pdf'
    source.write_bytes(source.read_bytes() + b'\n% synthetic unread edition\n')
    unread_edition = workbench.create_edition(material['id'], uid(), local_copy_confirmed=True)
    state = workbench.edition_state(marked_edition)
    assert state['page'] == 1 and state['revision'] == 0

    page = app()
    resume_keys = [item.key for item in page.button if item.key and item.key.startswith('resume_')]
    assert resume_keys == ['resume_' + read_edition]

    mark_id = uid()
    workbench.save_annotation(marked_edition, 1, 'bookmark', '第一页：下次从这里复习', mark_id)
    page.run()
    assert not page.exception and not page.error
    resume_keys = [item.key for item in page.button if item.key and item.key.startswith('resume_')]
    assert resume_keys[0] == 'resume_' + marked_edition
    assert 'resume_' + unread_edition not in resume_keys
    # A text bookmark must make the edition discoverable without inventing
    # a page-turn action or advancing the saved reader revision.
    state = workbench.edition_state(marked_edition)
    assert state['page'] == 1 and state['revision'] == 0
    page.button(key='resume_' + marked_edition).click().run()
    assert page.selectbox(key='shelf_edition').value == marked_edition
    assert any(c.value == 'test edition: ' + marked_edition for c in page.caption)

    # Removed annotations do not keep otherwise unread editions in recents.
    workbench.save_annotation(marked_edition, 1, 'bookmark', '第一页：下次从这里复习', uid(),
                              identity=mark_id, revision=1, deleted=True)
    navigate(page, '今日学习')
    resume_keys = {item.key for item in page.button}
    assert 'resume_' + marked_edition not in resume_keys
    assert 'resume_' + unread_edition not in resume_keys


def test_removing_last_courseware_can_be_undone_with_files_and_reading_data_intact(root):
    path, courses = seed(root)
    material, first, second = editions(root, path, courses[0]['id'])
    workbench = Workbench(path)
    workbench.save_annotation(first, 2, 'bookmark', '移除后仍应保留的书签', uid())
    source = root / 'sources/导航 中文课件.pdf'
    original_hash = storage.hash_file(source)
    editions_before = workbench.rows('reading_editions')
    reading_hashes = {row['id']: storage.hash_file(path.parent / row['pdf_relpath']) for row in editions_before}
    progress_before = {identity: workbench.edition_state(identity) for identity in (first, second)}
    annotations_before = workbench.rows('annotations')
    page = app()
    page.button(key='resume_' + first).click().run()
    assert not page.exception and not page.error
    page.button(key='remove_courseware_' + material['id']).click().run()
    assert not page.exception and not page.error
    service = MaterialService(path)
    assert service.get_material(material['id'])['deleted_at'] is not None
    assert service.list_courseware(courses[0]['id']) == []
    assert not any(item.key == 'shelf_material' for item in page.selectbox)
    assert page.button(key='undo_remove_' + material['id'])
    assert storage.hash_file(source) == original_hash
    assert workbench.rows('reading_editions') == editions_before
    assert workbench.rows('annotations') == annotations_before
    assert {identity: workbench.edition_state(identity) for identity in (first, second)} == progress_before
    navigate(page, '今日学习')
    assert 'resume_' + first not in {item.key for item in page.button}
    select_course(page, courses[0])
    page.button(key='undo_remove_' + material['id']).click().run()
    assert not page.exception and not page.error
    assert service.get_material(material['id'])['deleted_at'] is None
    assert page.selectbox(key='shelf_material').value == material['id']
    assert storage.hash_file(source) == original_hash
    assert workbench.rows('reading_editions') == editions_before
    assert workbench.rows('annotations') == annotations_before
    assert {identity: workbench.edition_state(identity) for identity in (first, second)} == progress_before
    assert {row['id']: storage.hash_file(path.parent / row['pdf_relpath']) for row in editions_before} == reading_hashes
    assert not any(item.key == 'undo_remove_' + material['id'] for item in page.button)

def test_home_lists_all_active_courses_and_last_one_opens_its_shelf(root):
    path,courses=seed(root);service=LearningService(path)
    for title in ('机器人视觉','电机控制','人工智能','离散数学','自动控制原理'):
        courses.append(service.create_course(courses[0]['semester_id'],title,request_id=uid()))
    archived=service.create_course(courses[0]['semester_id'],'归档课程',request_id=uid())
    service.set_course_archived(archived['id'],True,archived['revision'])
    page=app()
    buttons=[item for item in page.button if item.key and item.key.startswith('home_course_')]
    assert [item.key.removeprefix('home_course_') for item in buttons]==[row['id'] for row in courses]
    page.button(key='home_course_'+courses[-1]['id']).click().run()
    assert page.session_state['navigation']=='课程书架' and page.session_state['_selected_course']==courses[-1]['id']
    assert not page.exception and not page.error
