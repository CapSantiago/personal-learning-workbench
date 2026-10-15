"""Semester/course UI. Queries never initialize data; every write is explicit."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from uuid import uuid4

import streamlit as st

from plw import config, db
from plw.services import LearningService, LearningError

STATUSES = {"planned": "计划中", "active": "学习中", "completed": "已结课", "paused": "暂停"}
ERRORS = (LearningError, db.DatabaseError, sqlite3.Error, OSError)


def _semester_label(row: dict, rows: list[dict]) -> str:
    if sum(other["name"] == row["name"] for other in rows) < 2:
        return row["name"]
    dates = f"{row['start_date'] or '?'} 至 {row['end_date'] or '?'}"
    return f"{row['name']} · {dates} · {row['id'][:6]}"


def _error(exc: Exception) -> None:
    st.error(f"操作未完成：{exc}")


def _done(message: str) -> None:
    st.session_state["flash"] = message
    st.rerun()


def _snapshot(kind: str, row: dict) -> dict:
    key = f"{kind}_snapshot"
    if key not in st.session_state or st.session_state[key]["row"]["id"] != row["id"]:
        st.session_state[key] = {"row": dict(row), "token": str(uuid4())}
    return st.session_state[key]


def _reload(kind: str, row: dict) -> None:
    st.session_state[f"{kind}_snapshot"] = {"row": dict(row), "token": str(uuid4())}


def _new_semester(service: LearningService) -> None:
    token = st.session_state.setdefault("semester_create_token", str(uuid4()))
    with st.form(f"semester_new_{token}"):
        name = st.text_input("学期名称", key=f"semester_new_name_{token}", placeholder="例如：2026 秋季", max_chars=200)
        left, right = st.columns(2)
        start = left.text_input("开始日期（可留空）", key=f"semester_new_start_{token}", placeholder="2026-09-01")
        end = right.text_input("结束日期（可留空）", key=f"semester_new_end_{token}", placeholder="2027-01-31")
        submit = st.form_submit_button("创建学期", type="primary")
    if submit:
        try:
            service.create_semester(name, start or None, end or None, request_id=token)
            _done("学期已保存。")
        except ERRORS as exc:
            _error(exc)
    if st.button("继续新建学期", key="another_semester"):
        st.session_state["semester_create_token"] = str(uuid4())
        st.rerun()


def _semester_detail(service: LearningService, row: dict) -> None:
    snap = _snapshot("semester", row)
    original = snap["row"]
    token = snap["token"]
    if row["revision"] != original["revision"]:
        st.warning("这个学期已在其他页面更新。当前编辑内容仍保留，请重新载入后再保存。")
    archived = row["archived_at"] is not None
    if archived:
        st.info("该学期已归档，所属课程仍保留。取消归档后可以继续编辑。")
    with st.form(f"semester_edit_{token}"):
        name = st.text_input("修改学期名称", value=original["name"], key=f"semester_edit_name_{token}", disabled=archived, max_chars=200)
        left, right = st.columns(2)
        start = left.text_input("修改开始日期", value=original["start_date"] or "", key=f"semester_edit_start_{token}", disabled=archived)
        end = right.text_input("修改结束日期", value=original["end_date"] or "", key=f"semester_edit_end_{token}", disabled=archived)
        save = st.form_submit_button("保存学期修改", disabled=archived)
    if save:
        try:
            updated = service.update_semester(row["id"], original["revision"], name=name, start_date=start or None, end_date=end or None)
            _reload("semester", updated)
            _done("学期修改已保存。")
        except ERRORS as exc:
            _error(exc)
    left, right = st.columns(2)
    if left.button("取消学期归档" if archived else "归档学期", key=f"semester_archive_{row['id']}"):
        try:
            updated = service.set_semester_archived(row["id"], not archived, original["revision"])
            _reload("semester", updated)
            _done("学期已取消归档。" if archived else "学期已归档，课程仍保留。")
        except ERRORS as exc:
            _error(exc)
    if right.button("放弃编辑并重新载入学期", key="reload_semester"):
        _reload("semester", service.get_semester(row["id"]))
        st.rerun()


def _semesters_page(service: LearningService) -> None:
    st.header("学期管理")
    search, archive = st.columns([3, 1], vertical_alignment="bottom")
    query = search.text_input("搜索学期", key="semester_query", placeholder="输入名称")
    include = archive.checkbox("显示已归档学期", key="semester_include_archived")
    rows = service.list_semesters(query=query, include_archived=include)
    if rows:
        table = []
        for row in rows:
            item = {"学期": row["name"]}
            if any(x["start_date"] for x in rows):
                item["开始"] = row["start_date"] or "—"
            if any(x["end_date"] for x in rows):
                item["结束"] = row["end_date"] or "—"
            if include:
                item["状态"] = "已归档" if row["archived_at"] else "使用中"
            table.append(item)
        st.dataframe(table, hide_index=True, width="stretch")
        by_id = {x["id"]: x for x in rows}
        with st.expander("编辑学期", expanded=False):
            selected = st.selectbox("选择要查看的学期", list(by_id), format_func=lambda i: _semester_label(by_id[i], rows), key="semester_selected")
            _semester_detail(service, by_id[selected])
    else:
        st.info("没有符合条件的学期。可以调整筛选或创建一个新学期。")
    with st.expander("新建学期", expanded=not service.list_semesters(include_archived=True)):
        _new_semester(service)


def _course_fields(prefix: str, semesters: list[dict], row: dict | None = None, disabled: bool = False) -> dict:
    row = row or {}
    lookup = {x["id"]: x for x in semesters}
    ids = list(lookup)
    default = ids.index(row["semester_id"]) if row.get("semester_id") in ids else 0
    left, right = st.columns([2, 1])
    name = left.text_input("课程名称", value=row.get("name", ""), key=f"{prefix}_name", max_chars=200, disabled=disabled)
    semester = right.selectbox("所属学期", ids, index=default, format_func=lambda i: _semester_label(lookup[i], semesters), key=f"{prefix}_semester", disabled=disabled)
    left, right = st.columns(2)
    teacher = left.text_input("教师", value=row.get("teacher", ""), key=f"{prefix}_teacher", disabled=disabled)
    credit_value = None if "credits" in row and row["credits"] is None else float(row.get("credits", 0))
    credits = right.number_input("学分", min_value=0.0, max_value=100.0, value=credit_value, step=0.5, key=f"{prefix}_credits", disabled=disabled, placeholder="未设置")
    left, right = st.columns(2)
    schedule = left.text_input("上课时间", value=row.get("schedule_text", ""), placeholder="例如：周二 3–4 节", key=f"{prefix}_schedule", disabled=disabled)
    assessment = right.text_input("考核方式", value=row.get("assessment", ""), placeholder="例如：实验 40% + 期末 60%", key=f"{prefix}_assessment", disabled=disabled)
    statuses = list(STATUSES)
    status = st.selectbox("课程状态", statuses, index=statuses.index(row.get("status", "planned")), format_func=lambda v: STATUSES[v], key=f"{prefix}_status", disabled=disabled)
    remarks = st.text_area("备注", value=row.get("remarks", ""), key=f"{prefix}_remarks", disabled=disabled)
    return dict(semester_id=semester, name=name, teacher=teacher, credits=credits, schedule_text=schedule, assessment=assessment, status=status, remarks=remarks)


def _new_course(service: LearningService) -> None:
    semesters = service.list_semesters()
    if not semesters:
        st.info("请先到“学期管理”创建或取消归档一个学期。")
        return
    token = st.session_state.setdefault("course_create_token", str(uuid4()))
    with st.form(f"course_new_{token}"):
        fields = _course_fields(f"course_new_{token}", semesters)
        submit = st.form_submit_button("创建课程", type="primary")
    if submit:
        try:
            service.create_course(**fields, request_id=token)
            _done("课程已保存。")
        except ERRORS as exc:
            _error(exc)
    if st.button("继续新建课程", key="another_course"):
        st.session_state["course_create_token"] = str(uuid4())
        st.rerun()


def _course_detail(service: LearningService, row: dict) -> None:
    st.subheader(row["name"])
    details = [row["semester_name"], STATUSES[row["status"]]]
    if row["credits"] is not None:
        details.append(f"{row['credits']:g} 学分")
    if row["teacher"]:
        details.append(row["teacher"])
    st.caption(" · ".join(details))
    if row["schedule_text"]:
        st.text(f"上课时间：{row['schedule_text']}")
    if row["assessment"]:
        st.text(f"考核方式：{row['assessment']}")
    if row["remarks"]:
        st.text(row["remarks"])
    snap = _snapshot("course", row)
    original = snap["row"]
    token = snap["token"]
    if row["revision"] != original["revision"]:
        st.warning("这门课程已在其他页面更新。当前编辑内容仍保留，请重新载入后再保存。")
    archived = row["archived_at"] is not None
    parent_archived = row["semester_archived_at"] is not None
    if archived or parent_archived:
        st.info("该课程或所属学期已归档。历史信息仍可查看；先取消归档再编辑。")
    semesters = [s for s in service.list_semesters(include_archived=True) if s["archived_at"] is None or s["id"] == original["semester_id"]]
    with st.expander("编辑课程", expanded=False):
        with st.form(f"course_edit_{token}"):
            fields = _course_fields(f"course_edit_{token}", semesters, original, disabled=archived or parent_archived)
            save = st.form_submit_button("保存课程修改", disabled=archived or parent_archived)
        if save:
            try:
                updated = service.update_course(row["id"], original["revision"], **fields)
                _reload("course", updated)
                _done("课程修改已保存。")
            except ERRORS as exc:
                _error(exc)
        left, right = st.columns(2)
        if left.button("取消课程归档" if archived else "归档课程", key=f"course_archive_{row['id']}", disabled=parent_archived):
            try:
                updated = service.set_course_archived(row["id"], not archived, original["revision"])
                _reload("course", updated)
                _done("课程已取消归档。" if archived else "课程已归档，历史数据保留。")
            except ERRORS as exc:
                _error(exc)
        if right.button("放弃编辑并重新载入课程", key="reload_course"):
            _reload("course", service.get_course(row["id"]))
            st.rerun()


def _courses_page(service: LearningService) -> None:
    st.header("课程管理")
    semesters = service.list_semesters(include_archived=True)
    active = service.list_courses()
    history = service.list_courses(include_archived=True)
    st.caption(f"{len(active)} 门课程 · {sum(x['archived_at'] is None for x in semesters)} 个学期")
    search, semester_filter, archive = st.columns([2, 1, 1], vertical_alignment="bottom")
    query = search.text_input("搜索课程", placeholder="名称、教师或备注", key="course_query")
    include = archive.checkbox("显示已归档课程与学期", key="course_include_archived")
    selectable = {x["id"]: x for x in semesters if include or x["archived_at"] is None}
    selected_semester = semester_filter.selectbox("筛选学期", [None, *selectable], format_func=lambda i: "所有学期" if i is None else _semester_label(selectable[i], list(selectable.values())), key="course_semester_filter")
    rows = service.list_courses(semester_id=selected_semester, query=query, include_archived=include)
    if rows:
        table = []
        for row in rows:
            item = {"课程": row["name"], "学期": row["semester_name"], "状态": STATUSES[row["status"]]}
            if any(x["teacher"] for x in rows):
                item["教师"] = row["teacher"] or "—"
            if any(x["credits"] is not None for x in rows):
                item["学分"] = row["credits"]
            if include:
                item["归档"] = "已归档" if row["archived_at"] or row["semester_archived_at"] else "—"
            table.append(item)
        st.dataframe(table, hide_index=True, width="stretch")
        by_id = {x["id"]: x for x in rows}
        semester_lookup = {s["id"]: s for s in semesters}
        def course_label(identifier):
            item = by_id[identifier]
            label = f"{item['name']} · {_semester_label(semester_lookup[item['semester_id']], semesters)}"
            if sum(x["name"] == item["name"] and x["semester_id"] == item["semester_id"] for x in rows) > 1:
                label += f" · {identifier[:6]}"
            return label
        selected = st.selectbox("打开课程主页", list(by_id), format_func=course_label, key="course_selected")
        _course_detail(service, by_id[selected])
    else:
        st.info("没有符合条件的课程。可以调整筛选，或先创建学期再添加课程。")
    with st.expander("新建课程", expanded=not history):
        _new_course(service)


def main(db_path: Path | None = None) -> None:
    path = Path(db_path) if db_path is not None else config.DEFAULT_DB_PATH
    st.set_page_config(page_title="PLW · 课程工作台", page_icon="📘", layout="wide")
    st.title("Personal Learning Workbench")
    st.caption("让课程、资料与下一步学习任务各有归处。")
    st.sidebar.header("PLW")
    st.sidebar.info("M1 验收模式：仅使用独立合成数据，暂不导入真实学习资料。")
    page = st.sidebar.radio("导航", ["课程工作台", "学期管理", "项目进度"], key="navigation")
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))
    if not path.exists():
        st.subheader("准备 M1 验收数据集")
        st.write("首次使用需要显式创建一个空的合成数据库，之后可以添加验收用学期和课程。")
        if st.button("创建 M1 验收数据集", type="primary", key="initialize_m1"):
            try:
                db.initialize(path)
                _done("M1 验收数据集已创建。请先到学期管理添加一个学期。")
            except ERRORS as exc:
                _error(exc)
        st.stop()
    try:
        service = LearningService(path)
        service.list_semesters()  # Read-only schema/version check; never initialize or migrate.
    except ERRORS as exc:
        _error(exc)
        st.write("当前数据库不会被重建或覆盖。仅可检查并应用程序支持的迁移。")
        if st.button("检查并应用受支持迁移", key="migrate_m1"):
            try:
                db.initialize(path)
                _done("数据库版本已检查并更新。")
            except ERRORS as migration_error:
                _error(migration_error)
        st.stop()
    try:
        if page == "课程工作台":
            _courses_page(service)
        elif page == "学期管理":
            _semesters_page(service)
        else:
            st.header("项目进度")
            st.success("M1：学期、课程、查询、归档与数据库版本管理。")
            st.write("M2 将接入文件管理和完整备份恢复；M3 接入任务；M4 接入章节、笔记、公式与 PDF。")
            st.write("M0 文件与公式探针已保留，可以通过启动器的 --m0 参数单独运行。")
            st.caption("本轮没有真实资料导入、物理文件删除或数据库重置入口。")
    except ERRORS as exc:
        _error(exc)
