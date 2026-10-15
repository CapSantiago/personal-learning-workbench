"""Semester and course operations, independent of the Streamlit interface.

The caller initializes an explicitly selected database first. This service never
creates a database or a learning-data directory on construction.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator
from uuid import UUID

from . import db, locking


class LearningError(Exception):
    """An application error that can be shown to the user."""


class ValidationError(LearningError):
    """Input does not satisfy the learning model."""


class NotFoundError(LearningError):
    """The selected record no longer exists."""


class ConflictError(LearningError):
    """A stale edit or reused request token must not overwrite current data."""


class ArchivedError(LearningError):
    """Archived content must be unarchived before an ordinary edit."""


class StorageError(LearningError):
    """The data layer could not complete the operation."""


_COURSE_STATES = frozenset({"planned", "active", "completed", "paused"})
_SEMESTER_FIELDS = frozenset({"name", "start_date", "end_date"})
_COURSE_FIELDS = frozenset(
    {
        "semester_id", "name", "teacher", "credits", "schedule_text",
        "assessment", "status", "remarks",
    }
)
_TABLES = {"semester": "semesters", "course": "courses"}
_LABELS = {"semester": "学期", "course": "课程"}


def _uuid(value: str | UUID, label: str) -> str:
    if not isinstance(value, (str, UUID)):
        raise ValidationError(f"{label}必须是有效的 UUID。")
    try:
        return str(UUID(str(value).strip()))
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"{label}必须是有效的 UUID。") from exc


def _text(
    value: Any, label: str, *, required: bool = False,
    limit: int = 10_000, single_line: bool = False,
) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ValidationError(f"{label}必须是文本。")
    result = value.strip()
    if required and not result:
        raise ValidationError(f"{label}不能为空。")
    if len(result) > limit:
        raise ValidationError(f"{label}不能超过 {limit} 个字符。")
    if "\x00" in result or (
        single_line and any(ord(character) < 32 for character in result)
    ):
        raise ValidationError(f"{label}包含不支持的控制字符。")
    return result


def _date(value: date | str | None, label: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValidationError(f"{label}只接受日期，不能包含时间。")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                pass
    raise ValidationError(f"{label}必须是有效日期，格式为 YYYY-MM-DD。")


def _credits(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError("学分必须是 0 到 100 之间的有限数值。")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValidationError("学分必须是 0 到 100 之间的有限数值。") from exc
    if not math.isfinite(result) or not 0 <= result <= 100:
        raise ValidationError("学分必须是 0 到 100 之间的有限数值。")
    return 0.0 if result == 0 else result


def _revision(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError("编辑版本必须是正整数，请重新加载记录。")
    return value


def _boolean(value: bool, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{label}必须为是或否。")
    return value


def _semester_payload(values: dict[str, Any]) -> dict[str, Any]:
    start = _date(values["start_date"], "学期开始日期")
    end = _date(values["end_date"], "学期结束日期")
    if start is not None and end is not None and end < start:
        raise ValidationError("学期结束日期不能早于开始日期。")
    return {
        "name": _text(
            values["name"], "学期名称", required=True, limit=200, single_line=True
        ),
        "start_date": start,
        "end_date": end,
    }


def _course_payload(values: dict[str, Any]) -> dict[str, Any]:
    status = _text(values["status"], "课程状态", required=True, limit=20)
    if status not in _COURSE_STATES:
        raise ValidationError("课程状态只能是 planned、active、completed 或 paused。")
    return {
        "semester_id": _uuid(values["semester_id"], "学期 ID"),
        "name": _text(
            values["name"], "课程名称", required=True, limit=200, single_line=True
        ),
        "teacher": _text(values["teacher"], "教师", limit=200, single_line=True),
        "credits": _credits(values["credits"]),
        "schedule_text": _text(values["schedule_text"], "上课时间", limit=2000),
        "assessment": _text(values["assessment"], "考核方式", limit=2000),
        "status": status,
        "remarks": _text(values["remarks"], "备注"),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _search_pattern(query: str) -> str:
    text = _text(query, "搜索内容", limit=500)
    # A fixed escape character keeps %, _ and ! literal; values stay parameters.
    return "%" + text.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


class LearningService:
    """Short, transactional semester and course use cases."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @contextmanager
    def _session(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        try:
            with db.transaction(self.db_path, write=write) as connection:
                yield connection
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                "操作不符合数据约束，请检查所选学期、必填字段和数据范围。"
            ) from exc
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise ConflictError("数据库正被其他操作使用，请稍后重试。") from exc
            raise StorageError("数据库操作未完成，请检查数据位置、权限和可用空间。") from exc
        except sqlite3.DatabaseError as exc:
            raise StorageError("数据库无法完成操作，请停止写入并检查数据库状态。") from exc
        except db.DatabaseError as exc:
            raise StorageError(str(exc)) from exc
        except locking.LockError as exc:
            raise ConflictError(str(exc)) from exc

    @staticmethod
    def _fetch(
        connection: sqlite3.Connection, kind: str, entity_id: str
    ) -> dict[str, Any]:
        if kind == "course":
            row = connection.execute(
                """SELECT c.*, s.name AS semester_name,
                          s.archived_at AS semester_archived_at
                   FROM courses c JOIN semesters s ON s.id = c.semester_id
                   WHERE c.id = ?""",
                (entity_id,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM semesters WHERE id = ?", (entity_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"{_LABELS[kind]}不存在，请重新选择。")
        return dict(row)

    @staticmethod
    def _check_revision(row: dict[str, Any], expected_revision: int) -> None:
        if row["revision"] != expected_revision:
            raise ConflictError("这条记录已被其他操作更新，请重新加载后再编辑。")

    @staticmethod
    def _check_editable(row: dict[str, Any], kind: str) -> None:
        if row["archived_at"] is not None:
            raise ArchivedError(f"该{_LABELS[kind]}已归档，请先取消归档。")
        if kind == "course" and row["semester_archived_at"] is not None:
            raise ArchivedError("所属学期已归档，请先取消学期归档。")

    def _active_semester(
        self, connection: sqlite3.Connection, semester_id: str
    ) -> dict[str, Any]:
        semester = self._fetch(connection, "semester", semester_id)
        self._check_editable(semester, "semester")
        return semester

    def list_semesters(
        self, query: str = "", include_archived: bool = False
    ) -> list[dict[str, Any]]:
        include_archived = _boolean(include_archived, "是否包含归档")
        pattern = _search_pattern(query)
        sql = "SELECT * FROM semesters WHERE name LIKE ? ESCAPE '!'"
        if not include_archived:
            sql += " AND archived_at IS NULL"
        sql += " ORDER BY start_date DESC, name COLLATE NOCASE, id"
        with self._session(write=False) as connection:
            return [dict(row) for row in connection.execute(sql, (pattern,))]

    def get_semester(self, semester_id: str | UUID) -> dict[str, Any]:
        entity_id = _uuid(semester_id, "学期 ID")
        with self._session(write=False) as connection:
            return self._fetch(connection, "semester", entity_id)

    def create_semester(
        self, name: str, start_date: date | str | None = None,
        end_date: date | str | None = None, *, request_id: str | UUID,
    ) -> dict[str, Any]:
        payload = _semester_payload(
            {"name": name, "start_date": start_date, "end_date": end_date}
        )
        return self._create("semester", payload, request_id)

    def update_semester(
        self, semester_id: str | UUID, expected_revision: int, **changes: Any
    ) -> dict[str, Any]:
        return self._update("semester", semester_id, expected_revision, changes)

    def set_semester_archived(
        self, semester_id: str | UUID, archived: bool, expected_revision: int
    ) -> dict[str, Any]:
        return self._set_archived("semester", semester_id, archived, expected_revision)

    def list_courses(
        self, semester_id: str | UUID | None = None, query: str = "",
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        include_archived = _boolean(include_archived, "是否包含归档")
        pattern = _search_pattern(query)
        sql = """SELECT c.*, s.name AS semester_name,
                        s.archived_at AS semester_archived_at
                 FROM courses c JOIN semesters s ON s.id = c.semester_id
                 WHERE (c.name LIKE ? ESCAPE '!' OR c.teacher LIKE ? ESCAPE '!'
                        OR c.remarks LIKE ? ESCAPE '!')"""
        parameters: list[Any] = [pattern, pattern, pattern]
        if semester_id is not None:
            sql += " AND c.semester_id = ?"
            parameters.append(_uuid(semester_id, "学期 ID"))
        if not include_archived:
            sql += " AND c.archived_at IS NULL AND s.archived_at IS NULL"
        sql += " ORDER BY c.position, c.updated_at DESC, c.name COLLATE NOCASE, c.id"
        with self._session(write=False) as connection:
            return [dict(row) for row in connection.execute(sql, parameters)]

    @staticmethod
    def _ordered_courses(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(
            "SELECT c.* FROM courses c JOIN semesters s ON s.id=c.semester_id "
            "WHERE c.archived_at IS NULL AND s.archived_at IS NULL "
            "ORDER BY c.position,c.updated_at DESC,c.name COLLATE NOCASE,c.id"
        )]

    @staticmethod
    def _write_course_positions(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
        # Sorting is separate from course content edits: it must not fabricate
        # creation/update times or invalidate an unrelated course edit revision.
        connection.executemany("UPDATE courses SET position=? WHERE id=?",
                               [(position, row['id']) for position, row in enumerate(rows)
                                if row['position'] != position])

    def move_course(self, course_id: str | UUID, destination: int, *,
                    expected_order: list[str]) -> list[dict[str, Any]]:
        """Move within all visible courses, rejecting a stale or filtered list."""
        identity = _uuid(course_id, "课程 ID")
        if type(destination) is not int or destination < 1:
            raise ValidationError("目标位置必须是从 1 开始的整数。")
        if not isinstance(expected_order, list):
            raise ValidationError("请提供当前书架的完整课程顺序。")
        expected = [_uuid(value, "课程 ID") for value in expected_order]
        if len(set(expected)) != len(expected):
            raise ValidationError("当前课程顺序中存在重复记录。")
        with self._session(write=True) as connection:
            selected = self._fetch(connection, "course", identity)
            self._check_editable(selected, "course")
            rows = self._ordered_courses(connection)
            if [row['id'] for row in rows] != expected:
                raise ConflictError("课程列表已在其他页面发生变化，请刷新后重新调整。")
            if destination > len(rows):
                raise ValidationError(f"目标位置不能超过 {len(rows)}。")
            moved = next(row for row in rows if row['id'] == identity)
            rows.remove(moved)
            rows.insert(destination-1, moved)
            self._write_course_positions(connection, rows)
            # Include semester labels just like list_courses, using this same
            # transaction rather than observing a concurrent list afterwards.
            return [self._fetch(connection, "course", row['id']) for row in rows]

    def get_course(self, course_id: str | UUID) -> dict[str, Any]:
        entity_id = _uuid(course_id, "课程 ID")
        with self._session(write=False) as connection:
            return self._fetch(connection, "course", entity_id)

    def create_course(
        self, semester_id: str | UUID, name: str, *, teacher: str = "",
        credits: float | None = 0, schedule_text: str = "", assessment: str = "",
        status: str = "planned", remarks: str = "", request_id: str | UUID,
    ) -> dict[str, Any]:
        payload = _course_payload(
            {
                "semester_id": semester_id, "name": name, "teacher": teacher,
                "credits": credits, "schedule_text": schedule_text,
                "assessment": assessment, "status": status, "remarks": remarks,
            }
        )
        return self._create("course", payload, request_id)

    def update_course(
        self, course_id: str | UUID, expected_revision: int, **changes: Any
    ) -> dict[str, Any]:
        return self._update("course", course_id, expected_revision, changes)

    def set_course_archived(
        self, course_id: str | UUID, archived: bool, expected_revision: int
    ) -> dict[str, Any]:
        return self._set_archived("course", course_id, archived, expected_revision)

    def _create(
        self, kind: str, payload: dict[str, Any], request_id: str | UUID
    ) -> dict[str, Any]:
        entity_id = _uuid(request_id, "提交请求 ID")
        serialized = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self._session(write=True) as connection:
            previous = connection.execute(
                "SELECT * FROM create_requests WHERE request_id = ?", (entity_id,)
            ).fetchone()
            if previous is not None:
                if (
                    previous["entity_kind"] != kind
                    or previous["payload_hash"] != fingerprint
                    or previous["payload_json"] != serialized
                ):
                    raise ConflictError("此提交请求已经用于不同内容，请重新发起创建。")
                # Return the current row even if it was edited or archived later.
                return self._fetch(connection, kind, previous["entity_id"])
            if kind == "course":
                self._active_semester(connection, payload["semester_id"])
            now = _now()
            values = {
                "id": entity_id, **payload, "created_at": now, "updated_at": now,
                "revision": 1,
            }
            if kind == "course":
                ordered = self._ordered_courses(connection)
                self._write_course_positions(connection, ordered)
                values["position"] = len(ordered)
            # Table names and columns come only from the fixed model above.
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            connection.execute(
                f"INSERT INTO {_TABLES[kind]} ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            connection.execute(
                """INSERT INTO create_requests
                   (request_id, entity_kind, payload_json, payload_hash, entity_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (entity_id, kind, serialized, fingerprint, entity_id, now),
            )
            return self._fetch(connection, kind, entity_id)

    def _update(
        self, kind: str, raw_id: str | UUID, expected_revision: int,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        entity_id = _uuid(raw_id, f"{_LABELS[kind]} ID")
        expected_revision = _revision(expected_revision)
        allowed = _SEMESTER_FIELDS if kind == "semester" else _COURSE_FIELDS
        if set(changes) - allowed:
            raise ValidationError("包含不可编辑的字段，请通过正确的表单操作。")
        with self._session(write=True) as connection:
            row = self._fetch(connection, kind, entity_id)
            self._check_revision(row, expected_revision)
            self._check_editable(row, kind)
            merged = {field: row[field] for field in allowed}
            merged.update(changes)
            payload = (
                _semester_payload(merged) if kind == "semester"
                else _course_payload(merged)
            )
            if kind == "course":
                self._active_semester(connection, payload["semester_id"])
            if all(row[field] == value for field, value in payload.items()):
                return row
            assignments = ", ".join(f"{field} = ?" for field in payload)
            cursor = connection.execute(
                f"UPDATE {_TABLES[kind]} SET {assignments}, updated_at = ?, "
                "revision = revision + 1 WHERE id = ? AND revision = ?",
                (*payload.values(), _now(), entity_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ConflictError("记录版本已变化，请重新加载后再编辑。")
            return self._fetch(connection, kind, entity_id)

    def _set_archived(
        self, kind: str, raw_id: str | UUID, archived: bool,
        expected_revision: int,
    ) -> dict[str, Any]:
        entity_id = _uuid(raw_id, f"{_LABELS[kind]} ID")
        expected_revision = _revision(expected_revision)
        archived = _boolean(archived, "归档状态")
        with self._session(write=True) as connection:
            row = self._fetch(connection, kind, entity_id)
            self._check_revision(row, expected_revision)
            if kind == "course" and row["semester_archived_at"] is not None:
                raise ArchivedError("所属学期已归档，请先取消学期归档。")
            if (row["archived_at"] is not None) == archived:
                return row
            before = self._ordered_courses(connection)
            now = _now()
            cursor = connection.execute(
                f"UPDATE {_TABLES[kind]} SET archived_at = ?, updated_at = ?, "
                "revision = revision + 1 WHERE id = ? AND revision = ?",
                (now if archived else None, now, entity_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ConflictError("记录版本已变化，请重新加载后再操作。")
            visible = self._ordered_courses(connection)
            if not archived:
                # Restoring a course appends it. Restoring a semester appends
                # its visible courses as a group, in their retained order.
                before_ids = {item['id'] for item in before}
                visible = before + [item for item in visible if item['id'] not in before_ids]
            self._write_course_positions(connection, visible)
            return self._fetch(connection, kind, entity_id)
