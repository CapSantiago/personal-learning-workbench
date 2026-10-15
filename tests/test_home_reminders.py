"""Reminder ordering and homepage visibility, using only synthetic learning data."""
from datetime import datetime, timedelta, UTC
from html.parser import HTMLParser
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from plw import storage, ui_workbench, workspace
from plw.services import LearningService
from plw.workbench import Workbench


class ReminderRows(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.tags = []
        self.current = None
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        classes = set(dict(attrs).get('class', '').split())
        if tag == 'li':
            self.current = {'classes': classes, 'nested_classes': set(), 'text': []}
        elif self.current is not None:
            self.current['nested_classes'].update(classes)

    def handle_data(self, data):
        if self.current is not None and data.strip():
            self.current['text'].append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'li' and self.current is not None:
            self.rows.append(self.current)
            self.current = None


def task(title, *, due_kind='none', due_date=None, due_at_utc=None, priority='normal',
         course_id='course', status='todo'):
    return dict(id=str(uuid4()), course_id=course_id, title=title, due_kind=due_kind,
                due_date=due_date, due_at_utc=due_at_utc, priority=priority, status=status,
                created_at='2026-10-01T00:00:00+00:00')


def reminders(items, current=None, course_name='自动控制'):
    markup = ui_workbench.task_reminders(
        items, {'course': {'name': course_name}},
        current or datetime(2026, 10, 20, 10, tzinfo=UTC))
    return ReminderRows(markup)


def test_all_deadlines_sort_by_full_instant_with_no_deadline_last():
    items = [
        task('没有截止但重要', priority='high'),
        task('次日零点', due_kind='datetime', due_at_utc='2026-10-20T16:00:00+00:00'),
        task('当天结束', due_kind='date', due_date='2026-10-20'),
        task('超过七天的未来任务', due_kind='date', due_date='2026-11-01'),
        task('同日最后一秒', due_kind='datetime', due_at_utc='2026-10-20T15:59:59+00:00'),
        task('当天早上', due_kind='datetime', due_at_utc='2026-10-20T01:00:00+00:00'),
        task('很早的逾期任务', due_kind='date', due_date='2026-09-01'),
        task('当天上午稍后', due_kind='datetime', due_at_utc='2026-10-20T02:00:00+00:00'),
    ]
    assert [row['text'][0] for row in reminders(items).rows] == [
        '很早的逾期任务', '当天早上', '当天上午稍后', '同日最后一秒',
        '当天结束', '次日零点', '超过七天的未来任务', '没有截止但重要',
    ]


@pytest.mark.parametrize('item,expected,label', [
    (task('按日', due_kind='date', due_date='2026-10-20'),
     datetime(2026, 10, 20, 15, 59, 59, 999999, tzinfo=UTC), '2026-10-20 当天结束前'),
    (task('北京时间跨日', due_kind='datetime', due_at_utc='2026-10-19T16:05:00Z'),
     datetime(2026, 10, 19, 16, 5, tzinfo=UTC), '2026-10-20 00:05'),
    (task('无截止'), datetime.max.replace(tzinfo=UTC), '未设截止时间'),
])
def test_deadline_conversion_and_chinese_label(item, expected, label):
    assert ui_workbench.task_deadline(item) == expected
    assert ui_workbench.task_deadline_label(item) == label


@pytest.mark.parametrize('due_kind', ['date', 'datetime'])
def test_overdue_boundary_and_visible_marker(due_kind):
    item = task('边界任务', due_kind=due_kind, due_date='2026-10-20' if due_kind == 'date' else None,
                due_at_utc='2026-10-20T10:00:00+00:00' if due_kind == 'datetime' else None)
    instant = ui_workbench.task_deadline(item)
    for current, expected in [(instant-timedelta(microseconds=1), False),
                              (instant, False), (instant+timedelta(microseconds=1), True)]:
        row = reminders([item], current).rows[0]
        assert ('is-overdue' in row['classes']) is expected
        assert ('已逾期' in row['text']) is expected
    undated = reminders([task('无截止不逾期')], instant+timedelta(days=100)).rows[0]
    assert 'is-overdue' not in undated['classes'] and '已逾期' not in undated['text']


def test_importance_has_two_labels_and_breaks_equal_deadline_ties():
    items = [task('旧低优先级', priority='low'), task('普通事项'), task('重要事项', priority='high')]
    rows = reminders(items).rows
    assert rows[0]['text'][0] == '重要事项'
    assert rows[0]['text'][-1] == '重要'
    assert 'is-important' in rows[0]['nested_classes']
    for row in rows[1:]:
        assert row['text'][-1] == '正常'
        assert 'is-important' not in row['nested_classes']


def test_task_and_course_names_are_text_not_active_html():
    title = '<script>alert("task")</script> & "quoted"'
    course = '<img src=x onerror=alert(1)> & course'
    parsed = reminders([task(title)], course_name=course)
    assert 'script' not in parsed.tags and 'img' not in parsed.tags
    assert parsed.rows[0]['text'][:2] == [title, course]


def test_home_shows_only_active_pending_tasks_without_category_controls(monkeypatch):
    root = storage.ROOTS[1] / ('home-reminders-' + str(uuid4()))
    monkeypatch.setenv('PLW_WORKSPACE', str(root))
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    service = LearningService(path)
    semester = service.create_semester('当前学期', request_id=str(uuid4()))
    archived_semester = service.create_semester('旧学期', request_id=str(uuid4()))
    active = service.create_course(semester['id'], '当前课程', request_id=str(uuid4()))
    archived = service.create_course(semester['id'], '已归档课程', request_id=str(uuid4()))
    old_course = service.create_course(archived_semester['id'], '旧学期课程', request_id=str(uuid4()))
    workbench = Workbench(path)
    for course, name, status in [
        (active, '待开始可见', 'todo'), (active, '进行中可见', 'doing'),
        (active, '已完成不可见', 'done'), (active, '已取消不可见', 'cancelled'),
        (archived, '归档课程任务不可见', 'todo'), (old_course, '归档学期任务不可见', 'todo'),
    ]:
        values = dict(title=name, task_type='assignment', due_kind='none', due_date=None,
                      due_at_utc=None, due_timezone=None, planned_date=None, priority='normal',
                      status=status, estimated_minutes=None, actual_minutes=0, remarks='')
        workbench.save_task(course['id'], values, [], str(uuid4()))
    service.set_course_archived(archived['id'], True, archived['revision'])
    service.set_semester_archived(archived_semester['id'], True, archived_semester['revision'])
    page = AppTest.from_file(str(storage.PROJECT_ROOT / 'app.py'), default_timeout=30).run()
    assert not page.exception and not page.error
    markup = ''.join(item.proto.body for item in page.get('html')
                     if 'plw-task-list' in item.proto.body and '<ol' in item.proto.body)
    rows = ReminderRows(markup).rows
    assert {row['text'][0] for row in rows} == {'待开始可见', '进行中可见'}
    assert not page.radio and not page.metric
    assert any('2 项待办' in item.value for item in page.caption)
