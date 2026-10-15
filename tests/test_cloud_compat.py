"""Windows synthetic coverage for cloud preparation; these are NOT Linux container tests."""
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
import zipfile

import pytest
from starlette.applications import Starlette

from plw import backup_transfer, backups, db, storage, workspace
from plw.materials import MaterialService
from plw.services import LearningService
from plw.workbench import Workbench
from plw.private_auth import PrivateAccess, password_hash
from test_private_auth import fetch, login, PASSWORD, ORIGIN


def uid():
    return str(uuid4())


@pytest.fixture
def sample():
    root = storage.ROOTS[1] / ('cloud-compat-' + uid())
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    term = service.create_semester('合成学期', request_id=uid())
    course = service.create_course(term['id'], '合成机器人课程', request_id=uid())
    material = MaterialService(path).import_upload(course['id'], '中文 课件.pdf', b'%PDF-synthetic', request_id=uid())
    w = Workbench(path)
    note = w.save_note(course['id'], '合成笔记', '$x^2$', None, [material['id']], uid())
    return root, path, course, material, note


def test_backup_zip_restores_in_an_independent_workspace(sample):
    root, path, course, material, note = sample
    before = storage.hash_file(path)
    report = backup_transfer.pack_backup(backups.create_backup(path)['path'])
    assert storage.hash_file(path) == before
    verified = backup_transfer.unpack_backup(report['archive_path'], root / 'received')
    assert verified['manifest_sha256'] == report['manifest_sha256']
    target = storage.ROOTS[1] / ('cloud-rehearsal-' + uid())
    target.mkdir()
    backups.restore_backup(target, verified['path'], confirmation='EMPTY')
    restored = workspace.active_db(target)
    assert Workbench(restored).note_body(note) == '$x^2$'
    assert (restored.parent / material['managed_relpath']).read_bytes() == b'%PDF-synthetic'
    assert workspace.active_db(root) == path and storage.hash_file(path) == before
    assert backup_transfer.unpack_backup(report['archive_path'], root / 'received')['complete']


def test_v3_to_v4_preserves_rows_and_foreign_keys(sample, monkeypatch):
    _, source, *_ = sample
    root = storage.ROOTS[1] / ('cloud-v3-' + uid())
    real = db._load_migrations
    with monkeypatch.context() as patch:
        patch.setattr(db, '_load_migrations', lambda: real()[:3])
        workspace.initialize_workspace(root)
        path = workspace.active_db(root)
        s = LearningService(path)
        term = s.create_semester('v3 合成', request_id=uid())
        course = s.create_course(term['id'], '运动学', request_id=uid())
        m = MaterialService(path).import_upload(course['id'], 'v3.pdf', b'%PDF-fake', request_id=uid())
        note = Workbench(path).save_note(course['id'], '保留关联', '内容', None, [m['id']], uid())
        report = backups.create_backup(path)
    snapshot = Path(report['path']) / 'payload/plw.sqlite3'
    fingerprint = storage.hash_file(path)
    backups.restore_backup(root, report['path'], confirmation=path.parent.name)
    new = workspace.active_db(root)
    assert storage.hash_file(path) == fingerprint
    assert Workbench(new).note_body(note) == '内容'
    with closing(db.connect(new)) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 4
        assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
        assert c.execute('SELECT material_id FROM note_materials').fetchone()[0] == m['id']
    assert backups.verify_backup(report['path'])['schema_version'] == 3
    backups.rollback_restore(root, confirmation=new.parent.name)
    assert workspace.active_db(root) == path


def test_posix_source_metadata_and_old_windows_metadata_both_valid(sample):
    _, path, _, material, _ = sample
    original = material['original_path']
    with db.transaction(path) as c:
        c.execute('UPDATE materials SET original_path=? WHERE id=?', ('/var/lib/plw/data/上传.pdf', material['id']))
        assert c.execute('SELECT count(*) FROM materials').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('UPDATE materials SET original_path=? WHERE id=?', ('relative.pdf', material['id']))
    assert MaterialService(path).check_material(material['id'])['file_status'] == 'normal'
    with db.transaction(path) as c:
        c.execute('UPDATE materials SET original_path=? WHERE id=?', (original, material['id']))


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'payload/../escape', 'payload/CON', 'payload/a:stream'])
def test_untrusted_archive_paths_rejected_before_extract(sample, name):
    root, *_ = sample
    archive = root / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'x') as z:
        z.writestr(name, b'synthetic')
    with pytest.raises((ValueError, backups.BackupError)):
        backup_transfer.unpack_backup(archive, root / 'unpacked')
    assert not (root / 'unpacked').exists()


def test_corrupted_zip_payload_never_switches_dataset(sample):
    root, path, *_ = sample
    report = backup_transfer.pack_backup(backups.create_backup(path)['path'])
    bad = root / 'corrupt.zip'
    with zipfile.ZipFile(report['archive_path']) as old, zipfile.ZipFile(bad, 'x') as new:
        for entry in old.infolist():
            data = old.read(entry)
            new.writestr(entry.filename, b'corrupt' if entry.filename.endswith('plw.sqlite3') else data)
    with pytest.raises(backups.VerificationError):
        backup_transfer.unpack_backup(bad, root / 'corrupt-extract')
    assert workspace.active_db(root) == path


def test_backup_download_requires_login_and_refuses_tampering(sample):
    _, path, *_ = sample
    report = backup_transfer.pack_backup(backups.create_backup(path)['path'])
    url = backup_transfer.register_download(report)
    app = PrivateAccess(Starlette(routes=backup_transfer.routes()), username='student',
                        password_digest=password_hash(PASSWORD), origin=ORIGIN)
    async def scenario():
        assert (await fetch(app, url))[0] == 401
        status, cookie, _ = await login(app)
        assert status == 303
        status, headers, body = await fetch(app, url, cookie=cookie)
        assert status == 200 and b'no-store' in headers[b'cache-control']
        assert hashlib.sha256(body).hexdigest() == report['archive_sha256']
        with Path(report['archive_path']).open('ab') as f:
            f.write(b'changed')
        assert (await fetch(app, url, cookie=cookie))[0] == 409
    asyncio.run(scenario())


def test_failed_v4_rebuild_rolls_back_all_rows_and_ddl(monkeypatch):
    from dataclasses import replace
    root = storage.ROOTS[1] / ('failed-v4-' + uid())
    real = db._load_migrations()
    with monkeypatch.context() as patch:
        patch.setattr(db, '_load_migrations', lambda: real[:3])
        workspace.initialize_workspace(root)
        path = workspace.active_db(root)
        s = LearningService(path)
        term = s.create_semester('合成旧版', request_id=uid())
        course = s.create_course(term['id'], '机器人', request_id=uid())
        m = MaterialService(path).import_upload(course['id'], 'old.pdf', b'%PDF-fake', request_id=uid())
        note = Workbench(path).save_note(course['id'], '关联不能丢失', '内容', None, [m['id']], uid())
    before = storage.hash_file(path)
    sql = real[-1].sql + '\nSELECT * FROM deliberately_missing;'
    broken = (*real[:-1], replace(real[-1], sql=sql, checksum=hashlib.sha256(sql.encode()).hexdigest()))
    monkeypatch.setattr(db, '_load_migrations', lambda: broken)
    with pytest.raises(db.SchemaError, match='rolled back'):
        db.initialize(path)
    assert storage.hash_file(path) == before
    with closing(db.connect_snapshot(path)) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 3
        assert c.execute('SELECT material_id FROM note_materials WHERE note_id=?', (note,)).fetchone()[0] == m['id']
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


def test_internal_health_never_reveals_paths_or_bypasses_other_routes():
    app = PrivateAccess(Starlette(), username='student', password_digest=password_hash(PASSWORD),
                        origin=ORIGIN, health_check=lambda: {'ok': True, 'version': db.APP_VERSION})
    async def probe(host, client, path='/plw-health'):
        sent = []
        scope = dict(type='http', asgi={'version':'3.0'}, http_version='1.1', scheme='http',
                     path=path, method='GET', headers=[(b'host',host.encode())],
                     query_string=b'', client=(client,1234), server=('127.0.0.1',8501))
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        async def send(message):sent.append(message)
        await app(scope, receive, send)
        return sent[0]['status'], b''.join(m.get('body', b'') for m in sent)
    async def scenario():
        status, body = await probe('127.0.0.1:8501', '127.0.0.1')
        assert status == 200 and json.loads(body)['ok'] and b'path' not in body
        assert (await probe('127.0.0.1:8501','203.0.113.7'))[0] == 403
        assert (await probe('study.example.test','127.0.0.1'))[0] == 403
        assert (await probe('127.0.0.1:8501','127.0.0.1','/plw-reader/secret'))[0] == 403
    asyncio.run(scenario())


def test_existing_windows_v3_can_open_without_auto_migration(monkeypatch):
    import os
    from streamlit.testing.v1 import AppTest
    if os.name != 'nt':
        pytest.skip('Windows local v3 compatibility only')
    root = storage.ROOTS[1] / ('windows-local-v3-' + uid())
    real = db._load_migrations()
    with monkeypatch.context() as patch:
        patch.setattr(db, '_load_migrations', lambda: real[:3])
        workspace.initialize_workspace(root)
        path = workspace.active_db(root)
        service = LearningService(path)
        term = service.create_semester('合成本地旧学期', request_id=uid())
        service.create_course(term['id'], '本地机器人', request_id=uid())
    before = storage.hash_file(path)
    monkeypatch.setenv('PLW_WORKSPACE', str(root))
    monkeypatch.delenv('PLW_PRIVATE_SITE', raising=False)
    page = AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()
    assert not page.exception and not page.error
    assert any(h.value == '今日学习' for h in page.header)
    assert not any(b.label == '备份并升级学习库' for b in page.button)
    assert storage.hash_file(path) == before
