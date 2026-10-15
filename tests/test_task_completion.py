"""Completion preserves content and associations; archives survive reload and backup."""
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import backups, storage, workspace
from plw.materials import MaterialService, MaterialError
from plw.services import LearningService
from plw.workbench import Workbench


def uid():return str(uuid4())


@pytest.fixture
def sample(monkeypatch):
    root=storage.ROOTS[1]/('task-completion-'+uid())
    monkeypatch.setenv('PLW_WORKSPACE',str(root))
    workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    semester=service.create_semester('测试学期',request_id=uid())
    course=service.create_course(semester['id'],'测试课程',request_id=uid())
    source=root/'sources/关联学习资料.txt';source.parent.mkdir();source.write_text('需要保留的资料',encoding='utf-8')
    material=MaterialService(path).import_file(course['id'],source,'managed_copy',request_id=uid())
    values=dict(title='需要完成的实验',task_type='lab',due_kind='date',due_date='2026-10-12',
        due_at_utc=None,due_timezone=None,planned_date='2026-10-11',priority='high',status='todo',
        estimated_minutes=30,actual_minutes=12,remarks='保留实验步骤与笔记')
    w=Workbench(path);identity=w.save_task(course['id'],values,[material['id']],uid())
    return root,path,service,semester,course,material,values,identity


@pytest.mark.parametrize('status',['todo','doing'])
def test_completion_reopen_and_retry_preserve_task_and_links(sample,status,monkeypatch):
    root,path,_,_,course,material,values,identity=sample;w=Workbench(path)
    if status=='doing':w.save_task(course['id'],{**values,'status':status},[material['id']],uid(),identity=identity,revision=1)
    before=w.rows('tasks')[0];request=uid()
    monkeypatch.setattr('plw.workbench.now',lambda:'2026-10-13T03:45:00+00:00')
    w.set_task_completed(identity,True,before['revision'],request)
    done=w.rows('tasks')[0]
    assert done['status']=='done' and done['completed_at']=='2026-10-13T03:45:00+00:00'
    assert done['revision']==before['revision']+1
    changed={'status','completed_at','updated_at','revision'}
    assert {k:v for k,v in done.items() if k not in changed}=={k:v for k,v in before.items() if k not in changed}
    w.set_task_completed(identity,True,before['revision'],request)
    assert w.rows('tasks')[0]==done
    w.set_task_completed(identity,False,done['revision'],uid())
    reopened=w.rows('tasks')[0]
    assert reopened['status']=='todo' and reopened['completed_at'] is None
    assert w.associations('task',identity)==[material['id']]
    # A delayed retry of an acknowledged completion must not re-complete it.
    w.set_task_completed(identity,True,before['revision'],request)
    assert w.rows('tasks')[0]==reopened


def test_stale_conflicting_cancelled_and_archived_actions_are_rejected(sample):
    _,path,service,_,course,material,values,identity=sample;w=Workbench(path)
    request=uid();w.set_task_completed(identity,True,1,request)
    done=w.rows('tasks')[0]
    with pytest.raises(ValueError,match='其他页面'):w.set_task_completed(identity,False,1,uid())
    with pytest.raises(ValueError,match='请求内容'):w.set_task_completed(identity,False,2,request)
    with pytest.raises(ValueError,match='状态'):w.set_task_completed(identity,True,2,uid())
    assert w.rows('tasks')[0]==done
    w.save_task(course['id'],{**values,'status':'cancelled'},[material['id']],uid(),identity=identity,revision=2)
    with pytest.raises(ValueError,match='状态'):w.set_task_completed(identity,True,3,uid())
    w.save_task(course['id'],values,[material['id']],uid(),identity=identity,revision=3)
    service.set_course_archived(course['id'],True,course['revision'])
    with pytest.raises(MaterialError):w.set_task_completed(identity,True,4,uid())
    assert w.rows('tasks')[0]['status']=='todo'


def test_editing_completed_details_keeps_original_completion_time(sample,monkeypatch):
    _,path,_,_,course,material,values,identity=sample;w=Workbench(path)
    monkeypatch.setattr('plw.workbench.now',lambda:'2026-10-13T01:00:00+00:00')
    w.set_task_completed(identity,True,1,uid())
    monkeypatch.setattr('plw.workbench.now',lambda:'2026-10-14T01:00:00+00:00')
    w.save_task(course['id'],{**values,'title':'补充标题','status':'done'},[material['id']],uid(),identity=identity,revision=2)
    row=w.rows('tasks')[0]
    assert row['completed_at']=='2026-10-13T01:00:00+00:00'
    assert row['updated_at']=='2026-10-14T01:00:00+00:00'


def test_completed_archive_and_links_survive_full_backup_restore(sample):
    root,path,_,_,_,material,_,identity=sample;w=Workbench(path)
    w.set_task_completed(identity,True,1,uid());before=w.rows('tasks')
    backup=backups.create_backup(path)
    backups.restore_backup(root,backup['path'],confirmation=path.parent.name)
    restored=Workbench(workspace.active_db(root))
    assert restored.rows('tasks')==before
    assert restored.associations('task',identity)==[material['id']]


def app():return AppTest.from_file(str(storage.PROJECT_ROOT/'app.py'),default_timeout=30).run()


def button(page,label):return next(x for x in page.button if x.label==label)


def test_home_complete_archive_reload_and_reopen(sample):
    _,path,_,_,_,_,_,identity=sample;w=Workbench(path);page=app()
    page.button(key='complete_task_'+identity).click().run()
    assert not page.exception and not page.error
    assert any('已移入' in item.value for item in page.success)
    assert not [b for b in page.button if b.key=='complete_task_'+identity]
    assert w.rows('tasks')[0]['status']=='done'
    button(page,'已完成任务').click().run()
    assert next(r for r in page.radio if r.label=='显示任务').value=='已完成任务'
    assert any('完成时间：' in item.value for item in page.text)
    assert any('关联学习资料.txt' in item.value for item in page.text)
    assert any('保留实验步骤' in item.value for item in page.text)
    page=app();button(page,'已完成任务').click().run()
    page.button(key='reopen_task_'+identity).click().run()
    assert not page.exception and not page.error
    assert not [b for b in page.button if b.key=='reopen_task_'+identity]
    page.button(key='nav_今日学习').click().run()
    assert page.button(key='complete_task_'+identity)
    assert w.rows('tasks')[0]['status']=='todo'
    page.button(key='nav_任务管理').click().run()
    page.button(key='complete_task_'+identity).click().run()
    assert not page.exception and not page.error
    assert w.rows('tasks')[0]['status']=='done'


def test_archive_remains_accessible_when_all_courses_and_semester_are_archived(sample):
    _,path,service,semester,course,_,_,identity=sample
    Workbench(path).set_task_completed(identity,True,1,uid())
    service.set_course_archived(course['id'],True,course['revision'])
    service.set_semester_archived(semester['id'],True,semester['revision'])
    page=app();button(page,'已完成任务').click().run()
    assert not page.exception and not page.error
    assert page.button(key='reopen_task_'+identity).disabled
    assert any('关联学习资料.txt' in item.value for item in page.text)


def test_stale_home_button_does_not_overwrite_a_newer_edit(sample):
    _,path,_,_,course,material,values,identity=sample;page=app();w=Workbench(path)
    w.save_task(course['id'],{**values,'remarks':'另一个窗口修改'},[material['id']],uid(),identity=identity,revision=1)
    page.button(key='complete_task_'+identity).click().run()
    assert not page.exception
    assert any('其他页面' in item.value for item in page.error)
    assert w.rows('tasks')[0]['status']=='todo'
    assert w.rows('tasks')[0]['remarks']=='另一个窗口修改'
