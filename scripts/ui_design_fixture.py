"""Run the real app against disposable synthetic learning data, loopback only."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo / 'src'), str(repo / 'scripts')]
from plw import storage, workspace
from plw.services import LearningService
from plw.materials import MaterialService
from plw.workbench import Workbench
from reader_navigation_seed import pdf_bytes


def main():
    folder = Path(os.environ['PLW_DESIGN_FOLDER'])
    folder.mkdir(exist_ok=True)
    root = storage.ROOTS[1] / ('ui-design-' + str(uuid4()))
    workspace.initialize_workspace(root)
    database = workspace.active_db(root)
    service = LearningService(database)
    semester = service.create_semester('2026 秋季 · 合成验收', request_id=str(uuid4()))
    names = ['机器人技术基础', '自主移动机器人', '机器人视觉', '电机驱动与运动控制',
             '自动控制原理', '人工智能', '离散数学与计算机科学基础（长名称排版验收）']
    courses = [service.create_course(semester['id'], name, teacher='合成教师', request_id=str(uuid4())) for name in names]
    archived = service.create_course(semester['id'], '已归档测试课', request_id=str(uuid4()))
    service.set_course_archived(archived['id'], True, archived['revision'])
    workbench = Workbench(database)
    documents = []
    for index, (course, name, specs) in enumerate([
        (courses[0], '01 横向课件.pdf', [(960, 540, 0, None)] * 6),
        (courses[0], '02 纵向旋转课件.pdf', [(600, 800, 0, None), (800, 600, 90, [40, 35, 760, 565])]),
        (courses[1], '自主移动机器人：定位与路径规划.pdf', [(960, 540, 0, None)] * 8),
        (courses[2], '机器人视觉与三维重建：课程介绍和完整实验说明.pdf', [(960, 540, 0, None)] * 10),
    ]):
        body=pdf_bytes(specs)
        if os.environ.get('PLW_DESIGN_ENCRYPTED')=='1' and index in (0,1):
            from io import BytesIO
            from pypdf import PdfReader,PdfWriter
            writer=PdfWriter(clone_from=PdfReader(BytesIO(body)))
            writer.encrypt('',owner_password='synthetic-owner-only',algorithm='AES-256' if index==0 else 'RC4-128')
            stream=BytesIO();writer.write(stream);body=stream.getvalue()
        material = MaterialService(database).import_upload(course['id'], name, body, request_id=str(uuid4()))
        edition = workbench.create_edition(material['id'], str(uuid4()), local_copy_confirmed=True)
        documents.append(dict(name=name, material=material['id'], edition=edition))
        if index != 1:
            state = workbench.edition_state(edition)
            workbench.reader_action(dict(id=str(uuid4()), run=database.parent.name, doc=edition,
                                         page=2, base_revision=state['revision'], kind='position'))
    today = datetime.now(timezone(timedelta(hours=8))).date()
    for title, offset, priority in [('完成第二章课后习题并整理实验记录', 0, 'high'),
                                    ('复习坐标变换，补充尚未理解的推导和笔记', -1, 'normal'),
                                    ('准备小组实验与课件批注', 3, 'normal')]:
        workbench.save_task(courses[0]['id'], dict(title=title, task_type='assignment', due_kind='date',
            due_date=(today + timedelta(days=offset)).isoformat(), due_at_utc=None, due_timezone=None,
            planned_date=today.isoformat(), priority=priority, status='todo', estimated_minutes=30,
            actual_minutes=0, remarks='仅用于 UI 验收的合成任务。'), [], str(uuid4()))
    workbench.save_note(courses[0]['id'], '坐标变换与实验笔记', '# 学习记录\n\n整理本周课件中的重点与疑问。\n\n- 坐标变换\n- 运动学推导', None, [], str(uuid4()))
    os.environ['PLW_WORKSPACE'] = str(root)
    os.environ['PLW_PRIVATE_SITE'] = '1'
    (folder / 'config.json').write_text(json.dumps(dict(root=str(root), database=str(database),
        courses=courses, documents=documents, origin='http://127.0.0.1:8506'), ensure_ascii=False), encoding='utf-8')
    import streamlit as st
    from plw.reader_runtime import reader_routes
    st.App(str(repo / 'app.py'), routes=reader_routes()).run(config={
        'server.address': '127.0.0.1', 'server.port': 8506, 'server.headless': True,
        'browser.gatherUsageStats': False, 'server.fileWatcherType': 'none',
        'server.enableCORS': True, 'server.enableXsrfProtection': True, 'server.enableStaticServing': False})


if __name__ == '__main__':
    main()
