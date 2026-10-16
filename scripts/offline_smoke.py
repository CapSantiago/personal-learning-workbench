"""Synthetic deployment acceptance; never opens the real learning workspace.

Run seed and check in separate containers with the same isolated test mount.
The resulting receipt is evidence for persistence, not a production backup.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['seed', 'check'])
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    receipt = Path(args.receipt)
    scope = PROJECT / '.sandbox/test-runs'
    if not receipt.is_absolute() or not receipt.is_relative_to(scope) or '..' in receipt.parts:
        raise ValueError('Only an isolated project test-runs receipt is permitted')
    if any(p.is_symlink() or p.is_junction() for p in (receipt, *receipt.parents)):
        raise ValueError('Linked test paths are not permitted')
    if args.action == 'seed' and receipt.exists():
        raise ValueError('Use a new receipt; existing tests are never overwritten')
    if args.action == 'check':
        data = json.loads(receipt.read_text(encoding='utf-8'))
        root = Path(data['root'])
    else:
        root = receipt.parent / ('offline-acceptance-' + str(uuid4()))
    if not root.is_relative_to(scope) or root == scope or '..' in root.parts:
        raise ValueError('The synthetic workspace must stay inside test-runs')
    os.environ.update(PLW_DATA_ROOT=str(root / 'workspace'), PLW_BACKUP_ROOT=str(root / 'backups'),
                      PLW_PRIVATE_SITE='1')
    from plw import workspace, db, storage, backups, backup_transfer
    from plw.services import LearningService
    from plw.materials import MaterialService
    from plw.workbench import Workbench
    uid = lambda: str(uuid4())
    if args.action == 'seed':
        workspace.initialize_workspace(storage.PRODUCTION_ROOT)
        path = workspace.active_db(storage.PRODUCTION_ROOT)
        service = LearningService(path)
        term = service.create_semester('Synthetic deployment semester', request_id=uid())
        course = service.create_course(term['id'], '合成机器人课程', request_id=uid())
        pdf_python = os.environ.get('PLW_PDF_PYTHON', sys.executable)
        result = subprocess.run([pdf_python, '-c',
            'import io, sys; from pypdf import PdfWriter; w=PdfWriter(); '
            'w.add_blank_page(width=960,height=540); w.add_blank_page(width=960,height=540); '
            'buffer=io.BytesIO(); w.write(buffer); sys.stdout.buffer.write(buffer.getvalue())'],
            capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise RuntimeError('Synthetic PDF generation failed: ' + result.stderr.decode('utf-8', errors='replace')[-2000:])
        material = MaterialService(path).import_upload(course['id'], '中文 空格 课件.pdf', result.stdout, request_id=uid())
        work = Workbench(path)
        edition = work.create_edition(material['id'], uid(), local_copy_confirmed=True)
        state = work.edition_state(edition)
        work.reader_action(dict(doc=edition, id=uid(), run=path.parent.name, page=2,
            base_revision=state['revision'], kind='mark', type='highlight', points=[[0.1, 0.1], [0.7, 0.2]]))
        mark = work.save_annotation(edition, 2, 'bookmark', 'Synthetic bookmark', uid())
        note = work.save_note(course['id'], 'Synthetic note', '# 合成笔记\n$x^2+y^2$\n', None, [material['id']], uid())
        values = dict(title='Synthetic task', task_type='assignment', due_kind='none', due_date=None,
            due_at_utc=None, due_timezone=None, planned_date=None, priority='normal', status='todo',
            estimated_minutes=30, actual_minutes=0, remarks='No real learning data')
        task = work.save_task(course['id'], values, [material['id']], uid())
        row = next(t for t in work.rows('tasks') if t['id'] == task)
        work.set_task_completed(task, True, row['revision'], uid())
        report = backup_transfer.pack_backup(backups.create_backup(path)['path'])
        verified = backup_transfer.unpack_backup(report['archive_path'], root / 'received')
        target = root / 'restored'
        target.mkdir()
        backups.restore_backup(target, verified['path'], confirmation='EMPTY')
        restored = workspace.active_db(target)
        assert Workbench(restored).note_body(note) == '# 合成笔记\n$x^2+y^2$\n'
        assert Workbench(restored).edition_state(edition)['page'] == 2
        assert (restored.parent / material['managed_relpath']).read_bytes() == result.stdout
        data = dict(root=str(root), original=str(path), restored=str(restored), course=course['id'],
            material=material['id'], edition=edition, note=note, task=task, bookmark=mark,
            file_hashes={p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*')
                         if p.is_file() and 'cache' not in p.parts},
            checks=['schema4', 'Chinese PDF upload', 'two-page PDF reading copy', 'highlight', 'bookmark',
                    'reading progress', 'Markdown formula note', 'task completion', 'complete ZIP backup', 'isolated restore'])
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
    for name, expected in data['file_hashes'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe receipt path')
        path = storage.safe_path(root / relative, root=root, must_exist=True, directory=False)
        assert digest(path) == expected, name
    path = workspace.active_db(storage.PRODUCTION_ROOT)
    assert str(path) == data['original']
    with closing(db.connect(path)) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 4
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert connection.execute('SELECT status FROM tasks WHERE id=?', (data['task'],)).fetchone()[0] == 'done'
        assert connection.execute('SELECT count(*) FROM annotations WHERE edition_id=?', (data['edition'],)).fetchone()[0] == 2
    assert Workbench(path).edition_state(data['edition'])['page'] == 2
    print(json.dumps(dict(passed=True, action=args.action, platform=sys.platform,
        checks=data['checks'], files_verified=len(data['file_hashes'])), ensure_ascii=False))


if __name__ == '__main__':
    main()
