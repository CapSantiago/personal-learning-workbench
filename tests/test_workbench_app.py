from pathlib import Path
from datetime import date, datetime, time, UTC
from uuid import uuid4
import pytest
from streamlit.testing.v1 import AppTest
from plw import storage,workspace
from plw.services import LearningService
from plw.workbench import Workbench

PROJECT=storage.PROJECT_ROOT

@pytest.fixture
def root(monkeypatch):
    path=storage.ROOTS[1]/('usable-ui-'+str(uuid4()))
    monkeypatch.setenv('PLW_WORKSPACE',str(path))
    return path

def button(page,label):return next(x for x in page.button if x.label==label)
def text(page,label):return next(x for x in page.text_input if x.label==label)
def area(page,label):return next(x for x in page.text_area if x.label==label)
def app():return AppTest.from_file(str(PROJECT/'app.py'),default_timeout=30).run()

def seed(root):
    workspace.initialize_workspace(root);p=workspace.active_db(root);s=LearningService(p)
    sem=s.create_semester('测试学期',request_id=str(uuid4()))
    s.create_course(sem['id'],'测试课程',request_id=str(uuid4()))
    return p

def test_explicit_first_use_and_no_implicit_initialization(root):
    page=app();assert not root.exists() and not page.exception
    assert button(page,'创建学习库并开始').disabled
    page.checkbox[0].check().run()
    button(page,'创建学习库并开始').click().run()
    assert workspace.active_db(root).exists()
    assert not page.exception and not page.error

def test_tasks_notes_chapters_and_navigation(root):
    p=seed(root);page=app()
    page.button(key='nav_'+'任务管理').click().run()
    text(page,'任务标题').set_value('期末复习')
    button(page,'保存任务').click().run()
    assert not page.exception and not page.error
    assert Workbench(p).rows('tasks')[0]['title']=='期末复习'
    page.button(key='nav_'+'章节与知识点').click().run()
    text(page,'章节名称').set_value('反馈与稳定性')
    button(page,'保存章节').click().run()
    text(page,'知识点名称').set_value('奈奎斯特')
    button(page,'保存知识点').click().run()
    assert not page.exception and not page.error
    page.button(key='nav_'+'笔记').click().run()
    text(page,'笔记标题').set_value('公式笔记')
    area(page,'Markdown 正文').set_value('$$G(s)=1/(s+1)$$')
    button(page,'保存笔记').click().run()
    assert not page.exception and not page.error
    note=Workbench(p).rows('notes')[0]
    assert Workbench(p).note_body(note['id'])=='$$G(s)=1/(s+1)$$'
    for label in ['今日学习','课程书架','资料管理','数据与备份','课程管理','学期管理','使用说明']:
        page.button(key='nav_'+label).click().run()
        assert not page.exception and not page.error,label

@pytest.mark.parametrize('due_kind',['date','datetime'])
def test_missing_date_keeps_task_input_and_calendar_save(root,due_kind):
    p=seed(root);page=app();page.button(key='nav_'+'任务管理').click().run()
    text(page,'任务标题').set_value('保留草稿')
    importance=next(x for x in page.selectbox if x.label=='重要程度')
    assert importance.options==['正常','重要']
    importance.set_value('high')
    next(x for x in page.selectbox if x.label=='截止方式').set_value(due_kind)
    assert next(x for x in page.date_input if x.label=='截止日期').value is None
    button(page,'保存任务').click().run()
    assert page.error and not page.exception
    assert any('请选择截止日期' in x.value for x in page.error)
    assert text(page,'任务标题').value=='保留草稿'
    assert Workbench(p).rows('tasks')==[]
    next(x for x in page.date_input if x.label=='截止日期').set_value(date(2026,10,20))
    next(x for x in page.time_input if x.label=='截止时间（北京时间）').set_value(time(0,5))
    next(x for x in page.date_input if x.label=='计划学习日期（可留空）').set_value(date(2026,10,19))
    button(page,'保存任务').click().run()
    assert not page.exception and not page.error
    task=Workbench(p).rows('tasks')[0]
    assert task['title']=='保留草稿' and task['due_kind']==due_kind
    assert task['priority']=='high'
    assert task['planned_date']=='2026-10-19'
    if due_kind=='date':
        assert task['due_date']=='2026-10-20' and task['due_at_utc'] is None and task['due_timezone'] is None
    else:
        assert task['due_date'] is None and task['due_timezone']=='Asia/Shanghai'
        assert datetime.fromisoformat(task['due_at_utc'])==datetime(2026,10,19,16,5,tzinfo=UTC)
        # A legacy/service-authored deadline can include seconds. Editing the
        # title must not silently round that unchanged deadline to the minute.
        fields=['title','task_type','due_kind','due_date','due_at_utc','due_timezone','planned_date','priority','status','estimated_minutes','actual_minutes','remarks']
        values={key:task[key] for key in fields}
        values['due_at_utc']='2026-10-19T16:05:37.123456+00:00'
        values['priority']='low'
        Workbench(p).save_task(task['course_id'],values,[],str(uuid4()),identity=task['id'],revision=task['revision'])
    next(x for x in page.selectbox if x.label=='编辑任务').set_value(task['id']).run()
    assert next(x for x in page.date_input if x.label=='截止日期').value==date(2026,10,20)
    if due_kind=='datetime':
        assert next(x for x in page.time_input if x.label=='截止时间（北京时间）').value==time(0,5)
        assert next(x for x in page.selectbox if x.label=='重要程度').value=='normal'
        text(page,'任务标题').set_value('仅修改标题')
        button(page,'保存任务').click().run()
        assert not page.exception and not page.error,[x.value for x in page.error]
        assert Workbench(p).rows('tasks')[0]['due_at_utc']=='2026-10-19T16:05:37.123456+00:00'
        assert Workbench(p).rows('tasks')[0]['priority']=='normal'
        next(x for x in page.selectbox if x.label=='编辑任务').set_value(task['id']).run()
    next(x for x in page.selectbox if x.label=='截止方式').set_value('none')
    next(x for x in page.date_input if x.label=='计划学习日期（可留空）').set_value(None)
    button(page,'保存任务').click().run()
    assert not page.exception and not page.error
    task=Workbench(p).rows('tasks')[0]
    assert task['due_kind']=='none'
    assert task['due_date'] is None and task['due_at_utc'] is None and task['due_timezone'] is None
    assert task['planned_date'] is None

