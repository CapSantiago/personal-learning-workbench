"""The usable local workbench. Real data is initialized only by an explicit click."""
from datetime import date, datetime, timedelta, timezone, UTC
from html import escape
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

import streamlit as st

from . import backups, db, locking, storage, workspace, ui_theme
from .services import LearningService
from .materials import MaterialService
from .workbench import Workbench
from .uploads import import_courseware, MAX_BATCH_FILES, MAX_BATCH_BYTES
from .reader_runtime import ReaderAssets
from .ocr import OcrService, MAX_BATCH_PAGES
from .courseware_media import CoursewareMedia
from .ui import _courses_page, _semesters_page
from .ui_m2 import ERRORS, _backups_page, _material_detail, _done, TYPES, MODES

TASK_TYPES={'assignment':'作业','lab':'实验','exam':'考试','preview':'预习','review':'复习','project':'项目'}
TASK_STATES={'todo':'待开始','doing':'进行中','done':'已完成','cancelled':'已取消'}
KNOWLEDGE={'not_started':'未学习','learning':'学习中','understood_not_applied':'已理解，尚不能独立应用','mastered':'已掌握'}
MARKS={'bookmark':'书签','comment':'批注','important':'重点','question':'疑问'}
PAGES=['今日学习','课程书架','任务管理','笔记','章节与知识点','课程管理','学期管理','资料管理','数据与备份','外观设置','使用说明']
TZ=timezone(timedelta(hours=8))


def private_site():
    return os.environ.get('PLW_PRIVATE_SITE')=='1'


def interface_css(relative):
    """One token palette for native UI and isolated reader/library components."""
    folder=Path(__file__).parent
    return (folder/'design_tokens.css').read_text(encoding='utf-8')+'\n'+ui_theme.theme_css(st.session_state.get('_plw_theme',ui_theme.DEFAULT))+(folder/relative).read_text(encoding='utf-8')


def token(key):
    return st.session_state.setdefault(key,str(uuid4()))


def navigate(page,course_id=None,material_id=None,edition_id=None):
    st.session_state.navigation=page
    if page=='任务管理':st.session_state.task_scope='待完成'
    if page=='课程书架':st.session_state._shelf_nav_open=True
    if course_id:
        st.session_state._selected_course=course_id
        st.session_state.active_course=course_id
    if material_id:
        st.session_state._shelf_target={'material':material_id,'edition':edition_id}
        st.session_state._import_report_course=None


def toggle_bookshelf():
    st.session_state._shelf_nav_open=not st.session_state.get('_shelf_nav_open',False)


def navigation(path):
    page=st.session_state.get('navigation','今日学习')
    if page not in PAGES:page='今日学习'
    with st.sidebar:
        st.html('<div class="plw-brand-lockup"><span class="plw-brand-mark" aria-hidden="true"></span>'
                '<div><div class="plw-brand"><span class="plw-wordmark" aria-hidden="true"></span><span class="plw-brand-name">PLW</span></div>'
                '<div class="plw-brand-sub">个人学习工作台</div></div></div>')
        for label in PAGES[:4]:
            if label=='课程书架':
                opened=st.session_state.setdefault('_shelf_nav_open',page=='课程书架')
                with st.container(key='nav_item_bookshelf_'+('open' if opened else 'closed')):
                    st.button(label,key='nav_'+label,width='stretch',type='primary' if page==label else 'secondary',
                              on_click=toggle_bookshelf,help='展开或收起课程列表')
                if opened:
                    with st.container(key='sidebar_course_list'):
                        courses=LearningService(path).list_courses()
                        if page==label and courses and st.session_state.get('_selected_course') not in {c['id'] for c in courses}:
                            st.session_state._selected_course=courses[0]['id']
                        for course in courses:
                            title=course['name']
                            if sum(c['name']==title for c in courses)>1:title+=' · '+course['semester_name']
                            st.button(title,key='shelf_course_'+course['id'],width='stretch',
                                      type='primary' if page==label and st.session_state.get('_selected_course')==course['id'] else 'secondary',
                                      on_click=navigate,args=('课程书架',course['id']))
                        if not courses:
                            st.caption('还没有课程')
                            destination='课程管理' if LearningService(path).list_semesters() else '学期管理'
                            st.button('去添加课程' if destination=='课程管理' else '先创建学期',key='sidebar_course_empty',on_click=navigate,args=(destination,))
                continue
            with st.container(key='nav_item_'+{'今日学习':'today','任务管理':'tasks','笔记':'notes'}[label]):
                st.button(label,key='nav_'+label,width='stretch',type='primary' if page==label else 'secondary',on_click=navigate,args=(label,))
        # Stable identity keeps the user's disclosure state when the course tree
        # or current page changes, instead of closing it during navigation.
        with st.expander('课程与设置',expanded=page in PAGES[4:],key='sidebar_settings'):
            for label in PAGES[4:]:
                st.button(label,key='nav_'+label,width='stretch',type='primary' if page==label else 'secondary',on_click=navigate,args=(label,))
        with st.container(key='sidebar_footer'):
            st.caption('私人学习库 · 课件可下载离线阅读' if private_site() else '本地保存 · 离线可用')
            if private_site():st.link_button('退出登录','/plw-auth/logout',width='stretch')
    return page


def course_picker(path,key,*,show_selector=True):
    rows=LearningService(path).list_courses()
    if not rows:
        st.info('添加第一门课程，开始整理学习资料。')
        destination='课程管理' if LearningService(path).list_semesters() else '学期管理'
        st.button('去添加课程' if destination=='课程管理' else '先创建学期',on_click=navigate,args=(destination,),key=key+'_empty')
        return None
    items={r['id']:r for r in rows}
    preferred=st.session_state.get('_selected_course')
    if not show_selector:
        identity=preferred if preferred in items else next(iter(items))
        st.session_state._selected_course=identity
        return items[identity]
    if st.session_state.get('active_course') not in items:st.session_state.active_course=preferred if preferred in items else next(iter(items))
    def label(k):
        c=items[k]
        return c['name'] if sum(r['name']==c['name'] for r in rows)==1 else f"{c['name']} · {c['semester_name']}"
    def remember():st.session_state._selected_course=st.session_state.active_course
    identity=st.selectbox('选择课程',list(items),format_func=label,key='active_course',on_change=remember)
    st.session_state._selected_course=identity
    return items[identity]


def material_picker(path,course_id,key,default=()):
    rows={r['id']:r for r in MaterialService(path).list_materials(course_id,include_deleted=True)
          if r['import_state']=='ready' and (not r['deleted_at'] or r['id'] in default)}
    return st.multiselect('关联资料',list(rows),default=[v for v in default if v in rows],
                          format_func=lambda k:rows[k]['name']+('（已从书架移除）' if rows[k]['deleted_at'] else ''),key=key)


def chapter_picker(w,course_id,key,value=None):
    rows={r['id']:r for r in w.rows('chapters',course_id)}
    ids=[None,*rows]
    return st.selectbox('所属章节',ids,index=ids.index(value) if value in ids else 0,format_func=lambda k:'不指定章节' if k is None else rows[k]['title'],key=key)


def task_deadline(task):
    """One comparable instant: date-only deadlines expire at local day end."""
    if task['due_kind']=='date':
        return (datetime.fromisoformat(task['due_date']).replace(tzinfo=TZ)
                +timedelta(days=1,microseconds=-1)).astimezone(UTC)
    if task['due_kind']=='datetime':return datetime.fromisoformat(task['due_at_utc']).astimezone(UTC)
    return datetime.max.replace(tzinfo=UTC)


def task_deadline_label(task):
    if task['due_kind']=='date':return task['due_date']+' 当天结束前'
    if task['due_kind']=='datetime':return task_deadline(task).astimezone(TZ).strftime('%Y-%m-%d %H:%M')
    return '未设截止时间'


def task_reminders(tasks,courses,current):
    rows=[]
    for task in sorted(tasks,key=lambda t:(task_deadline(t),t['priority']!='high',t['created_at'],t['id'])):
        overdue=task['due_kind']!='none' and task_deadline(task)<current
        important=task['priority']=='high'
        rows.append(
            '<li class="plw-task-row'+(' is-overdue' if overdue else '')+'">'
            '<div class="plw-task-main"><div class="plw-task-title">'+escape(task['title'])+'</div>'
            '<div class="plw-task-course">'+escape(courses[task['course_id']]['name'])+'</div></div>'
            '<div class="plw-task-due"><span>'+escape(task_deadline_label(task))+'</span>'
            +('<span class="plw-task-overdue">已逾期</span>' if overdue else '')+'</div>'
            '<span class="plw-task-priority'+(' is-important' if important else '')+'">'
            +('重要' if important else '正常')+'</span></li>')
    return '<ol class="plw-task-list" aria-label="按截止时间排序的待办任务">'+''.join(rows)+'</ol>'


def open_task_archive():
    navigate('任务管理')
    st.session_state.task_scope='已完成任务'


def change_task_completion(path,identity,completed,revision,request_id):
    try:
        Workbench(path).set_task_completed(identity,completed,revision,request_id)
    except (*ERRORS,ValueError) as exc:
        st.session_state._task_action_error=str(exc)
        return
    st.session_state.pop('_task_action_error',None)
    st.session_state._m2_notice='任务已完成，已移入“已完成任务”存档。' if completed else '任务已恢复到待办列表。'


def pending_task_list(path,items,courses,current):
    for task in sorted(items,key=lambda t:(task_deadline(t),t['priority']!='high',t['created_at'],t['id'])):
        with st.container(border=True,key='pending_task_'+task['id']):
            details,action=st.columns([5,1],vertical_alignment='center')
            with details:st.html(task_reminders([task],courses,current))
            action.button('完成',key='complete_task_'+task['id'],width='stretch',
                help='完成后移入存档，任务内容和关联资料继续保留。',
                on_click=change_task_completion,args=(path,task['id'],True,task['revision'],str(uuid4())))


def task_archive(path):
    st.subheader('已完成任务')
    st.caption('按完成时间从近到远保存，可查看详情或恢复待办。归档课程中的已完成任务也会保留。')
    courses={r['id']:r for r in LearningService(path).list_courses(include_archived=True)}
    chosen=st.selectbox('存档课程',[None,*courses],format_func=lambda k:'全部课程' if k is None else courses[k]['name']+' · '+courses[k]['semester_name'])
    query=st.text_input('搜索已完成任务',placeholder='输入任务标题')
    w=Workbench(path)
    rows=[r for r in w.rows('tasks') if r['status']=='done' and (chosen is None or r['course_id']==chosen) and query.casefold() in r['title'].casefold()]
    st.caption(f'{len(rows)} 项已完成')
    if not rows:st.info('暂无符合条件的已完成任务。完成待办后，会自动保存在这里。')
    for task in sorted(rows,key=lambda r:(datetime.fromisoformat(r['completed_at']),r['id']),reverse=True):
        course=courses[task['course_id']]
        completed=datetime.fromisoformat(task['completed_at']).astimezone(TZ).strftime('%Y-%m-%d %H:%M')
        with st.expander(task['title']+' · '+completed,key='archived_task_'+task['id']):
            st.text('课程：'+course['name']+' · '+course['semester_name'])
            st.text('完成时间：'+completed+'（北京时间）')
            st.text('截止：'+task_deadline_label(task))
            st.text('类型：'+TASK_TYPES[task['task_type']]+' · 重要程度：'+('重要' if task['priority']=='high' else '正常'))
            st.text(f"预计耗时：{task['estimated_minutes'] if task['estimated_minutes'] is not None else '未设置'} 分钟 · 实际耗时：{task['actual_minutes']} 分钟")
            if task['planned_date']:st.text('计划学习日期：'+task['planned_date'])
            if task['remarks']:st.text('备注：'+task['remarks'])
            linked=set(w.associations('task',task['id']))
            for material in MaterialService(path).list_materials(course['id'],include_deleted=True):
                if material['id'] in linked:st.text('关联资料：'+material['name']+('（已从书架移除）' if material['deleted_at'] else ''))
            archived=bool(course['archived_at'] or course['semester_archived_at'])
            if archived:st.caption('所属课程或学期已归档；恢复课程与学期后可恢复待办。')
            st.button('恢复待办',key='reopen_task_'+task['id'],disabled=archived,
                on_click=change_task_completion,args=(path,task['id'],False,task['revision'],str(uuid4())))


def home(path):
    st.header('今日学习')
    st.caption(datetime.now(TZ).strftime('%m 月 %d 日')+' · 从上次停下的地方继续。')
    w=Workbench(path);current=datetime.now(UTC)
    courses={r['id']:r for r in LearningService(path).list_courses()}
    if not courses:
        with st.container(border=True):
            st.subheader('建立你的第一门课程')
            st.write('创建学期和课程，再添加 PPT 或 PDF。课件、标记和笔记都会按课程整理。')
            destination='课程管理' if LearningService(path).list_semesters() else '学期管理'
            st.button('添加第一门课程' if destination=='课程管理' else '创建第一个学期',type='primary',on_click=navigate,args=(destination,))
        st.button('已完成任务',on_click=open_task_archive)
        return
    tasks=[r for r in w.rows('tasks') if r['status'] not in ('done','cancelled') and r['course_id'] in courses]
    st.subheader('继续阅读')
    with db.transaction(path,write=False) as c:
        recent=[dict(r) for r in c.execute('''SELECT e.id edition_id,e.page_count,m.id material_id,m.name,m.course_id,p.page,
            MAX(p.updated_at,COALESCE(a.updated_at,p.updated_at)) AS updated_at
            FROM reading_progress p JOIN reading_editions e ON e.id=p.edition_id JOIN materials m ON m.id=e.material_id
            LEFT JOIN (SELECT edition_id,MAX(updated_at) updated_at FROM annotations WHERE deleted_at IS NULL GROUP BY edition_id) a ON a.edition_id=e.id
            WHERE m.deleted_at IS NULL AND (p.revision>0 OR a.edition_id IS NOT NULL) ORDER BY updated_at DESC''') if r['course_id'] in courses][:3]
    if recent:
        for index,(col,r) in enumerate(zip(st.columns(len(recent)),recent)):
            with col.container(key='resume_card_'+r['edition_id']):
                st.caption(courses[r['course_id']]['name'])
                st.write('**'+r['name']+'**')
                st.progress(r['page']/r['page_count'],text=f"上次读到第 {r['page']} / {r['page_count']} 页")
                st.button('继续阅读',key='resume_'+r['edition_id'],type='primary' if index==0 else 'secondary',width='stretch',on_click=navigate,args=('课程书架',r['course_id'],r['material_id'],r['edition_id']))
    else:
        with st.container(border=True):
            st.write('选一份课件开始阅读，下次可以从这里继续。')
            st.button('打开课程书架',type='primary',on_click=navigate,args=('课程书架',))
    left,right=st.columns([1.4,1])
    with left:
        st.subheader('接下来要做')
        st.caption(f'{len(tasks)} 项待办 · 按截止时间从早到晚，未设截止时间的排在最后。')
        if tasks:pending_task_list(path,tasks,courses,current)
        else:st.caption('暂无待办任务，可以按自己的节奏学习。')
        with st.container(horizontal=True):
            st.button('安排学习任务',on_click=navigate,args=('任务管理',))
            st.button('已完成任务',on_click=open_task_archive)
    with right:
        with st.container(key='home_courses'):
            st.subheader('我的课程')
            for c in courses.values():
                st.button(c['name'],key='home_course_'+c['id'],width='stretch',on_click=navigate,args=('课程书架',c['id']))
            st.button('管理课程',on_click=navigate,args=('课程管理',))


def add_material(path,course_id,key='import'):
    scope=key+'_'+course_id
    generation=token(scope+'_upload_token')
    files=st.file_uploader('选择课件文件',type=['pdf','ppt','pptx'],accept_multiple_files=True,
        max_upload_size=200,key=scope+'_'+generation,
        help='点击选择按钮打开系统文件选择器。电脑可按 Ctrl / Shift 多选；iPad 和手机可从“文件”中选择。')
    st.caption('支持一次选择多份 PDF、PPT、PPTX。导入后保存完整课件并自动准备阅读，原文件保持不变。')
    ready=bool(files) and len(files)<=MAX_BATCH_FILES and sum(f.size for f in files)<=MAX_BATCH_BYTES
    if files:
        st.caption(f'已选 {len(files)} 份 · 合计 {sum(f.size for f in files)/1024/1024:.1f} MB')
        if not ready:st.warning('请分批导入：每批最多 20 份、合计 500 MB，每份不超过 200 MB。')
    a,b=st.columns([2,1])
    submitted=a.button('导入所选课件',key=scope+'_submit',type='primary',disabled=not ready,width='stretch')
    if b.button('清空选择',key=scope+'_clear',disabled=not files,width='stretch'):
        st.session_state[scope+'_upload_token']=str(uuid4())
        st.rerun()
    if submitted:
        bar=st.progress(0,text='正在保存课件并准备阅读…')
        with st.spinner('正在导入；PPT 将自动转换为可阅读的静态页面…'):
            results=import_courseware(path,course_id,[(f.name,f.getvalue()) for f in files],generation,
                progress=lambda done,total,item:bar.progress(done/total,text=f"{done}/{total} · {item['filename']}"))
        st.session_state[scope+'_report']=results
        st.session_state._import_report_course=course_id
        st.rerun()
    results=st.session_state.get(scope+'_report')
    if results:
        ready_items=[r for r in results if r['status']=='ready']
        saved=sum(r['material_id'] is not None for r in results)
        notice=f'本批 {len(results)} 份：{len(ready_items)} 份可阅读，{saved-len(ready_items)} 份已保存待处理，{len(results)-saved} 份未导入。'
        (st.success if len(ready_items)==len(results) else st.warning)(notice)
        st.dataframe([{'课件':r['filename'],'结果':r['message']} for r in results],hide_index=True,width='stretch')
        if any(r['status']!='ready' for r in results):
            st.caption('未完成的文件不会影响其他课件。可保留当前选择后再次点击导入；已完成的文件不会重复添加。PPT 转换失败时，可从 PowerPoint 导出 PDF 后选择导入。')
        if ready_items:
            item=ready_items[0]
            st.button('阅读刚导入的课件',key=scope+'_read',on_click=navigate,
                args=('课程书架',course_id,item['material_id'],item['edition_id']))


def add_path_material(path,course_id,key='path_import'):
    t=token(key+'_token')
    with st.form(key+'_'+t):
        source=st.text_input('文件绝对路径',placeholder=r'E:\课程资料\控制原理\第一讲.pdf')
        name=st.text_input('资料名称（留空使用文件名）')
        mode=st.selectbox('存储方式',list(MODES),format_func=MODES.get)
        kind=st.selectbox('资料类型',list(TYPES),format_func=TYPES.get)
        submit=st.form_submit_button('添加资料',type='primary')
    if submit:
        source=source.strip().strip('"')
        if Path(source).is_dir():
            st.error('这里填入的是文件夹。请选择具体文件，或使用上方“选择课件文件”一次导入多份。')
            return
        MaterialService(path).import_file(course_id,source,mode,name=name or None,material_type=kind,request_id=t)
        st.session_state[key+'_token']=str(uuid4())
        _done('资料已添加。原文件保持不变。')
    st.caption('每次添加一个文件，分别选择复制或引用。可从资源管理器“复制文件地址”后粘贴路径，去掉首尾引号。')


@st.cache_resource
def reader_assets(origin):
    return ReaderAssets(origin)


def device_downloads(path):
    # Legacy standalone databases have no active dataset pointer or device library.
    if locking.workspace_for(path) is None:return
    assets=reader_assets(f"http://127.0.0.1:{st.get_option('server.port')}")
    url=assets.register_library(path);folder=Path(__file__).with_name('reader')
    with st.expander('此设备课件下载库'):
        render=st.components.v2.component('plw_device_library',html='<div class="device-library"></div>',
            css=interface_css('reader/library.css'),js=(folder/'library_ui.js').read_text(encoding='utf-8'))
        render(key='device_library_'+path.parent.name,data={'base':assets.url,'run':path.parent.name,'manifest':url})


def read_edition(path,edition):
    w=Workbench(path);identity=edition['id']
    state=w.edition_state(identity)
    material=MaterialService(path).get_material(edition['material_id'])
    assets=reader_assets(f"http://127.0.0.1:{st.get_option('server.port')}")
    assets.register(path,edition)
    try:ocr_texts=OcrService(path).texts(identity)
    except (ValueError,RuntimeError,OSError) as exc:
        ocr_texts={};st.warning('OCR 文字暂不可用：'+str(exc))
    reset_key='reader_reset_'+identity
    folder=Path(__file__).with_name('reader')
    render=st.components.v2.component('plw_reader',html='<div class="reader-root"></div>',css=interface_css('reader/reader.css'),js=(folder/'reader.js').read_text(encoding='utf-8'))
    result=render(key='reader_'+identity,data={'base':assets.url,'run':path.parent.name,'doc':identity,'filename':material['name'],'pages':edition['page_count'],'bytes':edition['size_bytes'],'digest':edition['pdf_sha256'],'state':state,'ocr_texts':ocr_texts,'revision':state['revision'],'ack':st.session_state.get('reader_ack',''),'error':st.session_state.get('reader_error',''),'reset':st.session_state.get(reset_key,''),'goto':st.session_state.get('goto_'+identity)},on_action_change=lambda:None)
    if result.action:
        try:
            w.reader_action(result.action)
            st.session_state.reader_ack=result.action['id'];st.session_state.reader_error=''
        except (*ERRORS,ValueError,KeyError,TypeError) as exc:
            st.session_state.reader_error=str(exc)
        st.rerun()
    with st.expander('书签与批注',expanded=False):
        annotation_panel(path,edition,state)


def edition_tools(path,edition):
    identity=edition['id'];state=Workbench(path).edition_state(identity)
    material=MaterialService(path).get_material(edition['material_id'])
    assets=reader_assets(f"http://127.0.0.1:{st.get_option('server.port')}")
    with st.expander('下载与离线阅读',key='downloads_'+identity):
        st.link_button('下载 PDF 到设备',assets.register_download(path,material,edition),width='stretch')
        if material['storage_mode']=='managed_copy' and not material['file_deleted_at']:
            try:original_url=assets.register_download(path,material)
            except (*ERRORS,ValueError):st.caption('原始课件暂不可下载，可继续阅读和下载独立 PDF。请在资料管理中检查原件。')
            else:st.link_button('下载原始课件',original_url,width='stretch')
        else:st.caption('原件使用外部路径引用；PDF 阅读副本可以独立下载。迁移网站前请导入完整原件。')
        st.caption('先下载并保存到手机或 iPad 的“文件”，之后断网可用 PDF 阅读器打开。此 PDF 为静态课件，不包含 PLW 标记；离线修改暂不自动同步。')
    if not private_site():
        with st.expander('图片文字识别（OCR）',key='ocr_panel_'+identity):
            try:texts=OcrService(path).texts(identity)
            except (ValueError,RuntimeError,OSError) as exc:st.warning('OCR 文字暂不可用：'+str(exc))
            else:ocr_panel(path,edition,state,texts)
    material=MaterialService(path).get_material(edition['material_id'])
    if not private_site() and Path(material['original_path']).suffix.lower() in ('.ppt','.pptx'):
        with st.expander('动画与视频',key='media_panel_'+identity):
            media_panel(path,edition,state,assets)
    with st.expander('阅读器维护'):
        st.caption(f"阅读副本创建于 {edition['created_at'][:10]}。标记只属于当前版本，原文件保持不变。")
        if st.button('重新载入阅读器',help='其他窗口修改后使用。尚未保存的图形会被放弃。'):
            st.session_state['reader_reset_'+identity]=str(uuid4());st.session_state.pop('reader_error',None);st.rerun()


def ocr_panel(path,edition,state,texts):
    identity=edition['id'];service=OcrService(path)
    st.caption(f"在本机识别中英文图片文字，已识别 {len(texts)} / {edition['page_count']} 页。识别后可在上方搜索并跳页；公式与手写内容可能不准确。")
    if st.button('识别当前页',key='ocr_current_'+identity):
        with st.spinner(f"正在识别第 {state['page']} 页…"):
            service.recognize_pages(identity,[state['page']])
        _done('当前页文字已识别，可在课件内查找。')
    with st.expander('批量识别课件',key='ocr_batch_panel_'+identity):
        a,b=st.columns(2)
        first=a.number_input('起始页',min_value=1,max_value=edition['page_count'],value=state['page'],key='ocr_first_'+identity)
        last=b.number_input('结束页',min_value=1,max_value=edition['page_count'],value=min(state['page']+MAX_BATCH_PAGES-1,edition['page_count']),key='ocr_last_'+identity)
        st.caption(f'每次最多 {MAX_BATCH_PAGES} 页；长课件可分批识别，已完成的结果会保留。')
        if st.button('识别所选页面',key='ocr_range_'+identity):
            if last<first or last-first+1>MAX_BATCH_PAGES:st.error(f'请选择连续的 1–{MAX_BATCH_PAGES} 页。')
            else:
                progress=st.progress(0,text='正在准备本地文字识别…')
                service.recognize_pages(identity,range(first,last+1),progress=lambda done,total,page:progress.progress(done/total,text=f'已处理 {done}/{total} 页 · 第 {page} 页'))
                _done('所选页面已识别，可在课件内查找。')
    current=texts.get(str(state['page']))
    if current is not None:
        if current:st.code(current,language=None,wrap_lines=True)
        else:st.caption('本页未识别到文字，可以尝试更清晰的图片。')
    if texts:
        content='\n\n'.join(f'第 {p} 页\n{texts[p]}' for p in sorted(texts,key=int))
        st.download_button('导出识别文字',content,file_name='课件识别文字.txt',mime='text/plain',key='ocr_download_'+identity)
    with st.expander('识别单张图片',key='ocr_image_panel_'+identity):
        uploaded=st.file_uploader('选择图片',type=['png','jpg','jpeg'],max_upload_size=20,key='ocr_image_'+identity)
        if st.button('识别图片文字',disabled=uploaded is None,key='ocr_image_start_'+identity):
            with st.spinner('正在识别图片…'):
                text=service.recognize_image(uploaded.name,uploaded.getvalue())
                st.session_state['ocr_image_result_'+identity]={'file_id':uploaded.file_id,'text':text}
        saved=st.session_state.get('ocr_image_result_'+identity)
        result=saved['text'] if uploaded and isinstance(saved,dict) and saved.get('file_id')==uploaded.file_id else None
        if result is not None:
            if result:st.code(result,language=None,wrap_lines=True)
            else:st.caption('未识别到文字，请换一张更清晰的图片。')
            st.download_button('导出图片文字',result,file_name='图片识别文字.txt',mime='text/plain',key='ocr_image_download_'+identity)
    st.caption('识别结果可重新生成；需要长期保留的文字请导出或复制到笔记中。')


def media_panel(path,edition,state,assets):
    identity=edition['id']
    st.caption('PPTX 内的视频可直接在页面播放。动画会生成整份演示视频，按顺序回放；逐步点击和交互按钮仍需 PowerPoint。')
    if not st.toggle('显示播放与准备工具',key='media_tools_'+identity):return
    service=CoursewareMedia(path)
    a,b=st.columns(2)
    if a.button('读取课件内视频',key='media_extract_'+identity,width='stretch'):
        try:
            with st.spinner('正在准备课件中的视频…'):service.prepare_embedded(identity)
        except (ValueError,RuntimeError,OSError) as exc:st.error('视频准备未完成：'+str(exc))
        else:_done('视频检查完成。')
    if b.button('生成动画播放版',key='media_animation_'+identity,width='stretch'):
        try:
            with st.spinner('PowerPoint 正在生成动画视频，最多等待三分钟…'):service.prepare_animation(identity)
        except (ValueError,RuntimeError,OSError) as exc:st.error('动画准备未完成：'+str(exc))
        else:_done('动画播放版已准备好。')
    try:
        clips=service.embedded(identity);animation=service.animation(identity)
        for message in service.messages(identity):st.info(message)
        items=([animation] if animation else [])+sorted(clips,key=lambda item:(item['page']!=state['page'],item['page'] or 0,item['label']))
        if not items:
            st.caption('先读取内嵌视频，或生成一次动画播放版。普通 PDF 的静态页面不含 PPT 动画。')
            return
        index=st.selectbox('选择播放内容',range(len(items)),format_func=lambda i:items[i]['label']+('（当前页）' if items[i]['page']==state['page'] else ''),key='media_choice_'+identity+'_'+str(state['page']))
        item=items[index]
        if item['playable']:
            url=assets.register_media(path,identity,item)
            st.html('<video controls playsinline preload="metadata" style="width:100%;max-height:560px;background:#18231f;border-radius:10px" src="'+escape(url,quote=True)+'">当前浏览器无法播放此视频，请使用原格式课件。</video>')
            st.caption('可播放、暂停、拖动进度或全屏。视频解码能力取决于浏览器；链接视频需先在 PowerPoint 中嵌入。')
        else:st.info('此视频格式暂不能在浏览器中播放，请用 PowerPoint 打开原格式，或将视频转换成 MP4 后嵌入课件。')
    except (ValueError,RuntimeError,OSError) as exc:st.warning('播放副本暂不可用：'+str(exc))


def annotation_panel(path,edition,state):
    w=Workbench(path);identity=edition['id']
    t=token('mark_token')
    with st.form('mark_'+identity+'_'+t):
        left,right=st.columns(2)
        page=left.number_input('标记页码',min_value=1,max_value=edition['page_count'],value=state['page'])
        kind=right.selectbox('标记类型',list(MARKS),format_func=MARKS.get)
        body=st.text_area('标记内容（可写公式和 Markdown）',key='mark_body_'+identity+'_'+t)
        save=st.form_submit_button('保存标记')
    if save:
        w.save_annotation(identity,page,kind,body,t);st.session_state.mark_token=str(uuid4());_done('标记已保存。')
    filters=st.multiselect('筛选标记',list(MARKS),default=list(MARKS),format_func=MARKS.get)
    marks=[r for r in w.rows('annotations') if r['edition_id']==identity and not r['deleted_at'] and r['kind'] in filters]
    export=[]
    for mark in sorted(marks,key=lambda r:(r['page'],r['created_at'])):
        with st.expander(f"第 {mark['page']} 页 · {MARKS[mark['kind']]}{' · 已解决' if mark['resolved'] else ''} · {mark['body'][:40]}"):
            markdown(mark['body'])
            if st.button('跳到该页',key='goto_'+mark['id']):
                w.reader_action({'id':str(uuid4()),'run':path.parent.name,'doc':identity,'page':mark['page'],'base_revision':state['revision'],'kind':'position'})
                st.session_state['goto_'+identity]={'page':mark['page'],'token':str(uuid4())};st.rerun()
            with st.form('editmark_'+mark['id']+'_'+str(mark['revision'])):
                text=st.text_area('修改标记内容',value=mark['body'])
                resolved=st.checkbox('疑问已解决',value=bool(mark['resolved']),disabled=mark['kind']!='question')
                save=st.form_submit_button('保存修改');hide=st.form_submit_button('移除标记')
            if save or hide:
                w.save_annotation(identity,mark['page'],mark['kind'],text,str(uuid4()),identity=mark['id'],revision=mark['revision'],resolved=resolved,deleted=hide);_done('标记已更新。')
        export.append(f"## 第 {mark['page']} 页 · {MARKS[mark['kind']]}\n\n{mark['body']}\n")
    st.download_button('导出文字标记 Markdown','\n'.join(export),file_name='课件标记.md',mime='text/markdown')
    st.caption('框选、区域荧光笔和手写保存在完整备份中。当前导出的是文字标记；原始 PDF 不会被修改。')


def courseware_order_controls(path, course_id, selected, all_courseware):
    order=[row['id'] for row in all_courseware]
    current=order.index(selected)+1
    with st.expander('调整课件顺序'):
        st.caption(f'当前是本课程第 {current} / {len(order)} 份课件。调整按完整课程列表生效，搜索和章节筛选不会改变排序范围。')
        up,down=st.columns(2)
        destination=None
        if up.button('↑ 上移',key='order_up_'+selected,disabled=current==1,width='stretch'):
            destination=current-1
        if down.button('↓ 下移',key='order_down_'+selected,disabled=current==len(order),width='stretch'):
            destination=current+1
        target=st.number_input('移至第几份',min_value=1,max_value=len(order),value=current,step=1,
                               key=f'order_target_{selected}_{current}_{len(order)}')
        if st.button('移动到此位置',key='order_move_'+selected,disabled=target==current):
            destination=target
        if destination is not None:
            MaterialService(path).move_courseware(course_id,selected,destination,expected_order=order)
            _done(f'课件已移至第 {destination} 份。')


def move_shelf_course(path, course_id, destination, expected_order, target_key=None):
    try:
        if target_key:destination=st.session_state[target_key]
        LearningService(path).move_course(course_id,destination,expected_order=expected_order)
    except ERRORS as exc:
        st.session_state._course_order_error=f'课程排序未完成：{exc}'
        return
    st.session_state.pop('_course_order_error',None)
    st.session_state['_m2_notice']=f'课程已移至第 {destination} 门。'


def course_order_controls(path, course_id):
    order=[row['id'] for row in LearningService(path).list_courses()]
    current=order.index(course_id)+1
    st.write('调整课程顺序')
    st.caption(f'当前第 {current} / {len(order)} 门，按所有未归档课程统一排序。')
    up,down=st.columns(2)
    up.button('↑ 课程上移',key='course_order_up_'+course_id,disabled=current==1,width='stretch',
              on_click=move_shelf_course,args=(path,course_id,current-1,order))
    down.button('↓ 课程下移',key='course_order_down_'+course_id,disabled=current==len(order),width='stretch',
                on_click=move_shelf_course,args=(path,course_id,current+1,order))
    target_key=f'course_order_target_{course_id}_{current}_{len(order)}'
    target=st.number_input('课程移至第几门',min_value=1,max_value=len(order),value=current,step=1,key=target_key)
    st.button('移动课程到此位置',key='course_order_move_'+course_id,disabled=target==current,
              on_click=move_shelf_course,args=(path,course_id,None,order,target_key))


def set_shelf_course_archived(path, course_id, expected_revision, archived):
    """Callbacks keep the revision shown before the confirmation was clicked."""
    try:
        updated=LearningService(path).set_course_archived(course_id,archived,expected_revision)
    except ERRORS as exc:
        st.session_state._course_removal_error=f'课程操作未完成：{exc}'
        return
    st.session_state.pop('_course_removal_error',None)
    st.session_state.pop('_shelf_target',None)
    if archived:
        st.session_state._last_removed_course={key:updated[key] for key in ('id','name','revision')}
        st.session_state._last_removed_course['database']=str(path)
        st.session_state._selected_course=None
        st.session_state.active_course=None
        st.session_state['_m2_notice']='课程已从书架移除并归档。学习内容与磁盘文件均已保留。'
    else:
        st.session_state.pop('_last_removed_course',None)
        navigate('课程书架',course_id)
        st.session_state['_m2_notice']='课程已恢复，原有课件、任务、笔记和阅读记录继续保留。'


def course_removal_notice(path):
    if '_course_removal_error' in st.session_state:
        st.error(st.session_state.pop('_course_removal_error'))
    removed=st.session_state.get('_last_removed_course')
    if not removed or removed.get('database')!=str(path):return
    current=LearningService(path).get_course(removed['id'])
    if not current['archived_at']:
        st.session_state.pop('_last_removed_course',None)
        return
    with st.container(border=True):
        st.write('已从书架移除课程：'+removed['name'])
        st.caption('课程内容和文件已保留。可在这里撤销，或到“课程管理”显示已归档课程后恢复。')
        if current['semester_archived_at']:
            st.info('所属学期已归档。请先在“学期管理”取消学期归档，再恢复课程。')
        st.button('撤销课程删除',key='undo_course_removal_'+removed['id'],
                  disabled=bool(current['semester_archived_at']),on_click=set_shelf_course_archived,
                  args=(path,removed['id'],removed['revision'],False))


def bookshelf(path):
    with st.container(key='shelf_workspace'):
        bookshelf_content(path)


def bookshelf_content(path):
    # Keep restoration available even after the last visible course is removed.
    if '_course_order_error' in st.session_state:
        st.error(st.session_state.pop('_course_order_error'))
    course_removal_notice(path)
    course=course_picker(path,'shelf_course',show_selector=False)
    if not course:
        st.header('课程书架')
        device_downloads(path)
        return
    with st.container(key='shelf_heading'):
        with st.container(horizontal=True,vertical_alignment='top',key='shelf_title_row'):
            st.header(course['name'])
            options=st.popover('课程选项',width=132)
        st.caption(' · '.join(v for v in (course['semester_name'],course['teacher']) if v))
    with options:
        device_downloads(path)
        course_order_controls(path,course['id'])
        st.divider()
        st.write('删除课程（可恢复）')
        st.write(course['name'])
        st.caption('从书架移除并归档此课程。课件文件、任务、笔记、阅读进度和标记继续保留，不删除磁盘文件。')
        st.caption('可撤销；也可在“课程管理”勾选“显示已归档课程与学期”，再取消课程归档恢复。')
        st.button('确认移除课程',key='remove_shelf_course_'+course['id'],
                  on_click=set_shelf_course_archived,args=(path,course['id'],course['revision'],True))
    if st.session_state.get('_shelf_course_id')!=course['id']:
        st.session_state.shelf_query=''
        st.session_state.shelf_chapter=None
        st.session_state.shelf_material=None
        st.session_state.shelf_edition=None
        st.session_state._shelf_course_id=course['id']
    target=st.session_state.pop('_shelf_target',None)
    if target:
        st.session_state.shelf_query=''
        st.session_state.shelf_chapter=None
        st.session_state.shelf_material=target['material']
        st.session_state.shelf_edition=target['edition']
    with st.container(horizontal=True,vertical_alignment='center',key='shelf_switcher'):
        material_column=st.container(width='stretch')
        tools=st.popover('课件工具',width=132)
    w=Workbench(path)
    removed=st.session_state.get('_last_removed_courseware')
    if removed and removed['course_id']==course['id']:
        with st.container(border=True):
            st.caption('已移除：'+removed['name']+'。课件文件、阅读进度和标记已保留。')
            if st.button('撤销移除',key='undo_remove_'+removed['id']):
                MaterialService(path).set_deleted(removed['id'],False)
                st.session_state.pop('_last_removed_courseware',None)
                st.session_state.shelf_query='';st.session_state.shelf_chapter=None
                st.session_state.shelf_material=removed['id']
                _done('课件已恢复到书架末尾。')
    all_materials=MaterialService(path).list_materials(course['id'])
    with tools:
        with st.expander('导入课件',expanded=not all_materials or st.session_state.get('_import_report_course')==course['id']):add_material(path,course['id'],'shelf_import')
        with st.expander('搜索与章节筛选'):
            query=st.text_input('搜索课件',key='shelf_query')
            chapter=chapter_picker(w,course['id'],'shelf_chapter')
    permitted=set(w.associations('chapter',chapter)) if chapter else None
    all_courseware=MaterialService(path).list_courseware(course['id'])
    matching={r['id'] for r in MaterialService(path).list_materials(course['id'],query)}
    rows=[r for r in all_courseware if r['id'] in matching and (permitted is None or r['id'] in permitted)]
    if rows:
        items={r['id']:r for r in rows}
        if st.session_state.get('shelf_material') not in items:st.session_state.shelf_material=next(iter(items))
        def material_label(identity):
            item=items[identity]
            if sum(r['name']==item['name'] for r in rows)>1:
                return f"{item['name']} · {item['created_at'][:10]} · {identity[:6]}"
            return item['name']
        with material_column:
            selected=st.selectbox('选择课件',list(items),format_func=material_label,key='shelf_material',label_visibility='collapsed')
        with tools:
            courseware_order_controls(path,course['id'],selected,all_courseware)
            with st.expander('移除课件'):
                st.write('从书架移除这份课件？')
                st.write(items[selected]['name'])
                st.caption('保留课件文件、阅读进度和标记。移除后可撤销，也可在资料管理中恢复。')
                if st.button('确认移除',key='remove_courseware_'+selected):
                    MaterialService(path).set_deleted(selected,True)
                    st.session_state._last_removed_courseware={key:items[selected][key] for key in ('id','course_id','name')}
                    _done('课件已从书架移除。')
        material=items[selected]
        editions=sorted([e for e in w.rows('reading_editions') if e['material_id']==selected],key=lambda e:e['created_at'],reverse=True)
        if editions:
            if len(editions)>1:
                lookup={e['id']:e for e in editions}
                if st.session_state.get('shelf_edition') not in lookup:st.session_state.shelf_edition=editions[0]['id']
                with tools:
                    with st.expander('选择其他阅读版本'):
                        edition_id=st.selectbox('阅读版本',list(lookup),key='shelf_edition',format_func=lambda i:f"{lookup[i]['created_at'][:19]} · {lookup[i]['page_count']} 页 · {i[:6]}")
                edition=lookup[edition_id]
            else:
                edition=editions[0]
            with tools:edition_tools(path,edition)
            read_edition(path,edition)
        else:
            st.info('这份课件还未准备阅读。请打开“课件工具”生成阅读副本，即可翻页和标记。')
        with tools:
            with st.expander('课件详情'):
                if not editions and material['storage_mode']=='managed_copy' and not material['file_deleted_at']:
                    assets=reader_assets(f"http://127.0.0.1:{st.get_option('server.port')}")
                    try:original_url=assets.register_download(path,material)
                    except (*ERRORS,ValueError):st.caption('原始课件暂不可下载，请检查文件状态或重新导入完整课件。')
                    else:st.link_button('下载原始课件',original_url,width='stretch')
                if material['managed_relpath'] and Path(material['original_path'])==path.parent/material['managed_relpath']:
                    st.caption('通过文件选择导入 · 完整课件已保存在学习库')
                elif not private_site():st.text(material['original_path'])
                details=' · '.join(v for v in (course['teacher'],course['schedule_text'],course['assessment']) if v)
                if details:st.caption(details)
                if not private_site() and st.button('使用系统程序打开原格式'):
                    source=storage.relative_file(path.parent,material['managed_relpath'],True) if material['managed_relpath'] else storage.check_source(material['reference_path'],True,db_path=path)
                    os.startfile(source)
            with st.expander('生成阅读副本 / 添加新版本',expanded=not editions):
                st.write('保存独立的 PDF 阅读副本并纳入完整备份。可选择已从 PowerPoint 导出的 PDF，原课件和旧阅读版本继续保留。')
                uploaded=st.file_uploader('选择已导出的 PDF',type=['pdf'],max_upload_size=200,key='manual_upload_'+selected)
                confirmed=st.checkbox('确认保存 PDF 阅读副本' if private_site() else '确认生成并保存本地 PDF 阅读副本',key='copy_'+selected)
                manual=None if private_site() else st.text_input('使用已导出的 PDF 路径（可选）',key='manual_'+selected)
                if st.button('生成阅读副本',disabled=not confirmed):
                    with st.spinner('生成并校验静态页面，PPT 转换最多等待两分钟…'):
                        w.create_edition(selected,str(uuid4()),local_copy_confirmed=confirmed,exported_pdf=manual or None,uploaded_pdf=uploaded.getvalue() if uploaded else None)
                    _done('阅读副本已保存，可以开始阅读和标记。')
    else:
        with material_column:st.caption('尚无可阅读课件')
        st.info('此课程下暂无符合条件的 PPT/PDF。请打开“课件工具”导入课件或调整筛选。')


def tasks(path):
    st.header('任务管理')
    scope=st.radio('显示任务',['待完成','已完成任务','全部'],horizontal=True,key='task_scope')
    if scope=='已完成任务':
        task_archive(path)
        return
    course=course_picker(path,'task_course')
    if not course:return
    w=Workbench(path);rows={r['id']:r for r in w.rows('tasks',course['id'])}
    if rows:
        visible=[r for r in rows.values() if scope=='全部' or r['status'] not in ('done','cancelled')]
        if visible and scope=='待完成':
            pending_task_list(path,visible,{course['id']:course},datetime.now(UTC))
        elif visible:
            st.dataframe([{'任务':r['title'],'类型':TASK_TYPES[r['task_type']],'状态':TASK_STATES[r['status']],
                '截止':task_deadline_label(r),'重要程度':'重要' if r['priority']=='high' else '正常'}
                for r in sorted(visible,key=task_deadline)],hide_index=True,width='stretch')
        else:st.success('这门课的任务都完成了。')
    else:st.caption('写下下一件要做的事，截止日期和其他信息可以稍后补充。')
    selected=st.selectbox('编辑任务',[None,*rows],format_func=lambda k:'＋ 新任务' if k is None else f"{TASK_STATES[rows[k]['status']]} · {rows[k]['title']}")
    r=rows.get(selected,{})
    t=token('task_token_'+str(selected)+'_'+str(r.get('revision')))
    with st.expander('编辑任务详情' if selected else '添加新任务',expanded=bool(selected) or not rows):
        with st.form('task_'+t):
            name=st.text_input('任务标题',value=r.get('title',''),placeholder='例如：完成第二章课后习题')
            a,b,c=st.columns(3)
            kind=a.selectbox('任务类型',list(TASK_TYPES),index=list(TASK_TYPES).index(r.get('task_type','assignment')),format_func=TASK_TYPES.get)
            status=b.selectbox('任务状态',list(TASK_STATES),index=list(TASK_STATES).index(r.get('status','todo')),format_func=TASK_STATES.get)
            priority=c.selectbox('重要程度',['normal','high'],index=1 if r.get('priority')=='high' else 0,format_func=lambda k:{'normal':'正常','high':'重要'}[k])
            due_kind=st.selectbox('截止方式',['none','date','datetime'],index=['none','date','datetime'].index(r.get('due_kind','none')),format_func=lambda k:{'none':'无截止时间','date':'当天结束前','datetime':'精确时间（北京时间）'}[k])
            due_local=datetime.fromisoformat(r['due_at_utc']).astimezone(TZ) if r.get('due_at_utc') else None
            due_default=date.fromisoformat(r['due_date']) if r.get('due_date') else (due_local.date() if due_local else None)
            a,b=st.columns(2)
            due=a.date_input('截止日期',value=due_default,format='YYYY-MM-DD',help='选择有截止时间的方式后，请在日历中选择日期；无截止时间时忽略此项。')
            due_time=b.time_input('截止时间（北京时间）',value=due_local.time() if due_local else '18:00',step=300,help='仅“精确时间”生效；可选择或输入小时和分钟。')
            planned=st.date_input('计划学习日期（可留空）',value=date.fromisoformat(r['planned_date']) if r.get('planned_date') else None,format='YYYY-MM-DD')
            with st.expander('耗时、备注与关联资料'):
                a,b=st.columns(2)
                estimated=a.number_input('预计耗时（分钟）',min_value=0,value=r.get('estimated_minutes') or 0)
                actual=b.number_input('实际耗时（分钟）',min_value=0,value=r.get('actual_minutes',0))
                remarks=st.text_area('备注',value=r.get('remarks',''))
                materials=material_picker(path,course['id'],'task_links_'+t,w.associations('task',selected) if selected else [])
            save=st.form_submit_button('保存任务',type='primary')
    if save:
        if due_kind!='none' and due is None:
            st.error('请选择截止日期，或将截止方式改为“无截止时间”。')
            return
        if due_kind=='datetime' and due_time is None:
            st.error('请选择截止时间（北京时间）。')
            return
        instant=None
        if due_kind=='datetime':
            moment=datetime.combine(due,due_time,tzinfo=TZ)
            # Minute-step widgets strip seconds. Preserve an existing exact
            # deadline when the user only edits other fields in this form.
            if due_local and due==due_local.date() and due_time==due_local.time().replace(second=0,microsecond=0):
                moment=due_local
            instant=moment.astimezone(UTC).isoformat()
        w.save_task(course['id'],dict(title=name,task_type=kind,due_kind=due_kind,due_date=due.isoformat() if due_kind=='date' else None,due_at_utc=instant,due_timezone='Asia/Shanghai' if instant else None,planned_date=planned.isoformat() if planned else None,priority=priority,status=status,estimated_minutes=estimated,actual_minutes=actual,remarks=remarks),materials,t,identity=selected,revision=r.get('revision'))
        st.session_state['task_token_'+str(selected)+'_'+str(r.get('revision'))]=str(uuid4());_done('任务已保存。')


def markdown(body):
    # Do not fetch images embedded in imported/user Markdown from remote hosts.
    body=re.sub(r'!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])?', '[图片引用未自动加载]',body)
    st.markdown(body,unsafe_allow_html=False)


def notes(path):
    st.header('笔记');course=course_picker(path,'note_course')
    if not course:return
    w=Workbench(path)
    with st.expander('搜索笔记'):query=st.text_input('搜索笔记标题')
    rows={r['id']:r for r in w.rows('notes',course['id']) if not r['deleted_at'] and query.lower() in r['title'].lower()}
    selected=st.selectbox('选择笔记',[None,*rows],format_func=lambda k:'＋ 新笔记' if k is None else rows[k]['title'])
    r=rows.get(selected,{})
    t=token('note_token_'+str(selected)+'_'+str(r.get('version')))
    body=w.note_body(selected) if selected else ''
    edit_tab,preview_tab=st.tabs(['编辑','阅读预览'])
    with edit_tab:
        with st.form('note_'+t):
            name=st.text_input('笔记标题',value=r.get('title',''),placeholder='给这条笔记起个名字')
            body=st.text_area('Markdown 正文',value=body,height=350,help=r'行内公式 $x^2$，独立公式使用 $$ 包围。')
            with st.expander('所属章节与关联资料'):
                chapter=chapter_picker(w,course['id'],'note_chapter_'+t,r.get('chapter_id'))
                materials=material_picker(path,course['id'],'note_links_'+t,w.associations('note',selected) if selected else [])
            save=st.form_submit_button('保存笔记',type='primary');preview=st.form_submit_button('预览草稿')
    if save:
        w.save_note(course['id'],name,body,chapter,materials,t,identity=selected,version=r.get('version'))
        st.session_state['note_token_'+str(selected)+'_'+str(r.get('version'))]=str(uuid4());_done('Markdown 笔记已保存；历史版本保留并纳入备份。')
    with preview_tab:
        st.caption('修改后先点击“保存笔记”或“预览草稿”，再切换到这里查看。')
        if body:markdown(body)
        else:st.caption('写下内容后，在这里查看排版和公式。')
        st.download_button('导出当前 Markdown',body,file_name='学习笔记.md',mime='text/markdown')
    if selected:
        with st.expander('历史版本'):
            with db.transaction(path,write=False) as c:versions=[dict(v) for v in c.execute('SELECT * FROM note_revisions WHERE note_id=? ORDER BY revision_no DESC',(selected,))]
            version=st.selectbox('查看历史版本',versions,format_func=lambda v:f"版本 {v['revision_no']} · {v['created_at'][:19]}")
            old=w.note_body(selected,version['id']);markdown(old)
            if st.button('将该版本恢复为新版本'):
                w.save_note(course['id'],r['title'],old,r['chapter_id'],w.associations('note',selected),str(uuid4()),identity=selected,version=r['version']);_done('已恢复为新版本；中间历史仍保留。')


def chapters(path):
    st.header('章节与知识点');course=course_picker(path,'chapter_course')
    if not course:return
    w=Workbench(path);rows={r['id']:r for r in w.rows('chapters',course['id'])}
    selected=st.selectbox('编辑章节',[None,*rows],format_func=lambda k:'＋ 新章节' if k is None else rows[k]['title'])
    r=rows.get(selected,{});t=token('chapter_'+str(selected)+'_'+str(r.get('revision')))
    with st.form('chapter_'+t):
        name=st.text_input('章节名称',value=r.get('title',''))
        position=st.number_input('章节顺序',min_value=0,value=r.get('position',0))
        materials=material_picker(path,course['id'],'chapter_links_'+t,w.associations('chapter',selected) if selected else [])
        save=st.form_submit_button('保存章节')
    if save:
        w.save_chapter(course['id'],name,materials,t,identity=selected,revision=r.get('revision'),position=position)
        st.session_state['chapter_'+str(selected)+'_'+str(r.get('revision'))]=str(uuid4());_done('章节已保存。')
    st.subheader('知识点')
    points={r['id']:r for r in w.rows('knowledge_points',course['id'])}
    if points:
        st.progress(sum(p['learning_state']=='mastered' for p in points.values())/len(points),text='已掌握知识点比例')
        st.dataframe([{'知识点':p['title'],'状态':KNOWLEDGE[p['learning_state']]} for p in points.values()],hide_index=True)
    selected=st.selectbox('编辑知识点',[None,*points],format_func=lambda k:'＋ 新知识点' if k is None else points[k]['title'])
    r=points.get(selected,{});t=token('knowledge_'+str(selected)+'_'+str(r.get('revision')))
    with st.form('knowledge_'+t):
        name=st.text_input('知识点名称',value=r.get('title',''))
        chapter=chapter_picker(w,course['id'],'knowledge_chapter_'+t,r.get('chapter_id'))
        state=st.selectbox('掌握状态',list(KNOWLEDGE),index=list(KNOWLEDGE).index(r.get('learning_state','not_started')),format_func=KNOWLEDGE.get)
        remarks=st.text_area('知识点备注',value=r.get('remarks',''))
        save=st.form_submit_button('保存知识点')
    if save:
        w.save_knowledge(course['id'],chapter,name,state,remarks,t,identity=selected,revision=r.get('revision'))
        st.session_state['knowledge_'+str(selected)+'_'+str(r.get('revision'))]=str(uuid4());_done('知识点已保存。')


def materials(path):
    st.header('资料管理');course=course_picker(path,'materials_course')
    if not course:return
    service=MaterialService(path)
    with st.expander('搜索与筛选'):
        query=st.text_input('搜索资料');hidden=st.checkbox('显示已隐藏资料')
    rows={r['id']:r for r in service.list_materials(course['id'],query,include_deleted=hidden)}
    if rows:
        selected=st.selectbox('查看资料',list(rows),format_func=lambda k:rows[k]['name'])
        with st.expander('文件详情与管理'):
            if private_site():
                row=rows[selected];st.text(row['name'])
                st.caption('完整文件已保存' if row['storage_mode']=='managed_copy' else '外部路径引用：迁移前请导入完整文件。')
                if row['deleted_at']:
                    if st.button('恢复资料'):service.set_deleted(selected,False);_done('资料已恢复。')
                elif st.button('从书架移除资料'):service.set_deleted(selected,True);_done('已移除并保留文件，可恢复。')
            else:_material_detail(service,rows[selected])
    with st.expander('导入课件',expanded=not rows):add_material(path,course['id'])
    if not private_site():
        with st.expander('高级：通过电脑路径添加'):
            st.caption('仅用于电脑本地路径与外部引用。日常 PPT/PDF 请使用上方文件选择导入。')
            add_path_material(path,course['id'])
    with st.expander('文件操作维护'):
        if st.button('核对未完成资料操作'):st.json(service.reconcile_operations())


def appearance_settings(root):
    st.header('外观设置')
    st.caption('更改按钮、边框和选中提示的强调色。页面与侧栏背景保持不变。')
    current=st.session_state.get('_plw_theme',ui_theme.DEFAULT)
    if st.session_state.get('_theme_choice_loaded')!=current:
        st.session_state.theme_choice=current
        st.session_state._theme_choice_loaded=current
    with st.form('appearance_settings'):
        selected=st.selectbox('主题强调色',list(ui_theme.PALETTES),format_func=lambda k:ui_theme.PALETTES[k]['label'],key='theme_choice')
        st.caption('保存到网站后会长期沿用。电脑和 iPad 刷新或重新打开后使用同一设置。')
        if st.form_submit_button('保存主题颜色',type='primary'):
            ui_theme.save_theme(root,selected)
            _done('主题强调色已更新。')
    if st.button('恢复默认绿色',disabled=current==ui_theme.DEFAULT):
        ui_theme.save_theme(root,ui_theme.DEFAULT)
        _done('已恢复默认绿色。')


def main():
    root=Path(os.environ.get('PLW_WORKSPACE',str(storage.PRODUCTION_ROOT)))
    storage.safe_path(root,directory=True)
    st.set_page_config(page_title='PLW · 个人学习工作台',page_icon='📘',layout='wide')
    st.set_option('client.toolbarMode','minimal')
    try:theme=ui_theme.load_theme(root);theme_warning=None
    except (storage.StorageError,OSError,ValueError,TypeError):theme=ui_theme.DEFAULT;theme_warning='主题设置暂不可用，已使用默认绿色；可在“外观设置”重新保存。'
    st.session_state._plw_theme=theme
    st.html('<style>'+interface_css('workbench.css')+'</style>')
    if not (root/'control/active.json').exists():
        st.sidebar.header('PLW')
        st.sidebar.caption('个人学习工作台')
        st.header('欢迎使用 PLW')
        st.write('先创建学习库，再添加学期和课程。随后可以导入 PDF、PPT/PPTX，在课程书架里阅读和标记。')
        if not private_site():
            st.text(f'学习数据目录：{root}')
            st.text(f'完整备份目录：{storage.BACKUP_ROOT if root==storage.PRODUCTION_ROOT else root/"backups"}')
        confirmed=st.checkbox('确认在上述学习数据目录创建新的空学习库')
        if st.button('创建学习库并开始',disabled=not confirmed,type='primary'):
            workspace.initialize_workspace(root);_done('学习库已创建。请先创建学期和课程。')
        st.caption('查看本页面不会初始化数据库，也不会导入任何文件。')
        return
    path=workspace.active_db(root)
    if st.session_state.get('dataset') not in (None,path.parent.name):
        st.session_state.clear()
    st.session_state._plw_theme=theme
    st.session_state.dataset=path.parent.name
    with closing_snapshot(path) as c:version=c.execute('PRAGMA user_version').fetchone()[0]
    if not db.schema_ready(version):
        st.warning('学习库需要升级到当前版本。升级前会创建完整备份。')
        if st.button('备份并升级学习库'):
            report=backups.create_backup(path)
            backups.restore_backup(root,report['path'],confirmation=path.parent.name)
            _done('已在新副本中验证并升级；旧数据与升级前完整备份已保留。')
        return
    # Keep the page's element positions stable when a one-shot notice appears
    # or disappears; otherwise nested panels collapse during uploads/reruns.
    with st.container(key='plw_notices'):
        if theme_warning:st.warning(theme_warning)
        for key in ('_m2_notice','flash'):
            if key in st.session_state:st.success(st.session_state.pop(key))
        if '_task_action_error' in st.session_state:st.error(st.session_state.pop('_task_action_error'))
    status=backups.recovery_status(root)
    if status['phase'] not in ('none','complete','rolled_back','failed') or (status['phase']=='failed' and status.get('switch_state')=='new_active'):
        st.warning('上次恢复尚未结束，请先核对或回滚。');st.session_state.navigation='数据与备份'
    page=navigation(path)
    if page=='今日学习':home(path)
    elif page=='课程书架':bookshelf(path)
    elif page=='任务管理':tasks(path)
    elif page=='笔记':notes(path)
    elif page=='章节与知识点':chapters(path)
    elif page=='课程管理':_courses_page(LearningService(path))
    elif page=='学期管理':_semesters_page(LearningService(path))
    elif page=='资料管理':materials(path)
    elif page=='外观设置':appearance_settings(root)
    elif page=='数据与备份':
        _backups_page(root,path)
        if not private_site():
            with st.expander('学习库位置'):
                st.text(f'学习数据：{root}')
                st.text(f'完整备份：{storage.BACKUP_ROOT if root==storage.PRODUCTION_ROOT else root/"backups"}')
        with st.expander('未完成的阅读副本与笔记操作'):
            w=Workbench(path);pending=[o for o in w.rows('content_operations') if o['state']!='committed']
            if pending:st.dataframe(pending,hide_index=True)
            else:st.caption('没有未完成内容操作。')
            if st.button('核对并重试提交内容'):st.write(w.recover_content())
            value=st.text_input('取消尚未生成目标文件的操作 ID')
            if st.button('取消未发布操作（保留暂存文件）'):w.cancel_content(value);_done('已取消未发布操作。')
    else:
        st.header('使用说明')
        st.markdown('1. 创建学期与课程。\n2. 在左侧展开“课程书架”，点击课程，再展开“导入课件”，点击“选择文件”，一次选择多份 PDF、PPT 或 PPTX。\n3. 点击“导入所选课件”，自动保存完整文件并准备阅读，然后点击“阅读刚导入的课件”。\n4. 在任务、章节和笔记中关联同一课程资料。\n5. 定期创建完整备份，并把备份目录另存到其他磁盘。')
        st.write('课件顺序：选择框下展开“调整课件顺序”，可上移、下移或移至第几份。阅读默认整页适配；左侧预览可跳页，两侧箭头可翻页。Ctrl＋滚轮或缩放滑杆可连续缩放，整页适配可一键恢复。')
        st.write('PPT 静态转换使用本机 PowerPoint；也可手动导出 PDF 后导入。荧光笔为区域标记，扫描件同样可用。公式支持 Markdown 中的 $…$ 和 $$…$$。')
        st.write('课程选项中可调整课程顺序，或删除课程（可恢复）；课件可单独移除并撤销。首页任务按截止时间排列，逾期标记加深，重要程度分正常与重要。')
        st.write('点击待办右侧“完成”，任务会移入“已完成任务”存档，保留完成时间、备注与关联资料。首页和任务管理均可打开存档；误点时可“恢复待办”。完整备份包含已完成任务。')
        st.write('“下载与离线阅读”可将 PDF 和托管原件保存到设备；提前保存到手机或 iPad 的“文件”后可断网打开。PDF 不包含 PLW 标记，离线修改暂不自动同步。上传完整课件无需提供电脑原始路径。')
        st.write('“图片文字识别（OCR）”支持扫描页和上传图片的本机中英文识别，识别后可搜索跳页或导出文字。“动画与视频”支持 PPTX 内嵌视频与动画视频回放；生成后在网页中播放。动态交互和逐步点击仍需 PowerPoint。')
        st.write('原件更新后请添加新阅读版本；旧版与旧标记继续保留。OCR 和播放缓存可重新生成，不纳入完整备份；托管原课件仍完整备份。触控笔压感、批注写回 PDF 留待后续优化。')
        st.caption(f'版本 {db.APP_VERSION} · 个人学习工作台 · Personal Learning Workbench')


def closing_snapshot(path):
    from contextlib import closing
    return closing(db.connect_snapshot(path))


def run():
    try:main()
    except (*ERRORS,ValueError,KeyError,TypeError) as exc:
        st.error(f'操作未完成：{exc}')
        st.caption('原数据和已保存版本继续保留。请检查输入；未完成操作可在“数据与备份”核对。')
