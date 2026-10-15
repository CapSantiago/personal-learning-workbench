"""Local synthetic M2 interface; mutations require explicit user actions."""
from pathlib import Path
import sqlite3
from uuid import uuid4

import streamlit as st

from . import backups, config, db, locking, storage, workspace
from .materials import MaterialService, MaterialError
from .services import LearningService, LearningError
from .ui import _courses_page, _semesters_page

ERRORS = (backups.BackupError, MaterialError, LearningError, db.DatabaseError,
          locking.LockError, storage.StorageError, workspace.WorkspaceError, OSError, sqlite3.Error)
TYPES = {'slides': '课件', 'textbook': '教材', 'assignment': '作业说明', 'lab_guide': '实验指导', 'exam_paper': '试卷', 'code': '代码资料', 'other': '其他'}
STATES = {'normal': '正常', 'missing': '缺失', 'inaccessible': '不可访问', 'possibly_changed': '内容可能变化', 'unchecked': '未检查'}
IMPORT_STATES = {'ready': '已就绪', 'pending': '未完成', 'failed': '失败'}
MODES = {'managed_copy': '托管复制（原文件保留）', 'external_reference': '外部引用（只保存路径）'}


def _done(text):
    st.session_state['_m2_notice'] = text
    st.rerun()


def _error(error):
    st.error(f'操作未完成：{error}')


def _samples(root):
    location = storage.safe_path(root / 'sources', directory=True)
    location.mkdir(parents=True, exist_ok=True)
    for name, text in [('合成 控制原理.txt', '这是 PLW M2 合成托管资料。\n传递函数与闭环控制。\n'), ('合成 外部参考.txt', '这是 PLW M2 合成外部引用。\n原文保持不变。\n')]:
        path = storage.safe_path(location / name, directory=False)
        expected = text.encode('utf-8')
        if path.exists():
            if path.read_bytes() != expected:
                raise storage.StorageError('已有合成样例内容不同，保留现有文件，不覆盖。')
        else:
            with path.open('xb') as target:
                target.write(expected)


def _material_detail(service, row):
    st.subheader('资料详情')
    st.text(f"{row['name']} · {row['id']}")
    st.text(f"存储：{MODES[row['storage_mode']]}；状态：{STATES[row['file_status']]}；导入：{IMPORT_STATES[row['import_state']]}")
    st.text(f"原始路径：{row['original_path']}")
    st.text(f"当前路径：{row['reference_path'] or str(service.db_path.parent / row['managed_relpath'])}")
    st.text(f"大小：{row['size_bytes']} 字节；最近检查：{row['last_checked_at'] or '未检查'}")
    with st.expander('校验值与关联'):
        st.text(f"导入基线 SHA-256：{row['baseline_sha256'] or '未计算'}")
        st.text(f"最近观察 SHA-256：{row['observed_sha256'] or '未计算'}")
        counts = service.association_counts(row['id'])
        st.text(f"关联：{counts['tasks']} 个任务、{counts['notes']} 篇笔记、{counts['chapters']} 个章节")
        duplicates = service.find_duplicates(row['id'])
        if duplicates:
            st.info('发现内容校验值相同的资料。各记录和文件独立保留，可以按需要隐藏多余索引。')
            st.dataframe([{'名称': x['name'], '资料 ID': x['id']} for x in duplicates], hide_index=True)
    left, right = st.columns(2)
    if left.button('完整检查文件状态', key=f"check_{row['id']}"):
        checked = service.check_material(row['id'], full_hash=True)
        _done(f"检查完成：{STATES[checked['file_status']]}。")
    if right.button('恢复资料记录' if row['deleted_at'] else '隐藏资料记录（保留文件）', key=f"hide_{row['id']}"):
        service.set_deleted(row['id'], not bool(row['deleted_at']))
        _done('资料索引显示状态已更新，磁盘文件未删除。')
    if row['storage_mode'] == 'external_reference':
        with st.expander('重新定位外部引用'):
            with st.form(f"relink_{row['id']}"):
                new_path = st.text_input('新的外部文件路径', value=row['reference_path'])
                changed = st.checkbox('允许指向不同内容；保留原始基线并标记内容可能变化')
                submit = st.form_submit_button('更新引用路径')
            if submit:
                service.relink_reference(row['id'], new_path, confirm_changed=changed)
                _done('引用路径已更新，原始来源和内容基线已保留。')
    elif row['deleted_at'] and not row['file_deleted_at']:
        with st.expander('永久删除托管副本（需单独确认）'):
            st.warning('仅删除这份托管副本，保留删除记录与原始来源。存在任务、笔记或章节关联时不能删除。')
            st.text(f"确认范围：{row['id']} · {row['managed_relpath']}")
            with st.form(f"physical_delete_{row['id']}"):
                confirmation = st.text_input('输入资料 ID 确认删除')
                submit = st.form_submit_button('永久删除托管副本')
            if submit:
                service.delete_managed_file(row['id'], confirmation=confirmation)
                _done('已删除经确认的托管副本，原始来源保持不变。')
    elif row['file_deleted_at']:
        st.info('这份托管正文已被单独确认删除；删除记录仍保留。')


def _materials_page(root, path):
    st.header('资料管理')
    service = MaterialService(path)
    courses = LearningService(path).list_courses(include_archived=True)
    lookup = {row['id']: row for row in courses}
    selected = st.selectbox('筛选资料课程', [None, *lookup], format_func=lambda i: '全部课程' if i is None else f"{lookup[i]['name']} · {i[:6]}")
    query = st.text_input('搜索资料')
    deleted = st.checkbox('显示已隐藏资料')
    rows = service.list_materials(course_id=selected, query=query, include_deleted=deleted)
    if rows:
        st.dataframe([{'资料': r['name'], '模式': MODES[r['storage_mode']], '状态': STATES[r['file_status']], '导入': IMPORT_STATES[r['import_state']], '已隐藏': bool(r['deleted_at'])} for r in rows], hide_index=True, width='stretch')
        by_id = {r['id']: r for r in rows}
        identity = st.selectbox('查看资料', list(by_id), format_func=lambda i: f"{by_id[i]['name']} · {i[:6]}")
        _material_detail(service, by_id[identity])
    else:
        st.info('没有符合条件的资料。')
    st.divider()
    st.subheader('添加资料')
    st.caption('每次提交一个文件，可单独选择复制或引用。目前来源仅允许项目合成 sources 目录。')
    if st.button('生成合成来源样例'):
        _samples(root)
        _done('合成来源样例已就绪，已有文件不会覆盖。')
    active = {r['id']: r for r in courses if not r['archived_at'] and not r['semester_archived_at']}
    if active:
        token = st.session_state.setdefault('m2_import_token', str(uuid4()))
        with st.form(f'import_{token}'):
            course_id = st.selectbox('资料所属课程', list(active), format_func=lambda i: f"{active[i]['name']} · {i[:6]}")
            source = st.text_input('来源文件路径', value=str(root / 'sources' / '合成 控制原理.txt'))
            mode = st.selectbox('存储方式', list(MODES), format_func=MODES.get)
            name = st.text_input('资料名称（留空使用文件名）')
            kind = st.selectbox('资料类型', list(TYPES), format_func=TYPES.get)
            submit = st.form_submit_button('添加资料', type='primary')
        if submit:
            result = service.import_file(course_id, source, mode, name=name or None, material_type=kind, request_id=token)
            _done(f"资料已保存：{result['name']}。相同请求再次提交不会重复添加。")
        if st.button('继续添加另一份资料'):
            st.session_state['m2_import_token'] = str(uuid4())
            st.rerun()
    else:
        st.info('先创建一个未归档的学期和课程，再添加资料。')
    with st.expander('核对未完成文件操作'):
        st.write('只核对已记录的内部操作。不会重新复制来源、删除未知残留或清理失败文件。失败或隔离记录未解决前，完整备份会停止。')
        if st.button('核对文件操作'):
            st.session_state['m2_reconcile'] = service.reconcile_operations()
        if 'm2_reconcile' in st.session_state:
            st.json(st.session_state['m2_reconcile'])


def _backup_summary(report, label):
    st.text(f"{label}：{report['path']}")
    st.text(f"已验证 {report['count']} 个内部文件，合计 {report['size_bytes']:,} 字节；{len(report['external'])} 份外部引用仅保留索引。")
    if report.get('reading_pdfs'):
        st.text(f"已包含 {len(report['reading_pdfs'])} 份 PDF 阅读副本；文字/图形标记及阅读进度包含在数据库中。")
        with st.expander('已包含的阅读副本'):
            st.dataframe([{'阅读版本':r['entity_id'],'内部路径':r['relative_path'],'字节':r['size_bytes'],'包含在备份':'是'} for r in report['reading_pdfs']],hide_index=True)
    if report['external']:
        st.dataframe([{'外部文件路径': x['reference_path'], '正文包含在备份': '否', '上次记录状态': STATES.get(x['recorded_status'], x['recorded_status']), '上次检查': x['last_checked_at'] or '未检查'} for x in report['external']], hide_index=True, width='stretch')
        st.caption('备份与恢复不会读取外部原文件；表中状态来自数据库上次检查记录。')
    if report['deleted']:
        st.caption(f"另有 {len(report['deleted'])} 份托管正文曾被明确确认删除，删除记录保留。")
    with st.expander(f'{label}的校验详情'):
        st.json(report)


def _backups_page(root, path):
    import os
    if os.environ.get('PLW_PRIVATE_SITE') == '1':
        from .ui_cloud_backup import panel
        return panel(root, path)
    st.header('数据与备份')
    current_id = path.parent.name if path else 'EMPTY'
    st.text(f'当前数据集：{current_id}')
    st.caption('完整备份包含数据库、保留的托管正文及全部笔记版本；外部引用正文不包含，逐条列入报告。')
    if path and st.button('创建完整备份', type='primary'):
        with st.spinner('冻结写入，复制并独立验证备份…'):
            report = backups.create_backup(path)
        st.session_state['m2_backup_path'] = report['path']
        st.session_state['m2_backup_report'] = report
    if 'm2_backup_report' in st.session_state:
        st.success('完整备份已验证。外部引用只备份索引。')
        _backup_summary(st.session_state['m2_backup_report'], '新备份')
    st.subheader('验证与恢复备份')
    backup_path = st.text_input('备份目录路径', key='m2_backup_path')
    if st.button('验证并预览备份'):
        with st.spinner('检查清单、文件校验值、数据库及关系…'):
            report = backups.verify_backup(backup_path)
        st.session_state['m2_restore_preview'] = {'report': report, 'path': str(Path(backup_path)), 'dataset_id': current_id}
    preview = st.session_state.get('m2_restore_preview')
    if preview:
        _backup_summary(preview['report'], '待恢复备份')
        st.warning('恢复将切换整套数据集。先生成恢复前完整副本，再恢复到新目录并验证；旧数据集与副本继续保留。外部原文件不会写回。')
        st.text(f"确认切换范围：{preview['dataset_id']} → 新数据集；来源备份：{preview['path']}")
        with st.form('restore_confirm'):
            confirm = st.text_input('输入当前数据集 ID 确认恢复')
            submitted = st.form_submit_button('恢复并切换数据集')
        if submitted:
            if str(Path(backup_path)) != preview['path']:
                raise backups.RestoreError('备份路径已改变，请重新预览。')
            if confirm != preview['dataset_id']:
                raise backups.RestoreError('确认值必须与预览的数据集完全一致。')
            storage.safe_path(root, directory=True).mkdir(parents=True, exist_ok=True)
            with st.spinner('保留旧数据、恢复并验证新数据集…'):
                backups.restore_backup(root, backup_path, confirmation=confirm, expected_manifest_sha256=preview['report']['manifest_sha256'])
            _done('恢复验证完成，已切换到新数据集；旧数据及恢复前副本保留。')
    status = backups.recovery_status(root)
    if status['phase'] != 'none':
        st.subheader('恢复状态与回滚')
        labels = {'preparing': '正在准备', 'old_preserved': '旧数据已保留', 'copying': '正在恢复文件', 'ready_to_switch': '等待切换', 'complete': '恢复完成', 'failed': '上次操作未完成', 'rolling_back': '回滚待核对', 'rolled_back': '已回滚'}
        st.text(f"恢复状态：{labels.get(status['phase'], '未知，需要核对')}。旧数据和副本均保留。")
        with st.expander('恢复记录与诊断详情'):
            st.json(status)
        with st.form('recovery_confirm'):
            confirm = st.text_input('输入当前数据集 ID 确认维护操作')
            reconcile = st.form_submit_button('核对并结束中断维护')
            rollback = st.form_submit_button('保存当前副本并回滚', disabled=not status.get('can_rollback'))
        if reconcile:
            backups.reconcile_restore(root, confirmation=confirm)
            _done('恢复状态核对完成；所有旧数据集和诊断文件仍保留。')
        if rollback:
            with st.spinner('备份当前数据，验证旧数据并切回…'):
                backups.rollback_restore(root, confirmation=confirm)
            _done('已回滚到恢复前数据集，并保留回滚前的完整副本。')


def main(workspace_root=None):
    root = Path(workspace_root) if workspace_root else config.DEFAULT_WORKSPACE
    st.set_page_config(page_title='PLW · 学习工作台', page_icon='📘', layout='wide')
    path = None
    startup_error = None
    try:
        if (root / 'control' / 'active.json').exists():
            path = workspace.active_db(root)
        new_id = path.parent.name if path else None
        previous = st.session_state.get('m2_dataset_id')
        if previous and previous != new_id:
            notice = st.session_state.get('_m2_notice', '活动数据集已切换，已重新载入表单。')
            st.session_state.clear()
            st.session_state['_m2_notice'] = notice
        st.session_state['m2_dataset_id'] = new_id
    except ERRORS as exc:
        startup_error = exc
    st.title('Personal Learning Workbench')
    st.caption('课程、资料与备份，在本机有序保存。')
    st.sidebar.header('PLW')
    st.sidebar.info('M2 合成验收模式。资料来源与数据库仅限项目沙盒；尚未启用真实学习数据目录。')
    page = st.sidebar.radio('导航', ['课程工作台', '学期管理', '资料管理', '数据与备份', '项目进度'], key='navigation')
    if '_m2_notice' in st.session_state:
        st.success(st.session_state.pop('_m2_notice'))
    if 'flash' in st.session_state:
        st.success(st.session_state.pop('flash'))
    if startup_error:
        _error(startup_error)
        st.stop()
    if path is None:
        st.subheader('准备 M2 合成工作区')
        st.write('首次创建会建立独立数据集。原 M1 数据保持原状，普通查看不会初始化。')
        if st.button('创建 M2 合成工作区', type='primary'):
            try:
                workspace.initialize_workspace(root)
                _done('M2 合成工作区已创建，请添加验收用学期和课程。')
            except ERRORS as exc:
                _error(exc)
        if page == '数据与备份':
            try:
                _backups_page(root, None)
            except ERRORS as exc:
                _error(exc)
        st.stop()
    try:
        status = backups.recovery_status(root)
        if status['phase'] not in ('none', 'complete', 'rolled_back', 'failed') or (status['phase'] == 'failed' and status.get('switch_state') == 'new_active'):
            st.warning('检测到未完成恢复。先在本页核对状态或回滚，再继续学习数据操作。')
            page = '数据与备份'
        if page == '课程工作台':
            _courses_page(LearningService(path))
        elif page == '学期管理':
            _semesters_page(LearningService(path))
        elif page == '资料管理':
            _materials_page(root, path)
        elif page == '数据与备份':
            _backups_page(root, path)
        else:
            st.header('项目进度')
            st.write('M2：逐文件复制或引用、状态核对、逻辑隐藏、完整备份、暂存恢复与回滚。')
            st.write('下一阶段 M3：任务、截止时间和多资料关联。正式笔记编辑、公式与 PDF 阅读仍在 M4。')
            st.caption('M0 和 M1 可通过启动器 --m0 / --m1 单独运行；本轮仍不创建真实学习数据目录。')
    except ERRORS as exc:
        _error(exc)
