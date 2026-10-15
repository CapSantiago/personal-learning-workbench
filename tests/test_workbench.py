from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

import pytest

from plw import db, workspace, storage, backups
from plw.materials import MaterialService, MaterialError
from plw.services import LearningService
from plw.workbench import Workbench

FIXTURES=storage.PROJECT_ROOT/'.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources'

def uid():return str(uuid4())

@pytest.fixture
def sample():
    root=storage.ROOTS[1]/('framework-'+uid())
    workspace.initialize_workspace(root)
    path=workspace.active_db(root)
    s=LearningService(path)
    semester=s.create_semester('合成学期',request_id=uid())
    course=s.create_course(semester['id'],'自动控制',request_id=uid())
    source=root/'sources/中文 课件.pdf';source.parent.mkdir()
    shutil.copyfile(FIXTURES/'原生 PDF 中文课件.pdf',source)
    m=MaterialService(path).import_file(course['id'],source,'external_reference',request_id=uid())
    return root,path,course['id'],m,source

def task_values(**changes):
    return dict(title='复习闭环控制',task_type='review',due_kind='date',due_date='2026-10-12',due_at_utc=None,due_timezone=None,planned_date='2026-10-11',priority='high',status='todo',estimated_minutes=30,actual_minutes=0,remarks='',**changes)

def test_full_learning_restore_and_rollback(sample):
    root,path,course,m,source=sample;w=Workbench(path)
    original=storage.hash_file(source)
    edition=w.create_edition(m['id'],uid(),local_copy_confirmed=True)
    chapter=w.save_chapter(course,'第一章',[m['id']],uid())
    w.save_knowledge(course,chapter,'传递函数','understood_not_applied','需要练习',uid())
    w.save_task(course,task_values(),[m['id']],uid())
    note=w.save_note(course,'闭环公式','$G(s)=1/(s+1)$',chapter,[m['id']],uid())
    w.save_note(course,'闭环公式','$$G(s)=1/(s+1)$$',chapter,[m['id']],uid(),identity=note,version=1)
    w.save_annotation(edition,2,'question','为什么稳定？',uid())
    action=dict(id=uid(),run=path.parent.name,doc=edition,page=2,base_revision=0,kind='mark',type='rectangle',points=[[.1,.2],[.4,.5]])
    w.reader_action(action);w.reader_action(action)
    assert len(w.edition_state(edition)['marks'])==1
    report=backups.create_backup(path)
    manifest=json.loads((Path(report['path'])/'manifest.json').read_text(encoding='utf-8'))
    assert sum(f['type']=='reading_pdf' for f in manifest['files'])==1
    assert sum(f['type']=='note_revision' for f in manifest['files'])==2
    assert report['external'][0]['included'] is False
    backups.restore_backup(root,report['path'],confirmation=path.parent.name,expected_manifest_sha256=report['manifest_sha256'])
    restored=workspace.active_db(root);new=Workbench(restored)
    assert new.note_body(note)=='$$G(s)=1/(s+1)$$'
    assert new.edition_state(edition)['page']==2 and len(new.edition_state(edition)['marks'])==1
    assert len(new.rows('tasks'))==len(new.rows('knowledge_points'))==1
    assert storage.hash_file(source)==original
    backups.rollback_restore(root,confirmation=restored.parent.name)
    assert workspace.active_db(root)==path

def test_legacy_backup_remains_unchanged_and_migrates_on_restore(monkeypatch):
    root=storage.ROOTS[1]/('legacy-framework-'+uid());real=db._load_migrations
    with monkeypatch.context() as patch:
        patch.setattr(db,'_load_migrations',lambda:real()[:1])
        workspace.initialize_workspace(root);path=workspace.active_db(root)
        LearningService(path).create_semester('旧版学期',request_id=uid())
        report=backups.create_backup(path)
    snapshot=Path(report['path'])/'payload/plw.sqlite3';before=storage.hash_file(snapshot)
    assert backups.verify_backup(report['path'])['schema_version']==1
    backups.restore_backup(root,report['path'],confirmation=path.parent.name)
    new=workspace.active_db(root)
    with db.transaction(new,write=False) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==db._load_migrations()[-1].version
        assert c.execute('SELECT name FROM semesters').fetchone()[0]=='旧版学期'
    assert storage.hash_file(snapshot)==before
    backups.rollback_restore(root,confirmation=new.parent.name)
    assert workspace.active_db(root)==path
    with closing(db.connect_snapshot(path)) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==1

def test_notes_idempotence_history_and_stale_edit(sample):
    _,path,course,m,_=sample;w=Workbench(path);rid=uid()
    note=w.save_note(course,'笔记','第一版',None,[m['id']],rid)
    assert w.save_note(course,'笔记','第一版',None,[m['id']],rid)==note
    w.save_note(course,'笔记','第二版',None,[],uid(),identity=note,version=1)
    with pytest.raises(ValueError):w.save_note(course,'笔记','冲突草稿',None,[],uid(),identity=note,version=1)
    assert w.note_body(note)=='第二版'
    pending=[o for o in w.rows('content_operations') if o['state']!='committed']
    assert len(pending)==1
    w.cancel_content(pending[0]['id'])
    assert backups.create_backup(path)['complete']

def test_interrupted_note_recovers_from_durable_payload(sample,monkeypatch):
    _,path,course,_,_=sample;w=Workbench(path);rid=uid()
    with monkeypatch.context() as patch:
        patch.setattr(w,'_finish_content',lambda identity:(_ for _ in ()).throw(OSError('fault before publish')))
        with pytest.raises(OSError):w.save_note(course,'恢复笔记','草稿不丢',None,[],rid)
    with pytest.raises(backups.BackupError):backups.create_backup(path)
    assert '已完成' in w.recover_content()[0]
    assert w.note_body(rid)=='草稿不丢'
    assert backups.create_backup(path)['complete']

def test_tasks_validate_cross_course_and_cas(sample):
    _,path,course,m,_=sample;w=Workbench(path);rid=uid();v=task_values()
    w.save_task(course,v,[m['id']],rid);w.save_task(course,v,[m['id']],rid)
    changed={**v,'status':'done','actual_minutes':45}
    w.save_task(course,changed,[],uid(),identity=rid,revision=1)
    with pytest.raises(ValueError):w.save_task(course,v,[],uid(),identity=rid,revision=1)
    assert w.rows('tasks')[0]['completed_at']
    s=LearningService(path);other=s.create_course(s.list_semesters()[0]['id'],'电路',request_id=uid())
    with pytest.raises(ValueError):w.save_task(other['id'],v,[m['id']],uid())
    assert len(w.rows('tasks'))==1

@pytest.mark.parametrize('change',[{'page':0},{'page':4},{'page':True},{'base_revision':3},{'points':[[0,0],[float('nan'),1]]},{'points':[[0,0],[2,1]]},{'type':'script'},{'run':'other'}])
def test_invalid_annotation_rejected_without_state_change(sample,change):
    _,path,_,m,_=sample;w=Workbench(path);edition=w.create_edition(m['id'],uid(),local_copy_confirmed=True)
    action=dict(id=uid(),run=path.parent.name,doc=edition,page=1,base_revision=0,kind='mark',type='ink',points=[[0,0],[1,1]])
    with pytest.raises(ValueError):w.reader_action({**action,**change})
    assert w.edition_state(edition)['revision']==0

def test_source_changes_preserve_old_edition_and_marks(sample):
    _,path,_,m,source=sample;w=Workbench(path)
    first=w.create_edition(m['id'],uid(),local_copy_confirmed=True)
    w.save_annotation(first,1,'bookmark','旧版',uid())
    source.write_bytes(source.read_bytes()+b'\n%synthetic revision\n')
    second=w.create_edition(m['id'],uid(),local_copy_confirmed=True)
    assert first!=second and len(w.rows('annotations'))==1
    assert w.rows('annotations')[0]['edition_id']==first

def test_graphic_undo_redo_and_retry(sample):
    _,path,_,m,_=sample;w=Workbench(path);edition=w.create_edition(m['id'],uid(),local_copy_confirmed=True)
    action=dict(id=uid(),run=path.parent.name,doc=edition,page=1,base_revision=0,kind='mark',type='highlight',points=[[0,0],[1,1]])
    w.reader_action(action)
    w.reader_action({**action,'id':uid(),'base_revision':1,'kind':'undo'})
    assert not w.edition_state(edition)['marks']
    w.reader_action({**action,'id':uid(),'base_revision':2,'kind':'redo'})
    assert len(w.edition_state(edition)['marks'])==1

def test_ready_reading_pdf_corruption_blocks_backup(sample):
    _,path,_,m,_=sample;w=Workbench(path);edition=w.create_edition(m['id'],uid(),local_copy_confirmed=True)
    pdf=path.parent/f'reading/{edition}.pdf';pdf.write_bytes(b'corrupt synthetic')
    with pytest.raises(backups.BackupError):backups.create_backup(path)

def test_managed_material_with_reading_edition_cannot_be_physically_deleted(sample):
    _,path,course,_,source=sample;service=MaterialService(path)
    m=service.import_file(course,source,'managed_copy',request_id=uid())
    Workbench(path).create_edition(m['id'],uid(),local_copy_confirmed=True)
    service.set_deleted(m['id'],True)
    with pytest.raises(MaterialError):service.delete_managed_file(m['id'],confirmation=m['id'])

def test_production_source_policy_with_only_synthetic_files(sample,monkeypatch):
    root,path,course,_,source=sample
    outside=storage.ROOTS[1]/('explicit-source-'+uid())/'中文 课件.pdf'
    outside.parent.mkdir();shutil.copyfile(source,outside)
    before=storage.hash_file(outside)
    monkeypatch.setattr(storage,'PRODUCTION_ROOT',root)
    monkeypatch.setattr(storage,'BACKUP_ROOT',storage.ROOTS[1]/('explicit-backup-'+uid()))
    # Model a separate source/code/data layout while keeping all fixtures in sandbox.
    monkeypatch.setattr(storage,'PROJECT_ROOT',root/'synthetic-code')
    service=MaterialService(path)
    managed=service.import_file(course,outside,'managed_copy',request_id=uid())
    reference=service.import_file(course,outside,'external_reference',request_id=uid())
    assert service.check_material(reference['id'])['file_status']=='normal'
    assert managed['baseline_sha256']==before[1]
    assert storage.hash_file(outside)==before
    with pytest.raises(storage.StorageError):storage.check_source(path,db_path=path)
    assert backups.create_backup(path)['complete']

def test_interrupted_atomic_publication_can_retry_without_partial_dataset_file(sample,monkeypatch):
    _,path,course,_,_=sample;w=Workbench(path);rid=uid()
    with monkeypatch.context() as patch:
        patch.setattr('plw.workbench.os.rename',lambda *a:(_ for _ in ()).throw(OSError('simulated crash')))
        with pytest.raises(OSError):w.save_note(course,'暂存','完整草稿',None,[],rid)
    assert not (path.parent/f'notes/{rid}/{rid}.md').exists()
    assert '已完成' in w.recover_content()[0]
    assert w.note_body(rid)=='完整草稿'
    assert backups.create_backup(path)['complete']


def save_linked_entity(w, kind, course, materials, *, request_id=None,
                       identity=None, version=None, label='关联测试'):
    rid = request_id or uid()
    if kind == 'task':
        return w.save_task(course, {**task_values(), 'title': label}, materials, rid,
                           identity=identity, revision=version)
    if kind == 'chapter':
        return w.save_chapter(course, label, materials, rid,
                              identity=identity, revision=version)
    return w.save_note(course, label, label, None, materials, rid,
                       identity=identity, version=version)


@pytest.mark.parametrize('kind', ['task', 'chapter', 'note'])
def test_hidden_existing_material_links_survive_edits_and_retries(sample, kind):
    _, path, course, material, source = sample
    w = Workbench(path)
    source_before = storage.hash_file(source)
    original_request = uid()
    identity = save_linked_entity(w, kind, course, [material['id']], request_id=original_request)
    MaterialService(path).set_deleted(material['id'], True)

    # Retrying the original save after shelf removal remains idempotent.
    assert save_linked_entity(w, kind, course, [material['id']],
                             request_id=original_request) == identity
    edited_request = uid()
    for _ in range(2):
        assert save_linked_entity(w, kind, course, [material['id']],
                                 request_id=edited_request, identity=identity,
                                 version=1, label='编辑后') == identity
    assert w.associations(kind, identity) == [material['id']]
    row = w.rows({'task': 'tasks', 'chapter': 'chapters', 'note': 'notes'}[kind])[0]
    assert row['title'] == '编辑后'
    assert row['version' if kind == 'note' else 'revision'] == 2
    assert storage.hash_file(source) == source_before

    # Explicitly unlinking still works; the removed link cannot be recreated
    # while the courseware stays hidden.
    save_linked_entity(w, kind, course, [], identity=identity, version=2)
    with pytest.raises(ValueError):
        save_linked_entity(w, kind, course, [material['id']], identity=identity,
                           version=3, label='禁止重新关联')
    assert w.associations(kind, identity) == []


@pytest.mark.parametrize('kind', ['task', 'chapter', 'note'])
def test_hidden_material_cannot_be_linked_to_new_or_other_entity(sample, kind):
    _, path, course, material, _ = sample
    w = Workbench(path)
    linked = save_linked_entity(w, kind, course, [material['id']])
    other = save_linked_entity(w, kind, course, [])
    MaterialService(path).set_deleted(material['id'], True)
    operations_before = w.rows('content_operations')
    with pytest.raises(ValueError):
        save_linked_entity(w, kind, course, [material['id']])
    with pytest.raises(ValueError):
        save_linked_entity(w, kind, course, [material['id']], identity=other, version=1)
    assert w.associations(kind, linked) == [material['id']]
    assert w.associations(kind, other) == []
    assert len(w.rows({'task': 'tasks', 'chapter': 'chapters', 'note': 'notes'}[kind])) == 2
    # Note validation must fail before creating a durable content operation.
    assert w.rows('content_operations') == operations_before


@pytest.mark.parametrize('kind', ['task', 'chapter', 'note'])
@pytest.mark.parametrize('state', ['pending', 'failed'])
def test_hidden_existing_link_does_not_bypass_material_readiness(sample, kind, state):
    _, path, course, material, _ = sample
    w = Workbench(path)
    identity = save_linked_entity(w, kind, course, [material['id']])
    MaterialService(path).set_deleted(material['id'], True)
    with db.transaction(path) as c:
        c.execute('UPDATE materials SET import_state=? WHERE id=?', (state, material['id']))
    with pytest.raises(ValueError):
        save_linked_entity(w, kind, course, [material['id']], identity=identity,
                           version=1, label='不能保存未就绪关联')
    assert w.associations(kind, identity) == [material['id']]


@pytest.mark.parametrize('kind', ['task', 'chapter', 'note'])
def test_hidden_existing_link_does_not_bypass_course_ownership(sample, kind):
    _, path, course, material, _ = sample
    w = Workbench(path)
    identity = save_linked_entity(w, kind, course, [material['id']])
    MaterialService(path).set_deleted(material['id'], True)
    service = LearningService(path)
    other = service.create_course(service.list_semesters()[0]['id'], '另一个课程', request_id=uid())
    with pytest.raises(ValueError):
        save_linked_entity(w, kind, other['id'], [material['id']], identity=identity,
                           version=1, label='不能跨课程保存')
    assert w.associations(kind, identity) == [material['id']]
