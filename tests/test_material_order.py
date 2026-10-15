"""Courseware order uses isolated synthetic records and never real learning data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from plw import db
from plw.materials import (MaterialService, MaterialConflictError,
                           MaterialStorageError, MaterialValidationError)
from plw.services import LearningService


@pytest.fixture
def env():
    root = Path(__file__).resolve().parents[1] / '.sandbox/test-runs' / ('order-' + uuid4().hex)
    path = root / 'dataset/plw.sqlite3'
    db.initialize(path)
    (root / 'sources').mkdir()
    learning = LearningService(path)
    semester = learning.create_semester('合成排序学期', request_id=uuid4())
    course = learning.create_course(semester['id'], '合成课件排序课程', request_id=uuid4())
    service = MaterialService(path)
    rows = [service.import_upload(course['id'], filename, b'synthetic bytes', request_id=uuid4())
            for filename in ('第三讲.pdf', '第二讲.pptx', '概述.pdf', '第一讲.pdf')]
    return service, course, semester, learning, rows


def ids(service, course):
    return [row['id'] for row in service.list_courseware(course['id'])]


def assert_unique_positions(service, course):
    positions = sorted(row['position'] for row in service.list_materials(course['id']))
    assert positions == list(range(len(positions)))


def test_import_order_is_selection_order_and_persists_in_new_service(env):
    service, course, _, _, rows = env
    assert ids(MaterialService(service.db_path), course) == [row['id'] for row in rows]
    assert_unique_positions(service, course)


def test_move_up_down_and_to_final_position_persists(env):
    service, course, _, _, rows = env
    initial = ids(service, course)
    service.move_courseware(course['id'], rows[2]['id'], 1, expected_order=initial)
    assert ids(service, course) == [initial[2], initial[0], initial[1], initial[3]]
    service.move_courseware(course['id'], rows[2]['id'], 2, expected_order=ids(service, course))
    service.move_courseware(course['id'], rows[2]['id'], 4, expected_order=ids(service, course))
    assert ids(MaterialService(service.db_path), course) == [initial[0], initial[1], initial[3], initial[2]]
    assert_unique_positions(service, course)


def test_legacy_collisions_are_read_only_until_move_then_normalized(env):
    service, course, _, _, rows = env
    with db.transaction(service.db_path) as connection:
        connection.execute('UPDATE materials SET position=0')
    original = service.db_path.read_bytes()
    expected = [row['id'] for row in sorted(rows, key=lambda row: (row['name'], row['created_at'], row['id']))]
    assert ids(service, course) == expected
    assert service.db_path.read_bytes() == original
    service.move_courseware(course['id'], expected[-1], 1, expected_order=expected)
    assert ids(service, course) == [expected[-1], *expected[:-1]]
    assert_unique_positions(service, course)


def test_new_upload_and_path_import_append_after_manual_order(env):
    service, course, _, _, rows = env
    service.move_courseware(course['id'], rows[-1]['id'], 1, expected_order=ids(service, course))
    before = ids(service, course)
    upload = service.import_upload(course['id'], '000 不能插到前面.pdf', b'bytes', request_id=uuid4())
    source = service.root.parent / 'sources/合成 中文 资料.pdf'
    source.write_bytes(b'synthetic path-import bytes')
    path_import = service.import_file(course['id'], source, 'external_reference', request_id=uuid4())
    assert ids(service, course) == [*before, upload['id'], path_import['id']]
    assert_unique_positions(service, course)


def test_idempotent_import_retry_does_not_reset_position(env):
    service, course, _, _, _ = env
    token = uuid4()
    upload = service.import_upload(course['id'], '重复.pdf', b'bytes', request_id=token)
    service.move_courseware(course['id'], upload['id'], 1, expected_order=ids(service, course))
    before = ids(service, course)
    service.import_upload(course['id'], '重复.pdf', b'bytes', request_id=token)
    assert ids(service, course) == before


def test_hidden_file_excluded_and_restoration_appends(env):
    service, course, _, _, rows = env
    service.set_deleted(rows[1]['id'], True)
    before = ids(service, course)
    assert rows[1]['id'] not in before
    service.move_courseware(course['id'], before[-1], 1, expected_order=before)
    reordered = ids(service, course)
    service.set_deleted(rows[1]['id'], False)
    assert ids(service, course) == [*reordered, rows[1]['id']]
    assert_unique_positions(service, course)


def test_non_courseware_slot_is_preserved_during_move(env):
    service, course, _, _, _ = env
    source = service.root.parent / 'sources/合成实验.txt'
    source.write_bytes(b'synthetic text')
    other = service.import_file(course['id'], source, 'external_reference', request_id=uuid4())
    tail = service.import_upload(course['id'], '附录.pdf', b'bytes', request_id=uuid4())
    before = ids(service, course)
    service.move_courseware(course['id'], tail['id'], 1, expected_order=before)
    assert ids(service, course) == [tail['id'], *before[:-1]]
    assert service.get_material(other['id'])['position'] == other['position']
    assert_unique_positions(service, course)


def test_same_names_are_ordered_by_identity_without_changing_bytes(env):
    service, course, _, _, _ = env
    duplicate = [service.import_upload(course['id'], '同名.pdf', bytes([value]), request_id=uuid4())
                 for value in (1, 2)]
    before = {row['id']: hashlib.sha256((service.root / row['managed_relpath']).read_bytes()).hexdigest()
              for row in service.list_materials(course['id'])}
    service.move_courseware(course['id'], duplicate[1]['id'], 1, expected_order=ids(service, course))
    assert ids(service, course)[0] == duplicate[1]['id']
    after = {row['id']: hashlib.sha256((service.root / row['managed_relpath']).read_bytes()).hexdigest()
             for row in service.list_materials(course['id'])}
    assert before == after


@pytest.mark.parametrize('destination', [0, -1, 5, 1.5, True, '2', None])
def test_invalid_destination_leaves_all_positions_unchanged(env, destination):
    service, course, _, _, rows = env
    before = service.list_materials(course['id'])
    with pytest.raises(MaterialValidationError):
        service.move_courseware(course['id'], rows[-1]['id'], destination, expected_order=ids(service, course))
    assert service.list_materials(course['id']) == before


@pytest.mark.parametrize('change', ['reorder', 'import', 'hide'])
def test_stale_view_is_rejected_instead_of_overwriting_other_page(env, change):
    service, course, _, _, rows = env
    stale = ids(service, course)
    if change == 'reorder':
        service.move_courseware(course['id'], stale[-1], 1, expected_order=stale)
    elif change == 'import':
        service.import_upload(course['id'], '新课件.pdf', b'bytes', request_id=uuid4())
    else:
        service.set_deleted(rows[2]['id'], True)
    before = service.list_materials(course['id'], include_deleted=True)
    with pytest.raises(MaterialConflictError, match='刷新'):
        service.move_courseware(course['id'], rows[1]['id'], 1, expected_order=stale)
    assert service.list_materials(course['id'], include_deleted=True) == before


def test_partial_filtered_order_cannot_drop_unseen_courseware(env):
    service, course, _, _, rows = env
    with pytest.raises(MaterialConflictError, match='刷新'):
        service.move_courseware(course['id'], rows[-1]['id'], 1,
                                expected_order=[rows[0]['id'], rows[-1]['id']])
    assert ids(service, course) == [row['id'] for row in rows]


def test_cross_course_and_hidden_material_rejected(env):
    service, course, semester, learning, rows = env
    other = learning.create_course(semester['id'], '另一门课程', request_id=uuid4())
    other_file = service.import_upload(other['id'], '其他课程.pdf', b'bytes', request_id=uuid4())
    with pytest.raises(MaterialConflictError, match='当前课程'):
        service.move_courseware(course['id'], other_file['id'], 1, expected_order=ids(service, course))
    service.set_deleted(rows[1]['id'], True)
    with pytest.raises(MaterialConflictError, match='尚未移除'):
        service.move_courseware(course['id'], rows[1]['id'], 1, expected_order=ids(service, course))
    assert ids(service, other) == [other_file['id']]


@pytest.mark.parametrize('scope', ['course', 'semester'])
def test_archived_course_or_semester_cannot_reorder(env, scope):
    service, course, semester, learning, rows = env
    if scope == 'course':
        learning.set_course_archived(course['id'], True, course['revision'])
    else:
        learning.set_semester_archived(semester['id'], True, semester['revision'])
    with pytest.raises(MaterialConflictError, match='归档'):
        service.move_courseware(course['id'], rows[-1]['id'], 1, expected_order=ids(service, course))


def test_two_simultaneous_reorders_only_one_commits(env):
    service, course, _, _, rows = env
    original = ids(service, course)
    barrier = Barrier(2)
    def move(identity):
        barrier.wait()
        try:
            MaterialService(service.db_path).move_courseware(course['id'], identity, 1, expected_order=original)
            return 'saved'
        except MaterialConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, [rows[-1]['id'], rows[-2]['id']]))
    assert sorted(results) == ['conflict', 'saved']
    assert_unique_positions(service, course)


def test_partial_sql_failure_rolls_back_the_entire_order(env, monkeypatch):
    service, course, _, _, rows = env
    before = service.list_materials(course['id'])
    def fail(connection, reordered):
        connection.execute('UPDATE materials SET position=999 WHERE id=?', (reordered[0]['id'],))
        raise RuntimeError('synthetic interrupted update')
    monkeypatch.setattr(service, '_write_positions', fail)
    with pytest.raises(MaterialStorageError):
        service.move_courseware(course['id'], rows[-1]['id'], 1, expected_order=ids(service, course))
    assert service.list_materials(course['id']) == before


def bookshelf_app(service):
    from streamlit.testing.v1 import AppTest
    source = ('from pathlib import Path\nfrom plw.ui_workbench import bookshelf\n'
              f'bookshelf(Path({str(service.db_path)!r}))\n')
    return AppTest.from_string(source, default_timeout=30).run()


def test_ui_move_keeps_selected_file_and_updates_dropdown_order(env):
    service, course, _, _, rows = env
    page = bookshelf_app(service)
    page.selectbox(key='shelf_material').set_value(rows[-1]['id']).run()
    page.button(key='order_up_' + rows[-1]['id']).click().run()
    assert not page.exception and not page.error
    assert page.selectbox(key='shelf_material').value == rows[-1]['id']
    order = ids(service, course)
    assert order == [rows[0]['id'], rows[1]['id'], rows[3]['id'], rows[2]['id']]
    target = next(item for item in page.number_input if item.label == '移至第几份')
    assert target.value == 3
    target.set_value(1).run()
    page.button(key='order_move_' + rows[-1]['id']).click().run()
    assert not page.exception and not page.error
    assert ids(service, course)[0] == rows[-1]['id']
    assert page.button(key='order_up_' + rows[-1]['id']).disabled
    assert page.selectbox(key='shelf_material').options[0] == rows[-1]['name']


def test_ui_filtered_courseware_moves_in_complete_course_order(env):
    service, course, _, _, rows = env
    page = bookshelf_app(service)
    page.text_input(key='shelf_query').set_value('第三讲').run()
    assert len(page.selectbox(key='shelf_material').options) == 1
    assert not page.button(key='order_down_' + rows[0]['id']).disabled
    page.button(key='order_down_' + rows[0]['id']).click().run()
    assert not page.exception and not page.error
    assert ids(service, course) == [rows[1]['id'], rows[0]['id'], rows[2]['id'], rows[3]['id']]
    assert page.selectbox(key='shelf_material').value == rows[0]['id']
