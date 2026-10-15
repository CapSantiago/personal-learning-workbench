"""Course sorting and schema upgrades use isolated synthetic workspaces only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
from threading import Barrier
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import backups, db, storage, workspace
from plw.services import ArchivedError, ConflictError, LearningService, StorageError, ValidationError


def uid():
    return str(uuid4())


@pytest.fixture
def environment():
    root = storage.ROOTS[1] / ('course-order-' + uid())
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    semesters = [service.create_semester(name, request_id=uid()) for name in ('秋季', '春季')]
    rows = [service.create_course(semesters[index % 2]['id'], name, request_id=uid())
            for index, name in enumerate(('自动控制', '机器人学', '线性代数', '大学物理'))]
    return root, path, service, semesters, rows


def ids(service, **filters):
    return [row['id'] for row in service.list_courses(**filters)]


def payloads(service):
    return {row['id']: {key: value for key, value in row.items() if key != 'position'}
            for row in service.list_courses(include_archived=True)}


def assert_positions(service):
    assert [row['position'] for row in service.list_courses()] == list(range(len(service.list_courses())))


def test_created_courses_append_and_order_reads_do_not_write(environment):
    _, path, service, _, rows = environment
    before = storage.hash_file(path)
    assert ids(service) == [row['id'] for row in rows]
    assert ids(LearningService(path)) == ids(service)
    assert_positions(service)
    assert storage.hash_file(path) == before
    replayed = service.create_course(rows[0]['semester_id'], rows[0]['name'], request_id=rows[0]['id'])
    assert replayed['id'] == rows[0]['id']
    assert ids(service) == [row['id'] for row in rows]


def test_move_across_semesters_up_down_and_to_position_preserves_content(environment):
    _, path, service, semesters, rows = environment
    original = ids(service)
    content = payloads(service)
    service.move_course(rows[2]['id'], 1, expected_order=original)
    assert ids(service) == [original[2], original[0], original[1], original[3]]
    service.move_course(rows[2]['id'], 2, expected_order=ids(service))
    service.move_course(rows[2]['id'], 4, expected_order=ids(service))
    assert ids(LearningService(path)) == [original[0], original[1], original[3], original[2]]
    assert ids(service, semester_id=semesters[0]['id']) == [original[0], original[2]]
    assert ids(service, query='学') == [original[1], original[3]]
    assert payloads(service) == content
    assert_positions(service)


def test_course_edits_never_reorder_the_shelf(environment):
    _, _, service, semesters, rows = environment
    order = ids(service)
    service.update_course(rows[2]['id'], rows[2]['revision'], name='刚更新的名称', semester_id=semesters[1]['id'])
    assert ids(service) == order
    added = service.create_course(semesters[0]['id'], '新增课程', request_id=uid())
    assert ids(service) == order + [added['id']]


def test_archive_retains_course_and_restore_appends(environment):
    _, _, service, _, rows = environment
    archived = service.set_course_archived(rows[1]['id'], True, rows[1]['revision'])
    assert archived['position'] == rows[1]['position']
    assert ids(service) == [rows[i]['id'] for i in (0, 2, 3)]
    restored = service.set_course_archived(archived['id'], False, archived['revision'])
    assert ids(service) == [rows[i]['id'] for i in (0, 2, 3, 1)]
    assert restored['position'] == 3
    assert_positions(service)


def test_restoring_a_semester_appends_its_courses_as_an_ordered_group(environment):
    _, _, service, semesters, rows = environment
    archived = service.set_semester_archived(semesters[0]['id'], True, semesters[0]['revision'])
    assert ids(service) == [rows[i]['id'] for i in (1, 3)]
    service.set_semester_archived(archived['id'], False, archived['revision'])
    assert ids(service) == [rows[i]['id'] for i in (1, 3, 0, 2)]
    individually_hidden = service.set_course_archived(rows[2]['id'], True, rows[2]['revision'])
    current = service.get_semester(semesters[0]['id'])
    current = service.set_semester_archived(current['id'], True, current['revision'])
    service.set_semester_archived(current['id'], False, current['revision'])
    assert ids(service) == [rows[i]['id'] for i in (1, 3, 0)]
    assert service.get_course(rows[2]['id'])['archived_at'] == individually_hidden['archived_at']
    assert_positions(service)


@pytest.mark.parametrize('destination', [0, -1, True, 1.5, '2', None, 5])
def test_invalid_position_never_changes_order(environment, destination):
    _, _, service, _, rows = environment
    before = service.list_courses(include_archived=True)
    with pytest.raises(ValidationError):
        service.move_course(rows[0]['id'], destination, expected_order=ids(service))
    assert service.list_courses(include_archived=True) == before


@pytest.mark.parametrize('change', ['reordered', 'created', 'archived', 'semester_archived', 'filtered'])
def test_stale_or_filtered_order_is_rejected(environment, change):
    _, _, service, semesters, rows = environment
    stale = ids(service)
    if change == 'reordered':
        service.move_course(rows[3]['id'], 1, expected_order=stale)
    elif change == 'created':
        service.create_course(semesters[0]['id'], '另一窗口新课程', request_id=uid())
    elif change == 'archived':
        service.set_course_archived(rows[3]['id'], True, rows[3]['revision'])
    elif change == 'semester_archived':
        service.set_semester_archived(semesters[1]['id'], True, semesters[1]['revision'])
    else:
        stale = stale[:2]
    before = service.list_courses(include_archived=True)
    with pytest.raises(ConflictError):
        service.move_course(rows[0]['id'], 2, expected_order=stale)
    assert service.list_courses(include_archived=True) == before


def test_duplicate_expected_ids_and_archived_selection_are_rejected(environment):
    _, _, service, _, rows = environment
    order = ids(service)
    with pytest.raises(ValidationError):
        service.move_course(rows[0]['id'], 1, expected_order=order + order[:1])
    service.set_course_archived(rows[0]['id'], True, rows[0]['revision'])
    with pytest.raises(ArchivedError):
        service.move_course(rows[0]['id'], 1, expected_order=ids(service))


def test_sorting_failure_rolls_back_all_positions(environment, monkeypatch):
    _, _, service, _, rows = environment
    before = service.list_courses(include_archived=True)
    write = LearningService._write_course_positions
    def fail(connection, ordered):
        write(connection, ordered)
        raise sqlite3.OperationalError('synthetic failure after position writes')
    monkeypatch.setattr(LearningService, '_write_course_positions', staticmethod(fail))
    with pytest.raises(StorageError):
        service.move_course(rows[3]['id'], 1, expected_order=ids(service))
    assert service.list_courses(include_archived=True) == before


def test_concurrent_moves_cannot_overwrite_the_newer_order(environment):
    _, path, service, _, rows = environment
    expected = ids(service)
    barrier = Barrier(2)
    def move(index, destination):
        barrier.wait()
        try:
            LearningService(path).move_course(rows[index]['id'], destination, expected_order=expected)
            return 'moved'
        except ConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(move, 0, 4), pool.submit(move, 3, 1)]
        assert sorted(future.result() for future in futures) == ['conflict', 'moved']
    assert_positions(service)


def test_full_backup_and_restore_preserve_course_order(environment):
    root, path, service, _, rows = environment
    service.move_course(rows[2]['id'], 1, expected_order=ids(service))
    expected = service.list_courses(include_archived=True)
    report = backups.create_backup(path)
    backups.restore_backup(root, report['path'], confirmation=path.parent.name)
    restored = workspace.active_db(root)
    assert LearningService(restored).list_courses(include_archived=True) == expected


def legacy_workspace(monkeypatch):
    root = storage.ROOTS[1] / ('course-order-legacy-' + uid())
    load = db._load_migrations
    with monkeypatch.context() as patch:
        patch.setattr(db, '_load_migrations', lambda: load()[:2])
        workspace.initialize_workspace(root)
        path = workspace.active_db(root)
        semester = LearningService(path).create_semester('旧版学期', request_id=uid())
        with db.transaction(path) as connection:
            for name, stamp in [('C课程', '2026-10-01T00:00:00Z'), ('B课程', '2026-10-03T00:00:00Z'), ('A课程', '2026-10-03T00:00:00Z')]:
                connection.execute('INSERT INTO courses(id,semester_id,name,created_at,updated_at) VALUES(?,?,?,?,?)',
                                   (uid(), semester['id'], name, stamp, stamp))
        report = backups.create_backup(path)
    with closing(db.connect_snapshot(path)) as connection:
        before = [dict(row) for row in connection.execute('SELECT * FROM courses ORDER BY updated_at DESC,name COLLATE NOCASE,id')]
    return root, path, report, before


def test_schema2_backup_upgrades_only_restored_copy_preserving_existing_order(monkeypatch):
    root, old_db, report, before = legacy_workspace(monkeypatch)
    snapshot = Path(report['path']) / 'payload/plw.sqlite3'
    hashes = {file: storage.hash_file(file) for file in (old_db, snapshot)}
    assert backups.verify_backup(report['path'])['schema_version'] == 2
    backups.restore_backup(root, report['path'], confirmation=old_db.parent.name)
    restored = workspace.active_db(root)
    assert restored != old_db
    service = LearningService(restored)
    assert ids(service) == [row['id'] for row in before]
    assert [{key: value for key, value in row.items() if key not in ('position', 'semester_name', 'semester_archived_at')}
            for row in service.list_courses()] == before
    assert_positions(service)
    with db.transaction(restored, write=False) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == db._load_migrations()[-1].version
    assert {file: storage.hash_file(file) for file in hashes} == hashes
    backups.rollback_restore(root, confirmation=restored.parent.name)
    assert workspace.active_db(root) == old_db
    assert {file: storage.hash_file(file) for file in hashes} == hashes


def broken_migrations():
    # This historical test deliberately fails migration 003, even after 004 exists.
    migrations = db._load_migrations()[:3]
    sql = migrations[-1].sql + '\nSELECT * FROM synthetic_missing_table;\n'
    return (*migrations[:-1], replace(migrations[-1], sql=sql, checksum=hashlib.sha256(sql.encode()).hexdigest()))


def test_failed_schema3_migration_leaves_schema2_database_bytes_unchanged(monkeypatch):
    _, path, _, _ = legacy_workspace(monkeypatch)
    before = storage.hash_file(path)
    broken = broken_migrations()
    monkeypatch.setattr(db, '_load_migrations', lambda: broken)
    with pytest.raises(db.SchemaError, match='rolled back'):
        db.initialize(path)
    assert storage.hash_file(path) == before
    with closing(db.connect_snapshot(path)) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert 'position' not in [row[1] for row in connection.execute('PRAGMA table_info(courses)')]


def test_failed_migration_during_restore_keeps_active_pointer_and_input_unchanged(monkeypatch):
    root, path, report, _ = legacy_workspace(monkeypatch)
    snapshot = Path(report['path']) / 'payload/plw.sqlite3'
    pointer = root / 'control/active.json'
    hashes = {file: storage.hash_file(file) for file in (path, snapshot, pointer)}
    initialize = db._initialize
    broken = broken_migrations()
    def fail_only_upgrade(target):
        if Path(target).exists():
            with closing(db.connect_snapshot(target)) as connection:
                historical = connection.execute('PRAGMA user_version').fetchone()[0] == 2
            if historical:
                with monkeypatch.context() as patch:
                    patch.setattr(db, '_load_migrations', lambda: broken)
                    return initialize(target)
        return initialize(target)
    monkeypatch.setattr(db, '_initialize', fail_only_upgrade)
    with pytest.raises(backups.RestoreError, match='rolled back'):
        backups.restore_backup(root, report['path'], confirmation=path.parent.name)
    assert workspace.active_db(root) == path
    assert {file: storage.hash_file(file) for file in hashes} == hashes
    assert backups.recovery_status(root)['switch_state'] == 'old_active'


def test_sidebar_order_controls_persist_without_changing_selected_course(environment, monkeypatch):
    root, path, service, _, rows = environment
    monkeypatch.setenv('PLW_WORKSPACE', str(root))
    page = AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()
    page.button(key='nav_课程书架').click().run()
    chosen = rows[2]['id']
    page.button(key='shelf_course_' + chosen).click().run()
    page.button(key='course_order_up_' + chosen).click().run()
    assert not page.exception and not page.error
    assert ids(service) == [rows[i]['id'] for i in (0, 2, 1, 3)]
    assert page.session_state['_selected_course'] == chosen
    target = next(item for item in page.number_input if item.label == '课程移至第几门')
    target.set_value(4).run()
    page.button(key='course_order_move_' + chosen).click().run()
    assert not page.exception and not page.error
    assert ids(service) == [rows[i]['id'] for i in (0, 1, 3, 2)]
    assert [item.key.removeprefix('shelf_course_') for item in page.sidebar.button
            if item.key and item.key.startswith('shelf_course_')] == ids(service)
    assert page.button(key='course_order_down_' + chosen).disabled
    new_page = AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()
    new_page.button(key='nav_课程书架').click().run()
    assert [item.key.removeprefix('shelf_course_') for item in new_page.sidebar.button
            if item.key and item.key.startswith('shelf_course_')] == ids(LearningService(path))


def test_ui_rejects_a_move_from_an_outdated_rendered_course_list(environment, monkeypatch):
    root, _, service, _, rows = environment
    monkeypatch.setenv('PLW_WORKSPACE', str(root))
    page = AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()
    page.button(key='nav_课程书架').click().run()
    page.button(key='shelf_course_' + rows[1]['id']).click().run()
    service.move_course(rows[3]['id'], 1, expected_order=ids(service))
    expected = ids(service)
    page.button(key='course_order_up_' + rows[1]['id']).click().run()
    assert not page.exception and any('其他页面发生变化' in item.value for item in page.error)
    assert ids(service) == expected
